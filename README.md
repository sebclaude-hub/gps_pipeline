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
| `python -m gps_pipeline` | Alle Tracks aus `data/` verarbeiten, HTML + Feather nach `output/` (Cuts aus `<basename>.cuts.json` werden automatisch angewendet) |
| `python view.py [output_dir]` | React-Viewer-Server starten, Browser öffnet automatisch |
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

# Alle Tracks aus data/ verarbeiten -- erzeugt sowohl Plotly-HTML
# in output/ als auch React-Viewer-Output in output/<prefix>/track.json
# (mit DEM-LODs + Karten + ggf. Schnittanweisungen, siehe Workflow 2):
$env:PYTHONUTF8 = "1"
python -m gps_pipeline

# Viewer starten -- öffnet http://localhost:8765
$env:PYTHONUTF8 = "1"
python view.py output/nmea_track    # Subdir-Name = <quelltyp>_<basename>
```

Für volle Kontrolle (z.B. ein einzelner Track per Library):

```powershell
$env:PYTHONUTF8 = "1"
python -c "
from pathlib import Path
from gps_pipeline import (
    process_nmea, apply_sidecar_cuts, export_for_viewer, find_charts,
)
src = Path('data/track.txt')
df_raw, df_c = process_nmea(src)
df_raw, df_c, derivation, z_offset = apply_sidecar_cuts(src, df_raw, df_c)
export_for_viewer(
    df_c, Path('output/meine_tour'),
    name_prefix='meine_tour',
    df_raw=df_raw,
    dem_paths=[Path('data/linked_sued.tif')],
    charts=find_charts(Path('data')),
    derivation=derivation,
    source_file=src.name,
    suggested_z_offset=z_offset,
)
"
python view.py output/meine_tour
```

---

## Workflow 2 — Track schneiden / Synthetic / Gap (Round-Trip)

Der React-Viewer bearbeitet niemals die Daten selbst. Stattdessen
schreibt er eine kompakte **Schnittanweisung** (eine kleine JSON-Datei
neben der Quelldatei), die beim nächsten Pipeline-Lauf direkt aus den
Originaldaten angewendet wird. Vorteile: Originaldaten bleiben
unangetastet, Satelliten-Bursts bleiben erhalten, Datei ist nur ein
paar hundert Byte groß. Wenn der Hoehen-Offset-Slider verschoben wurde,
wird auch dieser Wert mit gespeichert -- so wird beim Teilen eines
Tracks die gewuenschte Hoehenanzeige direkt mitgeliefert (reine
Anzeige, Daten bleiben unveraendert).

```powershell
# 1. Track erstmalig verarbeiten (Workflow 1) und im Viewer öffnen

# 2. Im Viewer Cuts definieren (+ Cut, Reset, Export)
#    -> Drei Modi pro Cut:
#       * trim       (rot)   - Punkte komplett entfernen, Rand des Tracks
#       * gap        (grün)  - Punkte entfernen, sichtbare Lücke
#       * synthetic  (blau)  - Punkte entfernen UND Zeitachse zusammenrücken
#    Edge-Cuts (am Anfang / Ende) werden automatisch zu "trim" gezwungen.
#    -> Wenn der Hoehen-Offset-Slider != 0 ist, wird er ebenfalls
#       in die Datei geschrieben (reine Anzeige beim naechsten Laden).
#    -> Browser lädt <quelldatei>.cuts.json herunter (in Downloads)
#    -> Datei nach data/ verschieben (gleicher Ordner wie die Quelldatei,
#       Name muss exakt <quelldatei>.cuts.json sein)

# 3. Pipeline erneut laufen lassen -- die Schnittanweisung wird
#    automatisch erkannt und auf die Originaldaten angewendet
$env:PYTHONUTF8 = "1"
python -m gps_pipeline
# Output landet unter output/nmea_<basename>/ -- mit korrekten Cuts,
# Banner-Hinweis und voreingestelltem Hoehen-Offset.

# 4. Track im Viewer ansehen
$env:PYTHONUTF8 = "1"
python view.py output/nmea_<basename>
```

**Anweisungen deaktivieren ohne löschen:** Die Datei einfach umbenennen,
z.B. `track.txt.cuts.json` → `track.txt.cuts.json.disabled`. Der nächste
Pipeline-Lauf zeigt dann wieder den Original-Track. Zum Re-Aktivieren
einfach zurückbenennen.

Das Datei-Format:

```json
{
  "source": "track.txt",
  "n_points_reference": 24138,
  "z_offset_m": 7,
  "cut_ranges": [
    {"start": 0,     "end": 49,    "mode": "trim"},
    {"start": 200,   "end": 350,   "mode": "synthetic"},
    {"start": 600,   "end": 700,   "mode": "gap"}
  ],
  "created_at": "2026-05-25T17:30:00Z"
}
```

`z_offset_m` ist optional. Wenn gesetzt, übernimmt der Viewer beim
Laden den Wert als Slider-Default und blendet einen Banner-Hinweis ein.
Die Daten selbst werden nicht modifiziert.

Banner-Severity im Viewer:

| Anweisungs-Mischung | Banner |
|---|---|
| Nur `trim` (Rand) | kein Banner |
| `z_offset_m` ohne Cuts | ⓘ Info — "Höhendarstellung um X m verschoben" |
| Mindestens ein `gap` (ohne synthetic) | ⓘ Info — "Lücken im Track, Geschwindigkeit dort unzuverlässig" |
| Mindestens ein `synthetic` | ⚠ Warnung — "Zeitstempel verschoben, Sats unter verschobenen Zeitstempeln" |

---

## Workflow 3 — Mehrere Tracks vergleichen (Plotly-HTML)

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
