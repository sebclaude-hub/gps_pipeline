"""GPS-Pipeline CLI — Einstiegspunkt für ``python -m gps_pipeline``.

Liest NMEA-/GPX-/KML-Dateien aus ``data/``, verarbeitet sie zu Schema-C-
DataFrames und schreibt Visualisierungen plus Feather-Export nach ``output/``.

Die eigentlichen API-Funktionen liegen in ``api.py``. Direkt importieren via::

    from gps_pipeline import process_nmea, process_gpx, process_kml, render_visualizations
"""

from pathlib import Path

from .api import (
    process_nmea, process_gpx, process_kml,
    render_visualizations, export_for_viewer, apply_sidecar_cuts,
)
from .parsing.chart import find_charts, is_chart_config


# Verzeichnisse — relativ zum aktuellen Arbeitsverzeichnis.
DEFAULTS = {
    "input_dir": Path("data"),
    "output_dir": Path("output"),
}


def main() -> None:
    input_dir = DEFAULTS["input_dir"]
    output_dir = DEFAULTS["output_dir"]

    if not input_dir.exists():
        print(f"Input-Verzeichnis {input_dir} existiert nicht.")
        print(f"Lege dort NMEA-Logs (.txt), GPX-Dateien (.gpx) und/oder KML-Dateien "
              f"(.kml) ab und starte erneut.")
        return

    # Alle DEM-Tiles in data/ sammeln
    dem_paths = list(input_dir.glob("*.tif")) + list(input_dir.glob("*.tiff"))
    if dem_paths:
        print(f"DEM-Tiles gefunden: {[p.name for p in dem_paths]}")
    else:
        print("Keine DEM-Tiles (*.tif) in data/ gefunden. Visualisierungen ohne Terrain.")

    # Karten-Overlays (PNG + gleichnamige TXT mit 4 Eckkoordinaten) sammeln.
    # Die zugehoerigen TXT-Dateien duerfen nicht als NMEA-Logs verarbeitet
    # werden, daher filtern wir sie heraus.
    charts = find_charts(input_dir)
    if charts:
        print(f"Karten-Overlays gefunden: {[c.name for c in charts]}")

    nmea_files = [
        p for p in sorted(input_dir.glob("*.txt"))
        if not is_chart_config(p)
    ]
    gpx_files = sorted(input_dir.glob("*.gpx"))
    kml_files = sorted(input_dir.glob("*.kml"))

    if not nmea_files and not gpx_files and not kml_files:
        print(f"Keine NMEA-, GPX- oder KML-Dateien in {input_dir} gefunden.")
        return

    def _viewer_dir(prefix: str) -> Path:
        # Pro Track ein Unterordner unter output/, damit mehrere Tracks
        # nicht ihre track.json gegenseitig ueberschreiben.
        d = output_dir / prefix
        d.mkdir(parents=True, exist_ok=True)
        return d

    for path in nmea_files:
        prefix = f"nmea_{path.stem}"
        df_raw, df_c = process_nmea(path)
        df_raw, df_c, derivation, z_offset = apply_sidecar_cuts(
            path, df_raw, df_c)
        render_visualizations(df_c, output_dir,
                              name_prefix=prefix, df_raw=df_raw,
                              dem_paths=dem_paths)
        export_for_viewer(
            df_c, _viewer_dir(prefix),
            name_prefix=prefix, df_raw=df_raw,
            dem_paths=dem_paths, charts=charts,
            derivation=derivation, source_file=path.name,
            suggested_z_offset=z_offset, source_type="nmea",
        )

    for path in gpx_files:
        prefix = f"gpx_{path.stem}"
        df_c = process_gpx(path)
        _, df_c, derivation, z_offset = apply_sidecar_cuts(path, None, df_c)
        render_visualizations(df_c, output_dir, name_prefix=prefix,
                              dem_paths=dem_paths)
        export_for_viewer(
            df_c, _viewer_dir(prefix),
            name_prefix=prefix, dem_paths=dem_paths, charts=charts,
            derivation=derivation, source_file=path.name,
            suggested_z_offset=z_offset, source_type="gpx",
        )

    for path in kml_files:
        prefix = f"kml_{path.stem}"
        df_c = process_kml(path)
        if df_c.empty:
            print(f"Track {path.name} ist leer (parse fehlgeschlagen?), wird übersprungen.")
            continue
        _, df_c, derivation, z_offset = apply_sidecar_cuts(path, None, df_c)
        render_visualizations(df_c, output_dir, name_prefix=prefix,
                              dem_paths=dem_paths)
        export_for_viewer(
            df_c, _viewer_dir(prefix),
            name_prefix=prefix, dem_paths=dem_paths, charts=charts,
            derivation=derivation, source_file=path.name,
            suggested_z_offset=z_offset, source_type="kml",
        )

    print(f"\nFertig. Output in {output_dir.resolve()}")


if __name__ == "__main__":
    main()
