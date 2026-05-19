# Refactor-Plan — GPS-Track-Pipeline

**Stand:** 2026-05-04
**Ziel:** Modular, mit klaren Schemata zwischen den Modulen, vorbereitet auf Multi-Constellation.

---

## Leitprinzipien

Aus der Diskussion über die Unix-Philosophie destilliert:

1. **Jedes Modul macht eine konzeptionelle Operation** — nicht mehr, nicht weniger.
2. **DataFrames sind das universelle Interface** zwischen den Modulen, analog zu Unix-Textströmen.
3. **Stateless, wo möglich** — keine globalen Variablen (Achtung: das alte `extract_fields.py` hatte ein globales `last_valid_position`-Dict, das wird verschwinden), kein Modul-State.
4. **Eine Top-Level-Funktion pro Modul** als Export. Helper-Funktionen privat (`_helper`).
5. **Konfiguration als Parameter**, nicht als Hardcode. Sinnvolle Defaults.
6. **Pure Funktionen wo möglich** — `df_neu = transform(df_alt)`, nicht `transform(df_alt)` mit In-place-Modifikation.

---

## Ziel-Architektur

```
┌──────────────────┐
│ NMEA-Logfile     │  ← Rohdaten
└────────┬─────────┘
         │
┌────────▼─────────┐
│ parse_nmea       │  Liste[NMEASentence] (pynmea2-Objekte)
└────────┬─────────┘
         │
┌────────▼─────────┐
│ build_dataframe  │  DataFrame mit Roh-Spalten (sentence_type, gga_*, rmc_*, vtg_*, gsa_*, gsv_*)
└────────┬─────────┘
         │
┌────────▼─────────┐
│ filter_invalid   │  DataFrame, ungültige Einträge entfernt
└────────┬─────────┘
         │
┌────────▼─────────┐
│ consolidate      │  DataFrame mit konsolidierten Zeilen (eine pro Timestamp), interpolierter Höhe
└────────┬─────────┘
         │
┌────────▼─────────┐
│ enrich_speed     │  DataFrame plus geodätische Distanzen und Geschwindigkeiten
└────────┬─────────┘
         │
         ├────────────────────────┐
         │                        │
┌────────▼─────────┐    ┌─────────▼─────────┐
│ visualize_3d     │    │ visualize_satview │  Plotly-Figures
└──────────────────┘    └───────────────────┘

GPX-Pfad parallel:
GPX-File → parse_gpx → DataFrame mit gleichem Schema → enrich_speed → visualize
```

Der entscheidende Punkt: **NMEA und GPX münden in dasselbe Schema** — ab dem Punkt `enrich_speed` ist die Pipeline identisch. Das ist der Ort, an dem die Vergleichsvisualisierung ohne Sonderbehandlung funktioniert.

---

## Modulbaum (umgesetzter Stand)

```
gps_pipeline/
├── README.md                # Quickstart und Architektur-Übersicht
├── __init__.py              # Top-Level-Exporte
├── __main__.py              # Einstiegspunkt (python -m gps_pipeline)
├── config.py                # zentrale Konstanten und Defaults
│
├── parsing/
│   ├── nmea.py              # parse_nmea_file → Liste[NMEASentence]
│   ├── gpx.py               # parse_gpx_file → DataFrame (direkt Schema B)
│   └── nmea_to_dataframe.py # build_dataframe → DataFrame (Schema A)
│
├── processing/
│   ├── filter.py            # filter_invalid → DataFrame
│   ├── consolidate.py       # consolidate → DataFrame (Schema A → Schema B)
│   ├── enrich.py            # enrich_speed → DataFrame (Schema B → Schema C)
│   └── gsv_aggregate.py     # aggregate_gsv (intern, von nmea_to_dataframe genutzt)
│
├── visualization/
│   ├── three_d.py           # visualize_3d (Plotly, optional mit Terrain-Mesh)
│   ├── satellite_view.py    # visualize_satellites (Plotly Polar)
│   └── multi_track.py       # visualize_multiple (Track-Vergleich)
│
├── terrain/
│   └── dem.py               # load_dem (rasterio, Output für Plotly)
│
└── utils/
    └── safe_convert.py      # robuste Type-Konversion
```

**Insgesamt 14 Python-Module** (plus 6 leere `__init__.py` und 1 README) bei
~2200 Zeilen Code, gegenüber 70 Files / ~10.700 Zeilen im Ausgangsstand.

### Abweichungen vom ursprünglichen Plan-Entwurf

Der ursprüngliche Entwurf hatte ein paar Module vorgesehen, die in der
Umsetzung anders gelöst oder weggelassen wurden:

* **`parsing/gpx.py`** sollte laut Plan Schema A produzieren, springt jetzt
  direkt zu Schema B. Begründung: GPX hat keine separaten Sentence-Typen,
  ein Schema-A-Output wäre nur Durchwinken zu Schema B gewesen.
* **`visualization/terrain.py`** (PyVista) ist weggefallen — die Terrain-
  Anzeige wurde in `three_d.py` mit Plotly integriert (einheitliche HTML-
  Ausgabe statt separater PyVista-Fenster).
* **`terrain/satellite_tiles.py`** (ArcGIS-Tile-Downloader) ist nicht mehr
  nötig — Plotly bekommt das Terrain als 2D-Höhen-Array, eine Satelliten-
  textur wäre ein separater zukünftiger Schritt.
* **`utils/debug.py`** ist nicht angelegt — die `debug_dataframe_issues`-
  Funktion aus dem alten `fixed_distance_speed - not.py` wurde nicht
  zurückportiert. Bei Bedarf nachträglich ergänzbar.

### Geteilte Helfer innerhalb `visualization/`

`multi_track.py` und `satellite_view.py` greifen aktuell auf private
Hilfsfunktionen in `three_d.py` zu (`_make_hover_text`,
`_quantile_color_indices`, `_add_terrain_surface`). Das funktioniert,
bricht aber leise die Konvention "`_`-präfixierte Namen sind modulintern".

In einem strengeren Projekt würde man diese Helfer in eine eigene Datei
`visualization/_helpers.py` auslagern und sie von dort in alle drei
Visualisierungs-Module importieren. Vorteile:

* Klare Trennung: `three_d.py` darf sich auf seine öffentliche Aufgabe
  konzentrieren, die Helfer sind sichtbar gemeinsame Infrastruktur.
* Keine Suggestion mehr, `three_d.py` sei "wichtiger" als die anderen
  Visualisierungs-Module — derzeit fühlt sich `three_d.py` versehentlich
  wie der "Master" an.
* Refactoring der Helfer wirkt sich nicht versteckt auf andere Module aus.

Praktischer Aufwand: ~30 Minuten, keine Verhaltensänderung. Sinnvoll, wenn
ein viertes Visualisierungs-Modul dazukommt oder wenn die Helfer komplexer
werden — derzeit gut zu vertreten, beim nächsten Anlass aber gleich tun.

---

## Schemata zwischen Modulen

### Schema A — Roh-DataFrame (nach `parse → build_dataframe`)

Eine Zeile pro NMEA-Satz oder GPX-Trackpoint. Spalten gemischt belegt (NaN, wo der jeweilige Satz keine Daten liefert).

```
Pflichtspalten (immer da):
  sentence_type           : 'RMC' | 'GGA' | 'VTG' | 'GSA' | 'GSV' | 'GPX'
  timestamp_utc           : pd.Timestamp (UTC)
  talker_id               : 'GP' | 'GL' | 'GA' | 'GB' | 'GPX'

Positionsspalten (gemeinsam für RMC, GGA, GPX):
  directional_latitude    : float (Vorzeichen je N/S)
  directional_longitude   : float (Vorzeichen je E/W)

RMC-spezifisch:
  rmc_status              : 'A' | 'V' | NaN
  rmc_speed_knots         : float
  rmc_true_course         : float
  rmc_mag_variation       : float

GGA-spezifisch:
  gga_gps_quality         : UInt8 (0–8)
  gga_num_sats            : UInt8
  gga_hdop                : float
  gga_altitude            : float (m über Geoid)
  gga_geo_separation      : float (m)

VTG-spezifisch:
  vtg_speed_knots         : float
  vtg_speed_kmph          : float
  vtg_true_track          : float
  vtg_mag_track           : float

GSA-spezifisch:
  gsa_fix_type            : UInt8 (1=No, 2=2D, 3=3D)
  gsa_pdop, gsa_hdop, gsa_vdop : float

GSV-spezifisch (NACH der Aggregation, eine Zeile pro Multi-Sentence-Group):
  gsv_satellites          : list[dict] mit prn, elevation, azimuth, snr

GPX-spezifisch:
  gpx_speed_ms            : float (aus <speed> oder <extensions>)
  gpx_hdop                : float (aus <hdop>)

Validierungs-Flags (nur für RMC und GGA):
  gga_rmc_pos_mismatch    : bool   (Position GGA stimmt nicht mit zeitnahem RMC überein)
  gga_rmc_time_mismatch   : bool   (Zeit weicht ab)
```

### Schema B — Konsolidierter DataFrame (nach `consolidate`)

Eine Zeile pro **Timestamp** statt pro NMEA-Satz. GGA, RMC, VTG zusammengeführt. GSV und GSA fallen weg (waren Diagnose-Daten und liefern keine Position/Geschwindigkeit).

```
  timestamp_utc           : Index oder Spalte
  directional_latitude    : float
  directional_longitude   : float
  altitude_corrected      : float (gga_altitude + gga_geo_separation, interpoliert wo NaN)
  speed_kmh               : float (vereinheitlicht aus VTG bzw. RMC)
  speed_knots             : float
```

### Schema C — Angereicherter DataFrame (nach `enrich_speed`)

Schema B plus berechnete Werte:

```
  distance_m              : float (geodätisch zum vorherigen Punkt)
  speed_geodesic_kmh      : float
  speed_geodesic_knots    : float
  speed_diff_kmh          : float (geodesic - GPS, Plausibilitäts-Indikator)
  speed_diff_knots        : float
```

Der Unterschied zwischen den Schemata ist **strikt monoton**: jeder Schritt fügt Spalten hinzu oder lässt welche weg, aber nichts wird stillschweigend umbenannt oder umformatiert. Das macht die Pipeline auch dann nachvollziehbar, wenn man in der Mitte einsteigt.

---

## Konfiguration

`config.py` als zentraler Ort für alle einstellbaren Werte:

```python
# Filter
EXCLUDE_GGA_QUALITIES = [0, 5]      # 0=invalid, 5=Float RTK (oft als unzuverlässig)

# Visualization
DEFAULT_QUANTILES = 5
AVAILABLE_COLORSCALES = ['Plasma', 'Viridis', 'Cividis', 'Turbo', 'Inferno']
DEFAULT_COLORSCALE = 'Plasma'
DEFAULT_Z_EXAGGERATION = 8          # Höhenüberhöhung in 3D-Plots

# Terrain
DEFAULT_TILE_ZOOM = 15
MAX_TILES_WARNING = 100

# Diagnostics
GSV_AGGREGATION_GROUP_KEYS = ['talker_id', 'num_messages', 'num_sv_in_view']
```

Module greifen darauf zu, oder es wird als Default in Funktionssignaturen referenziert. Heißt: wenn ich später z.B. die Z-Überhöhung anders haben will, ein Wert ändern statt durch sieben Module zu suchen.

---

## Die heiklen Stellen — was beim Refactor passieren muss

### 1. GSV-Aggregation in `nmea_to_dataframe`

GSV hat **keinen eigenen Timestamp**. Aggregation muss über die Stream-Position passieren. Algorithmus:

```python
def aggregate_gsv(messages):
    """Gruppiere aufeinanderfolgende GSV-Sätze zu einer Liste pro Multi-Sentence-Group."""
    out = []                              # Liste fertiger Gruppen mit Timestamp
    current_group = []                    # akkumulierte sv_tuples einer laufenden Gruppe
    last_timestamp = None
    last_talker = None

    for msg in messages:
        if isinstance(msg, RMC) or isinstance(msg, GGA):
            last_timestamp = derive_utc_timestamp(msg)

        if isinstance(msg, GSV):
            # Edge case: leerer GSV-Satz mit num_sv_in_view = 0
            if msg.num_sv_in_view == 0:
                out.append({'timestamp': last_timestamp, 'talker': msg.talker, 'satellites': []})
                continue

            # Erste Zeile einer neuen Gruppe?
            if msg.msg_num == 1:
                # Falls die alte Gruppe unvollständig zu Ende ging, jetzt abschließen
                if current_group:
                    out.append({'timestamp': last_timestamp, 'talker': last_talker, 'satellites': current_group})
                current_group = []
                last_talker = msg.talker

            current_group.extend(extract_sv_tuples(msg))

            # Letzte Zeile einer Gruppe?
            if msg.msg_num == msg.num_messages:
                out.append({'timestamp': last_timestamp, 'talker': last_talker, 'satellites': current_group})
                current_group = []

    return out
```

Wichtige Eigenschaften:
- **Kein State-Modul**: alles lokal in der Funktion
- **Edge case `num_sv_in_view = 0`**: schadlos, leere Liste
- **Multi-Constellation**: Gruppen werden pro Talker getrennt (GP- und GL-Sätze landen in eigenen Einträgen)
- **Robust gegen Lücken**: wenn ein Satz mittendrin fehlt und eine neue Gruppe anfängt, wird die alte einfach so abgeschlossen wie sie ist

### 2. RMC-Datum für GGA und VTG übernehmen

GGA und VTG haben nur Zeit, kein Datum. Der heutige Code in `process_nmea_korrigiert.py` macht das schon — beim Refactor wird die Logik in `_combine_with_last_rmc_date` ausgelagert und gut testbar gemacht. Edge case: Mitternacht — wenn die Tour über 0:00 UTC geht, muss das Datum entsprechend einen Tag weiter laufen.

### 3. GGA/RMC-Mismatch-Erkennung

Bisher in `process_nmea_korrigiert.py` als Inline-Logik. Beim Refactor in eine eigene Funktion `_check_gga_rmc_consistency(rmc_msg, gga_msg)` mit klarer Signatur, die zwei Bool-Werte zurückgibt. Tolerance-Schwellen werden Parameter mit Default in `config.py`.

### 4. Z-Überhöhung statt Skalierung

Die `* 111000`-Skalierung verschwindet komplett. In `visualize_3d` stattdessen:

```python
fig.update_layout(
    scene=dict(
        aspectmode='manual',
        aspectratio=dict(x=1, y=1, z=z_exaggeration),
    )
)
```

`z_exaggeration` kommt aus dem Funktionsparameter (Default aus `config.DEFAULT_Z_EXAGGERATION`).

### 5. Quantil-Binning auf `pd.qcut`

```python
def color_indices(values: pd.Series, n_quantiles: int = 5) -> np.ndarray:
    """Liefert für jeden Wert einen Index 0..n-1, basierend auf Quantilen.
    NaN-Werte bleiben NaN (werden in Plotly als ungefärbt dargestellt)."""
    return pd.qcut(values, q=n_quantiles, labels=False, duplicates='drop').to_numpy()
```

Das `duplicates='drop'` ist ein Detail: wenn zu viele identische Werte vorkommen (z.B. wenn 80% des Tracks bei 0 km/h sind, weil das Auto stand), kann `qcut` keine eindeutigen Quantil-Grenzen finden. Mit `'drop'` werden zusammenfallende Grenzen übersprungen — man bekommt vielleicht weniger Klassen als angefordert, aber keinen Crash.

### 6. Hover-Text-Generierung als eigene Funktion

`create_hover_text` arbeitet jetzt zeilenweise mit `df.iterrows()`. Das ist O(n) und langsam bei vielen Punkten. Beim Refactor: einmal vektorisiert mit String-Operationen auf Spalten, statt 580× durch Python zu loopen.

```python
def make_hover_text(df: pd.DataFrame) -> pd.Series:
    timestamp_str = df['timestamp_utc'].dt.strftime('%Y-%m-%d %H:%M:%S')
    pos_str = df['directional_latitude'].apply(lambda x: f"{x:.6f}") + "°N, " + ...
    speed_str = df['speed_kmh'].apply(lambda x: f"{x:.1f} km/h" if pd.notna(x) else "N/A")
    return ("<b>Zeit:</b> " + timestamp_str + "<br>" +
            "<b>Position:</b> " + pos_str + "<br>" +
            ...)
```

---

## Was wegfallen kann

Beim Refactor verschwinden folgende Module komplett:

| Modul | Grund |
|---|---|
| `extract_fields.py` | Globale Variable `last_valid_position` ist genau das, was die neue Architektur vermeiden will. Logik wird zerlegt und in `nmea_to_dataframe.py` als pure Funktionen wieder eingebaut. |
| `optimize_nmea_dataframe.py` | Type-Konvertierung wird in `nmea_to_dataframe` integriert. |
| `distance_speed_improved.py` und `distance_speed.py` | Konsolidiert in `enrich_speed`. |
| `vis_sat.py` (in alter Form) | Aggregation passiert vorher, Modul wird viel einfacher. |
| `prepare_data_modular.py` | Aufgespalten in `consolidate` und `enrich_speed`. |
| `visualize_nmea_multi.py` | Verallgemeinerung mit Schema-C-Eingabe; landet als `multi_track.py`. |
| Alle `__main__*.py`-Varianten | Eine bleibt. |

---

## Reihenfolge der Umsetzung

Schritt für Schritt, sodass nach jedem Schritt etwas Lauffähiges existiert:

1. **`config.py` anlegen** — Defaults sammeln
2. **`utils/safe_convert.py`** — kopieren wie bisher
3. **`parsing/nmea.py`** — `parse_nmea_file` aus altem `parse_nmea.py`, weitgehend unverändert
4. **`processing/gsv_aggregate.py`** — neue Multi-Sentence-Logik
5. **`parsing/nmea_to_dataframe.py`** — `build_dataframe` aus `process_nmea_korrigiert.py`, refactored:
   - GSV-Aggregation eingebaut
   - Globale Variablen entfernt
   - Type-Konvertierung integriert
6. **`processing/filter.py`** — kopieren aus `filter_pandas.py` mit kleineren Anpassungen
7. **`processing/consolidate.py`** — der Teil aus `prepare_data_modular.py`, der GGA+RMC+VTG zusammenführt
8. **`processing/enrich.py`** — Geschwindigkeitsberechnung mit NaN-Checks (kompakte Variante)
9. **`parsing/gpx.py`** — aus `gpx_parser_xml7.py`, Output an Schema A angepasst
10. **`visualization/three_d.py`** — `..._modularized3.py`, mit `aspectratio` und `pd.qcut`, vektorisierter Hover-Text
11. **`visualization/satellite_view.py`** — `vis_sat.py` vereinfacht
12. **`visualization/multi_track.py`** — `visualize_nmea_multi.py` an Schema C angepasst
13. **`visualization/terrain.py`** und **`terrain/*`** — kopieren wie bisher, kleine Anpassungen
14. **`__main__.py`** — neue Pipeline orchestrieren

Nach jedem Schritt kurzer Smoke-Test mit den vorhandenen Beispieldateien.

---

## Validierung

Nach dem Refactor sollten diese Tests bestehen:

1. **Idempotenz**: `parse → build → filter → consolidate → enrich` zweimal aufrufen liefert identische DataFrames
2. **Schema-Stabilität**: jeder Schritt produziert Spalten gemäß seinem dokumentierten Schema, nicht mehr und nicht weniger
3. **NMEA-File-Test**: `nmea_testlog.txt` → 580 konsolidierte Zeilen, 456 m Strecke, 60 km/h max GPS-Speed (siehe Inventar Abschnitt 9)
4. **GPX-File-Test**: `flight_testtrack.gpx` → 1251 Zeilen, Höhenbereich 210–1193 m, max ~161 km/h
5. **Edge-Case-Test**: GSV mit `num_sv_in_view = 0` → leere `gsv_satellites`-Liste, kein Crash
6. **Vergleichs-Test**: NMEA und GPX nach Schema C haben **identische Spaltennamen** (`directional_latitude`, `directional_longitude`, `altitude_corrected`, `speed_kmh`, `speed_knots`, `distance_m`, ...) — Multi-Track-Visualisierung läuft ohne Anpassung

---

## Was bewusst NICHT gemacht wird

Damit der Refactor nicht zu groß wird, ein paar Sachen, die vielleicht nett wären, aber nicht jetzt:

- **Keine pytest-Suite**: nur Smoke-Tests im `__main__` und manuelle Validierung gegen die Beispieldateien. Test-Suite ist eine eigene Investition.
- **Keine Type-Hints überall**: nur an Modul-Boundaries (Funktionssignaturen). Innerhalb von Funktionen sparen wir uns das.
- **Kein Caching**: die Pipeline läuft schnell genug, dass Caching jetzt overkill wäre.
- **Keine API-/CLI-Schnittstelle**: der Code wird über Imports und das `__main__` aufgerufen, fertig.
- **Kein Logging-Framework**: weiter mit `print()`. Wenn das Projekt wächst, später auf `logging` umstellen.

Diese Sachen kommen, wenn das Projekt es verdient — nicht prophylaktisch.
