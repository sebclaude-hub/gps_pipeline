# Arbeitsnotizen für Claude — GPS-Viewer-Projekt

**Zuletzt aktualisiert:** 2026-05-26 abend
**Aktueller Branch:** master
**GitHub:** https://github.com/sebclaude-hub/gps_pipeline

---

## Architektur-Stand nach Schnittanweisungs-Refactor (26. Mai 2026)

Der grosse Refactor zum Schnittanweisungs-Workflow ist durch, getestet
und gepusht (siehe `CHANGES.md` Schritt 7). Die folgende Notiz
beschreibt den Architektur-Stand nach diesem Refactor zur schnellen
Orientierung in zukuenftigen Sessions.

### Was ist im Code (Schritte 1-7 + Folge-Korrekturen A/B/C/D)

**Backend — neue Module:**
- `gps_pipeline/parsing/cut_config.py` — `CutConfig`, `CutSpec`,
  `load_cut_config`, `find_cut_config`. Validierung inkl. `z_offset_m`.
  `force_edge_trim()` zwingt Edge-Cuts (start=0 oder end=N-1) auf
  Modus `"trim"`.
- `gps_pipeline/processing/apply_cut_config.py` — `apply_cut_config(
  df_raw, df_c, config) -> (df_raw, df_c, derivation)`. Behandelt
  alle drei Modi auf BEIDEN Schemata (df_raw via Timestamps gefiltert
  und mit-geshiftet). Edge-Detection und Derivation-Bau (Banner-Dict).

**Backend — geänderte Funktionen:**
- `api.apply_sidecar_cuts(source_path, df_raw, df_c) -> (df_raw, df_c,
  derivation, z_offset_m)` (4-tuple!) — schaut neben source_path nach
  `<basename>.cuts.json`, wendet an. Wenn nur z_offset gesetzt ist,
  baut sie ein `derivation = {"type": "z_offset", ...}` für Banner.
- `api.export_for_viewer` — Parameter `z_offset_mode` ENTFERNT;
  ersetzt durch `suggested_z_offset: float` (Default 0). Kein
  Auto-Offset mehr — Backend rührt Track-Höhen nicht mehr an.
- `api.render_visualizations` — `z_offset_mode` ebenfalls weg, immer 0.
- `export.json_export.export_track_json` — neuer Parameter `source_file:
  str` (in `meta.source_file` exportiert).

**Backend — entfernt:**
- `gps_pipeline/apply_cuts.py` (CLI obsolet)
- `gps_pipeline/processing/trim.py` (Logik in apply_cut_config)
- `gps_pipeline/processing/synthetic.py` (dito)

**`__main__.py` — neue Logik pro Track:**
1. `process_*(path)` — wie bisher
2. `apply_sidecar_cuts(path, df_raw, df_c)` — sucht und wendet an
3. `render_visualizations(...)` — Plotly-HTML in `output/`
4. `export_for_viewer(..., output_dir=output/<prefix>/,
   source_file=path.name, suggested_z_offset=z_offset)` — pro Track
   ein eigener Unterordner (sonst überschreibt sich `track.json`)

**Frontend:**
- `useRangeSelection` — `CutMode = "trim" | "gap" | "synthetic"`,
  per-Cut-Mode-State, globaler `setMiddleMode`, Edge-Auto-Detection
  (start=0/end=N-1 → trim forciert, auch beim Dragging).
- `RangeSelector` — Pill-Switch "Lücke / Zeit verschieben", Farben
  je Modus (rot/grün/blau, Schraffur für Edge-Trim). Export schreibt
  `<source_file>.cuts.json` mit optionalem `z_offset_m`-Feld.
  Export-Button aktiv wenn (Cuts > 0) OR (zOffset != 0). Disabled
  mit Tooltip wenn `meta.source_file` fehlt.
- `TrackViewer` — Cut-Paths-PathLayer farbcodiert pro Modus.
- `DerivationBanner` — drei Severities:
  * `null` (nur trim) → kein Banner
  * `info` (gap, oder z_offset_only) → blau-grau, ⓘ
  * `warn` (synthetic, oder Legacy trimmed) → bernstein/rot, ⚠
  Synthetic gewinnt visuell bei Misch-Cuts. Z-Offset-Hinweis wird
  bei allen Banner-Typen als Zusatztext eingeblendet wenn != 0.
- `App.tsx` reicht `meta.source_file` und `zOffset` an RangeSelector.

### Wichtige Detail-Entscheidungen

- **Subdir pro Track**: `__main__.py` schreibt Viewer-Output in
  `output/<prefix>/track.json`, NICHT `output/track.json`. Sonst
  würden mehrere Tracks die track.json gegenseitig überschreiben.
- **`python view.py output/<prefix>/`** ist jetzt der Standard-Aufruf.
  `python view.py output` (ohne Subdir) gibt eine Warnung und findet
  keine manifest.json.
- **z_offset ist REINE ANZEIGE.** Backend rührt Track-Höhen nicht an
  (`enrich_terrain_elevation` mit `track_z_offset=0.0`). Der Wert
  wandert nur in `meta.suggested_z_offset_m`, der Viewer-Slider
  startet damit.
- **Wort "Sidecar"** wurde aus User-facing Texten (README,
  ARCHITECTURE, CHANGES, Viewer-Hint-Popup) entfernt. Stattdessen
  "Schnittanweisungen" / "Datei neben der Quelldatei". Interne
  Funktionsnamen (`apply_sidecar_cuts`, `find_cut_config`) bleiben.

### E2E-Test bestanden

Test-Datei `data/2026-05-02_16-54-51_rx_log.txt.cuts.json` enthält
**alle Sonderfälle gleichzeitig**:
- 2 trim-Cuts (Edge)
- 1 gap-Cut bei 5000..6000
- 1 synthetic-Cut bei 12000..13000 (Pause 155s → Bridge 157s → -2s)
- `z_offset_m: 7`

Ergebnis nach `python -m gps_pipeline`:
- 24138 → 19136 Punkte (5002 entfernt)
- df_raw 80003 → 63486 (Schema A korrekt über Timestamps gefiltert)
- satellites.json: **3019 Bursts erhalten** (Sats werden NICHT mehr
  verworfen wie früher im Synthetic-Pfad)
- meta.source_file = "2026-05-02_16-54-51_rx_log.txt" ✓
- meta.suggested_z_offset_m = 7.0 ✓
- derivation.type = "synthetic", severity = "warn",
  z_offset_m = 7.0, n_trim_cuts=2, n_gap_cuts=1, n_synthetic_cuts=1 ✓
- Severity-Precedence-Check: nur-trim→null, nur-gap→info, mix→warn ✓
- Z-offset-only-Pfad (kein Cut): derivation.type = "z_offset", info ✓

### Letzter UI-Probelauf-Bug (behoben)

User startete `python view.py output` (ohne Subdir). Dort lag eine
alte `output/track.json` (mit `source_file: null`) aus einem früheren
Test-Lauf. Viewer lud die → "Quelldatei unbekannt", Export disabled.
**Lösung:** alte Top-Level-Dateien in `output/` aufgeräumt. Korrekter
Aufruf ist `python view.py output/nmea_2026-05-02_16-54-51_rx_log`.

### Nächster Schritt morgen

1. Diese Notiz lesen
2. UI-Probelauf bestätigen: `python view.py
   output/nmea_2026-05-02_16-54-51_rx_log`
   - Banner rot, "Synthetic-Cut aktiv", Hinweis "+7.0 m verschoben"
   - Cut-Balken farbig (rot-schraffiert / grün / blau)
   - Z-Slider startet bei +7m, nicht 0
   - Pill-Switch "Lücke / Zeit verschieben" funktioniert
   - Export-Button beschriftet `Export (z=+7.0m)`
3. Wenn alles passt: **EINEN Commit für das ganze Refactor** machen
   und pushen. Commit-Message muss die 7 Schritte + die 3 Folge-
   Korrekturen (A/B/C) bündeln.

### Optional (für später, NICHT jetzt)

- **`view.py` Auto-Discovery**: wenn `output_dir/manifest.json` fehlt
  aber `output_dir/<subdir>/manifest.json` existiert, automatisch
  dorthin routen. Wäre user-freundlicher als der jetzige
  Subdir-Zwang.
- **GPX/KML-Pipeline**: bisher nur NMEA real E2E-getestet. GPX/KML-
  Pfad ist im Code parallel zu NMEA, sollte aber theoretisch
  funktionieren (df_raw=None, derivation ohne Sats).
(TRACK_Z_OFFSET und `compare_track_dem` wurden in Schritt E1
vollstaendig entfernt -- der React-Viewer bringt einen Z-Slider mit
und Schnittanweisungen koennen einen vorgeschlagenen Offset mit-
liefern. Der `track_z_offset`-Parameter in `enrich_terrain_elevation`
und `visualize_3d` bleibt als manueller Override fuer den Plotly-Pfad.)

---

## ⏸ ARCHIV: SESSION-RESUMPTION 25. Mai (Plan VOR der Implementation)

**Diese Notiz beschrieb den Plan, der heute (26. Mai) abgearbeitet
wurde.** Hier zur historischen Nachvollziehbarkeit der ursprünglichen
Entscheidungen aufbewahrt. Stand des Codes oben spiegelt die
abgeschlossene Umsetzung wider.

### Diskutierter Stand vor der Pause

Die letzten Iterationen (Schritt 6a-f) sind alle gepusht. Was wir am
25. Mai abend besprochen haben, ist eine größere Architektur-Änderung
am Cut/Trim/Synthetic-Workflow. **Es ist NICHTS davon im Code** — nur
der Plan steht hier.

### Drei einvernehmlich getroffene Entscheidungen

1. **Satelliten in Synthetic-Mode behalten** — nicht mehr wegwerfen.
   GSV-Bursts werden analog zu den Track-Timestamps mit-verschoben.
   Der Banner kennzeichnet das.

2. **Banner auch im Gap-Mode**, aber mit Info-Severity:
   - Nur Trim (Rand) → kein Banner
   - Gap (Mitte ohne Zeit-Shift) → ⓘ blau-grau: "Lücke(n) im Track,
     Geschwindigkeit dort unzuverlässig"
   - Synthetic (Mitte mit Zeit-Shift) → ⚠ rot: "Zeitstempel verändert,
     Sats unter verschobenem Zeitstempel"
   - Bei Mischung gewinnt strengere Severity (Synthetic > Gap > nichts)

3. **Sidecar-Schnittanweisung statt apply_cuts-CLI:**
   - `data/<basename>.cuts.json` neben der Quelldatei
   - `__main__.py` erkennt die Sidecar-Datei nach `process_*` und
     wendet Cuts an
   - `apply_cuts.py` CLI **wird ersatzlos entfernt**
   - Output-Name bleibt gleich (KEIN `_trimmed`-Suffix) — die
     `cuts.json` ist Teil der Quelldaten, der Track unter dem normalen
     Namen ist eben der getrimmte
   - Cuts deaktivieren: cuts.json umbenennen
     (`<basename>.cuts.json.disabled`) → **muss in die README**

### Format der `<basename>.cuts.json`

```json
{
  "source": "2026-05-02_16-54-51_rx_log.txt",
  "n_points_reference": 24138,
  "cut_ranges": [
    {"start": 0,     "end": 49,    "mode": "trim"},
    {"start": 200,   "end": 350,   "mode": "synthetic"},
    {"start": 600,   "end": 700,   "mode": "gap"},
    {"start": 24100, "end": 24137, "mode": "trim"}
  ],
  "created_at": "2026-05-25T17:30:00Z"
}
```

- Mode `"trim"` wird vom System für Edge-Cuts (start=0 oder end=N-1)
  **immer forciert**, egal was der Viewer schickt
- Middle-Cuts kriegen `"synthetic"` oder `"gap"` je nach **globalem
  Toggle zum Export-Zeitpunkt** im Viewer
- User möchte **keinen Mischbetrieb** in der UI (ein globaler Toggle
  für ALLE Middle-Cuts), aber das **Datenformat soll per-Cut-Mode**
  stützen für spätere Flexibilität

### Geplante Implementierungs-Reihenfolge

1. **Format & Sidecar-Detection**
   - `gps_pipeline/parsing/cut_config.py` für Lesen/Validieren der `.cuts.json`
   - `meta.source_file` ins JSON-Export (Basename der Quelldatei)

2. **Apply-Logik**
   - Neues Modul `gps_pipeline/processing/apply_cut_config.py`
   - Funktion: `apply_cut_config(df_raw, df_c, config) → (df_raw_new, df_c_new, derivation)`
   - Behandelt alle drei Modi auf beiden DataFrames
   - **Synthetic**: time-shift wie in `create_synthetic_track`, aber
     JETZT auch df_raw mit-shiften (GSV-Bursts)
   - **Gap**: Zeilen entfernen, Timestamps unverändert
   - **Trim**: Zeilen entfernen, Timestamps unverändert
   - **Edge-Detection**: start==0 oder end==N-1 → forciert Mode "trim"
   - **Derivation-Output**:
     - Pure trim only → `None`
     - Any gap → `{type: "gap", source_name, n_gap_cuts, ...}`
     - Any synthetic (auch in Mischung) → `{type: "synthetic",
       source_name, n_synthetic_cuts, total_time_shift_s, warning}`

3. **Pipeline-Integration**
   - `__main__.py`: nach `process_nmea/gpx/kml` nach
     `<basename>.cuts.json` suchen, `apply_cut_config` aufrufen,
     Ergebnis an Export weitergeben
   - `api.export_for_viewer`: `derivation`-Param schon vorhanden
     (Schritt 6f), kann weiter genutzt werden
   - Output-Naming: gleicher Name wie ohne Cuts (NICHT `_trimmed`)

4. **`apply_cuts.py` weg + README-Update**
   - Datei `gps_pipeline/apply_cuts.py` löschen
   - README Workflow 2 komplett umschreiben: nur noch Viewer-Export +
     Datei nach `data/` verschieben + erneutes `python -m gps_pipeline`
   - **Hinweis "Cuts deaktivieren durch Umbenennen"** in README aufnehmen
   - `gps_pipeline/__init__.py` aufräumen (apply_cuts-Verweise weg)
   - CHANGES.md: Schritt 7 mit der ganzen Architektur-Reform

5. **Frontend**
   - `useRangeSelection`: jeder Cut bekommt
     `mode: "trim" | "gap" | "synthetic"`
   - Edge-Auto-Detection im Hook: start=0 / end=N-1 → mode="trim",
     egal was global gesetzt ist
   - Globaler Toggle "Middle-Mode" in RangeSelector:
     Pill-Switch "Lücke / Zeit verschieben" — wirkt auf alle Middle-Cuts
   - Farbcodierung der Cut-Bars:
     - **Trim** (rot mit Schraffur, wie jetzt)
     - **Gap** (grün)
     - **Synthetic** (blau)
   - Bei Edge-Cuts bleibt Schraffur, Farbe wie für Mode (also blau-
     schraffiert wenn Sync-Mode aktiv und Cut zufällig auch Edge ist —
     aber Edge erzwingt Trim, also rot-schraffiert)
   - Export-Button schreibt `<source_basename>.cuts.json` Format wie oben

6. **Banner-Severity**
   - `DerivationBanner`: drei Stile (kein / info / warn)
   - `describe()`-Funktion ausbauen für Gap-Variante
   - Bei mehreren Mode-Vorkommen die strengere wählen

7. **End-to-End-Test**
   - Beispiel-Track mit Trim + Gap + Synthetic Cuts
   - Verifizieren: Sats werden im Synthetic-Mode mit-verschoben
   - Verifizieren: Banner erscheint korrekt bei jeder Kombination
   - Verifizieren: VTG-Speed bei Gap-Lücken realistisch angezeigt

**Geschätzte Dauer: 3–4 Stunden.** Alles in EINEM Commit am Ende.

### Wichtige Subtilitäten zum Mitnehmen

- **Mode "trim" wird vom System forciert für Edge-Cuts**, egal was der
  User-Toggle sagt. Der Frontend-Toggle gilt nur für Middle-Cuts.
- **Banner zeigt strengste Mode-Severity** wenn mehrere vorhanden.
- **Schema-A-Filtering für df_raw**: über Timestamps, nicht über Index.
  Schema-A hat eine Zeile pro NMEA-Satz, Schema-C eine pro Timestamp.
  Mapping: für jeden Cut in df_c (Schema-C-Index lo..hi) die
  Timestamp-Range nehmen (`ts[lo]..ts[hi]`) und df_raw-Zeilen in diesem
  Zeit-Intervall droppen. Bei Synthetic: alle df_raw-Zeilen mit
  `ts > hi_ts` kriegen denselben Time-Shift wie das df_c.
- **VTG bei Gap-Lücken**: erste `speed_kmh` nach der Lücke verwenden
  (statt `dist/Δt`) für die Geschwindigkeitsanzeige in der Lücke.
  Implementation-Detail eher im Viewer-Render-Code als im Backend.
- **`create_synthetic_track` und `save_synthetic`** aus Schritt 5c
  werden vermutlich obsolet — die Logik wandert nach
  `apply_cut_config.py`. Vorher prüfen ob noch jemand sie importiert.

### Was BLEIBT (Schritte 5-6f sind durch)

Alles bis und inklusive Commit `3af5d33` ist fertig und gepusht:
- Schritt 5 (Charts, Cut-UI, Trim-CLI apply_cuts, Synthetic-Backend,
  klickbarer Track, Tooltip)
- Schritt 6a-f (Cut-Polish, DEM-Offset, Slider, Export-Hint,
  cut_ranges.json + Derivation-Banner v1)

Der jetzige Refactor ersetzt im Wesentlichen die Architektur aus
Schritt 6c (apply_cuts-CLI) und 6f (cut_ranges.json + Banner).

### Start morgen

Wenn der User Tag-2 wieder reinkommt:
1. Diese Notiz lesen (wir sind hier)
2. Bestätigen lassen, dass Plan noch gilt
3. Bei Schritt 1 (`parsing/cut_config.py`) starten
4. Schritt für Schritt durch, eine Commit am Ende

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

### Schritt 5 ✅ — Karten-Overlays, Trimming, Synthetic-Tracks, klickbarer Track (Session 2026-05-24)

Vier Features in einer Opus-4.7-Session implementiert. Details siehe
`CHANGES.md` Sektion "Schritt 5".

**5a -- Chart-Overlays (PNG drapt auf DEM):**
- Backend: `gps_pipeline/parsing/chart.py`, `gps_pipeline/export/chart_export.py`
- Frontend: `utils/chartMesh.ts`, `layers/chartLayer.ts`,
  `api/loadCharts.ts`, `hooks/useCharts.ts`
- Format: `data/<name>.png` + `data/<name>.txt` mit 4 Eckkoordinaten
  (`lon lat` pro Zeile, Reihenfolge TL/TR/BL/BR). Optional `elevation_m: 220`,
  optional `subdivision: N` als Mesh-Override.
- Manifest: zusätzlicher `charts: "charts.json" | null`-Eintrag.
- Toggle erscheint nur wenn Overlays geladen sind; mehrere PNGs gleichzeitig
  möglich (z.B. Anflug + Abflug).
- Wichtig: Z-Exaggeration (altBase, zScale) MUSS in `buildChartMesh()`
  identisch zu Terrain/Track sein, sonst schwebt die Karte weg.

**Wichtige Lehren aus dem E2E-Test (siehe Bug-Postmortem in CHANGES.md):**
- Das PNG selbst braucht KEINE manuelle Drehung/Spiegelung. UV-Mapping
  `(u, v)` direkt aus geographischer Position genuegt.
- SimpleMeshLayer sampelt Texturen mit unflipped U und V relativ zu
  HTMLImageElement-Pixeln.
- Wenn zwei SimpleMeshLayer-Meshes deckungsgleich sein sollen, muessen
  **drei** Dinge uebereinstimmen:
    1. Vertex-Positionen
    2. Anker + cos(lat)-Faktor (NICHT pro Mesh neu berechnen)
    3. Triangulation -- inkl. der gleichen Iterationsreihenfolge
       (sonst stehen die Diagonalen senkrecht aufeinander, auch wenn
        die Index-Reihenfolge wortgleich aussieht).
- Strategie A in chartMesh.ts macht das jetzt -- Z-Lift = 0 reicht.
- Strategie B (Fallback) braucht 5 m Z-Lift wegen unterschiedlicher
  Interpolation gegen Terrain-Mesh.

**5b -- RangeSelector (Trimming + Multi-Cut):**
- Frontend: `hooks/useRangeSelection.ts`, `components/RangeSelector.tsx`
- Cut-Ranges als rote Balken mit zwei Drag-Handles über einem eigenen
  Track (über dem normalen Slider). "+ Cut" / "Reset" / "Export"-Buttons.
- Export lädt `ranges.json` herunter; das Python-CLI nutzt sie.
- Backend: `gps_pipeline/processing/trim.py::trim_track()` + `load_cut_ranges()`.

**5c -- Synthetic-Tracks (Zeitachse stauchen):**
- Backend: `gps_pipeline/processing/synthetic.py`
- Pro Cut: erwartete Brückenzeit = geodetic(dist_vor, dist_nach) / avg_kmh
  der `interp_n` Nachbarpunkte. Nachfolgende Timestamps werden um die
  Differenz vorgeschoben.
- Spalte `is_synthetic` markiert Zeilen mit verschobenem Timestamp.
- `save_synthetic()` erzwingt `_synthetic.feather`-Suffix + Sidecar-
  `.meta.json` mit Warnung "GSV-Daten nicht gültig".

**5d -- Klickbarer Track:**
- Unsichtbarer pickbarer `ScatterplotLayer` über dem Track in
  `TrackViewer.tsx`. `onHover` setzt `activeIdx`. Synchronisiert
  InfoPanel/Skyplot/Marker ohne Slider-Bedienung.

**5e -- Hover-Tooltip:**
- `getTooltip` in TrackViewer mit Filter auf `layer.id === "track-pick"`.
- `InfoModeButtons` (Panel/Tooltip/Beide), Default "Beide".
- Im reinen Tooltip-Modus + ohne Satellitendaten wird das 300px Side-Panel
  komplett ausgeblendet (mehr Bildbreite fuer den Track).

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

- [x] ~~**Curtain unsichtbar**~~ — **behoben 2026-05-20 (Session 3, Teil 2)**:
  SolidPolygonLayer trianguliert das Polygon in 2D (XY) und ignoriert Z. Ein
  vertikales Quad mit identischem (lon,lat) für top und bot kollabiert zu
  Null-Fläche → 0 Dreiecke → unsichtbar. **Fix**: `extruded: true` mit dünnem
  perpendikularem XY-Footprint (eps ≈ 1e-6 grad ~ 11 cm) und `getElevation`
  pro Segment. Bodenhöhe via Z=base im Footprint, Höhe = top - base.
  Limitation: konstante Höhe pro Segment (Treppen-Stufen bei großen Höhen-
  sprüngen). Bei ~5 m Abstand zwischen GPS-Punkten visuell unauffällig.
  Zusätzlich: Curtain via Pill-Switch ein-/ausblendbar (`ToggleSwitch.tsx`,
  generische Komponente, ersetzt den vorherigen `ColorModeToggle`).


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

### Schritt 6 — ~~LOD-Automat kalibrieren~~ (erledigt 2026-05-24)
Punkt stammt aus der Plotly-HTML-Aera, wo LOD-Wechsel teuer war.
Im React-Viewer mit ``useDemLod`` + ``useTransition`` laeuft das Streaming
unauffaellig; die Default-Schwellen 8/11 reichen fuer alle bisher
getesteten Tracks. Bei Bedarf spaeter neu aufgreifen.

### Schritt 7 — CLI-Integration
- [ ] `__main__.py` um `--export`-Flag erweitern
- [ ] End-to-End-Test: `python -m gps_pipeline --export output/ && python view.py`

### Schritt 8 — Polish
- [ ] Touch-Gesten (Pinch-Zoom)
- [ ] Vergleichs-Ansicht (zwei Tracks gleichzeitig)
- [x] ~~Hover-Tooltip direkt im 3D-View~~ — erledigt 2026-05-24 (Schritt 5e)

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
