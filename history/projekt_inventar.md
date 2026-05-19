# Projektinventar — GPS-Track-Pipeline

**Stand:** 2026-05-03 (Rev. 2 — mit Designentscheidungen)
**Anzahl Dateien gesichtet:** 70 (`.py` + `.txt`)
**Gesamtumfang:** ~10.700 Zeilen

---

## Wichtige Vorbemerkung

Das Projekt wird demnächst überarbeitet, sobald ein neuer GPS-Empfänger ankommt, der **Multi-Constellation** (GPS + GLONASS + Galileo + ggf. BeiDou) unterstützt. Die aktuellen Logfiles enthalten nur GPS. Beim Refactor sollte die Multi-Constellation-Fähigkeit von Anfang an mitgedacht werden — vor allem bei GSV (verschiedene Talker-IDs `$GP`, `$GL`, `$GA`, `$GB`).

---

## 1. Was das Projekt tut

Pipeline für GPS-Track-Daten:

1. **NMEA-Logfile** (Roh-Datenstrom eines GPS-Empfängers) parsen → DataFrame mit einer Zeile pro NMEA-Satz
2. **Filtern und Bereinigen** (ungültige Fixes raus, Sätze ohne Anker raus, Einträge vor erstem gültigen RMC raus)
3. **Aufbereiten:** GGA/RMC/VTG-Zeilen pro Zeitstempel zusammenführen, Höhe korrigieren, Geschwindigkeit aus Position berechnen
4. **Optional GPX als zweite Quelle** (z.B. Smartphone-Track als Vergleich)
5. **Visualisieren:**
    - 3D-Track in Plotly (Hover-Info, farbcodiert nach Geschwindigkeit, Höhe als Balken zur Grundebene = "lineares Balkendiagramm in 3D")
    - 2D-Karte
    - Satellitendiagramm (Polar-Plot der GSV-Daten)
    - DEM-Mesh mit Satellitentextur und überlagertem Track (PyVista)

## 2. Kanonischer Stack (was bleiben soll)

| Modul | Zweck | Status |
|---|---|---|
| `parse_nmea.py` | NMEA-Zeilen mit pynmea2 parsen, Feldnamen und Typen sammeln | stabil |
| `process_nmea_korrigiert.py` | Pro NMEA-Satz eine DataFrame-Zeile, Spalten mit `gga_*`/`rmc_*`/`vtg_*`-Präfixen, `directional_lat/lon`, `timestamp_utc`, GGA/RMC-Mismatch-Flags | **kanonisch — soll als `process_nmea.py` laufen** |
| `filter_pandas.py` | Ungültige GGA-Fixes, ungekoppelte RMC/VTG, GSA ohne Fix, Einträge vor erstem gültigem RMC entfernen | stabil |
| `analyze_dataframe.py` | Statistik-Ausgaben (Strecke, Geschwindigkeit, Fix-Qualität, Mismatches, Zeitraum) | stabil |
| `prepare_data_modular.py` | GGA+RMC+VTG pro Timestamp joinen, Höhe interpolieren, geodätische Geschwindigkeit berechnen | wird beim Refactor um NaN-Checks ergänzt |
| `better_nmea_visualization_with_quantile_fix_modularized3.py` | 3D-Plotly-Visualisierung mit Quantil-Farbcodierung | stabil — Quantil-Binning beim Refactor auf `pd.qcut` umstellen |
| `gpx_parser_xml7.py` | GPX-Datei (XML) parsen, Duplikat-Timestamps behandeln | stabil |
| `visualize_nmea_multi.py` | Vergleichsvisualisierung mehrerer Datensätze | stabil |
| `vis_sat.py` | Polar-Plot der Satellitenpositionen (GSV) | wird beim Refactor vereinfacht (Multi-Sentence-Aggregation passiert dann schon in `process_nmea`) |
| `terrain_mesh.py` | DEM (GeoTIFF) → PyVista StructuredGrid | stabil |
| `terrain_texture.py` | Satellitenkacheln von ArcGIS herunterladen und stitchen | stabil |
| `terrain_visualization.py` | Mesh + Textur + Track in PyVista rendern (Colab-tauglich) | stabil |
| `__main___für_mesh_und_3d.py` | Einstiegspunkt | beim Refactor zu `__main__.py` umbenennen, Aufrufer-Mismatches korrigieren |

## 3. Designentscheidungen für den Refactor

### 3.1 Z-Skalierung — RAUS

**Was es war:** `directional_lat/lon` wurde mit `* 111000` skaliert (grob: Grad → Meter), damit in Plotly's `aspectmode='data'` die Höhenachse nicht zerquetscht wird. Der Faktor war im Wesentlichen Zufall — er sah okay aus.

**Was es eigentlich sollte:** Eine "relative Skalierung nur für z" — also eine Höhenüberhöhung (vertical exaggeration), wie sie in der Geländedarstellung Standard ist.

**Lösung:** Plotly-Layout mit `aspectmode='manual'` und explizitem `aspectratio={'x': ..., 'y': ..., 'z': ...}`. Damit lässt sich der Z-Übertreibungsfaktor sauber konfigurieren (Standard z.B. 5–10×), ohne die Eingabedaten zu manipulieren.

**Konkret betrifft das:**
- `distance_speed_improved.py` (skaliert am Ende mit `* 111000`) → komplette Datei wird obsolet (siehe 3.3)
- `better_nmea_visualization_with_quantile_fix_modularized3.py` → Hover-Text muss nicht mehr durch 111000 dividieren; Layout bekommt `aspectratio` mit konfigurierbarem `z`-Faktor

### 3.2 GSV-Aggregation — IN process_nmea

**Was es ist:** GSV-Sätze für viele Satelliten werden vom Empfänger über mehrere NMEA-Zeilen verteilt (z.B. 12 Satelliten → 3 GSV-Sätze à 4 Satelliten). Bisher passiert die Zusammenführung erst in `vis_sat.py` zur Laufzeit.

**Refactor-Plan:** In `process_nmea` nach dem pynmea2-Parsen, aber vor dem DataFrame-Bau:
- Gruppieren nach `(timestamp_utc, talker_id)` — letzteres wichtig für Multi-Constellation, damit GPS-Satelliten nicht mit GLONASS-Satelliten in eine Gruppe wandern
- Pro Gruppe alle `sv_tuples` zu einer Liste zusammenführen
- Eine einzige DataFrame-Zeile pro `(timestamp, talker_id)` mit Spalte `gsv_satellites = [{prn, elevation, azimuth, snr}, ...]`

**Folgewirkung:** `vis_sat.py` wird deutlich einfacher — der ganze Block, der nach gleichzeitigen GSV-Sätzen sucht, kann weg. Statt dessen direkt auf `gsv_satellites`-Spalte zugreifen.

### 3.3 Geschwindigkeitsberechnung — Kompakte Variante mit NaN-Checks

**Status quo:** Zwei parallele Implementierungen.
- `prepare_data_modular.py` — kompakt (Listen anhängen), aber ohne NaN-Checks
- `distance_speed_improved.py` — defensiver (NaN-Checks, Konfliktprüfung), aber wird nicht aufgerufen und enthält die fragwürdige `*111000`-Skalierung

**Refactor-Plan:** Kompakte Variante aus `prepare_data_modular.py` behalten, NaN-Checks ergänzen (überspringe Iteration bei NaN-Koordinate oder NaT-Timestamp). `distance_speed_improved.py` und `distance_speed.py` archivieren.

### 3.4 Quantil-Binning — auf pd.qcut umstellen

**Status quo:** Eigenbau mit `np.quantile` + `np.searchsorted`. Funktional in Ordnung für saubere Eingaben, hat aber einen stillen Bug bei NaN-Werten (werden in die höchste Klasse einsortiert, statt durchzurutschen) und ist 20+ Zeilen Code für etwas, das pandas-Standard ist.

**Refactor-Plan:** Durch `pd.qcut(values, q=5, labels=False)` ersetzen. Behandelt NaN sauber, ist eine Zeile, ist konventionell. Details siehe Lerndokument.

## 4. Knackpunkte aus dem Code (zu reparieren)

### 4.1 `process_nmea.py` ist nicht das aktuelle Modul

Die Datei `process_nmea.py` (kurz, 70 Zeilen) ruft `extract_fields` auf und produziert das **alte** Schema (`msg_type`, `latitude`, `combined_date_time`, `gps_quality`).

Die Datei `process_nmea_korrigiert.py` (479 Zeilen) produziert das **neue** Schema (`sentence_type`, `directional_latitude`, `timestamp_utc`, `gga_gps_quality`, plus Mismatch-Flags und Datentyp-Optimierung).

Alle nachgelagerten Module erwarten das neue Schema. Bei der Reparatur wird `process_nmea.py` durch den Inhalt von `process_nmea_korrigiert.py` ersetzt.

### 4.2 Funktionsnamen-Mismatch

`__main__*.py` ruft `from process_nmea import process_nmea_data_enhanced`. Diese Funktion existiert nicht. Existierende Namen:

- `process_nmea_data_to_dataframe` (in `process_nmea_korrigiert.py`)
- `process_nmea_data` (in alten Versionen)

Lösung: am Modulende `process_nmea_data_enhanced = process_nmea_data_to_dataframe` setzen, oder die Funktion direkt umbenennen.

### 4.3 Visualisierung gibt nur ein Argument zurück, Aufrufer erwarten zwei

`visualize_nmea_data` returnt nur `fig`. Alle `__main__*.py` machen `fig, df_processed = visualize_nmea_data(...)` → Auspacken-Fehler.

Lösung: Aufrufer auf Single-Return anpassen.

### 4.4 Daten-Aufbereitung wird in den meisten Mains übersprungen

Visualisierung erwartet die Spalten `altitude_corrected`, `speed_kmh`, `speed_geodesic_kmh`, `distance_m`. Diese entstehen erst in `prepare_data_modular.py`. Mehrere `__main__*` rufen `prepare_data` aber nicht auf.

Lösung: Pipeline-Reihenfolge erzwingen — `prepare_data` zwingend vor `visualize_nmea_data`.

### 4.5 `prepare_data` Rückgabewert

`__main___für_mesh_und_3d.py` erwartet `loc_data, scale_factor = prepare_data(df)`, aber die aktuelle Funktion gibt nur `df` zurück.

Lösung: Aufrufer auf Single-Return anpassen (mit der Skalierungs-Entscheidung aus 3.1 ist `scale_factor` ohnehin obsolet).

## 5. Iterations-Historie pro Modul

(Unverändert zur Vorversion — siehe vorheriges Inventar.)

### 5.1 GPX-Parser — 11 Versionen → bleibt: `gpx_parser_xml7.py`

Linie A (gpxpy-basiert, verworfen): `parse_gpx.py`, `parse_gpx_improved.py`, `improved_gpx_parser.py`, `improved_gpx_parser_xml.py`, `gpx_parser_-_immer_noch_mit_Fehler.py`, `gpx_parser.py`

Linie B (reines XML, gewinnt): `gpx_parser_xml.py`, `xml2.py`, `xml3.py` (kaputt), `xml4.py`, `xml5.py`, `xml6.py`, `xml7.py`

### 5.2 NMEA-3D-Visualisierung — 4 Versionen → bleibt: `..._modularized3.py`

`better_nmea_visualization_with_quantile_fix.py`, `..._modularized.py`, `..._modularized2.py` (kaputt: f-String-Syntax)

### 5.3 Distance/Speed — 3 Versionen → wird komplett konsolidiert (siehe 3.3)

`distance_speed.py`, `fixed_distance_speed_-_not.py`, `distance_speed_improved.py`

### 5.4 Terrain-Visualisierung — 3 Versionen → bleibt: `terrain_visualization.py`

### 5.5 Multi-Dataset-Visualisierung — 2 Versionen, identisch → bleibt: `visualize_nmea_multi.py`

### 5.6 Terrain-Code/Mesh/Texture — `corrected_*`/`improved_*` sind Duplikate → bleibt: `terrain_code.py`, `terrain_mesh.py`, `terrain_texture.py`

### 5.7 Hauptskripte — 5 Versionen + 1 .txt → bleibt: `__main___für_mesh_und_3d.py` (umbenennen zu `__main__.py`)

### 5.8 process_nmea — 14 Varianten → bleibt: `process_nmea_korrigiert.py` (umbenennen zu `process_nmea.py`)

## 6. Schema-Migration (alt → neu)

| Alt | Neu |
|---|---|
| `msg_type` | `sentence_type` |
| `latitude`, `lat_dir` (getrennt) | `directional_latitude` (mit Vorzeichen) |
| `longitude`, `lon_dir` (getrennt) | `directional_longitude` (mit Vorzeichen) |
| `gps_quality` | `gga_gps_quality` |
| `speed_knots` (RMC) | `rmc_speed_knots` |
| `altitude` | `gga_altitude` |
| `geo_sep` | `gga_geo_separation` |
| `status` (RMC) | `rmc_status` |
| `combined_date_time` | `timestamp_utc` |
| (keine) | `gga_rmc_pos_mismatch`, `gga_rmc_time_mismatch` |
| (RMC einmal) | `vtg_speed_knots`, `vtg_speed_kmph` (zusätzlich aus VTG) |

## 7. Archiv-Kandidaten — 50 Dateien

(Liste unverändert zur Vorversion. Gruppiert nach Funktionsbereich; jeweils nur die jüngste Version bleibt.)

### Alte GPX-Parser (12 Dateien)
`parse_gpx.py`, `parse_gpx_improved.py`, `improved_gpx_parser.py`, `improved_gpx_parser_xml.py`,
`gpx_parser_-_immer_noch_mit_Fehler.py`, `gpx_parser.py`,
`gpx_parser_xml.py`, `gpx_parser_xml2.py`, `gpx_parser_xml3.py`, `gpx_parser_xml4.py`, `gpx_parser_xml5.py`, `gpx_parser_xml6.py`

### Alte NMEA-Visualisierungen (3 Dateien)
`better_nmea_visualization_with_quantile_fix.py`, `..._modularized.py`, `..._modularized2.py`

### Alte Distance/Speed (3 Dateien — alle, wegen Konsolidierung in prepare_data)
`distance_speed.py`, `fixed_distance_speed_-_not.py`, `distance_speed_improved.py`

### Alte Terrain-Visualisierung (2 Dateien)
`terrain_visualization_before_improvement.py`, `corrected_visualization.py`

### Duplikate Multi-Dataset (1 Datei)
`multi_dataset_visualization.py`

### Duplikate Terrain Code/Mesh/Texture (3 Dateien)
`corrected_terrain_code.py`, `corrected_terrain_mesh.py`, `improved_terrain_texture.py`

### Alte Hauptskripte (5 Dateien)
`__main___old.txt`, `__main__.py`, `__main__alt.py`, `__main__neu.py`, `main.py`

### Alte process_nmea (13 Dateien)
`process_nmea.py`, `process_nmea_new.py`, `process_nmea_to_pandas.py`, `process_nmea_to_pandas_simple.py`,
`process_nmea_ALLE_Einträge.py`, `process_nmea_vor_Korrektur_durch_Claude.py`,
`process_nmea_vor_manueller_optimierung.py`, `process_nmea_with_example.py`,
`process_nmea_funktioniert__nur_nicht_alle_Werte_automatisch_erfasst.py`,
`combined_process_optimize.py`, `process_and_optimize_with_time_combination.py`,
`process_and_optimize_with_time_combination_directionalposition.py`, `extract_fields.py`

### Alte Hilfsmodule (4 Dateien)
`safe_convert.py`, `optimize_nmea_dataframe.py`, `analyze_pandas_noch_mit_alten_feldnamen.py`, `filter_nmea_data_einfach_aber_funktioniert.py`

### Test-/Beispiel-/Snippet-Dateien (8 Dateien)
`call_distance_speed.py`, `call_parse_gpx.py`, `call_nmea_vis_multi.py`,
`Beispielnutzung_*.py` (4 Stück), `snippet.py`, `robust-fix-code.py`, `import_old.txt`

## 8. Reparatur-Plan (für die nächste Sitzung)

In dieser Reihenfolge:

1. **Schema-Konsolidierung:** `process_nmea_korrigiert.py` → `process_nmea.py`, Funktion (oder Alias) `process_nmea_data_enhanced`.
2. **GSV-Aggregation** in `process_nmea` einbauen — gruppiert nach `(timestamp, talker_id)` für spätere Multi-Constellation-Tauglichkeit.
3. **Visualisierung:** Aufrufer in `__main__` an Single-Return anpassen.
4. **Z-Skalierung:** `*111000` raus, stattdessen `aspectratio={'x':1,'y':1,'z':...}` mit konfigurierbarem Z-Faktor.
5. **Pipeline-Reihenfolge:** `prepare_data` zwingend vor `visualize_nmea_data`.
6. **Geschwindigkeitsberechnung:** Kompakte Variante mit NaN-Checks, alle Distance-Speed-Module obsolet.
7. **Quantil-Binning** auf `pd.qcut` umstellen.
8. **`vis_sat.py`** vereinfachen (nutzt jetzt direkt die aggregierte `gsv_satellites`-Spalte).
9. **Aufräumen:** Archiv-Kandidaten in einen Ordner `_archiv/` verschieben.

## 9. Verifikation an realen Logfiles

Test gegen die hochgeladenen Beispieldateien — beide Module aus dem kanonischen Stack laufen ohne Fehler durch:

### NMEA: `nmea_testlog.txt`

- **GPS-Empfänger:** GPS-Testempfänger (per `$PGRMT`-Satz identifiziert)
- **Single-constellation** (nur `$GP*`)
- **Sample-Rate:** 10 Hz (alle 100ms ein RMC/GGA/VTG-Trio)
- **Satz-Häufigkeit:** RMC/GGA/VTG je 588, GSV 253 (also ~1× pro 2.3s, da Multi-Sentence), GSA 69, PGRMT 1
- **GSV-Edge-Case beobachtet:** `$GPGSV,1,1,00*79` — "0 Satelliten in View", muss vom Aggregator als leere Liste behandelt werden
- **Pipeline-Ergebnis:**
  - 2087 Zeilen geparst → 2057 nach Filter → 580 nach `prepare_data` (eine Zeile pro Timestamp)
  - 30 Pre-Fix-Zeilen wurden korrekt entfernt (RMC `V` → `A` Übergang)
  - Track: 68s Dauer, 456m Strecke, 6.7–60 km/h
  - Geschwindigkeitsabweichung GPS vs. geodätisch: max ~4 km/h (an Stellen mit übersprungenen Samples)
- **PGRMT** (proprietärer Garmin-Satz) wird von pynmea2 geparst, ohne Fehler — keine Sonderbehandlung nötig

### GPX: `flight_testtrack.gpx`

- **App:** GPS-Flugzeugapp (Flugplanungs-App)
- **Track-Inhalt: Flugzeug-Tour** (max 161 km/h, Median 111 km/h, Höhe 210–1193 m) — "Beispiel-Flugroute"
- **Sample-Rate:** ~1 Punkt alle 3 Sekunden
- **Speed-Element direkt im trkpt** (nicht in `<extensions>`) — der Parser behandelt beide Fälle
- **1271 Trackpoints**, davon **127 mit doppeltem Timestamp** (10%) — der `xml7`-Patch greift systematisch:
  - 20 vollständig identische Zeilen wurden gelöscht
  - 8 Timestamp-Reihenfolge-Korrekturen (mit Mikrosekunden-Offset)
  - Resultat: 1251 saubere Punkte
- **Kein HDOP** in den Daten — die Spalte enthält nur None

### Implikationen für Inventar/Reparatur

1. **Die beiden Test-Dateien gehören zu unterschiedlichen Touren** (Datum A vs. Datum B, Ort A vs. Ort B). `compare_datasets` würde laufen, aber das räumliche Vergleichen ergibt nur in der Anzeige Sinn — beide Tracks an unterschiedlichen Orten überlagern sich nicht.

2. **GSV-Aggregation muss die `,1,1,00`-Variante behandeln** (0 Satelliten = leere Liste). Edge case, aber im realen File enthalten.

3. **Die Z-Skalierungs-Diskussion gilt vor allem für den Flug-Track:** dort ist der Höhenbereich ~1000 m gegen ~37 km Track-Ausdehnung — Verhältnis 37:1. Eine Z-Überhöhung von 5–10× ist hier deutlich sichtbar; bei Auto-Tracks (4 m Höhenbereich gegen 400 m Strecke) macht sie keinen großen Unterschied.

4. **Das aktuelle NMEA-File ist kein Tour-Track**, sondern ein 68-Sekunden-Funktionstest. Für gründliche Pipeline-Tests nach dem Refactor wäre ein längerer NMEA-Track wertvoll.

5. **GSV-Sätze haben keinen eigenen Timestamp im NMEA-Stream.** Heißt: Aggregation kann nicht über `(timestamp_utc, talker_id)` erfolgen. Stattdessen müssen GSV-Sätze dem zuletzt empfangenen Timestamp (von RMC/GGA) zugeordnet werden. Das war im Lerndokument zunächst falsch dargestellt.

## 10. Vorbereitung auf Multi-Constellation

Wenn der neue Empfänger da ist:

- `parse_nmea.py` ist talker-ID-agnostisch (pynmea2 abstrahiert das) — sollte direkt funktionieren
- `process_nmea` muss `talker_id` als Spalte mitführen, mindestens für GSV
- Filterlogik: ggf. nach Talker-ID filtern (z.B. nur GP+GA verwenden, GL ignorieren)
- Visualisierung: Satellitendiagramm könnte verschiedene Konstellationen mit unterschiedlichen Marker-Farben darstellen
