# GPS-Pipeline — Stand 20. Mai 2026

Dieses Dokument beschreibt den aktuellen Stand nach der mehrtägigen Refactor-
und Ausbau-Session. Es ersetzt den älteren `refactor_plan.md` (Stand 4. Mai),
der nur den ursprünglichen Plan enthält und seitdem viele Details nicht mehr
widerspiegelt.

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
│   └── kml.py                 # KML (gx:Track) → Schema B
├── processing/
│   ├── filter.py              # GPS-Fix-Filter (Schema A)
│   ├── consolidate.py         # Schema A → Schema B
│   ├── enrich.py              # Schema B → Schema C (Distanz, Speed)
│   ├── enrich_terrain.py      # Schema C + DEM → Schema C + terrain_elevation
│   └── gsv_aggregate.py       # GSV-Sätze aggregieren (für Satellite-View)
├── visualization/
│   ├── three_d.py             # 3D-Track-Plot
│   ├── satellite_view.py      # Polar-Plot der Satellitenkonstellation
│   └── multi_track.py         # Vergleichs-Visualisierung
├── terrain/
│   └── dem.py                 # GeoTIFF-DEM laden, samplen, vergleichen
├── utils/
│   └── safe_convert.py        # Robuste Type-Konvertierungen
└── dataframe_io/
    └── feather.py             # DataFrame-Persistierung
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

## TODO / Geplant

- Track-Trimming-Werkzeug (in separatem Projekt)
- Test mit echten ZED-X20P-Multi-Constellation-Daten
- Satellite-View-Animation (Klick im Track-Plot → Satellitenkonstellation
  zu diesem Zeitpunkt anzeigen)

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
