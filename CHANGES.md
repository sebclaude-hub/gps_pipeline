# GPS-Pipeline — Änderungsverlauf

Chronologische Historie der Entwicklungsschritte. Architektur und
permanente Referenz liegen in [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Schritt 6d — Cut-Drag-Bug bei Trim-Edge-Übergang (25. Mai 2026)

**Symptom:** Beim Ziehen eines Cut-Handles bis zur Track-Kante (also
beim Übergang zu "Trim Start" / "Trim Ende") wurde der verbleibende
Handle anschließend "klebrig": schon das Hovern darüber ließ den Cut
auf Länge 0 zusammenschnurren. Erst Wegziehen und Hineinziehen brachte
ihn zurück.

**Ursache:** Pointer-Events hingen an den Handle-DOM-Knoten. Sobald
ein Cut zur Trim-Edge wurde (`trimStart === true`), entfernte React
den entsprechenden Handle-Div aus dem DOM. Damit ging die
Pointer-Capture verloren und das `pointerup` kam nie an — der lokale
`dragging`-State im `RangeBar` blieb auf `"start"` stehen. Der nächste
Pointer-Move-Event über dem verbleibenden Handle (auf der anderen
Seite) triggerte dessen `onPointerMove`-Handler; der sah `dragging ===
"start"` und behandelte das wie eine fortgesetzte Drag-Bewegung mit der
X-Position des falschen Handles. Mit der Overlap-Prevention im Hook
kollabierte der Cut zur Breite 0.

**Fix:** Pointer-Move/-Up auf **Window-Level** binden via `useEffect`,
mit dem `dragging`-State als Effekt-Dependency. Handles haben nur noch
`onPointerDown`. Vorteile:

- Drag überlebt das Verschwinden des Source-Handles aus dem DOM
- Pointer-Up wird immer empfangen, egal wo der Cursor losgelassen wird
- Keine `setPointerCapture`-Klimmzüge mehr nötig

Refs (`rangeRef`, `onMoveRef`, `xToIdxRef`) spiegeln aktuelle Props in
den Window-Handler, damit der Listener nicht bei jedem State-Update
neu gebunden werden muss.

---

## Schritt 6c — Trim-Re-Import-CLI (25. Mai 2026)

Round-Trip-Loch geschlossen: bisher konnten Cuts im Viewer definiert und
als `ranges.json` exportiert werden, aber das Ergebnis war nicht zurück
im Viewer sichtbar. Jetzt:

```powershell
python -m gps_pipeline.apply_cuts \
    --feather output/test.feather \
    --ranges  output/ranges.json \
    --output  output_trimmed/ \
    --dem     data/linked_sued.tif \
    --charts  data/
python view.py output_trimmed
```

* Neuer Modulpfad `gps_pipeline/apply_cuts.py` mit CLI (`python -m
  gps_pipeline.apply_cuts ...`) und Library-Funktion `apply_cuts(...)`.
* Validiert ranges.json gegen die Feather-Punktanzahl (warnt bei
  Off-by-One).
* Erzeugt ein vollständiges Viewer-Output mit track.json, DEM-LODs und
  charts.json — bereit für `view.py`.
* Satelliten-Daten werden **nicht** mitgetrimmt, weil das Schema-A
  (NMEA-Rohsätze inkl. GSV) nicht im Feather liegt. Für satellitenfähige
  getrimmte Tracks muss man später vom Quell-NMEA neu durchprozessieren
  (separater Workflow, derzeit nicht implementiert).
* `gps_pipeline/__init__.py` importiert `apply_cuts` bewusst nicht, weil
  das beim `python -m gps_pipeline.apply_cuts`-Aufruf eine
  RuntimeWarning durch Doppel-Import auslöst. Wer es als Library nutzt:
  `from gps_pipeline.apply_cuts import apply_cuts`.

---

## Schritt 6b — Interaktiver DEM-Offset-Slider (25. Mai 2026)

### Erkenntnis vorab — was Schritt 6a tatsächlich tat (und was nicht)

Bei der UI-Diskussion zum Offset-Slider fiel auf, dass der Schritt-6a-Fix
(P5-Perzentil + asymmetrisches Clamping) nur eines beeinflusst hat:
**die Zahl `above_terrain` im InfoPanel/Tooltip**. Die *3D-Darstellung*
des React-Viewers war davon unberührt, weil sie `points.alt` direkt
verwendet (ohne Offset). Der Plotly-HTML-Pfad wendet den Offset auf den
Track an, der React-Viewer nicht.

Das heißt: die "Track unter DEM"-Stellen, die zur Diskussion führten,
hatten mit der Offset-Heuristik nichts zu tun — das waren GPS-Bugs oder
echte Geoid-Differenzen, sichtbar weil der React-Viewer rohe Track-Höhen
zeigt. Schritt 6a verbesserte zwar das angezeigte `above_terrain`, aber
nicht den 3D-Eindruck.

### Was Schritt 6b macht

Der Offset wird zur **interaktiven Live-Größe** im React-Viewer:

* Backend-Änderung: `export_track_json` exportiert `points.above_terrain`
  *ohne* vorgebackenen Offset (direkt `alt − terrain_elev`). Neuer
  Meta-Eintrag `suggested_z_offset_m` enthält den Python-Auto-Vorschlag.
* Frontend: neue Komponente `OffsetSlider` mit Schieberegler + numerischer
  Anzeige (Doppelklick zum Edit) + Auto/0-Buttons. Range ±200 m um den
  Vorschlag, Schritt 1 m (0.1 m mit Shift).
* `TrackViewer.tsx`: `exagAlt(alt)` schiebt Track-Z um den Offset vor der
  Z-Exaggeration. Curtain-Top zieht mit; Curtain-Bottom und Terrain-Mesh
  bleiben unverändert (Offset nur auf den Track).
* `InfoPanel` und Tooltip rechnen `above_terrain` live aus
  `alt + zOffset − terrain_elev`, ebenso die angezeigte MSL-Höhe.

Damit kann der Nutzer das DEM-Alignment am laufenden Modell justieren —
typischer Anwendungsfall: Landeschwelle muss auf der Landebahn sitzen,
oder eine bekannt-ebene Strecke darf nicht nach Bergen aussehen.

### Konsequenz für Schritt 6a

Die Python-Auto-Detection (P5 + asymmetrisches Clamping) bleibt erhalten,
liefert aber jetzt nur noch den **Slider-Default**. Der Nutzer übernimmt
die Feinkalibrierung. Der Plotly-HTML-Pfad (Legacy) nutzt den Wert
weiterhin als Render-Offset.

---

## Schritt 6 — Cut-Polish + DEM-Offset-Bugfix (25. Mai 2026)

### Cut-Range UX
- Cuts dürfen sich nicht mehr überlappen — Drag-Handles werden gegen
  Nachbar-Cuts geclamped, "+ Cut" sucht automatisch die nächste freie
  Lücke und wird disabled, wenn keine mehr da ist.
- Cuts heißen "Cut 1", "Cut 2", … (sortiert nach Position auf dem Track).
- Edge-Cuts (start == 0 oder end == N-1) bekommen Spezial-Labels
  "Trim Start" / "Trim Ende" und Schraffur statt eines äußeren
  Drag-Handles, weil diese Kante am Track-Rand klebt.
- Cut-Segmente werden im 3D-Track rot übergezeichnet (5 px PathLayer),
  live aktualisiert beim Draggen.

### DEM-Offset-Bug
**Symptom:** Track-Teile (besonders Landungen, Taxi) verschwanden unter
dem DEM. **Ursache:** Der "auto"-Modus nahm `-Median(track - dem)` als
Offset; das verschob etwa die Hälfte der Track-Punkte unter den Median
und damit unter das DEM.

**Fix:** Zwei zusammenspielende Regeln für den Auto-Offset:
1. **Outlier-robust**: 5%-Perzentil statt strikt `min()`. Ein einzelner
   GPS-Bug-Punkt soll nicht den gesamten Track unnötig hochheben.
2. **Asymmetrisches Clamping**: das Sicherheits-Floor wird auf `0`
   gedeckelt, falls positiv. Damit kann das Clamping nur Abwärts-Shifts
   reduzieren, niemals einen neuen Aufwärts-Shift erzeugen.

In Formel: `offset = max(raw_median, min(0, -p5_diff))`.

Effekt:
- Flugtrack mit Landung: kein Shift, Landung bleibt sichtbar bei DEM.
- GPX-Ellipsoid-Track: Median-basierte Kalibrierung greift weiter.
- Sauberer MSL-Bodentrack: kein unnötiger Lift.
- Track mit GPS-Ausreißern: Ausreißer dürfen unter DEM bleiben, der
  Rest des Tracks ist sicher oben.

Die alte Mean-Median-Gap-Heuristik (Flug-Erkennung) wurde überflüssig
und entfernt — das asymmetrische Clamping erledigt es eleganter.

---

## Schritt 5e — Hover-Tooltip (24. Mai 2026)

Aufbauend auf 5d: der unsichtbare Pickable-Layer treibt jetzt zusätzlich
einen schwebenden Tooltip am Cursor (deck.gl `getTooltip`-Prop). Inhalt
minimal — Zeit, Geschwindigkeit, Höhe MSL, Höhe ü.Grd. Ein neuer
3-Wege-Pill-Switch `InfoModeButtons` schaltet zwischen:

- **Panel**: rechtsseitiges InfoPanel (Default-Verhalten bis Schritt 4)
- **Tooltip**: nur Floating-Tooltip; Side-Panel wird ausgeblendet (300 px
  mehr Bildbreite für den Track), falls auch kein Skyplot dort steht
- **Beide**: gleichzeitig (Default)

Tooltip filtert auf `layer.id === "track-pick"`, damit andere Layers
(Terrain, Chart-Overlays) ihn nicht auslösen.

---

## Schritt 5d — Klickbare Track-Punkte (24. Mai 2026)

Bisher ließ sich der aktive Punkt nur über den Slider scrubben. Jetzt
liegt ein unsichtbarer `ScatterplotLayer` (`getFillColor=[0,0,0,0]`,
`pickable: true`) über dem Track. `onHover` setzt direkt `activeIdx` —
InfoPanel, Skyplot und Aktiv-Marker reagieren sofort.

---

## Schritt 5c — Synthetic-Tracks (24. Mai 2026)

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

---

## Schritt 5b — Range-Selection / Trimming (24. Mai 2026)

Generischer Mechanismus zum Definieren von Index-Bereichen, die aus dem
Track entfernt werden sollen. Drei Anwendungsfälle:

* **Reines Trimming**: `[0..50]` und `[N-30..N-1]` als Cut-Ranges →
  Track-Anfang und -Ende abschneiden.
* **Zwischenstopp entfernen**: ein einzelner Cut `[200..350]` → die
  Pause in der Mitte verschwindet.
* **Mehrfach-Cuts**: Anfang/Ende UND mehrere Pausen gleichzeitig.

* **Frontend**: `hooks/useRangeSelection.ts` verwaltet die Liste,
  `components/RangeSelector.tsx` zeigt die Cuts als rote Balken auf einer
  Track-Leiste; jeder Cut hat zwei Drag-Handles und einen
  Entfernen-Button. "+ Cut" fügt einen neuen Cut um die aktuelle
  Slider-Position ein. "Export" lädt eine `ranges.json` herunter.
* **Backend**: `processing/trim.py::trim_track(df, ranges)` schneidet
  die Bereiche aus einem Schema-C-DataFrame. `load_cut_ranges(path)`
  liest die vom Viewer exportierte `ranges.json`.

---

## Schritt 5a — Karten-Overlays (24. Mai 2026)

Anflugkarten oder beliebige georeferenzierte Bilder lassen sich auf das
DEM-Mesh "drapen" — die Karte folgt den Höhenkonturen statt flach
darüber zu schweben.

* **Input-Format**: `EDFG.png` + `EDFG.txt` im `data/`-Ordner. Die TXT
  enthält vier Eckkoordinaten in WGS84 (links-oben, rechts-oben,
  links-unten, rechts-unten), je Zeile `lon lat`. Optional
  `elevation_m: 220` als Fallback ohne DEM. Optional
  `subdivision: N` als Mesh-Override für Strategie B.
* **Backend**: `parsing/chart.py` parst PNG+TXT-Paare;
  `export/chart_export.py` kopiert die PNGs nach `output/charts/` und
  schreibt `charts.json`.
* **Frontend**: `utils/chartMesh.ts` mit zwei Strategien (siehe
  ARCHITECTURE.md). `layers/chartLayer.ts` rendert mit
  `SimpleMeshLayer` und PNG-Textur.

### Bug-Postmortem — der "Triangulation um 90 Grad gedreht"-Bug

Beim End-to-End-Test (echtes DEM + zwei georeferenzierte PNGs) sind
vier verschachtelte Bugs aufgefallen. Reihenfolge der Diagnose und
Fixes:

1. **UV-Mapping**: erste Iteration `(u, 1-v)` zeigte das PNG um 180°
   gedreht; zweite `(1-u, v)` nur noch horizontal vertauscht; dritte
   `(u, v)` korrekt. Erkenntnis: `SimpleMeshLayer` sampelt mit
   unflipped U und V relativ zu den HTMLImageElement-Pixeln — die
   natürliche Mesh-Iteration (r=0 oben, c=0 links) ist direkt
   kompatibel. **Das PNG selbst muss nicht gedreht/gespiegelt
   werden.**

2. **Mesh-Auflösung vs. DEM-Auflösung**: zunächst nutzte Strategie A
   ein eigenes N×N-Gitter (Cap 256) mit DEM-Höhensampling pro Vertex.
   Bei großen Karten (z.B. 35 km) lag das bei ~140 m/Vertex — gröber
   als das DEM (Copernicus 30 m). Zwischen Chart-Vertices interpolierte
   das Chart linear, missed dabei aber die feineren DEM-Details. Fix:
   Chart-Mesh verwendet *exakt die DEM-Vertices innerhalb der
   Karten-Bounds* — identische Auflösung, gleiche Höhenwerte.

3. **Anker-Mismatch**: trotz identischer DEM-Vertices war die Karte um
   ~150 m horizontal gegenüber dem Terrain verschoben. Ursache: Chart
   nutzte den Karten-Mittelpunkt als Anker mit eigenem
   `cos(lat_chart_center)`-Faktor, Terrain nutzte den DEM-Mittelpunkt
   mit `cos(lat_dem_center)`. Bei 0.5° Lat-Differenz ergibt das ~0.6%
   horizontale Verzerrung — bei 35 km Karte sind das 150 m. Fix:
   Chart verwendet identischen Anker und cos-Faktor wie demMesh
   (DEM-Center).

4. **Der eigentliche "Z-Fighting"-Bug — 90 Grad gedrehte
   Triangulation**: selbst nach Schritten 1–3 traten an Geländekanten
   dreieckige braune Flecken auf, die so aussahen, als würden die
   DEM-Dreiecke aus der Karte herausragen. **Sie tun es auch — weil
   die Triangulation um 90 Grad versetzt lief.** Beide Meshes
   verwenden im Index-Buffer die Konvention `tl, bl, tr, br` mit der
   Diagonalen `tl-bl-tr` / `tr-bl-br`, ABER:
   - demMesh iteriert `r=0..n_rows-1` mit `r=0` bei `lat_min` (Süden).
     Damit ist `"tl"` geographisch SW, `"bl"` ist NW. Diagonale: NW-SE.
   - chartMesh Strategie A iterierte ursprünglich `r=r_max..r_min`
     (Norden zuerst), `"tl"` war NW, `"bl"` war SW. Diagonale: SW-NE.

   Die beiden Diagonalen stehen **senkrecht aufeinander**. Selbst bei
   identischen Vertex-Höhen interpolieren die Meshes über
   *verschiedene* Diagonalen — innerhalb jedes Quads kann die
   Höhendifferenz mehrere Meter erreichen. Das DEM-Dreieck stößt
   dann durch die Karte. Fix: Iterationsreihenfolge in Strategie A
   exakt an demMesh angeglichen (`r_min..r_max`). Die UV-Berechnung
   bleibt geo-basiert und ist iterations-unabhängig, also keine
   Orientierungs-Auswirkung.

Nach diesen vier Fixes ist **keinerlei Z-Lift mehr erforderlich**
(`Z_LIFT_SUBGRID_M = 0`). Chart und Terrain interpolieren über jeden
Punkt zwischen den Vertices bitidentisch — klassisches Z-Fighting ist
mathematisch unmöglich, die Karte gewinnt durch die spätere Position
in der Layer-Liste (Render-Order-Tiebreak).

Strategie B (Fallback ohne DEM oder bei gedrehten Karten) braucht
weiterhin einen 5 m-Lift, weil sie ein eigenes N×N-Gitter aufspannt und
zwischen Chart-Vertices anders interpoliert als das Terrain.

---

## Schritt 4 — DEM/Terrain, Z-Scale, InfoPanel (20. Mai 2026)

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
  wird in Track, Curtain UND Terrain-Mesh gleich angewendet. zScale war
  zuvor in TrackViewer.tsx als Konstante 15 hart kodiert.

- **ZScaleButtons.tsx**: Pill-Button-Gruppe 1×, 2×, 3×, 5×, 7.5×, 10×;
  gleicher Indigo-Gradient wie ToggleSwitch. Default: 3×.

- **InfoPanel**: neue Felder „Punkt #" (1-basiert, Gesamt) und
  „Höhe ü.Grd" (above_terrain aus DEM). „Höhe" umbenannt in „Höhe MSL".

---

## Schritt 3 — Farbgebung, Legende, Vorhang, Toggles (19./20. Mai 2026)

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

- **Vorhang (Curtain)** sichtbar gemacht: SolidPolygonLayer mit
  `extruded: true` + perpendikulärem EPS-Footprint (1e-6 Grad ≈ 11 cm).
  Hintergrund: earcut trianguliert nur in XY — ein senkrechtes Polygon
  hat Null-XY-Fläche → 0 Dreiecke → unsichtbar. Fix: dünner
  horizontaler Grundriss, `getElevation` extrudiert nach oben.

- **Vorhang-Toggle** (CurtainMode): gleicher Pill-Switch-Stil.

- **json_export.py**: `_detect_track_mode()` Schwelle 30 m → 100 m;
  kein DEM-Fallback. `quantile_breaks.altitude_m` und `points.alt_q_idx`
  exportiert.

---

## TODO / Geplant

- Test mit echten ZED-X20P-Multi-Constellation-Daten
- Satellite-View-Warnung bei `is_synthetic === true` (synthetische Punkte
  haben keine validen Satellitendaten — UI sollte das anzeigen)
- `ranges.json` direkt vom Viewer an einen kleinen Endpoint in `view.py`
  posten (statt Download/CLI-Roundtrip)
- Trim-Re-Import in den Viewer (siehe Trim-Workflow-Diskussion)
- Vergleichs-Ansicht (zwei Tracks gleichzeitig im React-Viewer)

## Geplant in eigenem Repo: PWA-Konvertierung

Das Hobbyprojekt wird in eine browser-native Progressive Web App
überführt, damit es auf Linux/Windows/macOS/Android ohne Python-
Installation läuft. Pipeline-Logik wird nach TypeScript portiert,
OPFS für lokales Storage, geotiff.js für DEM-Streaming. Siehe
Diskussion in der Session vom 24./25. Mai. Eigener GitHub-Repo,
diese Codebase bleibt als Referenz und Python-Power-User-Werkzeug
bestehen.
