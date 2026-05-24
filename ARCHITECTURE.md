# GPS-Pipeline — Architektur

Permanente Referenz: wie das Projekt aufgebaut ist und warum.
Für die Entstehungsgeschichte (welcher Schritt wann kam, welche Bugs
unterwegs entdeckt und gefixt wurden) siehe [CHANGES.md](CHANGES.md).

## Projekt-Scope

Die GPS-Pipeline ist ein Werkzeugkasten für die Verarbeitung und
Darstellung von GPS-Track-Daten. Sie deckt drei Ebenen ab:

1. **Parsing & Verarbeitung** (Python): NMEA-Logs, GPX-Dateien und KML-
   `gx:Track` werden in ein einheitliches Schema-C-DataFrame überführt
   (Position, Zeit, Höhe, Geschwindigkeit, Distanz, optional Terrain-Höhe).
2. **Visualisierung** (Python + React/TypeScript): Plotly-HTML-Ausgaben
   für schnelle Einzel-Snapshots; React-Viewer mit deck.gl für
   interaktive Erkundung mit DEM-Mesh, Vorhang-Layer, Skyplot,
   Z-Exaggeration.
3. **Track-Bearbeitung** (Python + React): Karten-Overlays (georef. PNGs),
   Trimming, Synthetic-Tracks mit kontrolliert verschobener Zeitachse.

Der React-Viewer wird einmalig gebaut (`npm run build`) und über
`python view.py output/` ausgeliefert -- kein laufendes Python nötig
während der Anzeige, kein Backend-Server.

## Folder-Struktur

```
gps_pipeline/
├── __init__.py          # Top-Level-Exporte (process_nmea, process_gpx, ...)
├── __main__.py          # CLI-Einstiegspunkt (python -m gps_pipeline)
├── api.py               # High-Level-API-Funktionen
├── config.py            # Alle einstellbaren Parameter
├── README.md
├── parsing/
│   ├── nmea.py                # NMEA-Datei -> Liste von pynmea2-Objekten
│   ├── nmea_to_dataframe.py   # NMEA -> Schema A (eine Zeile pro Satz)
│   ├── gpx.py                 # GPX -> Schema B
│   ├── kml.py                 # KML (gx:Track) -> Schema B
│   └── chart.py               # PNG+TXT-Paare -> ChartOverlay
├── processing/
│   ├── filter.py              # GPS-Fix-Filter (Schema A)
│   ├── consolidate.py         # Schema A -> Schema B
│   ├── enrich.py              # Schema B -> Schema C (Distanz, Speed)
│   ├── enrich_terrain.py      # Schema C + DEM -> Schema C + terrain_elevation
│   ├── gsv_aggregate.py       # GSV-Saetze aggregieren (fuer Satellite-View)
│   ├── trim.py                # Track-Trimming (Cut-Ranges)
│   └── synthetic.py           # Synthetic-Track (Zeitachse stauchen)
├── visualization/
│   ├── three_d.py             # 3D-Track-Plot (Plotly-Legacy)
│   ├── satellite_view.py      # Polar-Plot der Satellitenkonstellation
│   ├── track_with_satellites.py  # Sync 3D + Skyplot + Slider (HTML)
│   └── multi_track.py         # Vergleichs-Visualisierung
├── terrain/
│   └── dem.py                 # GeoTIFF-DEM laden, samplen, vergleichen
├── utils/
│   └── safe_convert.py        # Robuste Type-Konvertierungen
├── dataframe_io/
│   └── feather.py             # DataFrame-Persistierung
└── export/
    ├── json_export.py         # Schema-C -> track.json
    ├── dem_lod.py             # GeoTIFF -> DEM-LOD-JSONs
    └── chart_export.py        # ChartOverlay -> charts.json + PNG-Kopie

gps_viewer/                    # React + deck.gl Viewer (Web)
├── src/
│   ├── api/                   # Lader fuer track.json, satellites.json, DEM-LODs, charts.json
│   ├── hooks/                 # useTrackData, useDemLod, useCharts, useRangeSelection, ...
│   ├── components/            # TrackViewer, SkyPlot, InfoPanel, RangeSelector, Toggles
│   ├── layers/                # deck.gl-Layer-Factories (Terrain, Curtain, Chart)
│   ├── utils/                 # demMesh, chartMesh, colorMap, formatters
│   ├── types.ts               # Geteilte TypeScript-Interfaces
│   └── App.tsx                # Top-Level-State, Routing
└── dist/                      # gebauter statischer Output (committed)

view.py                        # HTTP-Server fuer den React-Viewer (laeuft nur waehrend Anzeige)
data/                          # Input (nicht im Repo, .gitignore)
output/                        # Output (nicht im Repo, .gitignore)
```

## Datenfluss

```
NMEA-Datei  ->  parse -> build_df -> filter -> consolidate -> enrich  ->  Schema C
                         (Schema A)             (Schema B)
                              v
                         visualize_satellites (nutzt GSV-Saetze)

GPX-Datei   ->  parse_gpx_file -> Schema B -> enrich -> Schema C

KML-Datei   ->  parse_kml_file -> Schema B -> enrich -> Schema C

Schema C + DEM -> enrich_terrain_elevation -> Schema C mit
                                              terrain_elevation und
                                              track_above_terrain
```

Trim und Synthetic sind eigenstaendige Seiten-Pfade, die Schema-C
konsumieren und Schema-C produzieren (mit zusaetzlicher Spalte
`is_synthetic` im Synthetic-Fall).

## Schemata

### Schema A (nur bei NMEA)

Eine Zeile pro NMEA-Satz. Spalten u.a.:

- `timestamp_utc` (datetime64[ns, UTC])
- `sentence_type` (category): RMC, GGA, VTG, GSA, GSV
- `talker_id` (category): GP, GL, GA, GB, ...
- Spezifische Spalten je Satztyp (`gga_*`, `rmc_*`, `vtg_*`, `gsa_*`, ...)
- `gsv_satellites` (object): Liste von Dicts pro GSV-Satz
- Dtypes: konsequent `UInt8`/`Float32`/`category`/`boolean` (alle nullable)

### Schema B (Zwischenstufe)

Eine Zeile pro Zeitstempel. Spalten:

- `timestamp_utc`
- `directional_latitude`, `directional_longitude` (float64, Vorzeichen-behaftet)
- `altitude_corrected` (float32, **MSL/NN-Bezug**)
- `speed_kmh`, `speed_knots` (float32)

### Schema C (Hauptausgabe)

Schema B plus angereicherte Spalten:

- `distance_m` (float32): Geodätische Distanz zum Vorgänger
- `speed_geodesic_kmh`, `speed_geodesic_knots` (float32): aus Distanz/Zeit
- `speed_diff_kmh`, `speed_diff_knots` (float32): GPS-Speed minus Geodesic
- Mit DEM zusätzlich:
  - `terrain_elevation` (Float32): DEM-Höhe an dieser Stelle
  - `track_above_terrain` (Float32): Höhe über Grund

Index ist ein RangeIndex (0..n-1) — bewusst, kein DatetimeIndex.

## Wichtige Designentscheidungen

### Höhen-Bezug

NMEA-`gga_altitude` ist **MSL** (Mean Sea Level), nicht ellipsoidisch.
Deutsche/europäische DEMs sind ebenfalls NN-bezogen. Deshalb wird die
Geoid-Trennung **nicht** addiert. `altitude_corrected = gga_altitude`.

Ähnliches gilt für KML `gx:Track` (Google Earth nutzt MSL).
GPX-Daten von Skydemon/OSMTracker u.ä. sind nominell MSL, aber je nach
Quelle teils ellipsoidisch — manchmal um ~46 m Geoid-Trennung verschoben.
Das wird über die `auto`-Diagnose erkannt und ggf. durch `track_z_offset`
korrigiert.

### Track-Z-Offset

Der Track wird relativ zum DEM um einen vertikalen Offset verschoben, um
Bezugsunterschiede (Ellipsoid vs. NN-MSL, Geoidmodelle, GPS-Drift) zu
kompensieren.

**Wo der Offset wirkt:**

- **Python-Auto-Diagnose** (`compare_track_dem` → `suggested_offset`):
  Median-basiert + outlier-robust (5%-Perzentil) + asymmetrisch
  geclampt (`max(raw, min(0, -p5))`). Liefert den Default für den
  Slider, ohne dabei `points.alt` im Export zu modifizieren.
- **Plotly-HTML-Pfad** (`three_d.py`): wendet den
  `track_z_offset`-Parameter direkt auf die Track-Z-Positionen an.
- **React-Viewer**: wendet den Offset **live im Frontend** an
  (`zOffset`-State, geliefert vom `OffsetSlider`). `exagAlt(alt + offset)`
  wird in TrackViewer-Pfad-Layer, Cut-Path-Overlay, aktivem Markerpunkt,
  Pick-Layer und Curtain-Top angewendet. Terrain-Mesh, Chart-Mesh und
  Curtain-Bottom bleiben unverändert (das DEM ist die Bezugsfläche).
- **InfoPanel und Tooltip** im React-Viewer rechnen `above_terrain`
  und `MSL` live aus `alt + zOffset − terrain_elev`.

**Konfiguration** (`TRACK_Z_OFFSET` in `config.py`):

- `"auto"` (Default): Auto-Diagnose mit Clamping. Wert landet in
  `track.json::meta.suggested_z_offset_m` als Slider-Default.
- `"none"` oder `None`: kein Offset, Vorschlag = 0.
- Zahl (z.B. `-36.4`): fester Wert in Metern (überschreibt die
  Auto-Diagnose). Slider-Default = dieser Wert.

In allen Fällen darf der Nutzer im React-Viewer den Slider beliebig
verschieben — der Python-Wert ist nur der Startpunkt.

### DEM-Auflösung

Adaptive Auflösung über zwei Parameter:

- `DEM_TARGET_PIXEL_SIZE_M = 50` — Ziel-Pixelgröße in Metern
- `DEM_MAX_PIXELS_PER_AXIS = 2000` — harte Obergrenze pro Achse

Das gröbere Downsampling der beiden gewinnt. Bei kleinen DEMs bleibt die
DEM-eigene Auflösung erhalten (keine künstliche Interpolation).

Zusätzlich `DEM_MAX_HTML_MB = 100` als Reservebremse: wenn die
geschätzte HTML-Dateigröße (3 Byte pro Vertex, empirisch ermittelt) das
Limit überschreitet, wird die Auflösung automatisch halbiert.

### Multi-DEM-Handling

Liegen mehrere DEM-Tiles im `data/`-Ordner, werden sie zur
Visualisierung gemerged. Für Diagnose und Sampling
(`compare_track_dem`, `enrich_terrain_elevation`) wird **nicht
gemerged**: pro Track-Punkt wird das passende Tile gesucht. So bleiben
die rohen DEM-Werte erhalten (nicht das geglättete Merge-Bild).

### Padding

Symmetrisch in alle vier Richtungen. Wert: 15% der **kleineren**
Bounds-Spannweite (in Grad). Das macht die Box ausgewogen, ohne in der
langen Achse zu sehr aufzublähen.

### Chart-Mesh-Strategien (siehe `gps_viewer/src/utils/chartMesh.ts`)

Bei Karten-Overlays auf dem DEM-Terrain muessen drei Dinge mit dem
Terrain-Mesh exakt uebereinstimmen, sonst kommt es zu sichtbarem
"Z-Fighting" (siehe Bug-Postmortem in CHANGES.md):

1. Vertex-Positionen (selbe DEM-Sample-Punkte)
2. Anker und cos(lat)-Faktor (gemeinsamer Bezugspunkt)
3. Triangulation und Iterationsreihenfolge (gleiche Diagonale)

Strategie A erfuellt alle drei und braucht keinen Z-Lift; Strategie B
(Fallback ohne DEM oder bei nicht-axenparallelen Karten) braucht 5 m
Lift.

### DataFrame-Persistierung

Feather-Format (Arrow IPC v2) via `dataframe_io.feather`:

- Behält alle Dtypes, auch nullable und datetime mit UTC
- `gsv_satellites`-Listen funktionieren
- Schnell zum Schreiben und Lesen
- Nicht für Langzeit-Archivierung (Format kann sich zwischen Arrow-
  Versionen leicht ändern), aber super für temporären Austausch
  zwischen Skripten

## Bekannte Einschränkungen

### Datumsgrenze (180° E/W)

Tracks, die die Datumsgrenze überqueren, würden falsche Bounds
berechnen. Praktisch irrelevant für den primären Use-Case, aber
sollte man wissen.

### Multi-Constellation-GSV-Sätze

Bei Multi-Constellation-Empfängern (ZED-X20P u.ä.) können GSV-Sätze
pro Konstellation mit minimal verschobenen Timestamps ankommen. Die
aktuelle `visualize_satellites` zeigt nur Gruppen mit exakt gleichem
Timestamp. Bei ersten echten Multi-Constellation-Daten ggf. Toleranz
einbauen.

### Lon/Lat-Verzerrung außerhalb des Äquators

Bei 50°N ist 1° Lon ≈ 71 km, 1° Lat ≈ 111 km. Padding wird in **Grad**
gerechnet, nicht in Metern — d.h. 0.6° Padding wirkt in Lon-Richtung
anders als in Lat-Richtung. In der Visualisierung gleicht
`aspectmode='manual'` das wieder aus, aber die rohe Box ist im
Kartesischen leicht asymmetrisch.

## Verwendung

### CLI

```powershell
$env:PYTHONUTF8 = "1"
python -m gps_pipeline
```

Erwartet `data/`-Ordner mit `.txt` (NMEA), `.gpx`, `.kml`, optional
`.tif` (DEM) und `.png`+`.txt`-Paare (Karten). Schreibt nach `output/`.

Hinweis: Auf Windows muss `PYTHONUTF8=1` gesetzt sein, sonst crashen
manche `print()`-Aufrufe der Pipeline mit `UnicodeEncodeError` (siehe
[CLAUDE_NOTES.md](CLAUDE_NOTES.md)). Vor *jedem* Python-Aufruf in einer
neuen Shell.

### Als Bibliothek

```python
from pathlib import Path
from gps_pipeline import (
    process_nmea, process_gpx, process_kml,
    export_for_viewer, render_visualizations,
    find_charts,
)
from gps_pipeline.dataframe_io.feather import save_df, load_df

# Track verarbeiten
df_raw, df_c = process_nmea(Path("data/track.txt"))

# Fuer React-Viewer exportieren
charts = find_charts(Path("data"))
export_for_viewer(
    df_c, Path("output"),
    name_prefix="my_track",
    df_raw=df_raw,
    dem_paths=[Path("data/dem.tif")],
    charts=charts,
)

# Persistieren / wieder laden
save_df(df_c, "output/my_track.feather")
df_c2 = load_df("output/my_track.feather")
```

## Workflow-Beispiele

### Karten-Overlay anzeigen

```powershell
# 1. PNG + TXT in data/ ablegen, z.B.:
#    data/EDFG.png  (Anflugkarte)
#    data/EDFG.txt  (4 Eckkoordinaten + optional elevation_m)
# 2. Export
$env:PYTHONUTF8 = "1"
python -c "
from pathlib import Path
from gps_pipeline import process_nmea, export_for_viewer, find_charts
df_raw, df_c = process_nmea(Path('data/track.txt'))
charts = find_charts(Path('data'))
export_for_viewer(df_c, Path('output'), name_prefix='test',
                  df_raw=df_raw, charts=charts)
"
$env:PYTHONUTF8 = "1"
python view.py output
```

### Track trimmen (Round-Trip mit dem React-Viewer)

```powershell
# 1. Im React-Viewer Cuts definieren, "Export" klickt -> ranges.json
#    (Browser-Download, manuell nach output/ verschieben oder
#    direkt referenzieren wo der Browser sie ablegt)
# 2. CLI ausfuehren
$env:PYTHONUTF8 = "1"
python -m gps_pipeline.apply_cuts `
    --feather output/test.feather `
    --ranges  output/ranges.json `
    --output  output_trimmed/ `
    --dem     data/linked_sued.tif `
    --charts  data/
# 3. Im Viewer betrachten
$env:PYTHONUTF8 = "1"
python view.py output_trimmed
```

Das CLI laedt das Schema-C-Feather, wendet die Cuts an und erzeugt ein
vollstaendiges Viewer-Output-Verzeichnis (track.json + DEM-LODs + charts).
Satelliten-Daten werden **nicht** mitgetrimmt -- der Output enthaelt
keine satellites.json, weil Schema A (NMEA-Rohsaetze) nicht im Feather
liegt.

Programmatisch:
```python
from pathlib import Path
from gps_pipeline.apply_cuts import apply_cuts
apply_cuts(
    feather_path=Path("output/test.feather"),
    ranges_path=Path("output/ranges.json"),
    output_dir=Path("output_trimmed/"),
    dem_paths=[Path("data/linked_sued.tif")],
    chart_dir=Path("data/"),
)
```

### Synthetic-Track (Pausen "wegtricksen")

```powershell
$env:PYTHONUTF8 = "1"
python -c "
from pathlib import Path
from gps_pipeline import (
    load_cut_ranges, create_synthetic_track, save_synthetic,
)
from gps_pipeline.dataframe_io.feather import load_df
df = load_df('output/test.feather')
cuts = load_cut_ranges(Path('ranges.json'))
df_synth, meta = create_synthetic_track(df, cuts, interp_n=10,
                                        source_name='test')
save_synthetic(df_synth, meta, Path('output/test'))
# -> output/test_synthetic.feather + test_synthetic.meta.json
"
```

## Verlauf der Konstanten und Defaults

Hilfreich beim Nachschauen, falls ein Wert in einem Plot nicht stimmt:

| Parameter | Wert | Bedeutung |
|---|---|---|
| `TRACK_Z_OFFSET` | `"auto"` | Höhen-Offset-Modus |
| `DEM_SMOOTH` | `1.0` | Sigma für Gaussian-Smoothing (0 deaktiviert) |
| `DEM_TARGET_PIXEL_SIZE_M` | `50` | Ziel-Pixelgröße in m |
| `DEM_MAX_PIXELS_PER_AXIS` | `2000` | Harte Pixel-Obergrenze |
| `DEM_MAX_HTML_MB` | `100` | HTML-Größen-Reservebremse (Plotly-Pfad) |
| `DEFAULT_QUANTILES` | `5` | Anzahl Speed-Quantile (in 3D-Plot) |
| `DEFAULT_COLORSCALE` | `"Plasma"` | Plotly-Colorscale |
| `DEFAULT_Z_EXAGGERATION` | `1.0` | Z-Überhöhung im 3D-Plot |
