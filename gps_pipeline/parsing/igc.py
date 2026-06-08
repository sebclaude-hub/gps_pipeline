"""IGC-Parser (FAI-Segelflug-Logger) → Schema B.

IGC ist ein flaches Zeilenformat. Relevant sind:
  - H-Records (Header): Datum im "HFDTE"-Record, alt "HFDTE150709" oder
    neu "HFDTEDATE:150709,01" (DDMMYY).
  - B-Records (Fix): feste Spaltenstruktur:

      B HHMMSS DDMMmmm N DDDMMmmm E A PPPPP GGGGG
      0 1----6 7-----13 14 15---22 23 24 25-29 30-34

    Zeit (UTC) + Datum aus HFDTE → Zeitstempel.
    Breite/Laenge in Grad+Minuten*1000 mit Hemisphaere.
    Spalte 24: 'A' = 3D-Fix (nur diese uebernehmen).
    PPPPP = Druckhoehe, GGGGG = GNSS-Hoehe (beide in Meter).

Hoehe: GNSS-Hoehe bevorzugt (WGS84-ellipsoidisch — ~46 m ueber NN bei
50°N; der z-Offset-Regler im Viewer gleicht das aus, wie bei
SkyDemon-GPX). Bei GNSS=0/fehlend auf Druckhoehe ausweichen.

IGC liefert keine Geschwindigkeit → None; die Enrich-Pipeline
fuellt sie geodaetisch auf (wie bei KML).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

import pandas as pd


def _parse_hfdte(rest: str) -> Optional[tuple[int, int, int]]:
    """DDMMYY aus dem Rest eines HFDTE-Records → (Jahr, Monat, Tag) oder None."""
    m = re.search(r"(\d{2})(\d{2})(\d{2})", rest)
    if not m:
        return None
    d, mo, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if d < 1 or d > 31 or mo < 1 or mo > 12:
        return None
    # Pivot bei 80: IGC existiert seit den 1990ern, praktisch alle Fluege >= 2000.
    y = 1900 + yy if yy >= 80 else 2000 + yy
    return (y, mo, d)


def parse_igc_file(path: str) -> pd.DataFrame:
    """Liest eine IGC-Datei und gibt einen Schema-B-DataFrame zurueck.

    Spalten:
        timestamp_utc          (datetime, UTC-aware)
        directional_latitude   (float, Grad)
        directional_longitude  (float, Grad)
        altitude_corrected     (float, Meter MSL — GNSS bevorzugt)
        speed_kmh              (float, NaN — wird downstream gefuellt)
        speed_knots            (float, NaN)

    Leerer DataFrame bei fehlendem Datum oder ohne 3D-Fixes.
    """
    with open(path, encoding="ascii", errors="replace") as f:
        lines = f.read().splitlines()

    date: Optional[tuple[int, int, int]] = None
    day_offset = 0
    prev_sec_of_day = -1
    rows: list[dict] = []

    for raw in lines:
        line = raw.rstrip()

        if line.startswith("HFDTE"):
            parsed = _parse_hfdte(line[5:])
            if parsed:
                date = parsed
            continue

        if not line or line[0] != "B" or len(line) < 35:
            continue
        if date is None:
            continue
        if line[24] != "A":  # nur gueltige 3D-Fixes
            continue

        try:
            hh = int(line[1:3])
            mi = int(line[3:5])
            ss = int(line[5:7])
        except ValueError:
            continue
        if hh > 23 or mi > 59 or ss > 59:
            continue

        try:
            lat_deg = int(line[7:9])
            lat_min = int(line[9:14]) / 1000.0
            lat_hemi = line[14]
            lon_deg = int(line[15:18])
            lon_min = int(line[18:23]) / 1000.0
            lon_hemi = line[23]
        except ValueError:
            continue

        lat = lat_deg + lat_min / 60.0
        lon = lon_deg + lon_min / 60.0
        if lat_hemi == "S":
            lat = -lat
        if lon_hemi == "W":
            lon = -lon
        if lat == 0.0 and lon == 0.0:  # Null-Island-Sentinel
            continue

        try:
            p_alt_str = line[25:30].strip()
            g_alt_str = line[30:35].strip()
            p_alt = int(p_alt_str) if p_alt_str else None
            g_alt = int(g_alt_str) if g_alt_str else None
        except ValueError:
            p_alt = g_alt = None

        # GNSS bevorzugt; bei 0/fehlend auf Druckhoehe ausweichen.
        if g_alt is not None and g_alt != 0:
            alt_m = float(g_alt)
        elif p_alt is not None and p_alt != 0:
            alt_m = float(p_alt)
        else:
            alt_m = float(g_alt) if g_alt is not None else float("nan")

        sec_of_day = hh * 3600 + mi * 60 + ss
        if prev_sec_of_day >= 0 and sec_of_day < prev_sec_of_day - 1:
            day_offset += 1
        prev_sec_of_day = sec_of_day

        y, mo, d = date
        ts = datetime(y, mo, d + day_offset, hh, mi, ss, tzinfo=timezone.utc)

        rows.append({
            "timestamp_utc": ts,
            "directional_latitude": lat,
            "directional_longitude": lon,
            "altitude_corrected": alt_m,
            "speed_kmh": float("nan"),
            "speed_knots": float("nan"),
        })

    if not rows:
        return pd.DataFrame(columns=[
            "timestamp_utc", "directional_latitude", "directional_longitude",
            "altitude_corrected", "speed_kmh", "speed_knots",
        ])

    df = pd.DataFrame(rows).sort_values("timestamp_utc").reset_index(drop=True)
    return df
