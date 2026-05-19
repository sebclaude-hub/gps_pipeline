"""GPS-Pipeline CLI — Einstiegspunkt für ``python -m gps_pipeline``.

Liest NMEA-/GPX-/KML-Dateien aus ``data/``, verarbeitet sie zu Schema-C-
DataFrames und schreibt Visualisierungen plus Feather-Export nach ``output/``.

Die eigentlichen API-Funktionen liegen in ``api.py``. Direkt importieren via::

    from gps_pipeline import process_nmea, process_gpx, process_kml, render_visualizations
"""

from pathlib import Path

from .api import process_nmea, process_gpx, process_kml, render_visualizations


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

    nmea_files = sorted(input_dir.glob("*.txt"))
    gpx_files = sorted(input_dir.glob("*.gpx"))
    kml_files = sorted(input_dir.glob("*.kml"))

    if not nmea_files and not gpx_files and not kml_files:
        print(f"Keine NMEA-, GPX- oder KML-Dateien in {input_dir} gefunden.")
        return

    for path in nmea_files:
        prefix = f"nmea_{path.stem}"
        df_raw, df_c = process_nmea(path)
        render_visualizations(df_c, output_dir,
                              name_prefix=prefix, df_raw=df_raw, dem_paths=dem_paths)

    for path in gpx_files:
        prefix = f"gpx_{path.stem}"
        df_c = process_gpx(path)
        render_visualizations(df_c, output_dir, name_prefix=prefix, dem_paths=dem_paths)

    for path in kml_files:
        prefix = f"kml_{path.stem}"
        df_c = process_kml(path)
        if df_c.empty:
            print(f"Track {path.name} ist leer (parse fehlgeschlagen?), wird übersprungen.")
            continue
        render_visualizations(df_c, output_dir, name_prefix=prefix, dem_paths=dem_paths)

    print(f"\nFertig. Output in {output_dir.resolve()}")


if __name__ == "__main__":
    main()
