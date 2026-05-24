# GPS-Pipeline — Stand 24. Mai 2026

Dieses Dokument beschreibt den aktuellen Stand nach der mehrtägigen Refactor-
und Ausbau-Session. Es ersetzt den älteren `refactor_plan.md` (Stand 4. Mai),
der nur den ursprünglichen Plan enthält und seitdem viele Details nicht mehr
widerspiegelt.

## Projekt-Scope

Die GPS-Pipeline ist ein Werkzeugkasten für die Verarbeitung und Darstellung
von GPS-Track-Daten. Sie deckt drei Ebenen ab:

1. **Parsing & Verarbeitung** (Python): NMEA-Logs, GPX-Dateien und KML-
   `gx:Track` werden in ein einheitliches Schema-C-DataFrame überführt
   (Position, Zeit, Höhe, Geschwindigkeit, Distanz, optional Terrain-Höhe).
2. **Visualisierung** (Python + React/TypeScript): Plotly-HTML-Ausgaben für
   schnelle Einzel-Snapshots; React-Viewer mit deck.gl für interaktive
   Erkundung mit DEM-Mesh, Vorhang-Layer, Skyplot, Z-Exaggeration.
3. **Track-Bearbeitung** (Python + React): Karten-Overlays (georef. PNGs),
   Trimming, Synthetic-Tracks mit kontrolliert verschobener Zeitachse.

Der React-Viewer wird einmalig gebaut (`npm run build`) und über
`python view.py output/` ausgeliefert -- kein laufendes Python nötig
während der Anzeige, kein Backend-Server.

## Architekturüberblick

```
gps_pipeline/
├── __init__.py          # Top-Level-Exporte (process_nmea, process_gpx, …)
├── __main__.py          # CLI-Einstiegspunkt (python -m gps_pipeline)
├── api.py               # High-Level-API-Funktionen
├── config.py            # Alle einstellbaren Parameter
├── README.md            # Übersicht
├── parsing/
│   ├── nmea.py                # NMEA-Datei → Liste von pynmea2-Objekten
│   ├── nmea_to_dataframe.py   # NMEA → Schema A (eine Zeile pro Satz)
│   ├── gpx.py                 # GPX → Schema B
│   ├── kml.py                 # KML (gx:Track) → Schema B
│   └── chart.py               # PNG+TXT-Paare → ChartOverlay (Schritt 5)
├── processing/
│   ├── filter.py              # GPS-Fix-Filter (Schema A)
│   ├── consolidate.py         # Schema A → Schema B
│   ├── enrich.py              # Schema B → Schema C (Distanz, Speed)
│   ├── enrich_terrain.py      # Schema C + DEM → Schema C + terrain_elevation
│   ├── gsv_aggregate.py       # GSV-Sätze aggregieren (für Satellite-View)
│   ├── trim.py                # Track-Trimming (Cut-Ranges)  [Schritt 5]
│   └── synthetic.py           # Synthetic-Track (Zeitachse stauchen) [Schritt 5]
├── visualization/
│   ├── three_d.py             # 3D-Track-Plot
│   ├── satellite_view.py      # Polar-Plot der Satellitenkonstellation
│   └── multi_track.py         # Vergleichs-Visualisierung
├── terrain/
│   └── dem.py                 # GeoTIFF-DEM laden, samplen, vergleichen
├── utils/
│   └── safe_convert.py        # Robuste Type-Konvertierungen
├── dataframe_io/
│   └── feather.py             # DataFrame-Persistierung
└── export/
    ├── json_export.py         # Schema-C → track.json
    ├── dem_lod.py             # GeoTIFF → DEM-LOD-JSONs
    └── chart_export.py        # ChartOverlay → charts.json + PNG-Kopie [Schritt 5]
```

## Datenfluss

```
NMEA-Datei  →  parse → build_df → filter → consolidate → enrich  →  Schema C
                       (Schema A)          (Schema B)
                            ↓
                       visualize_satellites (nutzt GSV-Sätze)

GPX-Datei   →  parse_gpx_file → Schema B → enrich → Schema C

KML-Datei   →  parse_kml_file → Schema B → enrich → Schema C

Schema C + DEM → enrich_terrain_elevation → Schema C mit
                                            terrain_elevation und
                                            track_above_terrain
```

## Schemata

### Schema A (nur bei NMEA)

Eine Zeile pro NMEA-Satz. Spalten u.a.:

- `timestamp_utc` (datetime64[ns, UTC])
- `sentence_type` (category): RMC, GGA, VTG, GSA, GSV
- `talker_id` (category): GP, GL, GA, GB, …
- Spezifische Spalten je Satztyp (`gga_*`, `rmc_*`, `vtg_*`, `gsa_*`, …)
- `gsv_satellites` (object): Liste von Dicts pro GSV-Satz
- Dtypes: konsequent `UInt8`/`Float32`/`category`/`boolean` (alle nullable)

### Schema B (Zwischenstufe, wird normalerweise direkt zu C)

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

In der Visualisierung wird der Track relativ zum DEM positioniert über
`TRACK_Z_OFFSET` in `config.py`. Vier Modi:

- `"auto"` (Default): automatische Diagnose. Bei Flügen (erkannt am Mean-
  Median-Gap > 50 m) wird auf 0 zurückgefallen.
- `"none"` oder `None`: kein Offset, Track wie er ist
- Zahl (z.B. `-36.4`): fester Wert in Metern

### DEM-Auflösung

Adaptive Auflösung über zwei Parameter:

- `DEM_TARGET_PIXEL_SIZE_M = 50` — Ziel-Pixelgröße in Metern
- `DEM_MAX_PIXELS_PER_AXIS = 2000` — harte Obergrenze pro Achse

Das gröbere Downsampling der beiden gewinnt. Bei kleinen DEMs bleibt die
DEM-eigene Auflösung erhalten (keine künstliche Interpolation).

Zusätzlich `DEM_MAX_HTML_MB = 100` als Reservebremse: wenn die geschätzte
HTML-Dateigröße (3 Byte pro Vertex, empirisch ermittelt) das Limit
überschreitet, wird die Auflösung automatisch halbiert.

### Multi-DEM-Handling

Liegen mehrere DEM-Tiles im `data/`-Ordner, werden sie zur Visualisierung
gemerged. Für Diagnose und Sampling (`compare_track_dem`,
`enrich_terrain_elevation`) wird **nicht gemerged**: pro Track-Punkt wird
das passende Tile gesucht. So bleiben die rohen DEM-Werte erhalten (nicht
das geglättete Merge-Bild).

### Padding

Symmetrisch in alle vier Richtungen. Wert: 15% der **kleineren** Bounds-
Spannweite (in Grad). Das macht die Box ausgewogen, ohne in der langen
Achse zu sehr aufzublähen.

### DataFrame-Persistierung

Feather-Format (Arrow IPC v2) via `dataframe_io.feather`:

- Behält alle Dtypes, auch nullable und datetime mit UTC
- `gsv_satellites`-Listen funktionieren
- Schnell zum Schreiben und Lesen
- Nicht für Langzeit-Archivierung (Format kann sich zwischen Arrow-
  Versionen leicht ändern), aber super für temporären Austausch zwischen
  Skripten (z.B. Trim-Workflow in eigenem Projekt)

## Bekannte Einschränkungen

### Datumsgrenze (180° E/W)

Tracks, die die Datumsgrenze überqueren, würden falsche Bounds berechnen.
Praktisch irrelevant für deinen Use-Case, aber sollte man wissen.

### Multi-Constellation-GSV-Sätze

Bei Multi-Constellation-Empfängern (ZED-X20P u.ä.) können GSV-Sätze pro
Konstellation mit minimal verschobenen Timestamps ankommen. Die aktuelle
`visualize_satellites` zeigt nur Gruppen mit exakt gleichem Timestamp.
Bei ersten echten Multi-Constellation-Daten ggf. Toleranz einbauen.

### Lon/Lat-Verzerrung außerhalb des Äquators

Bei 50°N ist 1° Lon ≈ 71 km, 1° Lat ≈ 111 km. Padding wird in **Grad**
gerechnet, nicht in Metern — d.h. 0.6° Padding wirkt in Lon-Richtung
anders als in Lat-Richtung. In der Visualisierung gleicht
`aspectmode='manual'` das wieder aus, aber die rohe Box ist im
Kartesischen leicht asymmetrisch.

## Verwendung

### CLI

```bash
python -m gps_pipeline
```

Erwartet `data/`-Ordner mit `.txt` (NMEA), `.gpx`, `.kml`, optional `.tif`
(DEM). Schreibt nach `output/`.

### Als Bibliothek

```python
from gps_pipeline import (
    process_nmea, process_gpx, process_kml,
    render_visualizations, render_comparison,
)
from gps_pipeline.dataframe_io.feather import save_df, load_df

# Track verarbeiten
df_raw, df_c = process_nmea(Path("track.txt"))

# Visualisieren
render_visualizations(df_c, Path("output"),
                      name_prefix="my_track",
                      df_raw=df_raw,
                      dem_paths=[Path("dem.tif")])

# Persistieren / wieder laden
save_df(df_c, "track.feather")
df_c2 = load_df("track.feather")
```

## React-Viewer (Schritt 3+4) — 19./20. Mai 2026

Der React/TypeScript GPS-Viewer (`gps_viewer/`) wurde in zwei Sessions um
folgende Features erweitert:

### Schritt 3: Farbgebung, Legende, Vorhang, Toggles

- **Plasma-Farbverlauf kontinuierlich** (rank-basiert, nicht diskret):
  `computeRankPositions()` in `colorMap.ts` berechnet t = rank/(N-1) pro
  Punkt, Durchschnittsrang bei Ties, NaN bei null-Werten.
  `plasmaColor(t, alpha)` gibt [r,g,b,a] zurück.
  Workaround: `interpolatePlasma` liefert Hex-Strings (`#cc4778`), nicht
  `rgb(r,g,b)` — `parseRgb()` parst beide Formate.

- **Speed/Höhe-Toggle** (ToggleSwitch.tsx): Generischer Pill-Switch
  `<ToggleSwitch<T>>`, Knopf gleitet mit CSS-Transition.

- **Proportionale Farbskalen-Legende** (ColorLegend.tsx): Ticks an
  Quantil-Grenzen, proportional zum Wertebereich positioniert.
  Iterativer Mindestabstand-Algorithmus (10%) verhindert Überlappungen.

- **Vorhang (Curtain)** sichtbar gemacht:
  SolidPolygonLayer mit `extruded: true` + perpendikulärem EPS-Footprint
  (1e-6 Grad ≈ 11 cm). Hintergrund: earcut trianguliert nur in XY — ein
  senkrechtes Polygon hat Null-XY-Fläche → 0 Dreiecke → unsichtbar.
  Fix: dünner horizontaler Grundriss, `getElevation` extrudiert nach oben.

- **Vorhang-Toggle** (CurtainMode): gleicher Pill-Switch-Stil.

- **json_export.py**: `_detect_track_mode()` Schwelle 30 m → 100 m;
  kein DEM-Fallback. `quantile_breaks.altitude_m` und `points.alt_q_idx`
  exportiert.

### Schritt 4: DEM/Terrain, Z-Scale, InfoPanel

- **DEM-Integration end-to-end**: `useDemLod` lädt Terrain-LODs per Zoom.
  `gridToMesh()` konvertiert DEM-Grid in Meter-Offsets vom Bounds-Center
  (equirektangular: `m_per_lon = 111320 * cos(lat_center_rad)`).
  SimpleMeshLayer nutzt `anchor = [lon_center, lat_center]` als
  `getPosition`-Anker — Mesh-Positionen sind Offsets davon, NICHT Lon/Lat.

- **Terrain sichtbar** (`material: false`): material mit ambient/diffuse
  benötigt LightingEffect in deck.gl; ohne diesen rendert das Mesh schwarz.
  Lösung: `material: false` → Flat-Shading, sichtbares Grau-Terrain.

- **Curtain mit negativem above_terrain** (GPS-Rauschen, −1 m):
  Früher `Math.max(0, top - bot)` → Höhe = 0 → Curtain unsichtbar.
  Jetzt: `base = min(top, bot)`, `height = abs(top - bot)`.

- **Z-Exaggeration konsistent**: `exag(h) = altBase + (h−altBase) * zScale`
  wird in Track, Curtain UND Terrain-Mesh gleich angewendet.
  zScale war zuvor in TrackViewer.tsx als Konstante 15 hart kodiert.

- **ZScaleButtons.tsx**: Pill-Button-Gruppe 1×, 2×, 3×, 5×, 7.5×, 10×;
  gleicher Indigo-Gradient wie ToggleSwitch. Default: 3×.

- **InfoPanel**: neue Felder „Punkt #" (1-basiert, Gesamt) und
  „Höhe ü.Grd" (above_terrain aus DEM). „Höhe" umbenannt in „Höhe MSL".

## Schritt 5 -- Karten-Overlays, Trimming, Synthetic-Tracks (24. Mai 2026)

Drei eng verwandte Features in einer Session:

### 5a -- Karten-Overlays (PNG drapt auf DEM)

Anflugkarten oder beliebige georeferenzierte Bilder lassen sich auf das
DEM-Mesh "drapen" -- die Karte folgt den Höhenkonturen statt flach
darüber zu schweben.

* **Input-Format**: `EDFG.png` + `EDFG.txt` im `data/`-Ordner. Die TXT
  enthält vier Eckkoordinaten in WGS84 (links-oben, rechts-oben,
  links-unten, rechts-unten), je Zeile `lon lat`. Optional
  `elevation_m: 220` als Fallback ohne DEM.
* **Backend**: `parsing/chart.py` parst PNG+TXT-Paare;
  `export/chart_export.py` kopiert die PNGs nach `output/charts/` und
  schreibt `charts.json`.
* **Frontend**: `utils/chartMesh.ts` mit zwei Strategien:
  - **Strategie A (Default, achsenparallele Karten + DEM)**: das
    Chart-Mesh wird aus dem aktiven DEM-LOD-Subgrid gebaut --
    es nutzt **dieselben Vertices wie das Terrain-Mesh**. UV ergibt
    sich aus der relativen Position innerhalb der Karten-Bounds.
  - **Strategie B (Fallback)**: kein DEM oder gedrehte Karte ->
    bilineare Interpolation der vier Ecken, adaptive Subdivision
    (~50 m/Vertex, Cap 256×256, Floor 8×8, override via
    `subdivision: N` in der TXT).
  `layers/chartLayer.ts` rendert das mit `SimpleMeshLayer` und PNG-Textur.

### Bug-Postmortem -- der "Triangulation um 90 Grad gedreht"-Bug

Beim End-to-End-Test (echtes DEM + zwei georeferenzierte PNGs) sind
mehrere subtile Bugs aufgefallen. Reihenfolge der Fixes:

1. **UV-Mapping**: erste Iteration `(u, 1-v)` zeigte das PNG um 180°
   gedreht; zweite `(1-u, v)` nur noch horizontal vertauscht; dritte
   `(u, v)` korrekt. Erkenntnis: `SimpleMeshLayer` sampelt mit
   unflipped U und V relativ zu den HTMLImageElement-Pixeln -- die
   natuerliche Mesh-Iteration (r=0 oben, c=0 links) ist direkt
   kompatibel. **Das PNG selbst muss nicht gedreht/gespiegelt
   werden.**

2. **Mesh-Aufloesung vs. DEM-Aufloesung**: zunaechst nutzte Strategie A
   ein eigenes N×N-Gitter (Cap 256) mit DEM-Höhensampling pro Vertex.
   Bei großen Karten (z.B. 35 km) lag das bei ~140 m/Vertex -- gröber
   als das DEM (Copernicus 30 m). Zwischen Chart-Vertices interpolierte
   das Chart linear, missed dabei aber die feineren DEM-Details. Fix:
   Chart-Mesh verwendet *exakt die DEM-Vertices innerhalb der
   Karten-Bounds* -- identische Auflösung, gleiche Höhenwerte.

3. **Anker-Mismatch**: trotz identischer DEM-Vertices war die Karte um
   ~150 m horizontal gegenüber dem Terrain verschoben. Ursache: Chart
   nutzte den Karten-Mittelpunkt als Anker mit eigenem
   `cos(lat_chart_center)`-Faktor, Terrain nutzte den DEM-Mittelpunkt
   mit `cos(lat_dem_center)`. Bei 0.5° Lat-Differenz ergibt das ~0.6%
   horizontale Verzerrung -- bei 35 km Karte sind das 150 m. Fix:
   Chart verwendet identischen Anker und cos-Faktor wie demMesh
   (DEM-Center).

4. **Der eigentliche "Z-Fighting"-Bug -- 90 Grad gedrehte
   Triangulation**: selbst nach Schritten 1-3 traten an Geländekanten
   dreieckige braune Flecken auf, die so aussahen, als würden die
   DEM-Dreiecke aus der Karte herausragen. **Sie tun es auch -- weil
   die Triangulation um 90 Grad versetzt lief.** Beide Meshes
   verwenden im Index-Buffer die Konvention `tl, bl, tr, br` mit der
   Diagonalen `tl-bl-tr` / `tr-bl-br`, ABER:
   - demMesh iteriert `r=0..n_rows-1` mit `r=0` bei `lat_min` (Süden).
     Damit ist `"tl"` geographisch SW, `"bl"` ist NW. Diagonale: NW-SE.
   - chartMesh Strategie A iterierte ursprünglich `r=r_max..r_min`
     (Norden zuerst), `"tl"` war NW, `"bl"` war SW. Diagonale: SW-NE.

   Die beiden Diagonalen stehen **senkrecht aufeinander**. Selbst bei
   identischen Vertex-Höhen interpolieren die Meshes über
   *verschiedene* Diagonalen -- innerhalb jedes Quads kann die
   Höhendifferenz mehrere Meter erreichen. Das DEM-Dreieck stößt
   dann durch die Karte. Fix: Iterationsreihenfolge in Strategie A
   exakt an demMesh angeglichen (`r_min..r_max`). Die UV-Berechnung
   bleibt geo-basiert und ist iterations-unabhängig, also keine
   Orientierungs-Auswirkung.

Nach diesen vier Fixes ist **keinerlei Z-Lift mehr erforderlich**
(`Z_LIFT_SUBGRID_M = 0`). Chart und Terrain interpolieren über jeden
Punkt zwischen den Vertices bitidentisch -- klassisches Z-Fighting ist
mathematisch unmöglich, die Karte gewinnt durch die spätere Position
in der Layer-Liste (Render-Order-Tiebreak).

Strategie B (Fallback ohne DEM oder bei gedrehten Karten) braucht
weiterhin einen 5 m-Lift, weil sie ein eigenes N×N-Gitter aufspannt und
zwischen Chart-Vertices anders interpoliert als das Terrain.
* **Z-Exaggeration**: identisch zu Terrain/Track verwendet -- die Karte
  bleibt konsistent am Gelände, auch wenn der Z-Scale-Faktor wechselt.
* **UI**: Karten-Toggle erscheint nur wenn `charts.json` Overlays enthält.
  Mehrere Karten gleichzeitig sind unterstützt (z.B. Anflug + Abflug).

Die mathematische "Verzerrung" durch die zusätzliche Mesh-Oberfläche ist
bei typischen Anflugkarten (~3 km Ausdehnung, 30 m Höhenvariation) bei
~5e-5 -- praktisch unsichtbar, aber visuell sieht der Track jetzt
"aufgelegt" statt "schwebend" aus.

### 5b -- Range-Selection (Trimming + Multi-Cut)

Generischer Mechanismus zum Definieren von Index-Bereichen, die aus dem
Track entfernt werden sollen. Drei Anwendungsfälle:

* **Reines Trimming**: `[0..50]` und `[N-30..N-1]` als Cut-Ranges -->
  Track-Anfang und -Ende abschneiden.
* **Zwischenstopp entfernen**: ein einzelner Cut `[200..350]` --> die
  Pause in der Mitte verschwindet.
* **Mehrfach-Cuts**: Anfang/Ende UND mehrere Pausen gleichzeitig.

* **Frontend**: `hooks/useRangeSelection.ts` verwaltet die Liste,
  `components/RangeSelector.tsx` zeigt die Cuts als rote Balken auf einer
  Track-Leiste; jeder Cut hat zwei Drag-Handles und einen Entfernen-Button.
  "+ Cut" fügt einen neuen Cut um die aktuelle Slider-Position ein. "Export"
  lädt eine `ranges.json` herunter.
* **Backend**: `processing/trim.py::trim_track(df, ranges)` schneidet die
  Bereiche aus einem Schema-C-DataFrame. `load_cut_ranges(path)` liest
  die vom Viewer exportierte `ranges.json`.

### 5c -- Synthetic-Tracks (Zeitachse stauchen)

Für Analysen, in denen Pausen "nie passiert sein" sollen (z.B. reine
Fahrzeit-Auswertung einer Autofahrt mit Ladestopps):

* `processing/synthetic.py::create_synthetic_track(df_c, cuts, interp_n=10)`
  entfernt Cut-Punkte UND berechnet pro Cut die natürliche Brückenzeit
  aus geodätischer Distanz zwischen den Cut-Rändern und der mittleren
  Geschwindigkeit der `interp_n` Nachbarpunkte. Alle nachfolgenden
  Zeitstempel werden entsprechend nach vorne geschoben.
* **Markierung**: Neue Spalte `is_synthetic` (True wenn der Zeitstempel
  der Zeile verändert wurde).
* **Schutzmechanismus**: `save_synthetic()` erzwingt das Suffix
  `_synthetic.feather` und schreibt eine Sidecar-Metadaten-Datei
  `_synthetic.meta.json` mit den ursprünglichen Cut-Ranges,
  Erstellungszeit und einer expliziten Warnung, dass GSV-/Satellitendaten
  für diesen Track nicht mehr gültig sind.

### 5d -- Klickbare Track-Punkte für Satellitenauswahl

Bisher ließ sich der aktive Punkt nur über den Slider scrubben. Jetzt
liegt ein unsichtbarer `ScatterplotLayer` (`getFillColor=[0,0,0,0]`,
`pickable: true`) über dem Track. `onHover` setzt direkt `activeIdx` --
InfoPanel, Skyplot und Aktiv-Marker reagieren sofort, ohne dass der
Slider händisch bewegt werden muss.

### 5e -- Hover-Tooltip (Panel/Tooltip/Beide)

Aufbauend auf 5d: der unsichtbare Pickable-Layer treibt jetzt zusätzlich
einen schwebenden Tooltip am Cursor (deck.gl `getTooltip`-Prop). Inhalt
minimal -- Zeit, Geschwindigkeit, Höhe MSL, Höhe ü.Grd. Ein neuer
3-Wege-Pill-Switch `InfoModeButtons` schaltet zwischen:

- **Panel**: rechtsseitiges InfoPanel (Default-Verhalten bis Schritt 4)
- **Tooltip**: nur Floating-Tooltip; Side-Panel wird ausgeblendet (300px
  mehr Bildbreite für den Track), falls auch kein Skyplot dort steht
- **Beide**: gleichzeitig (Default)

Tooltip filtert auf `layer.id === "track-pick"`, damit andere Layers
(Terrain, Chart-Overlays) ihn nicht auslösen.

## TODO / Geplant

- Test mit echten ZED-X20P-Multi-Constellation-Daten
- Satellite-View-Warnung bei `is_synthetic === true` (synthetische Punkte
  haben keine validen Satellitendaten -- UI sollte das anzeigen)
- `ranges.json` direkt vom Viewer an einen kleinen Endpoint in `view.py`
  posten (statt Download/CLI-Roundtrip)
- Vergleichs-Ansicht (zwei Tracks gleichzeitig im React-Viewer)

## Verlauf der Konstanten und Defaults

Hilfreich beim Nachschauen, falls ein Wert in einem Plot nicht stimmt:

| Parameter | Wert | Bedeutung |
|---|---|---|
| `TRACK_Z_OFFSET` | `"auto"` | Höhen-Offset-Modus |
| `DEM_SMOOTH` | `1.0` | Sigma für Gaussian-Smoothing (0 deaktiviert) |
| `DEM_TARGET_PIXEL_SIZE_M` | `50` | Ziel-Pixelgröße in m |
| `DEM_MAX_PIXELS_PER_AXIS` | `2000` | Harte Pixel-Obergrenze |
| `DEM_MAX_HTML_MB` | `100` | HTML-Größen-Reservebremse |
| `DEFAULT_QUANTILES` | `5` | Anzahl Speed-Quantile (in 3D-Plot) |
| `DEFAULT_COLORSCALE` | `"Plasma"` | Plotly-Colorscale |
| `DEFAULT_Z_EXAGGERATION` | `1.0` | Z-Überhöhung im 3D-Plot |

## Workflow-Beispiele

### Karten-Overlay anzeigen

```powershell
# 1. PNG + TXT in data/ ablegen, z.B.:
#    data/EDFG.png         (Anflugkarte)
#    data/EDFG.txt         (4 Eckkoordinaten + optional elevation_m)
# 2. Export
python -c "
from pathlib import Path
from gps_pipeline import process_nmea, export_for_viewer, find_charts
df_raw, df_c = process_nmea(Path('data/track.txt'))
charts = find_charts(Path('data'))
export_for_viewer(df_c, Path('output'), name_prefix='test',
                  df_raw=df_raw, charts=charts)
"
python view.py output
```

### Track trimmen

```powershell
# 1. Im React-Viewer Cuts definieren, "Export" klickt -> ranges.json
# 2. Trimming anwenden
python -c "
from pathlib import Path
from gps_pipeline import load_cut_ranges, trim_track
from gps_pipeline.dataframe_io.feather import load_df, save_df
df = load_df('output/test.feather')
cuts = load_cut_ranges(Path('ranges.json'))
trimmed = trim_track(df, cuts)
save_df(trimmed, 'output/test_trimmed.feather')
"
```

### Synthetic-Track (Pausen "wegtricksen")

```powershell
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
