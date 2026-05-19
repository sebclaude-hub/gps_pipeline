"""3D-Visualisierung eines GPS-Tracks mit Plotly.

Eingabe: Schema-C-DataFrame (siehe processing/enrich.py). Das heißt: eine
Zeile pro Timestamp, mit Position, Höhe, Geschwindigkeit und geodätischer
Geschwindigkeit.

Visuelle Darstellung
--------------------
* Linie+Punkte in 3D, Position in Grad (Lat/Lon), Höhe in Metern.
* Farbcodierung nach einer wählbaren Spalte, mit Quantil-Binning
  (gleich viele Datenpunkte pro Farbklasse — gut sichtbar bei schiefer
  Verteilung wie "viel langsam, kurz schnell").
* Mesh als "Wand" zur Grundebene (MSL) für Höheneindruck — wirkt wie ein
  3D-Balkendiagramm entlang des Tracks.
* Z-Achse via ``aspectratio`` überhöht (siehe config.DEFAULT_Z_EXAGGERATION),
  damit Höhenunterschiede sichtbar werden ohne die Koordinaten zu verfälschen.

Hover-Text wird vektorisiert erzeugt (kein .iterrows()), das ist um Größenordnungen
schneller bei großen Tracks.
"""

from typing import Dict, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from ..config import (
    AVAILABLE_COLORSCALES,
    DEFAULT_COLORSCALE,
    DEFAULT_QUANTILES,
    DEFAULT_Z_EXAGGERATION,
)


def _make_hover_text(df: pd.DataFrame) -> pd.Series:
    """Erzeugt Hover-Text pro Zeile, vollständig vektorisiert.

    Kein .iterrows() — auf 10000 Punkten ist das etwa 100× schneller.
    Beinhaltet den DataFrame-Index als erste Zeile, damit man Track-
    Punkte für Trimming/Edit-Operationen direkt identifizieren kann.
    """
    def fmt(series: pd.Series, fmt_str: str = "{:.1f}", suffix: str = "") -> pd.Series:
        """Spalte zu Strings, NaN wird 'N/A'."""
        return series.apply(
            lambda x: f"{fmt_str.format(x)}{suffix}" if pd.notna(x) else "N/A"
        )

    idx = pd.Series(df.index, index=df.index).astype(str)
    ts = df["timestamp_utc"].dt.strftime("%Y-%m-%d %H:%M:%S")
    lat = fmt(df["directional_latitude"], "{:.6f}", "°")
    lon = fmt(df["directional_longitude"], "{:.6f}", "°")
    alt = fmt(df["altitude_corrected"], "{:.1f}", " m")
    spd_gps = fmt(df["speed_kmh"], "{:.1f}", " km/h")
    spd_geo = fmt(df.get("speed_geodesic_kmh", pd.Series([np.nan]*len(df))), "{:.1f}", " km/h")
    diff = fmt(df.get("speed_diff_kmh", pd.Series([np.nan]*len(df))), "{:.1f}", " km/h")
    dist = fmt(df.get("distance_m", pd.Series([np.nan]*len(df))), "{:.1f}", " m")

    base = (
        "<b>Index:</b> " + idx + "<br>"
        + "<b>Zeit:</b> " + ts + " UTC<br>"
        + "<b>Position:</b> " + lat + " N, " + lon + " E<br>"
        + "<b>Höhe:</b> " + alt + "<br>"
        + "<br>"
        + "<b>GPS-Geschwindigkeit:</b> " + spd_gps + "<br>"
        + "<b>Berechnet (geodesic):</b> " + spd_geo + "<br>"
        + "<b>Differenz:</b> " + diff + "<br>"
        + "<b>Distanz zu Vorgänger:</b> " + dist
    )

    # Wenn Terrain-Anreicherung vorhanden: zwei weitere Zeilen
    if "terrain_elevation" in df.columns:
        terrain = fmt(df["terrain_elevation"].astype("Float64"), "{:.1f}", " m")
        agl = fmt(df["track_above_terrain"].astype("Float64"), "{:.1f}", " m")
        base = base + (
            "<br>"
            + "<b>Geländehöhe:</b> " + terrain + "<br>"
            + "<b>Höhe über Grund:</b> " + agl
        )

    return base


def _quantile_color_indices(values: pd.Series, n_quantiles: int) -> np.ndarray:
    """Bin-Indizes 0..n-1 via Quantilen. NaN bleibt NaN (Plotly stellt es als Lücke dar).

    ``duplicates='drop'`` macht das Ganze robust, wenn zu viele identische Werte
    vorkommen (z.B. lange Stehphasen mit speed=0).
    """
    try:
        idx = pd.qcut(values, q=n_quantiles, labels=False, duplicates="drop")
        # Normalisieren auf [0, 1] für Plotly-Farbskala
        max_idx = idx.max()
        if max_idx is np.nan or max_idx == 0:
            return np.zeros(len(values))
        return (idx.astype("Float64") / max_idx).to_numpy()
    except ValueError:
        # qcut wirft bei zu wenigen distinkten Werten manchmal ValueError
        return np.zeros(len(values))


def _quantile_boundaries(values: pd.Series, n_quantiles: int) -> np.ndarray:
    """Tatsächliche Quantil-Grenzen für die Colorbar-Beschriftung."""
    probs = np.linspace(0, 1, n_quantiles + 1)
    valid = values.dropna()
    if len(valid) == 0:
        return np.array([0.0, 1.0])
    return np.quantile(valid, probs)


def _equirectangular_meters(
    lats: np.ndarray,
    lons: np.ndarray,
    ref_lat: float,
    ref_lon: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Konvertiert Lat/Lon in lokale Meter-Koordinaten (Equirectangular).

    Einfache, für kleine bis mittlere Bereiche (bis ~100 km) ausreichend
    genaue Approximation. Verzerrt nicht stärker als 0.5 %.

    Parameters
    ----------
    lats, lons : ndarray
        Geographische Koordinaten in Grad.
    ref_lat, ref_lon : float
        Referenzpunkt für das lokale System (typisch: Track-Mittelpunkt).

    Returns
    -------
    x, y : ndarray
        Lokale Koordinaten in Metern. x = Ost-West, y = Nord-Süd.
        Am Referenzpunkt sind beide 0.
    """
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = 111_320.0 * np.cos(np.deg2rad(ref_lat))
    x = (lons - ref_lon) * meters_per_deg_lon
    y = (lats - ref_lat) * meters_per_deg_lat
    return x, y


def visualize_3d(
    df: pd.DataFrame,
    color_by: str = "speed_kmh",
    *,
    n_quantiles: int = DEFAULT_QUANTILES,
    colorscale: str = DEFAULT_COLORSCALE,
    z_exaggeration: float = DEFAULT_Z_EXAGGERATION,
    title: Optional[str] = None,
    show_mesh: bool = True,
    dem_data: Optional[Dict[str, np.ndarray]] = None,
    terrain_colorscale: str = "Viridis",
    terrain_opacity: float = 0.7,
    track_z_offset: float = 0.0,
    width: int = 1200,
    height: int = 800,
) -> go.Figure:
    """Erzeugt eine 3D-Plotly-Figure für einen GPS-Track.

    Die Achsen werden in **echten Metern** dargestellt: Lat/Lon wird via
    Equirectangular-Projektion in ein lokales kartesisches Koordinatensystem
    umgerechnet. Damit ist ``z_exaggeration`` ein ehrlicher Multiplikator
    der Höhe gegenüber der horizontalen Distanz.

    Parameters
    ----------
    df : pd.DataFrame
        Schema-C-DataFrame.
    color_by : str
        Spalte, nach der eingefärbt wird.
    n_quantiles : int
        Anzahl Farbklassen für Quantil-Binning.
    colorscale : str
        Plotly-Colorscale-Name.
    z_exaggeration : float
        Echter Multiplikator der Höhenachse. 1.0 = maßstabstreu (Höhe und
        horizontale Distanz haben gleiche Pixel-Skala). Default: aus config.
        Sinnvolle Werte:
          * 1–3 für Flüge (echte Höhe schon dominant)
          * 5–10 für Bergtouren
          * 20–50 für Auto-/Radtouren (Höhenvariation gering)
    title : str, optional
        Titel der Figure.
    show_mesh : bool
        Wenn True: "Wand" zur Grundebene zeichnen (3D-Balkendiagramm-Effekt).
    dem_data : dict, optional
        Höhenmodell-Daten von ``terrain.dem.load_dem()``.
    terrain_colorscale : str
        Plotly-Colorscale für das Terrain.
    terrain_opacity : float
        Deckkraft des Terrain-Surface.
    track_z_offset : float
        Vertikaler Offset (in Metern), der vor dem Plotten auf die Track-Höhe
        addiert wird. Default 0. Nützlich, wenn Track und DEM unterschiedliche
        Höhen-Bezüge haben (z.B. ellipsoidische GPS-Höhe vs. NN-bezogenes DEM).
        Den passenden Wert liefert ``terrain.dem.compare_track_dem``.
    width, height : int
        Figure-Größe in Pixeln. Default 1200×800.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    if colorscale not in AVAILABLE_COLORSCALES:
        print(f"Warnung: Colorscale '{colorscale}' nicht in AVAILABLE_COLORSCALES. "
              f"Fallback auf {DEFAULT_COLORSCALE}.")
        colorscale = DEFAULT_COLORSCALE

    if color_by not in df.columns:
        raise ValueError(f"color_by-Spalte '{color_by}' nicht im DataFrame. "
                         f"Verfügbar: {list(df.columns)}")

    # Farbcodierung berechnen
    color_norm = _quantile_color_indices(df[color_by], n_quantiles)
    boundaries = _quantile_boundaries(df[color_by], n_quantiles)

    # Hover-Text (vektorisiert)
    hover = _make_hover_text(df)

    # Geo-Referenzpunkt für die Equirectangular-Projektion: Mittelpunkt
    # des Tracks. So liegt der Track-Schwerpunkt bei x=y=0.
    ref_lat = float(df["directional_latitude"].mean())
    ref_lon = float(df["directional_longitude"].mean())

    # Track in lokale Meter umrechnen
    track_x, track_y = _equirectangular_meters(
        df["directional_latitude"].to_numpy(),
        df["directional_longitude"].to_numpy(),
        ref_lat, ref_lon,
    )
    track_z = df["altitude_corrected"].to_numpy().astype(float) + track_z_offset

    fig = go.Figure()

    # 0. Terrain-Surface als Erstes, damit Track und Mesh darüber liegen
    if dem_data is not None:
        _add_terrain_surface(fig, dem_data, terrain_colorscale, terrain_opacity,
                             ref_lat=ref_lat, ref_lon=ref_lon)

    # 1. Hauptspur: 3D-Scatter mit Linie
    fig.add_trace(go.Scatter3d(
        x=track_x,
        y=track_y,
        z=track_z,
        mode="markers+lines",
        marker=dict(
            size=3,
            color=color_norm,
            colorscale=colorscale,
            colorbar=dict(
                title=color_by.replace("_", " ").capitalize(),
                tickvals=np.linspace(0, 1, len(boundaries)),
                ticktext=[f"{v:.1f}" for v in boundaries],
            ),
        ),
        line=dict(color=color_norm, colorscale=colorscale, width=3),
        text=hover,
        hoverinfo="text",
        name="GPS-Track",
    ))

    # 2. Optionaler Mesh zur Grundebene für 3D-Balkendiagramm-Effekt
    if show_mesh:
        # Untere Kante: wenn terrain_elevation im DataFrame ist, nutzen wir
        # die als Boden. Sonst 0 (MSL-Grundebene wie bisher).
        if "terrain_elevation" in df.columns:
            z_base = df["terrain_elevation"].to_numpy(dtype=float)
        else:
            z_base = np.zeros(len(df), dtype=float)
        _add_base_mesh(fig, track_x, track_y, track_z, z_base, color_norm, colorscale)

    # 3. Layout: ehrliche Meter-Skalierung mit Z-Multiplikator
    auto_title = title or f"GPS-Track 3D (Farbe: {color_by.replace('_', ' ')})"

    # Aspect ratio: x und y im Verhältnis ihrer echten Bereiche (in Metern),
    # z entsprechend der Höhenvariation mal z_exaggeration.
    # Wir normieren auf die größte horizontale Ausdehnung, damit
    # aspectratio-Werte vernünftig groß bleiben.
    x_range = float(np.ptp(track_x)) if len(track_x) > 1 else 1.0
    y_range = float(np.ptp(track_y)) if len(track_y) > 1 else 1.0
    z_range = float(np.nanmax(track_z) - np.nanmin(track_z)) if len(track_z) > 1 else 1.0
    horizontal = max(x_range, y_range, 1.0)
    # Mindesthöhen-Range, damit z_range=0 (alles auf einer Höhe) nicht crasht
    z_visible = max(z_range, 1.0)

    fig.update_layout(
        title=auto_title,
        width=width,
        height=height,
        scene=dict(
            xaxis_title=f"Ost-West (m, Ref {ref_lon:.4f}°E)",
            yaxis_title=f"Nord-Süd (m, Ref {ref_lat:.4f}°N)",
            zaxis_title="Höhe (m)",
            aspectmode="manual",
            aspectratio=dict(
                x=x_range / horizontal,
                y=y_range / horizontal,
                z=(z_visible / horizontal) * z_exaggeration,
            ),
        ),
        margin=dict(l=0, r=0, b=0, t=40),
        hoverlabel=dict(bgcolor="white", font_size=11, font_family="Arial"),
    )

    return fig


def _add_base_mesh(fig: go.Figure,
                   x: np.ndarray,
                   y: np.ndarray,
                   z: np.ndarray,
                   z_base: np.ndarray,
                   color_norm: np.ndarray,
                   colorscale: str) -> None:
    """Fügt einen Mesh3d mit Dreiecken zwischen Track und Grundebene hinzu.

    Pro Punktepaar (i, i+1) zwei Dreiecke, die einen "Streifen" zwischen
    Track-Höhe und der Grundebene bilden. Die Grundebene ist als
    Array ``z_base`` gleicher Länge wie der Track gegeben — typischerweise
    entweder konstant 0 (Grundebene = MSL) oder die DEM-Höhe an jedem
    Track-Punkt (Balken stehen auf dem Gelände).

    x, y, z sind bereits in das lokale kartesische System projiziert.
    """
    n = len(x)
    if n < 2:
        return

    # Vertices: für jeden Punkt einen oberen (z) und einen unteren (z_base).
    # Reihenfolge: alle oberen, dann alle unteren.
    # Falls z_base NaN enthält (Punkt außerhalb DEM), fällt der dort auf 0
    # zurück — sonst würde der ganze Mesh-Streifen unsichtbar.
    z_base_clean = np.where(np.isnan(z_base), 0.0, z_base)
    vx = np.concatenate([x, x])
    vy = np.concatenate([y, y])
    vz = np.concatenate([z, z_base_clean])
    intensity = np.concatenate([color_norm, color_norm])

    # Dreiecke: für jeden Streifen i → i+1 zwei Dreiecke
    # Oberer Streifen: top_i, top_{i+1}, bot_i  und  top_{i+1}, bot_{i+1}, bot_i
    top_indices = np.arange(n - 1)
    i1 = top_indices                  # top_i
    i2 = top_indices + 1              # top_{i+1}
    i3 = top_indices + n              # bot_i
    i4 = top_indices + n + 1          # bot_{i+1}

    # Erstes Dreieck: top_i, top_{i+1}, bot_i
    # Zweites Dreieck: top_{i+1}, bot_{i+1}, bot_i
    tri_i = np.concatenate([i1, i2])
    tri_j = np.concatenate([i2, i4])
    tri_k = np.concatenate([i3, i3])

    fig.add_trace(go.Mesh3d(
        x=vx, y=vy, z=vz,
        i=tri_i, j=tri_j, k=tri_k,
        intensity=intensity,
        colorscale=colorscale,
        opacity=0.5,
        showscale=False,
        name="Höhen-Wand",
    ))


def _add_terrain_surface(fig: go.Figure,
                         dem_data: Dict[str, np.ndarray],
                         colorscale: str,
                         opacity: float,
                         *,
                         ref_lat: float,
                         ref_lon: float) -> None:
    """Fügt eine ``go.Surface`` als Geländemodell hinzu.

    Das DEM kommt als Dict mit 1D-Arrays für Lat und Lon und einem 2D-Array
    für die Höhen. Das gesamte Gitter wird mit derselben Equirectangular-
    Projektion in Meter umgerechnet wie der Track, damit Terrain und Track
    im selben Koordinatensystem liegen.
    """
    lats = dem_data["lats"]
    lons = dem_data["lons"]
    elevations = dem_data["elevations"]

    # 1D-Achsen-Projektion: für die x-Achse nehmen wir die ref_lat als
    # konstante Breite (cos-Faktor) — das ist die Equirectangular-Konvention.
    dem_x = (lons - ref_lon) * 111_320.0 * np.cos(np.deg2rad(ref_lat))
    dem_y = (lats - ref_lat) * 111_320.0

    fig.add_trace(go.Surface(
        x=dem_x,
        y=dem_y,
        z=elevations,
        colorscale=colorscale,
        opacity=opacity,
        showscale=False,
        name="Gelände",
        hoverinfo="skip",
        contours={"z": {"show": True, "usecolormap": True, "highlightcolor": "limegreen",
                        "project_z": False, "size": 10}},
    ))
