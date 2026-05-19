"""Vergleichsvisualisierung mehrerer GPS-Tracks (z.B. NMEA vs. GPX).

Eingabe: Liste von Schema-C-DataFrames mit identischer Spaltenstruktur.
Ausgabe: eine Plotly-Figure mit allen Tracks in derselben 3D-Szene.

Anders als der alte ``visualize_nmea_multi.py`` brauchen wir keine eigene
Skalierungslogik mehr — durch ``aspectmode='manual'`` und einheitliches Lat/Lon
in Grad teilen sich alle Tracks automatisch denselben Koordinatenraum.

Anwendungsfall
--------------
NMEA-Logger vom Empfänger ↔ GPX-Aufzeichnung vom Smartphone derselben Tour
übereinanderlegen, um Empfänger-Qualitäten zu vergleichen. Funktioniert
natürlich nur, wenn beide Tracks räumlich dieselbe Tour abdecken.
"""

from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ..config import AVAILABLE_COLORSCALES, DEFAULT_QUANTILES, DEFAULT_Z_EXAGGERATION
from .three_d import _make_hover_text, _quantile_color_indices


# Standard-Colorscales für die Datasets, in Reihenfolge der Einträge
_DATASET_COLORS = ["Plasma", "Viridis", "Cividis", "Turbo", "Inferno"]


def visualize_multiple(
    datasets: Sequence[pd.DataFrame],
    dataset_names: Optional[Sequence[str]] = None,
    *,
    color_by: str = "speed_kmh",
    n_quantiles: int = DEFAULT_QUANTILES,
    z_exaggeration: float = DEFAULT_Z_EXAGGERATION,
    colorscales: Optional[Sequence[str]] = None,
    title: Optional[str] = None,
    dem_data: Optional[Dict[str, np.ndarray]] = None,
) -> go.Figure:
    """Mehrere GPS-Tracks in einer 3D-Plotly-Figure überlagern.

    Parameters
    ----------
    datasets : sequence of pd.DataFrame
        Liste von Schema-C-DataFrames (mit denselben Spalten).
    dataset_names : sequence of str, optional
        Anzeigenamen für die Legende. Default: "Dataset 1", "Dataset 2", ...
    color_by : str
        Spalte für die Farbcodierung. Default: 'speed_kmh'.
    n_quantiles : int
        Anzahl Farbklassen. Default: config.DEFAULT_QUANTILES.
    z_exaggeration : float
        Z-Achsen-Überhöhung. Default: config.DEFAULT_Z_EXAGGERATION.
    colorscales : sequence of str, optional
        Eine Colorscale pro Dataset. Default: 'Plasma', 'Viridis', ...
    title : str, optional
        Plot-Titel.
    dem_data : dict, optional
        Optionales Terrain-Mesh wie in visualize_3d.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    if not datasets:
        raise ValueError("Mindestens ein DataFrame muss übergeben werden.")

    if dataset_names is None:
        dataset_names = [f"Dataset {i+1}" for i in range(len(datasets))]
    if colorscales is None:
        colorscales = _DATASET_COLORS

    # Globale Quantil-Grenzen aus allen Datasets gemeinsam — sonst sind die
    # Farbskalen pro Dataset unterschiedlich kalibriert und ein Vergleich
    # wird irreführend.
    all_values = pd.concat([d[color_by].dropna() for d in datasets if color_by in d.columns])
    if all_values.empty:
        raise ValueError(f"Spalte '{color_by}' nicht oder leer in allen Datasets.")
    boundaries = np.quantile(all_values, np.linspace(0, 1, n_quantiles + 1))

    fig = go.Figure()

    # Globaler Geo-Referenzpunkt: Mittelpunkt aller Tracks zusammen.
    all_lats = pd.concat([d["directional_latitude"] for d in datasets])
    all_lons = pd.concat([d["directional_longitude"] for d in datasets])
    ref_lat = float(all_lats.mean())
    ref_lon = float(all_lons.mean())

    # Terrain als Erstes (damit der Track-Layer darüber sichtbar bleibt)
    if dem_data is not None:
        from .three_d import _add_terrain_surface
        _add_terrain_surface(fig, dem_data, colorscale="Viridis", opacity=0.5,
                             ref_lat=ref_lat, ref_lon=ref_lon)

    # Pro Track die globalen Projektions-Ranges sammeln für aspectratio
    all_x: list = []
    all_y: list = []
    all_z: list = []

    # Jeden Track als eigenen Trace hinzufügen
    for idx, (df, name) in enumerate(zip(datasets, dataset_names)):
        if color_by not in df.columns:
            print(f"Warnung: Dataset '{name}' hat keine '{color_by}'-Spalte, übersprungen.")
            continue

        from .three_d import _equirectangular_meters
        track_x, track_y = _equirectangular_meters(
            df["directional_latitude"].to_numpy(),
            df["directional_longitude"].to_numpy(),
            ref_lat, ref_lon,
        )
        track_z = df["altitude_corrected"].to_numpy()
        all_x.append(track_x); all_y.append(track_y); all_z.append(track_z)

        # Farbnormalisierung relativ zu den globalen Quantilen
        color_norm = _quantile_color_indices(df[color_by], n_quantiles)
        hover = _make_hover_text(df)
        cs = colorscales[idx % len(colorscales)]

        # Nur der erste Dataset bekommt eine Colorbar — sonst überlappen sie sich.
        marker_kwargs = dict(
            size=3,
            color=color_norm,
            colorscale=cs,
            opacity=0.85,
        )
        if idx == 0:
            marker_kwargs["colorbar"] = dict(
                title=color_by.replace("_", " ").capitalize(),
                tickvals=np.linspace(0, 1, len(boundaries)),
                ticktext=[f"{v:.1f}" for v in boundaries],
            )

        fig.add_trace(go.Scatter3d(
            x=track_x,
            y=track_y,
            z=track_z,
            mode="markers+lines",
            marker=marker_kwargs,
            line=dict(color=color_norm, colorscale=cs, width=3),
            text=hover,
            hoverinfo="text",
            name=name,
        ))

    # Aspect ratio über alle Tracks gemeinsam
    if all_x:
        x_all = np.concatenate(all_x); y_all = np.concatenate(all_y); z_all = np.concatenate(all_z)
        x_range = float(np.ptp(x_all))
        y_range = float(np.ptp(y_all))
        z_range = float(np.nanmax(z_all) - np.nanmin(z_all))
    else:
        x_range = y_range = z_range = 1.0
    horizontal = max(x_range, y_range, 1.0)
    z_visible = max(z_range, 1.0)

    auto_title = title or f"Track-Vergleich ({len(datasets)} Datensätze, Farbe: {color_by})"
    fig.update_layout(
        title=auto_title,
        width=1200,
        height=800,
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
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )
    return fig
