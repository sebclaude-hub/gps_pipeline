"""High-Level-API der GPS-Pipeline.

Diese Funktionen führen die einzelnen Pipeline-Schritte (Parsing → Filter →
Konsolidierung → Enrichment → Visualisierung) zu nützlichen Workflows zusammen.

Wird sowohl von ``__main__.py`` (CLI) als auch von externen Skripten verwendet,
die das Paket per ``from gps_pipeline import process_nmea, ...`` einbinden.
"""

from pathlib import Path
from typing import Optional

import pandas as pd

from .config import (
    DEM_SMOOTH,
    DEM_TARGET_PIXEL_SIZE_M, DEM_MAX_PIXELS_PER_AXIS, DEM_MAX_HTML_MB,
)
from .dataframe_io.feather import save_df
from .parsing.nmea import parse_nmea_file
from .parsing.nmea_to_dataframe import build_dataframe
from .parsing.gpx import parse_gpx_file
from .parsing.kml import parse_kml_file
from .processing.filter import filter_invalid
from .processing.consolidate import consolidate
from .processing.enrich import enrich_speed
from .processing.enrich_terrain import enrich_terrain_elevation
from .terrain.dem import (
    load_dems, get_track_bounds, reduce_dem_to_fit,
)
from .visualization.three_d import visualize_3d
from .visualization.track_with_satellites import render_track_with_satellites
from .visualization.multi_track import visualize_multiple
from .export.json_export import export_track_json, export_satellite_json
from .export.dem_lod import export_dem_lods
from .export.chart_export import export_charts
from .parsing.chart import ChartOverlay
from .parsing.cut_config import find_cut_config, load_cut_config
from .processing.apply_cut_config import apply_cut_config


def apply_sidecar_cuts(
    source_path: Path,
    df_raw: Optional[pd.DataFrame],
    df_c: pd.DataFrame,
) -> tuple[Optional[pd.DataFrame], pd.DataFrame, Optional[dict], float]:
    """Schaut neben ``source_path`` nach ``<basename>.cuts.json`` und
    wendet die Schnittanweisung an, falls vorhanden.

    Liefert ``(df_raw, df_c, derivation, z_offset_m)`` zurueck:

    * ``derivation`` ist ein Banner-Dict (Trim / Gap / Synthetic), oder
      ``None`` wenn nichts angewendet wurde.
    * ``z_offset_m`` ist der aus der Datei gelesene Anzeige-Offset (Default
      0.0). Wird vom Backend NICHT auf die Track-Daten angewendet -- der
      Viewer initialisiert damit nur seinen Hoehen-Offset-Slider.

    Diese Funktion ist die High-Level-Bruecke zwischen Viewer-Export
    (Schnittanweisung) und Pipeline-Anwendung. Sowohl ``__main__`` als
    auch externe Library-Nutzer rufen sie typischerweise direkt nach
    ``process_nmea/gpx/kml`` auf.
    """
    cuts_path = find_cut_config(source_path)
    if cuts_path is None:
        return df_raw, df_c, None, 0.0
    print(f"Schnittanweisung gefunden: {cuts_path.name}")
    config = load_cut_config(cuts_path)
    df_raw_new, df_c_new, derivation = apply_cut_config(
        df_raw, df_c, config,
        source_name=Path(config.source).stem,
    )
    z_offset_m = float(config.z_offset_m) if config.z_offset_m is not None else 0.0
    if z_offset_m != 0.0:
        print(f"  z_offset_m aus Schnittanweisung: {z_offset_m:+.1f} m "
              f"(Default fuer Viewer-Slider, Daten unveraendert)")
        # Wenn nur z_offset gesetzt ist (keine Cuts), trotzdem ein
        # leichtes derivation erzeugen, damit der Viewer im Banner darauf
        # hinweisen kann.
        if derivation is None:
            derivation = {
                "type": "z_offset",
                "severity": "info",
                "source_name": Path(config.source).stem,
                "z_offset_m": round(z_offset_m, 2),
            }
        else:
            derivation = {**derivation, "z_offset_m": round(z_offset_m, 2)}
    return df_raw_new, df_c_new, derivation, z_offset_m


def process_nmea(file_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Volle NMEA-Pipeline: parsen → build → filter → consolidate → enrich.

    Returns
    -------
    (df_raw, df_enriched)
        df_raw    : Schema A (für Satellite-View) — eine Zeile pro NMEA-Satz
        df_enriched: Schema C — eine Zeile pro Timestamp, mit Speed/Distance
    """
    print(f"\n=== NMEA-Pipeline: {file_path} ===")
    messages = parse_nmea_file(str(file_path))
    df_raw = build_dataframe(messages)
    df_filt = filter_invalid(df_raw)
    df_b = consolidate(df_filt)
    df_c = enrich_speed(df_b)
    return df_raw, df_c


def process_gpx(file_path: Path) -> pd.DataFrame:
    """GPX-Pipeline: parsen (direkt Schema B) → enrich.

    Returns
    -------
    df_enriched: Schema C
    """
    print(f"\n=== GPX-Pipeline: {file_path} ===")
    df_b = parse_gpx_file(str(file_path))
    df_c = enrich_speed(df_b)
    return df_c


def process_kml(file_path: Path) -> pd.DataFrame:
    """KML-Pipeline: parsen (gx:Track → Schema B) → enrich.

    Returns
    -------
    df_enriched: Schema C
    """
    print(f"\n=== KML-Pipeline: {file_path} ===")
    df_b = parse_kml_file(str(file_path))
    df_c = enrich_speed(df_b)
    return df_c


def render_visualizations(
    df_c: pd.DataFrame,
    output_dir: Path,
    *,
    name_prefix: str,
    df_raw: Optional[pd.DataFrame] = None,
    dem_paths: Optional[list] = None,
) -> None:
    """Erzeugt die Standard-Visualisierungen für einen Schema-C-Track.

    **Legacy-Pfad** (Plotly-HTML). Fuer die interaktive React-Viewer-Anzeige
    stattdessen ``export_for_viewer`` benutzen -- die HTML-Outputs hier
    werden bei groessen Tracks/DEMs schwergewichtig und sind primaer noch
    als Fallback und fuer einfache Vergleichs-Snapshots gedacht.

    Hoehen-Offset wird NICHT mehr automatisch ermittelt -- der Track wird
    in den HTML-Plots immer mit seinen Original-Hoehen dargestellt. Wer
    eine korrigierte Anzeige braucht, nutzt den React-Viewer mit dem
    interaktiven Z-Offset-Slider.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    track_z_offset = 0.0

    dem_data = None
    if dem_paths:
        bounds = get_track_bounds(df_c)
        dem_data = load_dems(
            dem_paths, bounds=bounds,
            dem_smooth=DEM_SMOOTH,
            target_pixel_size_m=DEM_TARGET_PIXEL_SIZE_M,
            max_pixels_per_axis=DEM_MAX_PIXELS_PER_AXIS,
        )
        if dem_data is None:
            print(f"Hinweis: für Track {name_prefix} konnte kein passendes DEM "
                  f"aus den verfügbaren Tiles geladen werden.")
        else:
            # HTML-Größen-Bremse
            dem_data = reduce_dem_to_fit(dem_data, DEM_MAX_HTML_MB)
            df_c = enrich_terrain_elevation(df_c, dem_paths,
                                            track_z_offset=track_z_offset)

    fig = visualize_3d(df_c, color_by="speed_kmh", dem_data=dem_data,
                       track_z_offset=track_z_offset)
    out = output_dir / f"{name_prefix}_3d.html"
    fig.write_html(out, include_plotlyjs="cdn")
    print(f"3D-Track geschrieben: {out}")

    save_df(df_c, output_dir / f"{name_prefix}.feather")

    fig = visualize_3d(df_c, color_by="altitude_corrected", dem_data=dem_data,
                       track_z_offset=track_z_offset)
    out = output_dir / f"{name_prefix}_3d_altitude.html"
    fig.write_html(out, include_plotlyjs="cdn")
    print(f"3D-Track (Höhen-Farbe) geschrieben: {out}")

    if df_raw is not None and "gsv_satellites" in df_raw.columns:
        # Synchronisierter Plot: 3D-Track + Polar-Skyplot + Slider, JS-basiert
        # damit die HTML-Größe nicht mit der Tracklänge skaliert. Klick auf
        # einen Track-Punkt setzt den Slider.
        out = output_dir / f"{name_prefix}_track_satellites.html"
        render_track_with_satellites(
            df_c, df_raw, out,
            color_by="speed_kmh",
            dem_data=dem_data,
            track_z_offset=track_z_offset,
        )


def export_for_viewer(
    df_c: pd.DataFrame,
    output_dir: Path,
    *,
    name_prefix: str,
    df_raw: Optional[pd.DataFrame] = None,
    dem_paths: Optional[list] = None,
    source_type: str = "nmea",
    suggested_z_offset: float = 0.0,
    charts: Optional[list[ChartOverlay]] = None,
    derivation: Optional[dict] = None,
    source_file: Optional[str] = None,
) -> Path:
    """Exportiert Track + DEM als statische JSON-Dateien für den React-Viewer.

    Erzeugt in ``output_dir``:
      * ``track.json``          — Track-Punkte, Quantile, Metadaten
      * ``satellites.json``     — GSV-Daten (nur wenn df_raw mit GSV übergeben)
      * ``{prefix}_dem_lod0.json`` bis ``_lod2.json``  — DEM in 3 Auflösungen
      * ``manifest.json``       — Liste der vorhandenen Dateien (für React)

    Parameters
    ----------
    df_c : pd.DataFrame
        Schema-C-DataFrame.
    output_dir : Path
        Zielverzeichnis (wird angelegt wenn nicht vorhanden).
    name_prefix : str
        Wird Teil der Dateinamen und des Anzeigenamens im Viewer.
    df_raw : pd.DataFrame, optional
        Schema-A-DataFrame für GSV-Satellitendaten (nur NMEA).
    dem_paths : list of Path, optional
        GeoTIFF-Dateien für die Terrain-Visualisierung.
    source_type : str
        "nmea" | "gpx" | "kml" — wird in track.json gespeichert.
    suggested_z_offset : float, optional
        Default-Wert des interaktiven Hoehen-Offset-Sliders im Viewer.
        REINE ANZEIGE -- die Track-Daten werden nicht modifiziert. Wenn
        != 0, kommt der Wert typischerweise aus einer ``.cuts.json`` und
        der Banner kennzeichnet das. Default 0.
    charts : list of ChartOverlay, optional
        Karten-Overlays (PNG + georeferenzierte Eckkoordinaten), die ueber
        das Terrain gedrapt im Viewer angezeigt werden. Werden ueber
        ``find_charts(data_dir)`` aus dem Daten-Ordner gesammelt.
    derivation : dict, optional
        Markiert diesen Track als bearbeitete Version eines anderen.
        Wird im Viewer als Warnhinweis-Banner angezeigt. Erwartete
        Struktur z.B. ``{"type": "trimmed", "source_name": "...", "n_cuts": ...}``
        oder ``{"type": "synthetic", "source_name": "...", "warning": "..."}``.

    Returns
    -------
    Path
        output_dir (für Chaining und Logging).
    """
    import json as _json

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Track-Enrichment: NUR fuer terrain_elevation-Spalte, OHNE Offset
    # auf die Datenpunkte anzuwenden. Der Offset ist reine Anzeige-Sache
    # im Viewer-Slider.
    dem_data_lod = None
    if dem_paths:
        bounds = get_track_bounds(df_c)
        df_c = enrich_terrain_elevation(df_c, dem_paths, track_z_offset=0.0)
        dem_data_lod = bounds   # nur Bounds weitergeben, LOD-Export macht eigene Loads

    # 1. track.json -- suggested_z_offset wird vom Viewer als Slider-Default
    #    uebernommen (kommt typischerweise aus einer .cuts.json).
    track_path = output_dir / "track.json"
    export_track_json(df_c, track_path, name_prefix=name_prefix,
                      suggested_z_offset=float(suggested_z_offset),
                      derivation=derivation,
                      source_file=source_file)

    # Patch: source_type in Metadaten korrigieren
    import json as _json2
    with open(track_path, "r", encoding="utf-8") as f:
        track_payload = _json2.load(f)
    track_payload["meta"]["source_type"] = source_type
    with open(track_path, "w", encoding="utf-8") as f:
        _json2.dump(track_payload, f, allow_nan=False, separators=(",", ":"))

    # 2. satellites.json (optional)
    has_satellites = False
    if df_raw is not None and "gsv_satellites" in df_raw.columns:
        sat_path = output_dir / "satellites.json"
        has_satellites = export_satellite_json(df_c, df_raw, sat_path)
        if has_satellites:
            # has_satellites-Flag in track.json nachpflegen
            track_payload["meta"]["has_satellites"] = True
            with open(track_path, "w", encoding="utf-8") as f:
                _json2.dump(track_payload, f, allow_nan=False, separators=(",", ":"))

    # 3. DEM-LODs (optional)
    written_lods: list[int] = []
    if dem_paths and dem_data_lod is not None:
        written_lods = export_dem_lods(
            dem_paths,
            bounds=dem_data_lod,
            output_dir=output_dir,
            name_prefix=name_prefix,
        )

    # 4. Karten-Overlays (optional) -- PNGs nach output/charts/ kopieren,
    # charts.json schreiben. Komplett unabhaengig vom Track-Pfad, daher
    # einfach hier am Ende eingefuegt.
    chart_entries: list[dict] = []
    if charts:
        chart_entries = export_charts(charts, output_dir)

    # 5. manifest.json — React liest das als erstes
    manifest = {
        "track": "track.json",
        "satellites": "satellites.json" if has_satellites else None,
        "dem_lods": written_lods,
        "dem_prefix": name_prefix,
        "charts": "charts.json" if chart_entries else None,
        "viewer_version": "1.1",
    }
    with open(output_dir / "manifest.json", "w", encoding="utf-8") as f:
        _json.dump(manifest, f, indent=2)

    print(f"\nViewer-Export abgeschlossen: {output_dir}")
    print(f"  Starten mit: python view.py {output_dir}")
    return output_dir


def render_comparison(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    output_dir: Path,
    *,
    name_a: str = "Track A",
    name_b: str = "Track B",
    output_name: str = "comparison",
    dem_paths: Optional[list] = None,
) -> None:
    """Erzeugt eine Vergleichs-Visualisierung zweier Schema-C-Tracks."""
    output_dir.mkdir(parents=True, exist_ok=True)

    dem_data = None
    if dem_paths:
        combined = pd.concat([
            df_a[["directional_longitude", "directional_latitude"]],
            df_b[["directional_longitude", "directional_latitude"]],
        ])
        bounds = (
            float(combined["directional_longitude"].min()),
            float(combined["directional_latitude"].min()),
            float(combined["directional_longitude"].max()),
            float(combined["directional_latitude"].max()),
        )
        dem_data = load_dems(
            dem_paths, bounds=bounds,
            dem_smooth=DEM_SMOOTH,
            target_pixel_size_m=DEM_TARGET_PIXEL_SIZE_M,
            max_pixels_per_axis=DEM_MAX_PIXELS_PER_AXIS,
        )
        if dem_data is not None:
            dem_data = reduce_dem_to_fit(dem_data, DEM_MAX_HTML_MB)

    fig = visualize_multiple(
        [df_a, df_b],
        dataset_names=[name_a, name_b],
        color_by="speed_kmh",
        dem_data=dem_data,
    )
    out = output_dir / f"{output_name}.html"
    fig.write_html(out, include_plotlyjs="cdn")
    print(f"Vergleichs-Visualisierung geschrieben: {out}")
