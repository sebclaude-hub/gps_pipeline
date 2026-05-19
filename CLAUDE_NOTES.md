# Arbeitsnotizen für Claude — GPS-Viewer-Projekt

**Zuletzt aktualisiert:** 2026-05-19
**Aktueller Branch:** master
**GitHub:** https://github.com/sebclaude-hub/gps_pipeline

---

## Projektziel

Die bestehenden Plotly-HTML-Ausgaben durch eine React/TypeScript-App mit
deck.gl ersetzen. Gründe: HTML-Dateien werden bei großen DEMs zu groß und
hängen den Browser auf. Zusätzlich: Level-of-Detail (LOD) für Terrain, damit
bei langen Flügen (z.B. Rom→Frankfurt) Details in den Alpen erhalten bleiben.

Kernfeatures:
- **Vorhang-Effekt**: vertikale Flächen vom Track bis zum Terrain, Plasma-
  Farbkodierung nach Geschwindigkeits-Quantilen. Für Flüge ausgefüllt,
  für Boden-Tracks kollabiert zur Linie.
- **LOD-Terrain**: 3 vorberechnete Auflösungsstufen (200/50/10 m/px), React
  wählt je nach Zoom die passende — kein Backend nötig.
- **Skyplot**: SVG-Polarplot synchronisiert mit Track-Slider.
- **Kein laufendes Python** nötig während der Anzeige — `python view.py` startet
  einmalig einen simplen HTTP-Server.

---

## Was bereits fertig ist

### Schritt 1 ✅ — Python-Export-Modul
- `gps_pipeline/export/__init__.py`
- `gps_pipeline/export/json_export.py` — Track → `track.json`, GSV → `satellites.json`
- `gps_pipeline/export/dem_lod.py` — DEM → 3 LOD-Stufen als JSON
- `gps_pipeline/api.py` — `export_for_viewer()` hinzugefügt
- `view.py` — HTTP-Server, öffnet Browser automatisch

### Schritt 2 ✅ — React-App Skeleton + Vorhang-Layer
- `gps_viewer/` — Vite + React 19 + TypeScript 6 (npm run build → dist/)
- `src/types.ts` — alle TypeScript-Interfaces
- `src/api/` — loadTrack, loadSatellites, loadDemLod, loadManifest
- `src/hooks/` — useTrackData, useSatelliteData, useDemLod (mit Anti-Flicker)
- `src/layers/curtainLayer.ts` — SolidPolygonLayer-basierter Vorhang
- `src/layers/terrainLayer.ts` — SimpleMeshLayer für DEM-Mesh
- `src/components/TrackViewer.tsx` — deck.gl MapView
- `src/components/SkyPlot.tsx` — SVG-Polarplot
- `src/components/TrackSlider.tsx` — Slider + Play/Pause
- `src/components/ColorLegend.tsx` — Quantil-Legende
- `src/utils/` — quantile.ts, demMesh.ts, formatters.ts
- `dist/` ist committed (kein Node-Build nötig für Endnutzer)

---

## Was noch fehlt (Schritte 3–8)

### Schritt 3 — Curtain-Layer verfeinern
- [ ] `dem_lod.py` fehlt noch im Git (war noch nicht committed — prüfen!)
- [ ] Testen mit echten Track-Daten (NMEA-File)
- [ ] Ground-Track: `PathLayer` statt Vorhang sicherstellen
- [ ] Vorhang-Transparenz und Rückseite korrekt rendern (deck.gl `side: 'both'`?)

### Schritt 4 — Terrain-Integration testen
- [ ] `export_for_viewer()` End-to-End mit echtem DEM-GeoTIFF testen
- [ ] LOD-Wechsel visuell verifizieren (Anti-Flicker)
- [ ] DEM-Mesh Beleuchtung / Shading verbessern (evtl. Höhen-Farbkodierung)

### Schritt 5 — Skyplot vollständig
- [ ] Skyplot testen mit echten GSV-Daten
- [ ] Age-Indikator ("GSV-Burst vor X Sekunden") anzeigen

### Schritt 6 — LOD-Automat kalibrieren
- [ ] Zoom-Schwellen (8 / 11) an echten Tracks kalibrieren
- [ ] Prefetch von LOD 1 wenn Zoom 7 erreicht wird

### Schritt 7 — CLI-Integration
- [ ] `__main__.py` um `--export`-Flag erweitern
- [ ] `view.py` Manifest-Injektion als inline `<script>` in index.html
  (aktuell: `window.__GPS_MANIFEST__` ist im Code referenziert aber noch
  nicht befüllt — view.py muss das beim Ausliefern von index.html einfügen)
- [ ] End-to-End-Test: `python -m gps_pipeline --export output/ && python view.py`

### Schritt 8 — Polish
- [ ] InfoPanel: Hover-Tooltip mit Speed/Höhe/Zeit im 3D-View
- [ ] Touch-Gesten (Pinch-Zoom)
- [ ] Vergleichs-Ansicht (zwei Tracks gleichzeitig)

---

## Wichtige technische Details

### deck.gl Setup
- Version: 9.3.x (React 19, Vite 8, TypeScript 6)
- `MapView` (nicht OrbitView!) — OrbitView erwartet kartesische `target`-Koordinaten
- `SolidPolygonLayer` mit `extruded: false` und direkten 3D-Lon/Lat/Alt-Koordinaten
- `SimpleMeshLayer` für Terrain (positions/indices aus `gridToMesh()`)

### Kritische offene Stelle: `window.__GPS_MANIFEST__`
`App.tsx` liest `window.__GPS_MANIFEST__?.dem_lods` und `dem_prefix`.
Dieses Objekt muss von `view.py` als inline `<script>` in die `index.html`
injiziert werden, wenn die Datei ausgeliefert wird. Aktuell ist das NOCH NICHT
implementiert — `view.py` liefert `index.html` statisch aus, ohne Injektion.

**Fix in `view.py` → `_serve_file`:**
```python
if file_path.name == "index.html":
    html = file_path.read_text(encoding="utf-8")
    manifest = json.loads((self.output_dir / "manifest.json").read_text())
    script = f'<script>window.__GPS_MANIFEST__={json.dumps(manifest)};</script>'
    html = html.replace("</head>", script + "</head>")
    data = html.encode("utf-8")
    # ... rest wie bisher
```

### JSON-Schema (track.json)
Spaltenorientiert: `points.lat[]`, `points.lon[]`, `points.alt[]`, etc.
Quantil-Index vorberechnet: `points.speed_q_idx[]` (int8, 0..n-1, -1=NaN).
Timestamps als Unix-ms: `points.timestamp_ms[]`.
`meta.track_mode`: `"flight"` wenn median(track_above_terrain) > 30 m.

### LOD-Dateinamen
`{name_prefix}_dem_lod0.json` (fein), `_lod1.json` (mittel), `_lod2.json` (grob).
Der `dem_prefix` steht in `manifest.json` und wird via `window.__GPS_MANIFEST__`
an die React-App übergeben.

---

## Workflow zum Testen (sobald Schritt 7 fertig)

```bash
# 1. Track exportieren
python -c "
from pathlib import Path
from gps_pipeline import process_nmea, export_for_viewer
df_raw, df_c = process_nmea(Path('data/nmea_testlog.txt'))
export_for_viewer(df_c, Path('output'), name_prefix='test', df_raw=df_raw)
"

# 2. Viewer öffnen
python view.py output/
```

---

## Nicht ändern

- `history/` — Planungs-Docs, keine aktiven Dateien
- `gps_pipeline/visualization/` — bleibt als Fallback für HTML-Output
- Die bestehende `render_visualizations()`-API in `api.py` bleibt erhalten
