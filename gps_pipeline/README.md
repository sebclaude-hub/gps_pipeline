# gps_pipeline

Python-Paket der GPS-Track-Pipeline. Für den **Projekt-Überblick und
alle CLI-Befehle** siehe die [README.md im Repo-Wurzelverzeichnis](../README.md).

## Schnellster Einstieg als Library

```python
from pathlib import Path
from gps_pipeline import process_nmea, export_for_viewer, find_charts

df_raw, df_c = process_nmea(Path("data/track.txt"))
export_for_viewer(
    df_c, Path("output"),
    name_prefix="my_track",
    df_raw=df_raw,
    dem_paths=[Path("data/dem.tif")],
    charts=find_charts(Path("data")),
)
# danach: python view.py output
```

## Pipeline-Architektur (Kurzfassung)

```
NMEA-Logfile  →  parse_nmea → build_dataframe → filter → consolidate
                  (Schema A)                              (Schema B)
                                                              │
GPX/KML  →  parse_gpx_file / parse_kml_file  →  Schema B     │
                                                              ▼
                                                          enrich_speed
                                                          (Schema C)
                                                              │
              ┌───────────────────────────────────────────────┼───────────────────┐
              ▼                                               ▼                   ▼
        export_for_viewer                               render_visualizations  apply_cuts
        (track.json + DEM-LODs + charts.json)           (Plotly-HTML, Legacy)  (Trim Round-Trip)
```

Volle Schema-Definitionen und Designentscheidungen: siehe
[../ARCHITECTURE.md](../ARCHITECTURE.md).

## Modulübersicht

| Pfad | Aufgabe |
|---|---|
| `config.py` | Zentrale Konstanten (Filter-Schwellen, DEM-Auflösungen, …) |
| `api.py` | High-Level-API (`process_*`, `export_for_viewer`, `render_*`) |
| `apply_cuts.py` | CLI + Library für Trim-Re-Import |
| `parsing/` | NMEA / GPX / KML / Chart-Parser |
| `processing/` | Filter, Consolidate, Enrich, Trim, Synthetic, GSV-Aggregate |
| `terrain/dem.py` | GeoTIFF-DEM laden, samplen, Track-Vergleich |
| `visualization/` | Plotly-HTML-Pfade (3D, Skyplot, Multi-Track, Track+Sat) |
| `export/` | JSON-Exporte für den React-Viewer (Track, DEM-LODs, Charts) |
| `dataframe_io/feather.py` | DataFrame-Persistierung (Arrow IPC v2) |
| `utils/safe_convert.py` | Robuste Type-Konversion |

## Abhängigkeiten

```
pynmea2
pandas
numpy
plotly        # nur für visualization/*
geopy
rasterio      # nur für terrain/dem.py
pyarrow       # für dataframe_io/feather.py
```
