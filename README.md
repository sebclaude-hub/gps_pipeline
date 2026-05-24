# GPS-Track-Pipeline + React-Viewer

Verarbeitung, Visualisierung und Bearbeitung von GPS-Tracks aus
NMEA-Logfiles, GPX und KML. Mit DEM-Terrain, Vorhang-Layer,
Karten-Overlays, Cut/Trim-Workflow und Synthetic-Tracks.

```
Track-Quelle  ─→  Python-Pipeline  ─→  output/  ─→  view.py-Server  ─→  React-Viewer (Browser)
(.txt/.gpx/.kml)                    (track.json + DEM-LODs + charts)
```

Eine Übersicht der Architektur steht in [ARCHITECTURE.md](ARCHITECTURE.md),
die Entwicklungsgeschichte in [CHANGES.md](CHANGES.md).

---

## Installation

### Python-Pipeline

```powershell
# 1. Python 3.11+ und pip vorhanden
# 2. Dependencies installieren
pip install pynmea2 pandas numpy plotly geopy rasterio pyarrow
```

`rasterio` braucht GDAL — auf Windows am einfachsten via
[OSGeo4W](https://trac.osgeo.org/osgeo4w/) oder vorgebaute Wheels von
[Christoph Gohlke](https://github.com/cgohlke/geospatial-wheels/releases).

### React-Viewer

Der React-Viewer ist bereits **vorgebaut im Repo** (`gps_viewer/dist/`).
Du brauchst nur Node, wenn du die TypeScript-Quellen änderst und neu
bauen willst:

```powershell
cd gps_viewer
npm install
npm run build       # erzeugt dist/ neu
```

---

## CLI-Befehle (Übersicht)

| Befehl | Zweck |
|---|---|
| `python -m gps_pipeline` | Alle Tracks aus `data/` verarbeiten, HTML + Feather nach `output/` |
| `python view.py [output_dir]` | React-Viewer-Server starten, Browser öffnet automatisch |
| `python -m gps_pipeline.apply_cuts ...` | `ranges.json` (aus Viewer-Export) auf Feather anwenden, neuen Viewer-Output erzeugen |
| `python -c "from gps_pipeline import ..."` | Library-Nutzung für individuelle Workflows |

Vor jedem Python-Aufruf auf Windows:

```powershell
$env:PYTHONUTF8 = "1"
```

(Verhindert Unicode-Encoding-Errors in `print()`-Ausgaben — siehe
[CLAUDE_NOTES.md](CLAUDE_NOTES.md).)

---

## Workflow 1 — Track verarbeiten und ansehen

```powershell
# Quelldateien nach data/ legen:
#   data/track.txt           NMEA-Log
#   data/track.gpx           oder GPX
#   data/track.kml           oder KML (gx:Track)
#   data/linked_sued.tif     DEM (optional, Copernicus GLO-30)
#   data/EDFG.png            Karten-Overlay (optional)
#   data/EDFG.txt            zugehörige Eckkoordinaten (4 Zeilen lon lat)

# Voll-Export für den React-Viewer (mit DEM + Karten):
$env:PYTHONUTF8 = "1"
python -c "
from pathlib import Path
from gps_pipeline import process_nmea, export_for_viewer, find_charts
df_raw, df_c = process_nmea(Path('data/track.txt'))
export_for_viewer(
    df_c, Path('output'),
    name_prefix='meine_tour',
    df_raw=df_raw,
    dem_paths=[Path('data/linked_sued.tif')],
    charts=find_charts(Path('data')),
)
"

# Viewer starten -- öffnet http://localhost:8765
$env:PYTHONUTF8 = "1"
python view.py output
```

Alternativ der "naive" Modus, der einfach alles aus `data/` verarbeitet
und zusätzlich HTML-Dateien erzeugt (Legacy-Plotly-Pfad):

```powershell
$env:PYTHONUTF8 = "1"
python -m gps_pipeline
```

---

## Workflow 2 — Track trimmen (Round-Trip)

```powershell
# 1. Im React-Viewer Cuts definieren (+ Cut, Reset, Export)
#    -> Browser lädt cut_ranges.json herunter (in Downloads)
#    -> Datei nach data/ verschieben (selber Ordner wie deine Quelldaten)

# 2. Cuts anwenden (--ranges entfaellt, Default ist data/cut_ranges.json)
$env:PYTHONUTF8 = "1"
python -m gps_pipeline.apply_cuts `
    --feather output/meine_tour.feather `
    --output  output_trimmed/ `
    --dem     data/linked_sued.tif `
    --charts  data/

# 3. Getrimmten Track im Viewer ansehen
$env:PYTHONUTF8 = "1"
python view.py output_trimmed
```

Im Viewer erscheint ein **Warnhinweis-Banner** ("Getrimmter Track —
Original 'meine_tour', N Cuts angewendet, M Punkte entfernt"), damit
unmissverständlich klar bleibt, dass die Ansicht eine bearbeitete
Version ist und nicht die ursprünglichen Messungen.

Alle Flags von `apply_cuts`:

| Flag | Bedeutung | Pflicht |
|---|---|---|
| `--feather PFAD` | Bestehender Schema-C-Feather aus `output/` | ja |
| `--output DIR` | Ziel-Verzeichnis für den neuen Viewer-Output | ja |
| `--ranges PFAD` | `cut_ranges.json` (Default: `data/cut_ranges.json`) | nein |
| `--dem PFAD` | DEM-GeoTIFF; mehrfach angebbar für Multi-Tile | nein |
| `--charts DIR` | Verzeichnis mit PNG+TXT-Karten-Overlays | nein |
| `--source-type` | `nmea` \| `gpx` \| `kml` (Default `nmea`) | nein |
| `--name-prefix` | Anzeigename im Viewer (Default: `<feather>_trimmed`) | nein |

> **Hinweis:** Satelliten-Daten werden beim Trimmen nicht mitgenommen
> (Schema A ist nicht im Feather gespeichert). Wenn der getrimmte Track
> Satelliten enthalten soll, muss vom Quell-NMEA neu prozessiert werden.

---

## Workflow 3 — Synthetic-Track (Zeitachse stauchen)

Anwendungsfall: Autofahrt mit Ladepausen, die für die reine Fahrzeit-
Auswertung "nie passiert sein sollen". Die Pausen werden entfernt und
die Zeitachse so geschlossen, dass die Brückenzeit aus der erwarteten
Geschwindigkeit der Nachbarpunkte interpoliert wird.

```powershell
$env:PYTHONUTF8 = "1"
python -c "
from pathlib import Path
from gps_pipeline import (
    load_cut_ranges, create_synthetic_track, save_synthetic,
)
from gps_pipeline.dataframe_io.feather import load_df

df = load_df('output/meine_tour.feather')
cuts = load_cut_ranges(Path('output/ranges.json'))
df_synth, meta = create_synthetic_track(
    df, cuts, interp_n=10, source_name='meine_tour',
)
save_synthetic(df_synth, meta, Path('output/meine_tour'))
# -> output/meine_tour_synthetic.feather
# -> output/meine_tour_synthetic.meta.json   (mit GSV-Warnung)
"
```

Das Suffix `_synthetic` wird erzwungen, damit die Datei klar als
modifiziert erkennbar bleibt. Die `meta.json` enthält die Cut-Ranges
und eine explizite Warnung, dass Satellitendaten durch die verschobene
Zeitachse nicht mehr gültig sind.

---

## Workflow 4 — Mehrere Tracks vergleichen (Plotly-HTML)

```powershell
$env:PYTHONUTF8 = "1"
python -c "
from pathlib import Path
from gps_pipeline import process_nmea, process_gpx, render_comparison
_, df_a = process_nmea(Path('data/track_a.txt'))
df_b = process_gpx(Path('data/track_b.gpx'))
render_comparison(df_a, df_b, Path('output'),
                  name_a='Auto', name_b='Smartphone',
                  output_name='vergleich',
                  dem_paths=[Path('data/dem.tif')])
"
```

Erzeugt `output/vergleich.html` (Plotly).

---

## Daten-Quellen

### DEM (Höhenmodell)

- **Copernicus GLO-30**: globales 30-m-DEM, kostenfrei
  - Web-UI: <https://portal.opentopography.org/>
    → "Global Data" → "COP30: Copernicus Global DSM 30m"
  - Direkter S3-Tile-Download: `https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N50_00_E009_00_DEM/Copernicus_DSM_COG_10_N50_00_E009_00_DEM.tif`
- Mehrere Tiles dürfen gleichzeitig in `data/` liegen, die Pipeline
  wählt pro Track-Punkt automatisch das passende.

### Karten-Overlay-Format

`<name>.png` + `<name>.txt` im `data/`-Ordner. Die TXT-Datei enthält
**vier Zeilen mit `lon lat`** (Dezimalgrad, WGS84) in dieser
Reihenfolge:

```
# Anflugkarte EDFG
# Reihenfolge: oben-links, oben-rechts, unten-links, unten-rechts
9.125000  50.227778
9.230556  50.227778
9.125000  50.151389
9.230556  50.151389
elevation_m: 220        # optional, Fallback ohne DEM
subdivision: 64         # optional, Mesh-Override (sonst adaptiv)
```

---

## Ordnerstruktur

```
.
├── README.md             ← diese Datei
├── ARCHITECTURE.md       ← technische Referenz, Schemata, Designentscheidungen
├── CHANGES.md            ← chronologische Entwicklungsgeschichte
├── CLAUDE_NOTES.md       ← Arbeitsnotizen (Windows/PowerShell-Eigenheiten)
├── view.py               ← HTTP-Server für den React-Viewer
├── data/                 ← Input (nicht im Repo)
├── output/               ← Output (nicht im Repo)
├── gps_pipeline/         ← Python-Pipeline (siehe ARCHITECTURE.md)
└── gps_viewer/           ← React + deck.gl + TypeScript
    ├── src/              ← Quellen
    └── dist/             ← vorgebauter Production-Build (committed)
```

---

## React-Viewer — Bedienung

Nach `python view.py output` und Browser-Öffnen:

| Steuerung | Wirkung |
|---|---|
| Maus-Drag | Karte verschieben |
| Maus-Wheel | Zoom |
| Shift + Drag (rechts) oder rechte Maustaste | Kamera neigen/drehen |
| Hover über Track | InfoPanel + Tooltip zeigen Punkt-Info |
| Slider unten | Aktiven Punkt scrubben |
| **+ Cut** | Cut-Range an aktueller Slider-Position einfügen |
| Cut-Drag-Handles | Start/Ende des Cuts verschieben |
| **Export** | `ranges.json` herunterladen |
| Toggle "Vorhang" | Vertikale Wand vom Track zum Boden |
| Toggle "Karten (N)" | Karten-Overlays ein/aus (nur wenn vorhanden) |
| Toggle "Panel/Tip/Beide" | Info-Anzeige-Modus |
| ZScale-Buttons | Höhen-Übertreibung 1×–10× |
| Offset-Slider | Track-Höhe gegen DEM kalibrieren (Auto/0/manuell) |

---

## Weiterführend

- [ARCHITECTURE.md](ARCHITECTURE.md) — Schemata A/B/C, Designentscheidungen, DEM-Handling, Chart-Mesh-Strategien
- [CHANGES.md](CHANGES.md) — chronologische Schritt-für-Schritt-Historie inkl. Bug-Postmortems
- [gps_pipeline/README.md](gps_pipeline/README.md) — Python-Paket-spezifische Notizen

## Geplant

Eine **PWA-Konvertierung** (Progressive Web App) ist im Konzept-Status.
Ziel: standalone-fähig ohne Python-Installation, auf
Linux/Windows/macOS/Android. Bekommt einen eigenen GitHub-Repo. Die
Pipeline hier bleibt als Power-User-Werkzeug und Referenzimplementierung
erhalten.
