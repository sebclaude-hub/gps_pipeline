"""KML-Datei (Google Earth gx:Track) parsen und Schema-B-DataFrame liefern.

Schema B ist das gleiche, das ``parsing/gpx.py`` und ``processing/consolidate.py``
produzieren. KML, GPX und NMEA münden also in denselben Datenstrom.

Unterstützter KML-Dialekt
-------------------------
Nur ``<gx:Track>`` mit parallelen ``<when>`` und ``<gx:coord>``-Listen wird
unterstützt — das ist das Format, das Google Earth, FlightAware und ähnliche
Tools für Bewegungstracks ausgeben.

Andere KML-Varianten (``<LineString>`` für statische Pfade ohne Zeitstempel,
``<Placemark><Point>`` für Wegpunkte, etc.) werden mit einer klaren
Fehlermeldung abgelehnt statt zu crashen.

Struktur eines gx:Track::

    <gx:Track>
      <altitudeMode>absolute</altitudeMode>
      <when>2026-03-20T09:24:34.503Z</when>
      <when>2026-03-20T09:24:36.313Z</when>
      ...
      <gx:coord>12.243432 41.775233 434</gx:coord>
      <gx:coord>12.244075 41.773727 457</gx:coord>
      ...
    </gx:Track>

``<gx:coord>`` enthält "lon lat alt", durch Leerzeichen getrennt.
``<when>`` und ``<gx:coord>`` müssen paarweise zusammenpassen (gleicher Index
ist eine Zeit-Position-Zuordnung).

Höhen-Bezug
-----------
``altitudeMode=absolute`` heißt laut KML-Spec: ellipsoidische WGS84-Höhe
oder MSL-Höhe, je nach Datenquelle. Google Earth selbst nutzt MSL (EGM96).
Bei dieser Pipeline behandeln wir den Wert wie alle anderen ``altitude_corrected``
auch — als nominell MSL/NN-bezogen. Wenn der Bezug nicht stimmt, korrigiert
der Z-Offset-Slider im React-Viewer interaktiv (oder das ``z_offset_m``-Feld
in der Schnittanweisung beim Teilen von Tracks).
"""

import xml.etree.ElementTree as ET
from typing import Optional

import numpy as np
import pandas as pd


_NS = {
    "kml": "http://www.opengis.net/kml/2.2",
    "gx": "http://www.google.com/kml/ext/2.2",
}

_SCHEMA_B_COLUMNS = [
    "timestamp_utc",
    "directional_latitude",
    "directional_longitude",
    "altitude_corrected",
    "speed_kmh",
    "speed_knots",
]


def _empty_result() -> pd.DataFrame:
    return pd.DataFrame(columns=_SCHEMA_B_COLUMNS)


def _parse_coord_text(text: str) -> Optional[tuple]:
    """Wandelt "lon lat alt" (Leerzeichen-getrennt) in (lon, lat, alt) um.

    Höhe darf fehlen; dann ist alt=None.
    """
    parts = text.strip().split()
    if len(parts) < 2:
        return None
    try:
        lon = float(parts[0])
        lat = float(parts[1])
        alt = float(parts[2]) if len(parts) >= 3 else None
        return lon, lat, alt
    except ValueError:
        return None


def parse_kml_file(kml_file_path: str) -> pd.DataFrame:
    """Liest eine KML-Datei mit ``<gx:Track>`` und gibt einen Schema-B-DataFrame zurück.

    Parameters
    ----------
    kml_file_path : str
        Pfad zur KML-Datei.

    Returns
    -------
    pd.DataFrame
        Schema-B-DataFrame. Bei Fehlern oder unsupportetem Dialekt: leerer
        DataFrame mit den Schema-B-Spalten und einer Konsolen-Meldung.
    """
    print(f"Lese KML-Daten aus {kml_file_path} ...")

    try:
        with open(kml_file_path, "r", encoding="utf-8-sig") as f:
            tree = ET.parse(f)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError, OSError) as e:
        print(f"Fehler beim Lesen/Parsen der KML-Datei: {e}")
        return _empty_result()

    # gx:Track-Elemente finden (kann mehrere geben, wir nehmen alle nacheinander)
    tracks = root.findall(".//gx:Track", _NS)
    if not tracks:
        # Klare Fehlermeldung für nicht-unterstützte Dialekte
        has_linestring = root.find(".//kml:LineString", _NS) is not None
        has_point = root.find(".//kml:Point", _NS) is not None
        if has_linestring or has_point:
            kinds = []
            if has_linestring:
                kinds.append("<LineString>")
            if has_point:
                kinds.append("<Point>")
            print(f"KML enthält keinen <gx:Track>, sondern nur {' / '.join(kinds)} "
                  f"(statischer Pfad / Wegpunkte ohne Zeitstempel). "
                  f"Dieses Format wird aktuell nicht unterstützt.")
        else:
            print(f"KML enthält keinen <gx:Track>. Dateistruktur scheint anders "
                  f"zu sein als erwartet — nicht unterstützt.")
        return _empty_result()

    # Aus allen Tracks die Punkte sammeln (mehrere Tracks → zusammenhängende
    # Liste, sortiert nach Timestamp).
    rows = []
    for track in tracks:
        whens = track.findall("kml:when", _NS)
        coords = track.findall("gx:coord", _NS)

        if len(whens) != len(coords):
            print(f"Warnung: <when>- und <gx:coord>-Listen haben unterschiedliche "
                  f"Längen ({len(whens)} vs. {len(coords)}). Track wird übersprungen.")
            continue

        for w, c in zip(whens, coords):
            if w.text is None or c.text is None:
                continue
            parsed = _parse_coord_text(c.text)
            if parsed is None:
                continue
            lon, lat, alt = parsed
            rows.append({
                "timestamp_utc": w.text,
                "directional_latitude": lat,
                "directional_longitude": lon,
                "altitude_corrected": alt if alt is not None else np.nan,
                "speed_kmh": np.nan,
                "speed_knots": np.nan,
            })

    if not rows:
        print("Keine gültigen Trackpunkte in der KML-Datei.")
        return _empty_result()

    df = pd.DataFrame(rows, columns=_SCHEMA_B_COLUMNS)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True, errors="coerce")

    # Konsistente Schema-B-Dtypes (wie in gpx.py und consolidate.py).
    for col in ("directional_latitude", "directional_longitude"):
        df[col] = df[col].astype("float64")
    for col in ("altitude_corrected", "speed_kmh", "speed_knots"):
        df[col] = df[col].astype("float32")

    n_before = len(df)
    df = df.dropna(subset=["timestamp_utc"])
    n_dropped = n_before - len(df)
    if n_dropped > 0:
        print(f"Info: {n_dropped} Punkte ohne gültigen Zeitstempel entfernt.")

    df = df.sort_values("timestamp_utc", kind="stable").reset_index(drop=True)

    # Diagnose: Duplikate
    n_dup = df["timestamp_utc"].duplicated().sum()
    if n_dup > 0:
        pct = 100 * n_dup / len(df)
        print(f"Info: {n_dup} Trackpunkte mit doppeltem Timestamp ({pct:.1f}%). "
              "Werden so belassen — nachgelagerte Module müssen damit umgehen.")

    print(f"KML gelesen: {len(df)} Trackpunkte (Schema B).")
    return df
