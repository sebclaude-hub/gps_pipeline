"""GPX-Datei (XML) parsen und direkt einen Schema-B-DataFrame ausgeben.

Schema B ist das gleiche, das ``processing/consolidate.py`` für NMEA produziert:
eine Zeile pro Timestamp, mit ``directional_latitude/longitude``,
``altitude_corrected``, ``speed_kmh``, ``speed_knots``. Heißt: GPX und NMEA
münden in denselben Datenstrom und können von ``enrich_speed`` und allen
nachfolgenden Modulen gleich behandelt werden.

Hinweise zum Format
-------------------
GPX ist ein XML-Format mit folgender Struktur::

    <trkpt lat="..." lon="...">
        <ele>...</ele>          (Höhe in m, optional)
        <time>...Z</time>       (ISO 8601 UTC)
        <speed>...</speed>      (m/s, manche Apps; OSM Tracker hat das in
                                 <extensions> stattdessen)
        <hdop>...</hdop>        (optional)
    </trkpt>

Wir unterstützen beide Varianten für ``<speed>``: als direktes Kind von
``<trkpt>`` (Skydemon, manche Geräte) und in ``<extensions>`` (OSM Tracker).

Duplikat-Behandlung
-------------------
Manche Apps loggen mehrere Trackpoints mit identischem Zeitstempel
(Skydemon: ~10% der Punkte in unseren Testdaten). Diese Duplikate werden
**nicht** automatisch verändert oder aufgebrochen — sie bleiben im
DataFrame stehen. Nachfolgende Module müssen damit umgehen
(``enrich_speed`` setzt z.B. NaN bei dt=0).
"""

import xml.etree.ElementTree as ET
from typing import Optional

import pandas as pd


_GPX_NS = {"gpx": "http://www.topografix.com/GPX/1/1"}

# Schema-B-Spalten (gleich wie processing/consolidate.py):
_SCHEMA_B_COLUMNS = [
    "timestamp_utc",
    "directional_latitude",
    "directional_longitude",
    "altitude_corrected",
    "speed_kmh",
    "speed_knots",
]


def _parse_time(time_text: Optional[str]) -> Optional[pd.Timestamp]:
    """ISO 8601 mit 'Z'-Suffix zu pandas Timestamp (UTC). None bei Fehler."""
    if not time_text:
        return None
    try:
        # pd.to_datetime versteht 'Z' direkt und liefert UTC-aware Timestamp
        return pd.to_datetime(time_text, utc=True)
    except (ValueError, TypeError):
        return None


def _find_speed_ms(trkpt: ET.Element) -> Optional[float]:
    """Geschwindigkeit in m/s aus <speed> finden, mit Fallback auf <extensions>."""
    # Variante 1: direktes Kind von <trkpt>
    speed_elem = trkpt.find("gpx:speed", _GPX_NS)
    if speed_elem is not None and speed_elem.text:
        try:
            return float(speed_elem.text)
        except ValueError:
            pass

    # Variante 2: in <extensions> (OSM Tracker)
    ext = trkpt.find("gpx:extensions", _GPX_NS)
    if ext is not None:
        # Manche Apps schreiben das speed-Tag ohne Namespace; daher beides probieren
        for path in ("gpx:speed", "speed"):
            try:
                speed_elem = ext.find(path, _GPX_NS) if path.startswith("gpx:") else ext.find(path)
            except Exception:
                continue
            if speed_elem is not None and speed_elem.text:
                try:
                    return float(speed_elem.text)
                except ValueError:
                    pass

    return None


def _parse_float_child(trkpt: ET.Element, tag: str) -> Optional[float]:
    """Hilfsfunktion: Float aus einem direkten Kind-Element holen, None wenn fehlt."""
    elem = trkpt.find(f"gpx:{tag}", _GPX_NS)
    if elem is None or not elem.text:
        return None
    try:
        return float(elem.text)
    except ValueError:
        return None


def parse_gpx_file(gpx_file_path: str) -> pd.DataFrame:
    """Liest eine GPX-Datei und gibt einen Schema-B-DataFrame zurück.

    Parameters
    ----------
    gpx_file_path : str
        Pfad zur GPX-Datei.

    Returns
    -------
    pd.DataFrame
        Schema-B-DataFrame. ``timestamp_utc`` ist eine Spalte (kein Index),
        Standard-RangeIndex 0..n-1. Bei Parse-Fehlern: leerer DataFrame mit
        den Schema-B-Spalten.
    """
    print(f"Lese GPX-Daten aus {gpx_file_path} ...")

    try:
        # encoding='utf-8-sig' frisst auch UTF-8-BOM, falls vorhanden
        with open(gpx_file_path, "r", encoding="utf-8-sig") as f:
            tree = ET.parse(f)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError, OSError) as e:
        print(f"Fehler beim Lesen/Parsen der GPX-Datei: {e}")
        return pd.DataFrame(columns=_SCHEMA_B_COLUMNS)

    rows = []
    for trkpt in root.findall(".//gpx:trkpt", _GPX_NS):
        try:
            lat = float(trkpt.get("lat"))
            lon = float(trkpt.get("lon"))
        except (TypeError, ValueError):
            continue  # Trackpoint ohne gültige Koordinaten überspringen

        elevation = _parse_float_child(trkpt, "ele")

        time_elem = trkpt.find("gpx:time", _GPX_NS)
        timestamp = _parse_time(time_elem.text if time_elem is not None else None)

        speed_ms = _find_speed_ms(trkpt)
        # Geschwindigkeiten in beide Einheiten umrechnen
        if speed_ms is not None:
            speed_kmh = speed_ms * 3.6
            speed_knots = speed_ms * 1.94384
        else:
            speed_kmh = None
            speed_knots = None

        rows.append({
            "timestamp_utc": timestamp,
            "directional_latitude": lat,
            "directional_longitude": lon,
            "altitude_corrected": elevation,
            "speed_kmh": speed_kmh,
            "speed_knots": speed_knots,
        })

    if not rows:
        print("Warnung: keine gültigen Trackpoints in der GPX-Datei.")
        return pd.DataFrame(columns=_SCHEMA_B_COLUMNS)

    df = pd.DataFrame(rows, columns=_SCHEMA_B_COLUMNS)

    # Zeitstempel als pandas datetime (UTC). Trackpoints ohne Zeit fliegen raus.
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True, errors="coerce")
    n_before = len(df)
    df = df.dropna(subset=["timestamp_utc"])
    n_dropped = n_before - len(df)
    if n_dropped > 0:
        print(f"Info: {n_dropped} Trackpoints ohne Zeitstempel entfernt.")

    # Konsistente Schema-B-Dtypes: float64 für Koordinaten (Präzision),
    # float32 für Sensordaten (Höhe, Speed) — Sensor-Auflösung rechtfertigt
    # nicht 64-bit.
    for col in ("directional_latitude", "directional_longitude"):
        df[col] = df[col].astype("float64")
    for col in ("altitude_corrected", "speed_kmh", "speed_knots"):
        df[col] = df[col].astype("float32")

    # Stabil sortieren (Original-Reihenfolge bei gleichem Timestamp bleibt erhalten)
    df = df.sort_values("timestamp_utc", kind="stable").reset_index(drop=True)

    # Duplikat-Diagnose, aber NICHT entfernen oder modifizieren:
    n_dup = df["timestamp_utc"].duplicated().sum()
    if n_dup > 0:
        pct = 100 * n_dup / len(df)
        print(f"Info: {n_dup} Trackpoints mit doppeltem Timestamp ({pct:.1f}%). "
              "Werden so belassen — nachgelagerte Module müssen damit umgehen.")

    print(f"GPX gelesen: {len(df)} Trackpoints (Schema B).")
    return df
