# gps_pipeline

Python-Paket der GPS-Track-Pipeline. Für den **Projekt-Überblick und
alle CLI-Befehle** siehe die [README.md im Repo-Wurzelverzeichnis](../README.md).

## Schnellster Einstieg als Library

```python
from pathlib import Path
from gps_pipeline import (
    process_nmea, apply_sidecar_cuts, export_for_viewer, find_charts,
)

src = Path("data/track.txt")
df_raw, df_c = process_nmea(src)
# Schnittanweisung <basename>.cuts.json automatisch erkennen + anwenden
# (Re-Run nach Cut-Export im Viewer). Macht nichts, wenn keine vorhanden.
df_raw, df_c, derivation, z_offset = apply_sidecar_cuts(src, df_raw, df_c)
export_for_viewer(
    df_c, Path("output/my_track"),
    name_prefix="my_track",
    df_raw=df_raw,
    dem_paths=[Path("data/dem.tif")],
    charts=find_charts(Path("data")),
    derivation=derivation,
    source_file=src.name,
    suggested_z_offset=z_offset,
)
# danach: python view.py output/my_track
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
                                                  apply_sidecar_cuts (optional)
                                                  (Sidecar <name>.cuts.json)
                                                              │
                          ┌───────────────────────────────────┴───────────────────┐
                          ▼                                                       ▼
                  export_for_viewer                                       render_visualizations
                  (track.json + DEM-LODs + charts.json)                   (Plotly-HTML, Legacy)
```

Die Schnittanweisung selbst wird vom React-Viewer geschrieben (Export-Button)
und liegt als `<quelldatei>.cuts.json` neben der Quelldatei im `data/`-Ordner.

Volle Schema-Definitionen und Designentscheidungen: siehe
[../ARCHITECTURE.md](../ARCHITECTURE.md).

## Modulübersicht

| Pfad | Aufgabe |
|---|---|
| `config.py` | Zentrale Konstanten (Filter-Schwellen, DEM-Auflösungen, …) |
| `api.py` | High-Level-API (`process_*`, `export_for_viewer`, `apply_sidecar_cuts`, `render_*`) |
| `parsing/` | NMEA / GPX / KML / Chart-Parser, Schnittanweisungs-Parser (cut_config) |
| `processing/` | Filter, Consolidate, Enrich, Cut-Anwendung (trim/gap/synthetic), GSV-Aggregate |
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
