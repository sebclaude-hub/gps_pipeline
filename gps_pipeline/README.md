# gps_pipeline

Modulare Pipeline zur Verarbeitung und Visualisierung von GPS-Tracks aus
NMEA-Logfiles und GPX-Dateien.

## Quickstart

```bash
# 1. Dateien in den data/-Ordner legen:
#    - NMEA-Logs als .txt
#    - GPX-Dateien als .gpx
#    - Optional: ein DEM als .tif (z.B. Copernicus GLO-30 von OpenTopography)
#
# 2. Vom Verzeichnis aus, das gps_pipeline/ und data/ enthält:
python -m gps_pipeline

# 3. Output landet in output/ als HTML-Dateien zum Öffnen im Browser.
```

Oder programmatisch:

```python
from pathlib import Path
from gps_pipeline import process_nmea, process_gpx, render_visualizations

df_raw, df = process_nmea(Path("data/nmea_log.txt"))
render_visualizations(df, Path("output"), name_prefix="meine_tour", df_raw=df_raw)
```

## Pipeline-Architektur

```
NMEA-Logfile  ──→  parse_nmea  ──→  build_dataframe  ──→  filter_invalid
                                                                │
                                                                ▼
                                                          consolidate
                                                                │
GPX-Datei  ──→  parse_gpx  ─────────────────────────────────────┤
                                                                ▼
                                                          enrich_speed
                                                                │
                                          ┌─────────────────────┼───────────────────┐
                                          ▼                     ▼                   ▼
                                    visualize_3d   visualize_satellites   visualize_multiple
```

**Schemata** zwischen den Schritten:

- **Schema A**: eine Zeile pro NMEA-Satz (sentence_type, talker_id, gga_*,
  rmc_*, vtg_*, gsv_satellites, ...)
- **Schema B**: eine Zeile pro Timestamp (directional_lat/lon, altitude_corrected,
  speed_kmh, speed_knots)
- **Schema C**: Schema B + Distanz und geodätische Geschwindigkeit
  (distance_m, speed_geodesic_*, speed_diff_*)

GPX-Parser springt direkt zu Schema B (keine separaten Sentence-Typen).

## Modulübersicht

| Pfad | Aufgabe |
|---|---|
| `config.py` | Zentrale Konstanten (Filter-Schwellen, Default-Farben, Z-Überhöhung) |
| `parsing/nmea.py` | NMEA-Datei → Liste pynmea2-Objekte |
| `parsing/nmea_to_dataframe.py` | pynmea2-Objekte → Schema-A-DataFrame |
| `parsing/gpx.py` | GPX-Datei → Schema-B-DataFrame |
| `processing/gsv_aggregate.py` | Multi-Sentence-GSV-Aggregation (Multi-Constellation-fähig) |
| `processing/filter.py` | Ungültige Sätze entfernen (Schema A → A) |
| `processing/consolidate.py` | GGA/RMC/VTG pro Timestamp zusammenführen (A → B) |
| `processing/enrich.py` | Geodätische Distanz/Geschwindigkeit (B → C) |
| `visualization/three_d.py` | 3D-Track in Plotly mit optionalem Terrain |
| `visualization/satellite_view.py` | Polar-Plot der Satellitenposition |
| `visualization/multi_track.py` | Mehrere Tracks im Vergleich |
| `terrain/dem.py` | DEM (GeoTIFF) laden und auf Track-Bounds zuschneiden |
| `utils/safe_convert.py` | Type-Konversion mit Fallback |

## DEM beschaffen (für Terrain-Visualisierung)

Empfohlene Quelle: **Copernicus GLO-30** über OpenTopography.

1. https://portal.opentopography.org/ aufrufen
2. "Global Data" → "COP30: Copernicus Global DSM 30m" wählen
3. Rechteck um das Track-Gebiet zeichnen, Download starten
4. Heruntergeladene `.tif` nach `data/` legen

Alternative: direkter Download eines 1°×1°-Tiles von AWS, z.B.:
```
https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N47_00_E011_00_DEM/Copernicus_DSM_COG_10_N47_00_E011_00_DEM.tif
```

Wenn der Track über mehrere 1°-Tiles geht, müssten die aktuell manuell mit
`rasterio.merge` zusammengeführt werden — der derzeitige `load_dem`
unterstützt nur eine Datei pro Aufruf.

## Konfiguration

Die wichtigsten Defaults in `config.py`:

```python
DEFAULT_QUANTILES = 5             # Farbklassen für Quantil-Binning
DEFAULT_COLORSCALE = "Plasma"     # Standard-Farbskala
DEFAULT_Z_EXAGGERATION = 1.0      # Zusätzliche Höhen-Übertreibung
EXCLUDE_GGA_QUALITIES = [0, 5]    # Welche Fix-Qualitäten verworfen werden
```

Pro Funktionsaufruf überschreibbar — siehe Docstrings der Visualisierungs-Funktionen.

## Test-Ergebnisse

Pipeline erfolgreich getestet mit:

- **NMEA**: GPS-Testempfänger, single-constellation, 10 Hz
  (Test-File: 2087 Zeilen → 580 Schema-C-Zeilen, 68 s Auto-Tour)
- **GPX**: GPS-Flugzeugapp (Flugplanungs-App), 1271 Trackpoints, ~1 Stunde Flug
  inklusive 138 doppelter Timestamps (10.9%), werden korrekt durchgereicht
- **Multi-Constellation**: synthetischer GPS+GLONASS+Galileo-Test
  (drei separate GSV-Gruppen, PRN-Nummern pro Konstellation getrennt)

## Bekannte Einschränkungen / TODOs

- DEM-Mehrkachel-Merge: aktuell muss manuell mit `rasterio.merge` gemacht werden
- Höhenvergleich Track ↔ DEM (z.B. "Flugzeug 200 m über Boden") wäre nice-to-have
- Echte Satellitenkachel-Drapierung über das Mesh statt Höhen-Farbskala
- Pytest-Suite: aktuell nur Smoke-Tests durch direkten Aufruf

## Abhängigkeiten

```
pynmea2
pandas
numpy
plotly
geopy
rasterio       # nur für terrain/dem.py
```
