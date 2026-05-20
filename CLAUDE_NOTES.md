# Arbeitsnotizen für Claude — GPS-Viewer-Projekt

**Zuletzt aktualisiert:** 2026-05-20
**Aktueller Branch:** master
**GitHub:** https://github.com/sebclaude-hub/gps_pipeline

---

## System-Eigenheiten (Windows / PowerShell) — was funktionierte, was nicht

### GitHub / SSH
- **SSH-Authentifizierung schlug fehl** (`Host key verification failed`) obwohl
  `gh auth login` mit SSH durchgelaufen war. Ursache: `known_hosts` war durch
  einen fehlgeschlagenen `ssh-keyscan`-Aufruf (stderr-Mixing in PS 5.1) korrumpiert.
  → **Lösung:** GitHub-Hostkeys manuell als String in `~/.ssh/known_hosts` schreiben
    (die offiziellen Fingerprints von docs.github.com).
- Danach noch `Permission denied (publickey)` weil der SSH-Agent im Terminal-Kontext
  von Claude den Key nicht lädt.
  → **Lösung:** Remote von SSH auf HTTPS umstellen (`git remote set-url origin https://...`)
    und `gh auth setup-git` aufrufen. HTTPS + gh-Token funktioniert zuverlässig,
    SSH ist in diesem Setup zu fragil.
- **`gh` nach Installation nicht gefunden**: PATH wird in laufender PS-Session nicht
  aktualisiert. → Nach jeder Installation neu laden mit:
  `$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")`

### Node.js / npm
- **Node.js war nicht installiert** → `winget install OpenJS.NodeJS.LTS` hat funktioniert.
- **npm.ps1 wurde blockiert** (ExecutionPolicy): `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force` einmalig ausführen.
- **`@`-Zeichen in Paketnamen** (`@deck.gl/core`) wird von PowerShell als Splat-Operator
  missverstanden → Paketnamen **immer in Anführungszeichen**: `npm install --save "@deck.gl/core@^9.1"`.
- **PATH nach Node-Installation**: auch hier nach Installation erst neu laden (s.o.).

### PowerShell allgemein
- **Git-Commit-Message mit Heredoc**: Bash-Syntax `<<'EOF'` funktioniert nicht.
  → PowerShell-Heredoc verwenden: `git commit -m @'...'@` (schließendes `'@` muss
  am Zeilenanfang stehen, kein Einrücken).
- **`&&` Operator**: In PS 5.1 nicht verfügbar → stattdessen `;` oder
  `A; if ($?) { B }` verwenden.
- **`2>&1` auf native Programme**: In PS 5.1 wraps stderr in ErrorRecord-Objekte
  und setzt `$?` auf false, auch wenn Exit-Code 0. Besser stderr weglassen oder
  mit `*>&1` zusammenführen.
- **Unicode in print()-Ausgaben**: Windows-Konsole läuft mit cp1252 — Sonderzeichen
  wie `→`, `⚠`, `×` crashen mit UnicodeEncodeError. Lösung: `$env:PYTHONUTF8 = "1"`
  vor jedem Python-Aufruf setzen, **oder** Sonderzeichen in allen print()-Aufrufen
  durch ASCII-Äquivalente ersetzen (`->`, `!`, `x`). Zweite Option robuster.
  Bereits gefixt in: `filter.py`, `api.py`, `terrain/dem.py`.

### deck.gl (React-Bibliothek)
- **`@deck.gl/react` nicht gefunden** obwohl in package.json eingetragen: Das Paket
  heißt in v9 **`deck.gl`** (Haupt-Paket inkl. React-Bindings), nicht `@deck.gl/react`.
  → `import DeckGL from "deck.gl"` — funktioniert.
- **`OrbitView` falscher Typ**: OrbitView erwartet `target: [x, y, z]` in kartesischen
  Koordinaten, nicht `longitude/latitude`. Für GPS-Daten immer **`MapView`** verwenden —
  der versteht lon/lat nativ und unterstützt 3D-Pitch/Bearing.

### git
- **`dist/` durch `.gitignore` geblockt**: `git add gps_viewer/dist/` schlägt still
  fehl. → `git add -f gps_viewer/dist/` zum Force-hinzufügen.
- **`git config --global` "not in a git directory"**: Tritt nur auf wenn git selbst
  nicht im PATH ist — war ein temporäres PATH-Problem, kein echter Fehler.

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
- **InfoPanel**: Punkt-Info (Höhe, Speed, Fix, HDOP, VDOP, Sats) synchron mit Slider.
- **Kein laufendes Python** nötig während der Anzeige — `python view.py` startet
  einmalig einen simplen HTTP-Server.

---

## Was bereits fertig ist

### Schritt 1 ✅ — Python-Export-Modul
- `gps_pipeline/export/__init__.py`
- `gps_pipeline/export/json_export.py` — Track → `track.json`, GSV → `satellites.json`
- `gps_pipeline/export/dem_lod.py` — DEM → 3 LOD-Stufen als JSON (**neu erstellt
  2026-05-20**, war vorher referenziert aber fehlte im Repo)
- `gps_pipeline/api.py` — `export_for_viewer()` hinzugefügt
- `gps_pipeline/__init__.py` — `export_for_viewer` war nicht exportiert, **nachgetragen**
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

### Schritt 3b ✅ — Kontinuierlicher Farbverlauf + Color-Mode-Toggle (Session 2026-05-20, Teil 2)
- **`json_export.py`**: zusätzlich `points.alt_q_idx[]` und `quantile_breaks.altitude_m`
  exportiert, damit der Viewer zwischen Speed- und Höhen-Färbung umschalten kann.
- **`utils/colorMap.ts`** (neu): kontinuierlicher Plasma-Verlauf via
  `computeRankPositions()` — jeder Punkt bekommt `t = rank(value) / (N-1)` und
  daraus `interpolatePlasma(t)`. Robust gegen Ausreißer.
  **WICHTIG**: `interpolatePlasma` aus d3-scale-chromatic 3.x liefert **Hex-Strings**
  (`#cc4778`), nicht `rgb(...)`. `parseRgb` muss beide Formate parsen, sonst
  fällt alles auf Grau zurück. (War der Bug "alles grau" am Anfang.)
- **`TrackViewer.tsx`**: PathLayer rendert jetzt n-1 Einzel-Segmente (statt eine
  graue Linie) mit individuellen Plasma-Farben. Curtain und Aktiv-Marker teilen
  den gleichen Verlauf. updateTriggers auf `colorMode` damit Toggle live wirkt.
- **`ColorLegend.tsx`**: vertikaler Plasma-Balken + Tickmarks an den Quantil-
  Grenzen. `distributeTicks()` setzt rohe Position = (value-min)/(max-min),
  spreizt aber Lücken < 10% auf 10% (proportional Re-Verteilung der großen
  Lücken). So bleiben Verhältnisse sichtbar und Labels lesbar.
- **`ColorModeToggle.tsx`** (neu): Pill-Switch, Knubbel gleitet mit 180ms
  cubic-bezier-Transition zwischen "km/h" und "Höhe".

### Schritt 3 ✅ (weitgehend) — Curtain-Layer + End-to-End-Test (Session 2026-05-20)
- **`view.py`**: Manifest-Injektion implementiert — `window.__GPS_MANIFEST__` wird
  als inline `<script>` in `index.html` injiziert. Ohne das lädt React keine Terrain-Daten.
- **Logic-Bug gefixt** in `TrackViewer.tsx`: Bedingung war
  `track_mode === "flight" || curtainSegments.length > 0` — letzteres ist immer true.
  Korrigiert auf `track_mode === "flight"`.
- **Z-Exaggeration** (Faktor 15) in `TrackViewer.tsx` und `curtainLayer.ts`:
  `exagAlt = altBase + (alt - altBase) * Z_SCALE`. Betrifft PathLayer (Boden) und
  Vorhang-Segmente (Flug) gleichermaßen — konsistent.
- **InfoPanel** (`src/components/InfoPanel.tsx`, neu): zeigt Zeit, Position, Höhe,
  Speed, Fix-Typ, Satellitenzahl, HDOP, VDOP — synchron mit Slider-Index.
- **HDOP/VDOP/Fix in Schema C**: `consolidate.py` mergt jetzt zusätzlich
  `gga_gps_quality`, `gga_num_sats`, `gga_hdop` aus GGA-Zeilen und
  `gsa_vdop`, `gsa_fix_type` aus GSA-Zeilen (per LEFT JOIN auf timestamp_utc).
  Felder sind optional (Guard gegen fehlende Spalten eingebaut).
- **`json_export.py`**: neue Felder in `points`-Objekt von track.json:
  `fix_quality`, `num_sats`, `hdop`, `vdop`. `_safe_float_list` robuster gegen
  `pandas.NA` (NAType) — vorher TypeError.
- **End-to-End getestet** mit `data/2026-05-02_16-54-51_rx_log.txt`:
  96.656 Nachrichten → 24.138 konsolidierte Punkte, 139 km, Skyplot funktioniert,
  InfoPanel zeigt Werte, Satellitengröße = SNR (kein Zufall!).
- **Curtain-Layer**: Boden jetzt auf 0 m MSL wenn kein Terrain vorhanden (statt
  `altBase`). Curtain wird für **alle** Track-Modi gerendert (nicht mehr flight-only).
  PathLayer bleibt als sichtbare Rückfallebene (1px grau) immer erhalten.
- **Marker-Bug behoben**: `ScatterplotLayer` nutzt jetzt `exagAlt(d.alt)`.
- **ACHTUNG**: Track wird trotz Flug als `"ground"` klassifiziert (→ Bekannte Bugs).

---

## Was noch fehlt

### Bekannte Bugs

- [ ] **Curtain unsichtbar** — auch im Color-Mode noch nicht sichtbar. Vermutung:
  SolidPolygonLayer mit `extruded:false` + 3D-Polygon liegt zwar in einer
  vertikalen Ebene, wird aber evtl. von deck.gl nicht korrekt trianguliert.
  Nächster Schritt: untersuchen ob `extruded:true` mit getElevation/Polygon-Base
  oder ein TriangleLayer-/PolygonsLayer-Ansatz besser passt.


- [x] ~~**`track_mode`-Erkennung falsch**~~ — **angepasst 2026-05-20 (Session 3)**:
  Schwelle in `_detect_track_mode()` von 30 m auf **100 m** über Terrain angehoben.
  100 m absorbieren GPS-Rauschen und DEM-Auflösungsfehler, fangen aber Gleitschirm-
  flüge zuverlässig ein (und schließen Drohnen-Tiefflüge aus). Eine Fallback-
  Heuristik ohne DEM wurde bewusst NICHT eingebaut — ohne Terrain-Daten kann
  Drohne nicht von Gleitschirm unterschieden werden; Nutzer soll DEM bereitstellen.

- [x] ~~**Aktiver-Punkt-Marker** lag auf nicht-exaggerierter Höhe~~ — **behoben**:
  `getPosition` nutzt jetzt `exagAlt(d.alt)`.

### Schritt 4 — Terrain-Integration testen
- [ ] `export_for_viewer()` End-to-End mit echtem DEM-GeoTIFF testen
- [ ] LOD-Wechsel visuell verifizieren (Anti-Flicker)
- [ ] DEM-Mesh Beleuchtung / Shading verbessern (evtl. Höhen-Farbkodierung)
- [ ] Z-Exaggeration und Terrain konsistent: wenn Terrain geladen, muss auch
  terrain_elev in `buildCurtainSegments` exaggeriert werden (bereits implementiert,
  aber ohne echtes DEM noch nicht getestet)

### Schritt 5 — Skyplot vollständig
- [x] Skyplot testen mit echten GSV-Daten ✅ — funktioniert, Größe = SNR
- [ ] Age-Indikator ("GSV-Burst vor X Sekunden") anzeigen

### Schritt 6 — LOD-Automat kalibrieren
- [ ] Zoom-Schwellen (8 / 11) an echten Tracks kalibrieren
- [ ] Prefetch von LOD 1 wenn Zoom 7 erreicht wird

### Schritt 7 — CLI-Integration
- [ ] `__main__.py` um `--export`-Flag erweitern
- [ ] End-to-End-Test: `python -m gps_pipeline --export output/ && python view.py`

### Schritt 8 — Polish
- [ ] Touch-Gesten (Pinch-Zoom)
- [ ] Vergleichs-Ansicht (zwei Tracks gleichzeitig)
- [ ] Hover-Tooltip direkt im 3D-View (zusätzlich zum InfoPanel)

---

## Workflow zum Testen

```powershell
# Im Projektordner, immer mit UTF8:
$env:PYTHONUTF8 = "1"

# 1. Track exportieren
python -c "
from pathlib import Path
from gps_pipeline import process_nmea, export_for_viewer
df_raw, df_c = process_nmea(Path('data/2026-05-02_16-54-51_rx_log.txt'))
export_for_viewer(df_c, Path('output'), name_prefix='test', df_raw=df_raw)
"

# 2. Viewer öffnen (Server läuft bis Strg+C)
python view.py output

# Browser: http://localhost:8765
# Nach Änderungen am Python-Code: Schritt 1 wiederholen, dann F5 im Browser.
# Nach Änderungen am React-Code: npm run build in gps_viewer/, dann F5.
```

---

## Wichtige technische Details

### deck.gl Setup
- Version: 9.3.x (React 19, Vite 8, TypeScript 6)
- `MapView` (nicht OrbitView!) — OrbitView erwartet kartesische `target`-Koordinaten
- `SolidPolygonLayer` mit `extruded: false` und direkten 3D-Lon/Lat/Alt-Koordinaten
- `SimpleMeshLayer` für Terrain (positions/indices aus `gridToMesh()`)
- Z-Exaggeration: `Z_SCALE = 15` in `TrackViewer.tsx`, Konstante oben in der Datei
  — bei Bedarf einfach anpassen

### JSON-Schema (track.json)
Spaltenorientiert: `points.lat[]`, `points.lon[]`, `points.alt[]`, etc.
Quantil-Index vorberechnet: `points.speed_q_idx[]` (int8, 0..n-1, -1=NaN).
Timestamps als Unix-ms: `points.timestamp_ms[]`.
`meta.track_mode`: `"flight"` wenn median(track_above_terrain) > 30 m.
Neu: `points.fix_quality[]`, `points.num_sats[]`, `points.hdop[]`, `points.vdop[]`.

### LOD-Dateinamen
`{name_prefix}_dem_lod0.json` (fein, ~10 m/px), `_lod1.json` (mittel, ~50 m/px),
`_lod2.json` (grob, ~200 m/px).
Der `dem_prefix` steht in `manifest.json` und wird via `window.__GPS_MANIFEST__`
an die React-App übergeben. Die Injektion passiert in `view.py → _serve_file`.

### Satelliten-Skyplot
- Punktgröße = SNR (Signal-Rausch-Verhältnis), Formel: `r = clamp(snr/6, 3, 10)`
- Farbe nach Konstellation: GP=hellblau, GL=grün, GA=orange, GB=rosa
- Synchronisation: `burst_idx_by_track[talker][track_idx]` → Index in `bursts_by_talker`

---

## Nicht ändern

- `history/` — Planungs-Docs, keine aktiven Dateien
- `gps_pipeline/visualization/` — bleibt als Fallback für HTML-Output
- Die bestehende `render_visualizations()`-API in `api.py` bleibt erhalten
