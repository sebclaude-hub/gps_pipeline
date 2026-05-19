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
    TRACK_Z_OFFSET, DEM_SMOOTH,
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
    load_dems, get_track_bounds, compare_track_dem, reduce_dem_to_fit,
)
from .visualization.three_d import visualize_3d
from .visualization.track_with_satellites import render_track_with_satellites
from .visualization.multi_track import visualize_multiple


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
    z_offset_mode=None,
) -> None:
    """Erzeugt die Standard-Visualisierungen für einen Schema-C-Track.

    Parameters
    ----------
    df_c : pd.DataFrame
        Schema-C-DataFrame.
    output_dir : Path
        Zielverzeichnis für die HTML-Dateien.
    name_prefix : str
        Wird Bestandteil der Output-Dateinamen.
    df_raw : pd.DataFrame, optional
        Schema-A-DataFrame (nur für NMEA, mit GSV-Daten).
    dem_paths : list of Path, optional
        Liste von DEM-GeoTIFF-Dateien.
    z_offset_mode : "auto" | "none" | None | float, optional
        Überschreibt config.TRACK_Z_OFFSET pro Aufruf.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    mode = z_offset_mode if z_offset_mode is not None else TRACK_Z_OFFSET

    dem_data = None
    track_z_offset = 0.0
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

            if mode == "none" or mode is None or mode == 0:
                print(f"Höhen-Offset: deaktiviert (Modus '{mode}'). "
                      f"Track wird ohne Korrektur dargestellt.")
                track_z_offset = 0.0
            elif mode == "auto":
                print("Höhen-Offset: automatische Diagnose...")
                stats = compare_track_dem(df_c, dem_paths)
                if stats:
                    # Heuristik: wenn der Mittelwert weit vom Median abweicht,
                    # ist es ein Flug-/Drohnen-Track. Median-Offset wäre dann
                    # irreführend — auf 0 zurückfallen.
                    mean_median_gap = abs(stats["mean_diff"] - stats["median_diff"])
                    if mean_median_gap > 50:
                        track_z_offset = 0.0
                        print(f"  → track_z_offset = 0 m (Flug erkannt — "
                              f"automatischer Median-Offset wäre irreführend)")
                    else:
                        track_z_offset = stats["suggested_offset"]
                        print(f"  → track_z_offset = {track_z_offset:+.1f} m")
            elif isinstance(mode, (int, float)):
                track_z_offset = float(mode)
                print(f"Höhen-Offset: fester Wert {track_z_offset:+.1f} m.")
            else:
                print(f"Warnung: unbekannter z_offset_mode '{mode}', verwende 'auto'.")
                stats = compare_track_dem(df_c, dem_paths)
                if stats:
                    track_z_offset = stats["suggested_offset"]

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
