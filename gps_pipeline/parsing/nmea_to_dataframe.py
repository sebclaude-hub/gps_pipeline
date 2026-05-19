"""Konvertiert pynmea2-Messages in einen Roh-DataFrame nach Schema A.

Schema A — eine Zeile pro NMEA-Satz (bzw. pro GSV-Multi-Sentence-Group nach
Aggregation). Spalten siehe Refactor-Plan, Abschnitt "Schemata".

Index: Standard-RangeIndex (0..n-1). ``timestamp_utc`` ist eine ganz normale
Spalte, kein Index.

Verantwortlichkeiten dieses Moduls:
  * Pro Message-Typ die relevanten Felder mit eindeutigen, präfixierten
    Spaltennamen extrahieren.
  * Datum aus RMC durch GGA und VTG weitertragen (GGA/VTG haben nur Zeit).
  * Latitude/Longitude mit Vorzeichen je nach Richtung versehen
    (``directional_latitude``, ``directional_longitude``).
  * GSV-Multi-Sentence-Groups über den Aggregator zu Listen zusammenführen
    und als eine Zeile mit Spalte ``gsv_satellites`` ablegen.
  * GGA/RMC-Konsistenz prüfen und Flags setzen.
  * Type-Konvertierung am Ende für effiziente Speichernutzung.
"""

import datetime as _dt
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import pynmea2

from ..config import POSITION_MISMATCH_TOLERANCE_DEG
from ..utils.safe_convert import safe_convert
from ..processing.gsv_aggregate import aggregate_gsv


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _directional(coord: Optional[float], direction: Optional[str]) -> Optional[float]:
    """Latitude/Longitude mit Vorzeichen je nach Richtung versehen.

    N und E sind positiv, S und W sind negativ.
    Gibt None zurück, wenn coord oder direction fehlt.
    """
    if coord is None or direction is None:
        return None
    if direction in ("S", "W"):
        return -float(coord)
    return float(coord)


def _combine_date_time(date: Optional[_dt.date],
                       time: Optional[_dt.time]) -> Optional[_dt.datetime]:
    """Erzeugt einen UTC-Datetime aus Datum und Zeit. Gibt None bei fehlendem Wert."""
    if date is None or time is None:
        return None
    return _dt.datetime.combine(date, time, tzinfo=_dt.timezone.utc)


# ---------------------------------------------------------------------------
# Pro-Satz-Typ-Extraktoren
# ---------------------------------------------------------------------------

def _extract_rmc(msg: pynmea2.types.talker.RMC) -> Dict[str, Any]:
    """RMC-Felder zu Schema-A-Spalten extrahieren."""
    return {
        "sentence_type": "RMC",
        "talker_id": msg.talker,
        "timestamp_utc": _combine_date_time(msg.datestamp, msg.timestamp),
        "directional_latitude": _directional(
            safe_convert(msg.latitude, float), getattr(msg, "lat_dir", None)),
        "directional_longitude": _directional(
            safe_convert(msg.longitude, float), getattr(msg, "lon_dir", None)),
        "rmc_status": getattr(msg, "status", None),
        "rmc_speed_knots": safe_convert(getattr(msg, "spd_over_grnd", None), float),
        "rmc_true_course": safe_convert(getattr(msg, "true_course", None), float),
        "rmc_mag_variation": safe_convert(getattr(msg, "mag_variation", None), float),
    }


def _extract_gga(msg: pynmea2.types.talker.GGA,
                 last_rmc_date: Optional[_dt.date]) -> Dict[str, Any]:
    """GGA-Felder extrahieren. Datum kommt vom letzten RMC, weil GGA nur Zeit hat."""
    return {
        "sentence_type": "GGA",
        "talker_id": msg.talker,
        "timestamp_utc": _combine_date_time(last_rmc_date, msg.timestamp),
        "directional_latitude": _directional(
            safe_convert(msg.latitude, float), getattr(msg, "lat_dir", None)),
        "directional_longitude": _directional(
            safe_convert(msg.longitude, float), getattr(msg, "lon_dir", None)),
        "gga_gps_quality": safe_convert(getattr(msg, "gps_qual", None), int),
        "gga_num_sats": safe_convert(getattr(msg, "num_sats", None), int),
        "gga_hdop": safe_convert(getattr(msg, "horizontal_dil", None), float),
        "gga_altitude": safe_convert(getattr(msg, "altitude", None), float),
        "gga_geo_separation": safe_convert(getattr(msg, "geo_sep", None), float),
    }


def _extract_vtg(msg: pynmea2.types.talker.VTG,
                 last_rmc_date: Optional[_dt.date],
                 last_time: Optional[_dt.time]) -> Dict[str, Any]:
    """VTG-Felder extrahieren. VTG hat weder Datum noch eigene Zeit — beides
    kommt aus dem zuletzt gesehenen RMC/GGA.
    """
    return {
        "sentence_type": "VTG",
        "talker_id": msg.talker,
        "timestamp_utc": _combine_date_time(last_rmc_date, last_time),
        "vtg_speed_knots": safe_convert(getattr(msg, "spd_over_grnd_kts", None), float),
        "vtg_speed_kmph": safe_convert(getattr(msg, "spd_over_grnd_kmph", None), float),
        "vtg_true_track": safe_convert(getattr(msg, "true_track", None), float),
        "vtg_mag_track": safe_convert(getattr(msg, "mag_track", None), float),
    }


def _extract_gsa(msg: pynmea2.types.talker.GSA,
                 last_rmc_date: Optional[_dt.date],
                 last_time: Optional[_dt.time]) -> Dict[str, Any]:
    """GSA-Felder extrahieren. GSA hat keinen eigenen Timestamp."""
    return {
        "sentence_type": "GSA",
        "talker_id": msg.talker,
        "timestamp_utc": _combine_date_time(last_rmc_date, last_time),
        "gsa_fix_type": safe_convert(getattr(msg, "mode_fix_type", None), int),
        "gsa_pdop": safe_convert(getattr(msg, "pdop", None), float),
        "gsa_hdop": safe_convert(getattr(msg, "hdop", None), float),
        "gsa_vdop": safe_convert(getattr(msg, "vdop", None), float),
    }


# ---------------------------------------------------------------------------
# GGA/RMC-Konsistenzprüfung
# ---------------------------------------------------------------------------

def _check_gga_rmc_consistency(df: pd.DataFrame,
                               position_tol: float = POSITION_MISMATCH_TOLERANCE_DEG
                               ) -> pd.DataFrame:
    """Markiert GGA-Zeilen, deren Position/Zeit von der zugehörigen RMC abweicht.

    Setzt die Spalten ``gga_rmc_pos_mismatch`` und ``gga_rmc_time_mismatch``
    auf GGA-Zeilen. Vergleichspartner ist die RMC-Zeile mit identischem
    Timestamp (also im gleichen Sample-Zyklus).

    Beide Spalten sind als nullable Boolean (pandas BooleanDtype) angelegt;
    bei Sätzen ohne Vergleichspartner bleibt der Wert NA.
    """
    df = df.copy()
    df["gga_rmc_pos_mismatch"] = pd.NA
    df["gga_rmc_time_mismatch"] = pd.NA

    # Wir bauen eine Lookup-Map: timestamp -> (lat, lon) der RMC mit Status A.
    rmc_mask = (df["sentence_type"] == "RMC") & (df["rmc_status"] == "A")
    rmc_subset = df.loc[rmc_mask, ["timestamp_utc", "directional_latitude",
                                    "directional_longitude"]]
    rmc_subset = rmc_subset.dropna(subset=["timestamp_utc"])
    # Bei mehreren RMC mit gleichem Timestamp (sollte nicht passieren) nehmen wir
    # den ersten — ist die einfachste Strategie und entspricht keep="first".
    rmc_subset = rmc_subset.drop_duplicates(subset="timestamp_utc", keep="first")
    rmc_map = rmc_subset.set_index("timestamp_utc")

    gga_mask = (df["sentence_type"] == "GGA")
    for idx in df.index[gga_mask]:
        ts = df.at[idx, "timestamp_utc"]
        if pd.isna(ts) or ts not in rmc_map.index:
            continue
        rmc_lat = rmc_map.at[ts, "directional_latitude"]
        rmc_lon = rmc_map.at[ts, "directional_longitude"]
        gga_lat = df.at[idx, "directional_latitude"]
        gga_lon = df.at[idx, "directional_longitude"]

        # Position: NaN-Vergleiche brauchen Sonderbehandlung
        if pd.isna(rmc_lat) or pd.isna(gga_lat) or pd.isna(rmc_lon) or pd.isna(gga_lon):
            pos_mismatch = pd.NA
        else:
            pos_mismatch = bool(
                abs(rmc_lat - gga_lat) > position_tol
                or abs(rmc_lon - gga_lon) > position_tol
            )

        # Zeit: durch den Map-Lookup ist der Timestamp definitionsgemäß identisch,
        # also kann kein Mismatch sein. Wenn wir hier sind, sind beide Timestamps
        # gleich (RMC wurde ja über ts gesucht).
        time_mismatch = False

        df.at[idx, "gga_rmc_pos_mismatch"] = pos_mismatch
        df.at[idx, "gga_rmc_time_mismatch"] = time_mismatch

    return df


# ---------------------------------------------------------------------------
# Type-Konvertierung
# ---------------------------------------------------------------------------

# Datentypen für Speichereffizienz und korrekte Semantik.
# Pandas' nullable Types (Int8, UInt8, Float32) erlauben NA, was wir brauchen.
_DTYPE_MAP = {
    "sentence_type": "category",
    "talker_id": "category",
    "rmc_status": "category",
    "gga_gps_quality": "UInt8",
    "gga_num_sats": "UInt8",
    "gsa_fix_type": "UInt8",
    "rmc_speed_knots": "Float32",
    "rmc_true_course": "Float32",
    "rmc_mag_variation": "Float32",
    "vtg_speed_knots": "Float32",
    "vtg_speed_kmph": "Float32",
    "vtg_true_track": "Float32",
    "vtg_mag_track": "Float32",
    "gga_hdop": "Float32",
    "gga_altitude": "Float32",
    "gga_geo_separation": "Float32",
    "gsa_pdop": "Float32",
    "gsa_hdop": "Float32",
    "gsa_vdop": "Float32",
    "gsv_num_sv_in_view": "UInt8",
    "gga_rmc_pos_mismatch": "boolean",
    "gga_rmc_time_mismatch": "boolean",
    # directional_latitude/longitude bleiben float64 — Präzision matters
    # gsv_satellites bleibt object (Liste von Dicts)
}


def _apply_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Wendet die Standard-Datentypen an. Fehlende Spalten werden ignoriert."""
    for col, dtype in _DTYPE_MAP.items():
        if col in df.columns:
            try:
                df[col] = df[col].astype(dtype)
            except (TypeError, ValueError) as e:
                # Schwer zu konvertierende Spalten zurücklassen statt zu crashen
                print(f"Warnung: Konnte Spalte {col!r} nicht auf {dtype} casten: {e}")
    return df


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def build_dataframe(messages: List[pynmea2.NMEASentence]) -> pd.DataFrame:
    """Konvertiert pynmea2-Messages in einen Roh-DataFrame nach Schema A.

    Eine Zeile entspricht einem NMEA-Satz, mit Ausnahme von GSV: Multi-Sentence-
    Groups werden zu **einer** Zeile mit Spalte ``gsv_satellites`` aggregiert.

    Parameters
    ----------
    messages : list of pynmea2.NMEASentence
        Geparste NMEA-Sätze in Stream-Reihenfolge.

    Returns
    -------
    pd.DataFrame
        Schema-A-DataFrame. ``timestamp_utc`` ist eine Spalte, kein Index.
        Standard-RangeIndex 0..n-1.
    """
    rows: List[Dict[str, Any]] = []

    # State, der durch den Stream geführt wird:
    last_rmc_date: Optional[_dt.date] = None
    last_time: Optional[_dt.time] = None

    for msg in messages:
        if isinstance(msg, pynmea2.types.talker.RMC):
            if msg.datestamp:
                last_rmc_date = msg.datestamp
            if msg.timestamp:
                last_time = msg.timestamp
            rows.append(_extract_rmc(msg))

        elif isinstance(msg, pynmea2.types.talker.GGA):
            if msg.timestamp:
                last_time = msg.timestamp
            rows.append(_extract_gga(msg, last_rmc_date))

        elif isinstance(msg, pynmea2.types.talker.VTG):
            rows.append(_extract_vtg(msg, last_rmc_date, last_time))

        elif isinstance(msg, pynmea2.types.talker.GSA):
            rows.append(_extract_gsa(msg, last_rmc_date, last_time))

        # GSV wird separat über den Aggregator behandelt — ignoriere einzelne
        # GSV-Sätze hier. Alles andere (z.B. proprietäre Sätze wie PGRMT) wird
        # stillschweigend übersprungen.

    # GSV-Aggregator: liefert eine Zeile pro Multi-Sentence-Group
    gsv_groups = aggregate_gsv(messages)
    for group in gsv_groups:
        rows.append({
            "sentence_type": "GSV",
            "talker_id": group["talker_id"],
            "timestamp_utc": group["timestamp_utc"],
            "gsv_num_sv_in_view": group["num_sv_in_view"],
            "gsv_satellites": group["satellites"],
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Timestamp-Spalte als pandas datetime mit UTC-Awareness
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True, errors="coerce")

    # Sortiere nach Timestamp (GSV-Zeilen sind ja erst am Ende angehängt worden).
    # Stabile Sortierung erhält die Reihenfolge gleicher Timestamps innerhalb der
    # ursprünglichen Gruppen.
    df = df.sort_values("timestamp_utc", kind="stable", na_position="first")
    df = df.reset_index(drop=True)

    # GGA/RMC-Mismatch-Flags setzen
    df = _check_gga_rmc_consistency(df)

    # Type-Konvertierung am Schluss, sobald alle Spalten ihren finalen Inhalt haben
    df = _apply_dtypes(df)

    print(f"DataFrame erstellt: {len(df)} Zeilen, {len(df.columns)} Spalten")
    return df
