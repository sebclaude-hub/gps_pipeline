# Lerndokument — Alte und neue Wege

**Zweck:** Du kommst in einem Jahr zurück zu diesem Projekt und fragst dich, warum manche Dinge so umständlich gemacht sind, obwohl es offensichtlich einfacher ginge. Dieses Dokument beantwortet das.

Jedes Kapitel hat:
- **Was ich machen wollte** — die fachliche Anforderung
- **Was ich zuerst probiert habe** — der Erstversuch und warum er nicht funktionierte
- **Was funktioniert hat** — die Lösung, die im Code stand
- **Was sauberer gewesen wäre** — die Standardlösung, die ich beim Refactor verwende

---

## 1. Farbcodierung der Geschwindigkeit (Quantil-Binning)

### Was ich machen wollte

Den GPS-Track im 3D-Plot nach Geschwindigkeit einfärben. Problem: bei einer Tour ist man die meiste Zeit langsam (Stadt, rote Ampeln) und nur kurz schnell (Autobahn). Mit normaler "lineare Skala von Min bis Max"-Färbung wären 95% des Tracks in derselben dunklen Farbe und nur ein winziger heller Punkt — die ganze Variation in der Stadt wäre unsichtbar.

### Was ich zuerst probiert habe

Lineares Binning: Wertebereich (z.B. 0–130 km/h) in 5 gleich große Intervalle teilen (0–26, 26–52, 52–78, 78–104, 104–130) und jeden in eine Farbe stecken. Klingt logisch, ist aber genau das Problem von oben — weil eben die meisten Werte im niedrigen Bereich liegen.

### Was funktioniert hat

**Quantil-Binning:** Statt den Wertebereich gleichmäßig zu teilen, teile ich die **Werte selbst** in gleich große Gruppen. Die unteren 20% der Werte bekommen Farbe 1, die nächsten 20% Farbe 2 usw. Wenn ich also 100 Datenpunkte habe, kommen jeweils 20 in jede Farbklasse — egal ob die Geschwindigkeitswerte sich häufen oder nicht.

In der `..._modularized3.py`-Datei steht das so:

```python
quantile_probs = np.linspace(0, 1, n_quantiles + 1)
# → [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]

color_bins = np.quantile(color_values, quantile_probs)
# → die Werte an diesen Prozentil-Grenzen, z.B. [0, 5, 12, 35, 70, 130]
# Heißt: 20% der Daten sind <= 5 km/h, 40% sind <= 12 km/h, usw.

quantile_indices = np.searchsorted(color_bins[1:-1], df[color_by], side='right')
# Für jeden Wert: in welche Klasse (0-4) gehört er?

color_vals_norm = quantile_indices / (n_quantiles - 1)
# Auf [0, 1] normalisieren, das will Plotly als Farbeingabe.
```

Was hier passiert: `np.quantile` berechnet die Klassengrenzen aus den Daten. `np.searchsorted` ordnet jeden Wert einer Klasse zu — vergleicht ihn mit allen Grenzen und gibt den passenden Index zurück. Funktioniert — aber das ist Marke Eigenbau.

### Was sauberer gewesen wäre

`pandas.qcut`. Tut **genau das Gleiche** in einer Zeile:

```python
color_vals_norm = pd.qcut(df[color_by], q=5, labels=False) / 4
# labels=False gibt Indizes 0-4 zurück; / 4 normalisiert auf [0, 1]
```

`qcut` heißt "quantile cut" und ist die offizielle pandas-Funktion für genau dieses Problem. Vorteile gegenüber meinem Eigenbau:

1. **Eine Zeile** statt zwanzig
2. **NaN-Handling automatisch** — `qcut` gibt für NaN-Eingabe NaN zurück. Mein Eigenbau mit `searchsorted` ordnet NaN stillschweigend in die höchste Klasse ein (stiller Bug, der nur deshalb nie auftrat, weil das Filtern davor NaNs wegnimmt).
3. **Konventionell** — jeder Pandas-Nutzer erkennt es sofort.

**Verwandte Funktion:** `pd.cut(values, bins=5)` macht *lineares* Binning (gleich große Intervalle im Wertebereich). Genau das, was ich oben als "Erstversuch" beschrieben habe und was bei schiefer Verteilung schlecht aussieht.

**Merke:** `qcut` = Quantile (gleich viele Werte pro Klasse). `cut` = Cut by Value (gleich große Wertebereiche pro Klasse).

---

## 2. Achsenmaßstäbe in 3D — Warum die Höhe nicht zu sehen war

### Was ich machen wollte

Den Track als Linie in 3D, aber mit einer kleinen "Wand" zur Grundebene runter (Höhe als Balken). Das ergibt ein dreidimensionales Balkendiagramm entlang des Tracks. Höhe sollte gut sichtbar sein.

### Was ich zuerst probiert habe

Plotly mit `aspectmode='data'` benutzt. Das heißt: "skaliere die Achsen so, dass eine Längeneinheit auf jeder Achse gleich lang erscheint" — also realistische Proportionen. Klingt richtig.

**Warum es nicht aussah wie erwartet:** Lat/Lon-Werte sind in Grad (z.B. 50.55 bis 50.17 = 0.38°), Höhe in Metern (z.B. 100 bis 350 m). Plotly nimmt die nominellen Werte. 0.38 Grad und 250 Meter — die Höhe erscheint als winziger Strich, weil 250 viel größer ist als 0.38. Aber: 0.38 Grad **bedeuten** in Wirklichkeit ~42 km, also 42000 m. Verglichen damit sind 250 m Höhenunterschied tatsächlich klein.

Das ist also kein Bug — die Darstellung ist *korrekt* maßstabsgetreu, nur visuell unbefriedigend.

### Was funktioniert hat (in Anführungszeichen)

`directional_lat/lon` mit `* 111000` skaliert. Das ist näherungsweise "Meter pro Grad" am Äquator. Damit sind alle drei Achsen in Metern, und 250 m Höhe gegen 42000 m Lat ist immer noch klein — aber jetzt zumindest realistisch.

Eigentlich wollte ich aber nicht "realistisch klein", sondern "übertrieben groß", damit man die Höhenunterschiede sieht. Der `*111000`-Trick hat das Problem nicht gelöst — er hat nur die Einheiten vereinheitlicht.

**Subtiles Problem:** Der Faktor 111000 stimmt nur für Lat (1° Lat ≈ 111 km, immer). Für Lon stimmt er **nur am Äquator**; in mittleren Breiten ist 1° Lon kürzer (~70 km bei 50° Breite, weil Längengrade zum Pol hin zusammenlaufen). Heißt: meine Tracks sind in der Lon-Richtung leicht gestreckt dargestellt.

### Was sauberer gewesen wäre

Plotly bietet genau für diesen Zweck `aspectmode='manual'` mit explizitem `aspectratio`:

```python
fig.update_layout(
    scene=dict(
        aspectmode='manual',
        aspectratio=dict(x=1, y=1, z=10)  # Höhe 10× überhöht
    )
)
```

Das nennt sich **Vertical Exaggeration** und ist der Standardansatz in der Geländedarstellung — Atlanten und Geographie-Bücher übertreiben die Höhe routinemäßig um Faktor 5–20×, damit Berge sichtbar werden.

Vorteile:
1. Eingangsdaten bleiben in Grad — keine Skalierung in Aufbereitung nötig
2. Z-Faktor ist explizit und konfigurierbar — nicht "irgendeine Zahl, die okay aussah"
3. Die x/y-Verzerrung durch cos(Breitengrad) ist immer noch da, aber bei Tracks im Bereich von wenigen Kilometern fällt das nicht auf
4. Wenn man später echte Maßstabstreue will, ersetzt man sie durch eine Projektion (z.B. UTM via `utm.from_latlon` — das wird in `terrain_visualization.py` für die PyVista-Darstellung schon so gemacht)

**Merke:** `aspectmode='data'` heißt "echte Proportionen" und ist für Tracks unbrauchbar. `aspectmode='manual'` mit `aspectratio` ist die Lösung. Bei UTM-Projektion wären alle drei Achsen in Metern und `aspectmode='data'` würde mit Z-Übertreibung Sinn machen — siehe Kapitel 5.

---

## 3. GSV-Sätze — Multi-Sentence-Aggregation

### Was ich machen wollte

Eine Liste aller aktuell gesehenen Satelliten mit ihren Eigenschaften (PRN-Nummer, Elevation, Azimuth, Signalstärke). Daraus wird ein Polar-Diagramm gezeichnet — Himmelskuppel von oben gesehen, jeder Satellit ein Punkt.

### Warum das tricky ist

NMEA-Satz GSV kann nur 4 Satelliten pro Zeile transportieren. Bei 12 sichtbaren Satelliten verteilt der Empfänger das auf **3 Zeilen mit gleichem Timestamp**:

```
$GPGSV,3,1,12,...,...,...,...   ← 3 Sätze insgesamt, das ist Satz 1, 12 Satelliten total
$GPGSV,3,2,12,...,...,...,...   ← Satz 2
$GPGSV,3,3,12,...,...,...,...   ← Satz 3
```

Will man die volle Satellitenliste, muss man die drei Zeilen zusammenführen.

### Was ich gemacht habe

Im aktuellen Code passiert die Aggregation **erst in `vis_sat.py`** zur Laufzeit:
- DataFrame enthält pro GSV-Satz eine Zeile mit `gsv_sv_1_prn`...`gsv_sv_4_prn` (max. 4 Satelliten flach pro Zeile)
- `vis_sat.py` sucht zur Visualisierung alle GSV-Zeilen mit gleichem Timestamp und kombiniert deren Daten

Das funktioniert, hat aber zwei Probleme:

1. **Spalten-Verschwendung:** Pro Zeile sind 16 Spalten (4 Sätze × {prn, elevation, azimuth, snr}) reserviert — meist sind nur die ersten 4 belegt
2. **Suche zur Anzeigezeit:** Jedes Modul, das Satellitendaten will, muss die Aggregation selbst nochmal machen

### Was sauberer gewesen wäre (und was beim Refactor gemacht wird)

Die Aggregation gehört in `process_nmea`, **bevor** das DataFrame gebaut wird.

**Wichtige Eigenheit von GSV:** GSV-Sätze haben **keinen eigenen Timestamp** im NMEA-Stream. Das macht die Gruppierung etwas komplizierter als ich zunächst dachte. Konkretes Vorgehen:

1. pynmea2-Parsen wie bisher → Liste von Messages in der Reihenfolge, in der sie im File standen
2. Beim Durchlaufen der Messages den **zuletzt gesehenen Timestamp** mitführen (von RMC oder GGA)
3. GSV-Sätze nach `(zuletzt gesehener Timestamp, talker_id, num_messages, num_sv_in_view)` gruppieren — die letzten beiden Felder identifizieren eine Multi-Sentence-Group eindeutig
4. Pro Gruppe alle `sv_tuples` zusammenführen → eine Liste von Dicts
5. Eine einzige DataFrame-Zeile mit Spalte `gsv_satellites = [{prn, elevation, azimuth, snr}, ...]`

**Edge case** — das Test-Logfile enthält tatsächlich:
```
$GPGSV,1,1,00*79
```
"1 Satz total, ich bin Satz 1, 0 Satelliten total" — also leere Liste. Der Aggregator muss das schadlos überstehen (`gsv_satellites = []`).

**Warum `talker_id` mit in den Schlüssel?** Bei Multi-Constellation (GPS + GLONASS + Galileo) sendet jedes System eigene GSV-Sätze:

- `$GPGSV` — GPS-Satelliten
- `$GLGSV` — GLONASS-Satelliten
- `$GAGSV` — Galileo-Satelliten

Die haben oft denselben Timestamp aber gehören nicht zusammen. Wenn man nur nach Timestamp gruppiert, mischt man die Konstellationen, was sich in falschen PRN-Nummern äußert (PRNs sind nur **innerhalb** einer Konstellation eindeutig).

**Aktueller Empfänger** kann das noch nicht — alle GSV sind `$GPGSV`. Aber der nächste wird Multi-Constellation, deshalb gleich richtig.

---

## 4. Geschwindigkeitsberechnung — defensiv vs. kompakt

### Was ich machen wollte

Aus der GPS-Position die "echte" Geschwindigkeit über Grund berechnen (geodätische Distanz zwischen aufeinanderfolgenden Punkten / Zeitdifferenz). Das ergibt ein zweites Geschwindigkeitssignal neben dem RMC-Wert vom Empfänger — beide vergleichbar als Sanity-Check.

### Zwei Implementierungen, beide funktional korrekt

**Variante A: kompakt (in `prepare_data_modular.py`)** — sammelt alle Werte in Listen, hängt sie am Ende ans DataFrame an.

```python
distances = [0.0]
speeds_geodesic_kmh = [0.0]

for i in range(1, len(df_pos)):
    dist = geodesic((lat_prev, lon_prev), (lat_curr, lon_curr)).meters
    time_diff = (ts_curr - ts_prev).total_seconds()
    distances.append(dist)
    speeds_geodesic_kmh.append(dist / time_diff * 3.6 if time_diff > 0 else 0)

df_pos['distance_m'] = distances
df_pos['speed_geodesic_kmh'] = speeds_geodesic_kmh
```

**Variante B: defensiv (in `distance_speed_improved.py`)** — iteriert direkt über das DataFrame, schreibt in vorhandene Zeilen, prüft auf NaN, prüft auf Konflikte beim Schreiben.

```python
for i in range(1, len(df)):
    prev = df.iloc[i - 1]
    curr = df.iloc[i]

    if (pd.isna(prev['directional_latitude']) or pd.isna(curr['directional_latitude']) or ...):
        continue  # Skip bei unvollständigen Daten

    dist = geodesic((prev[...], prev[...]), (curr[...], curr[...])).meters
    time_s = (curr.name - prev.name).total_seconds()
    speed = dist / time_s * 3.6 if time_s > 0 else 0.0

    update_with_conflict_check(df, curr.name, {
        'distance_m': dist,
        'speed_geodesic_kmh': speed
    })  # Warnt, wenn der Wert schon belegt ist
```

### Welche ist "besser"?

**Variante A** ist:
- Schneller (Listen-Anhängen ist O(1), `df.at[i, col] = x` in Variante B ist langsamer)
- Lesbarer
- Aber: bricht zusammen, wenn Eingabedaten NaN-Lücken haben

**Variante B** ist:
- Robuster (NaN-Checks, Konflikterkennung)
- Defensiver (überspringt einfach unvollständige Zeilen statt zu crashen)
- Aber: langsamer, mehr Code, und die Konfliktprüfung war vermutlich nie nötig (ich erinnere mich an keine Konflikt-Warnung im Output)

**Refactor-Entscheidung:** Variante A behalten, aber die NaN-Checks aus Variante B übernehmen. Die Konfliktprüfung weglassen — der Filter sorgt dafür, dass keine Zeilen doppelt geschrieben werden.

### Was ich nicht gewusst hätte

Die "kompakte" Variante hat noch einen kleinen Stilfehler — der allererste Eintrag wird auf den zweiten gesetzt:

```python
if len(speeds_geodesic_kmh) > 1:
    speeds_geodesic_kmh[0] = speeds_geodesic_kmh[1]
```

Das ist Kosmetik (damit der Plot nicht mit "0" anfängt). In sauberer Form würde man stattdessen `NaN` setzen — Plotly stellt NaN als "kein Punkt" dar, was ehrlicher ist als "wir tun so, als wüssten wir den Wert".

---

## 5. Koordinaten-Projektionen — Grad, Meter, UTM

### Was ich machen wollte

GPS-Positionen sind in (Lat, Lon)-Grad. Für viele Berechnungen (Distanz, Visualisierung in Metern) braucht man eine Umrechnung in ein lokales kartesisches System.

### Was ich gemacht habe (drei verschiedene Wege)

**Weg 1: Geodätische Distanz**
```python
from geopy.distance import geodesic
dist = geodesic((lat1, lon1), (lat2, lon2)).meters
```
Hier rechnet die Bibliothek auf dem Ellipsoid die echte Distanz. **Korrekt für Distanzberechnungen.** Aber: gibt nur einen Skalar zurück, nicht zwei Koordinaten — kann ich nicht zum Zeichnen verwenden.

**Weg 2: Quick-and-Dirty `* 111000`**
```python
df['lat_meters'] = df['directional_latitude'] * 111000
df['lon_meters'] = df['directional_longitude'] * 111000
```
Funktioniert für Lat (immer ~111 km/Grad), aber für Lon nur am Äquator. In Hessen ist 1° Lon ~70 km, also bekomme ich eine **Verzerrung in West-Ost-Richtung um Faktor 1.6×**. Für eine Visualisierung im Bereich weniger Kilometer ist das egal, für genauere Sachen nicht.

**Weg 3: UTM-Projektion**
```python
import utm
x, y, zone, letter = utm.from_latlon(lat, lon)
```
Wird in `terrain_visualization.py` für die PyVista-Darstellung verwendet. UTM ist ein metrisches Projektionssystem, das die Erde in 60 Längenstreifen ("Zonen") aufteilt und jeden in eine Mercator-Projektion umrechnet. Innerhalb einer Zone (~6° breit) sehr genau.

### Was ich beim Refactor nehme

- **Distanzen rechnen:** weiter mit `geodesic` — das ist exakt
- **3D-Plotly-Visualisierung:** unskaliert in Grad lassen, Höhe via `aspectratio` überhöhen (siehe Kapitel 2)
- **PyVista-Terrain:** UTM (wie schon jetzt) — dort sind alle drei Achsen in Metern und Plotting in Metern macht Sinn
- **Wenn ich die Pipeline jemals "wissenschaftlich sauber" haben will:** alles auf UTM umstellen, dann sind alle Berechnungen in Metern und `aspectmode='data'` im Plotly liefert echte Geometrie

**Merke:**
- `*111000` ist die "Notlösung" — funktioniert nur für Lat, verzerrt Lon, aber für Visualisierung in der Nähe okay
- `geodesic` ist exakt für Distanzen, aber gibt keine Koordinaten
- UTM ist der Standard für lokale metrische Berechnung — ein bisschen Overhead, aber sauber

---

## 6. GPX-Parsing — gpxpy vs. reines XML

### Was ich machen wollte

GPX-Dateien (von Smartphones, OSM Tracker, etc.) parsen, um sie als zweiten Track-Datensatz neben NMEA zu haben.

### Was ich zuerst probiert habe — gpxpy

```python
import gpxpy
with open(path) as f:
    gpx = gpxpy.parse(f)
for track in gpx.tracks:
    for segment in track.segments:
        for point in segment.points:
            ...
```

`gpxpy` ist die offensichtliche Wahl — eine Bibliothek genau für diesen Zweck. Funktioniert für Standard-GPX, aber ich hatte zwei wiederkehrende Probleme:

1. **Zeitstempel-Behandlung war inkonsistent** — manchmal kam ein `datetime`-Objekt zurück, manchmal ein String, abhängig vom GPX-Dialekt. Workaround mit `dateutil.parser.parse`.
2. **`speed`-Element in GPX-Extensions** wurde nicht zuverlässig erkannt. OSM Tracker schreibt `<speed>` in einen `<extensions>`-Block, der nicht zum Standard-GPX gehört. `gpxpy.point.speed` war oft None, obwohl der Wert in der Datei stand.

Die `improved_gpx_parser*.py`-Reihe waren Versuche, diese Probleme zu umgehen — mit Fallback auf XML-Parsing für die Extensions und manuellem Zeitstempel-Parsing.

### Was funktioniert hat — reines XML

```python
import xml.etree.ElementTree as ET
tree = ET.parse(path)
root = tree.getroot()
ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}
for trkpt in root.findall('.//gpx:trkpt', ns):
    lat = float(trkpt.get('lat'))
    ...
```

Direkt mit `xml.etree.ElementTree`. Mehr Code, aber **volle Kontrolle**:
- Zeitstempel-Parsing manuell, verlässlich
- Extensions explizit angesprochen
- Keine "Magie" der Bibliothek

Das ist die `gpx_parser_xml*.py`-Reihe. Die finale Version `xml7.py` hat dann noch Duplikat-Behandlung dazubekommen (manche GPX-Dateien haben mehrere Trackpoints mit identischem Timestamp — passiert bei Apps, die Hochfrequenz-Logging machen).

### Was ich gelernt habe

**Spezialisierte Bibliotheken sind nicht immer die beste Wahl**, vor allem wenn:
1. Die Datenformate dialekt-abhängig sind (GPX-Extensions, NMEA-Hersteller-Erweiterungen)
2. Die Bibliothek ihre eigene Vorstellung von "richtigem Verhalten" hat, die mit deiner kollidiert

Reines XML-Parsing ist mehr Code, aber **vorhersehbar**. Und in einer Welt, in der ich GPX-Dateien aus verschiedenen Quellen kombiniere, ist Vorhersehbarkeit wichtiger als Bequemlichkeit.

**Fürs nächste Mal:** Bei strukturierten Formaten (XML, JSON) zuerst mit Standard-Lib parsen — `ElementTree`, `json`. Spezialbibliotheken nur, wenn die Standardlösung sich als zu mühsam erweist. **Nicht andersrum.**

---

## 7. DataFrame-Schema — von "alle Felder flach" zu "präfixiert nach Satz-Typ"

### Was ich zuerst gemacht habe

Erste Version: jedes pynmea2-Feld wird mit seinem eigenen Namen ins DataFrame geschrieben. Das gibt Spalten wie:

| msg_type | latitude | longitude | gps_quality | speed_knots | altitude |
|---|---|---|---|---|---|
| RMC | 50.55 | 9.68 | NaN | 5.2 | NaN |
| GGA | 50.55 | 9.68 | 1 | NaN | 335.9 |
| VTG | NaN | NaN | NaN | 5.1 | NaN |

Probleme:
1. **`speed_knots`** kommt aus RMC und VTG — beide schreiben in dieselbe Spalte. Wenn man wissen will "ist das jetzt der RMC-Wert oder der VTG-Wert?", muss man auf `msg_type` schauen
2. **`latitude`** kommt aus RMC und GGA. Sind beide Werte für denselben Timestamp gleich? Wer weiß. Nicht aus dem DataFrame ablesbar.
3. Wenn ich später noch GLL-Sätze (auch Lat/Lon) parsen würde, würde es schlimmer

### Was ich dann gemacht habe — präfixierte Spalten

| sentence_type | directional_latitude | directional_longitude | gga_gps_quality | rmc_speed_knots | vtg_speed_knots | gga_altitude |
|---|---|---|---|---|---|---|
| RMC | 50.55 | 9.68 | NaN | 5.2 | NaN | NaN |
| GGA | 50.55 | 9.68 | 1 | NaN | NaN | 335.9 |
| VTG | NaN | NaN | NaN | NaN | 5.1 | NaN |

Vorteile:
1. **Eindeutigkeit:** Jede Spalte sagt schon im Namen, woher sie kommt
2. **Vergleichbarkeit:** RMC- und VTG-Geschwindigkeit kann ich jetzt direkt nebeneinander stellen und sehen, ob sie übereinstimmen
3. **Sanity-Check-Spalten möglich:** `gga_rmc_pos_mismatch`, `gga_rmc_time_mismatch` — Flags, die auf Inkonsistenzen hinweisen

**Trade-off:** Mehr Spalten, viele NaN. Aber NaN ist billig in pandas (besonders mit nullable dtypes), und Klarheit ist viel mehr wert.

### Wann man das wieder tun würde

Wenn man Daten aus mehreren Quellen kombiniert, die **dieselben semantischen Werte** in unterschiedlichen Formaten liefern, ist Präfixieren fast immer eine gute Idee. Das gilt nicht nur für NMEA — auch für API-Responses (z.B. Aktienkurse von verschiedenen Brokern), Sensordaten, Datenbankabfragen.

Das Prinzip dahinter heißt **"data lineage"** — der Pfad von der Quelle bis ins finale Schema sollte aus dem Spaltennamen ablesbar sein.

---

## 8. Wiederverwendung von Code beim Refactor — was ich nicht reflexartig wegwerfen sollte

Beim Aufräumen habe ich Versuchung, alle alten Versionen zu löschen. Aber ein paar Sachen sind erhaltenswert auch wenn sie aktuell unbenutzt sind:

### `safe_convert.py`

```python
def safe_convert(value: Any, conversion_func, default=None) -> Any:
    if value is None or value == '':
        return default
    try:
        return conversion_func(value)
    except (ValueError, TypeError):
        return default
```

Generisch nützlich. Nicht spezifisch für NMEA. Beim Refactor in `process_nmea_korrigiert.py` wird sowas inline gemacht (`_safe_get_attribute`), aber das `safe_convert`-Pattern ist sauberer. **Nicht löschen** — als Utility behalten.

### `debug_dataframe_issues` aus `fixed_distance_speed_-_not.py`

```python
def debug_dataframe_issues(df: pd.DataFrame, sample_size: int = 5):
    print(f"Shape: {df.shape}")
    print(f"Index type: {type(df.index)}")
    print(df.isnull().sum())
    if df.index.duplicated().any():
        print(f"⚠️ {df.index.duplicated().sum()} duplicate timestamps")
    ...
```

Eine Diagnose-Funktion, die schnell die häufigsten Probleme zeigt. Sollte in ein `debug_utils.py` umziehen, nicht weggeworfen.

### Quantil-Print-Diagnose in `..._modularized3.py`

Die langen Print-Schleifen, die zeigen, wie sich die Werte auf die Quantil-Bereiche verteilen — die sind unschön für Production, aber **extrem wertvoll beim Debuggen**. Statt löschen: in einen `verbose=False`-Parameter packen, der per Default aus ist.

---

## 9. Was ich beim nächsten Refactor anders machen würde

1. **Immer mit einem Test-Logfile anfangen.** Beim Bauen Hot-Reload, Daten durchschicken, sehen ob's geht. Ohne Daten sind die ganzen `if/else`-Pfade nicht abgedeckt — ich habe Code geschrieben für Fälle, die nie auftraten, und Fälle vergessen, die immer auftraten.

2. **Eine Spaltennamens-Konvention vorab festlegen.** Ich habe das Schema dreimal umgestellt (jedes Mal mit "Hilfs-Modulen", die alte Namen erwarten und brechen). Nächstes Mal: einmal `colspec.md` schreiben, dann implementieren.

3. **Einstiegspunkt zuerst.** Ich habe vier `__main__`-Versionen, weil ich zwischen Modulen hin- und hergesprungen bin und am Ende nicht mehr wusste, was zusammenpasst. Besser: eine `__main__.py` von Anfang an, die ich Schritt für Schritt befüllt mit "TODO"-Kommentaren wo Module noch fehlen.

4. **Erst Standard-Lösungen probieren** (`pd.qcut`, `aspectratio`, UTM) und nur ausweichen, wenn die nicht reichen. Mein Reflex war oft, "ich bau mir das selbst, dann verstehe ich es" — das ist beim Lernen okay, aber dann mit einem Refactor abschließen, der den Selbstbau durch den Standard ersetzt.

5. **Versionsnamen wie `_modularized2`, `_korrigiert`, `_neu` vermeiden.** Git hat dafür Branches und Commits. In einem Jahr weiß ich nicht mehr, was "korrigiert" gegenüber "vor Korrektur durch Claude" auszeichnet — der Commit-Log könnte es mir sagen, der Dateiname tut es nicht.

---

## 10. Was die Test-Daten gezeigt haben (wichtig für die Erinnerung)

Beim Wiederöffnen des Projekts habe ich die Pipeline einmal durchlaufen lassen. Was ich vorher nicht mehr wusste, jetzt aber:

- **Das NMEA-Test-File** (`nmea_testlog.txt`) ist nur ein **68-Sekunden-Funktionstest**, kein richtiger Tour-Track. 30 Pre-Fix-Zeilen am Anfang werden vom Filter wegen RMC-Status `V` entfernt, danach 580 saubere Sample-Zeilen mit 10 Hz Rate.
- Der GPS-Empfänger ist ein **GPS-Testempfänger** (per `$PGRMT`-Satz identifiziert) — das war der single-constellation-Empfänger, **nicht der neue, der noch in der Post ist**.
- **Das GPX-Test-File** ist eine echte Flugzeug-Tour (Kleinflugzeug, ~111 km/h Reise) mit einer GPS-Flugzeugapp aufgezeichnet. Höhenbereich 210–1193 m. Track heißt "Beispiel-Flugroute".
- **Doppelte Timestamps in GPX sind nicht selten, sondern systematisch:** ~10% der Trackpoints (127 von 1271). Der `xml7`-Patch ist also wirklich notwendig, nicht überengineered.
- **GSV im NMEA-Stream hat keinen eigenen Timestamp** — die Aggregation muss über die zeitliche Reihenfolge der Messages gehen, nicht über einen expliziten Schlüssel. Das war mein erster Plan, der so nicht funktioniert.
- **Edge case `$GPGSV,1,1,00*79`** kommt im Test-File tatsächlich vor: "0 Satelliten in View". Der Aggregator muss das schadlos überstehen (leere Liste, kein Crash).

Das alles zusammen: Die Test-Dateien sind klein, aber decken die wichtigsten Edge Cases ab. Für einen gründlichen Pipeline-Test nach dem Refactor wäre ein längerer NMEA-Track vom neuen Multi-Constellation-Empfänger wertvoll.
