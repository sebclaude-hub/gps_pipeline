"""Track- und Satelliten-Daten als JSON für den React-Viewer exportieren.

Das JSON-Schema ist spaltenorientiert (Arrays statt Array-of-Objects), weil:
  * 3–5× kompakter als Array-of-Objects
  * Direkt als TypedArray in JS nutzbar (Float32Array, Int32Array)
  * Keine Wiederholung von Feldnamen pro Zeile

Haupt-Exporte
-------------
export_track_json(df_c, path)
    Schema-C-DataFrame → track.json

export_satellite_json(df_c, df_raw, path)
    Schema-A-DataFrame (GSV-Rohdaten) + Schema-C (Timestamps) → satellites.json
"""

import json
import math
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from ..config import DEFAULT_QUANTILES


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _safe_list(series: pd.Series, dtype=float) -> list:
    """Konvertiert eine Series zu einer Python-Liste; NaN → null (None)."""
    vals = series.astype(object).where(series.notna(), other=None)
    if dtype is float:
        return [round(float(v), 6) if v is not None else None for v in vals]
    if dtype is int:
        return [int(v) if v is not None else None for v in vals]
    return vals.tolist()


def _safe_float_list(series: pd.Series, decimals: int = 4) -> list:
    result = []
    for v in series:
        try:
            fv = float(v)
            result.append(None if math.isnan(fv) else round(fv, decimals))
        except (TypeError, ValueError):
            result.append(None)
    return result


def _detect_track_mode(df_c: pd.DataFrame) -> str:
    """'flight' wenn Track im Median >100 m über Terrain liegt, sonst 'ground'.

    100 m ist hoch genug, um GPS-Rauschen und DEM-Auflösungsfehler zu absorbieren,
    aber niedrig genug um Gleitschirmflüge zuverlässig zu erfassen.
    """
    if "track_above_terrain" not in df_c.columns:
        return "ground"
    above = df_c["track_above_terrain"].dropna()
    if above.empty:
        return "ground"
    return "flight" if float(above.median()) > 100.0 else "ground"


def _compute_quantile_breaks(
    speed: pd.Series,
    n_quantiles: int = DEFAULT_QUANTILES,
) -> tuple[list[float], pd.Series]:
    """Berechnet Quantil-Grenzen und Index-Spalte (0..n-1) per pd.qcut.

    Returns
    -------
    (breaks, q_idx_series)
        breaks       : n+1 Grenzwerte (inklusive min und max)
        q_idx_series : Int-Serie mit Quantilklasse 0..n-1 pro Punkt, NaN → -1
    """
    clean = speed.dropna()
    if clean.empty or clean.nunique() < 2:
        breaks = [0.0] * (n_quantiles + 1)
        return breaks, pd.Series(0, index=speed.index, dtype="int8")

    labels = list(range(n_quantiles))
    q_cut, bins = pd.qcut(
        clean, q=n_quantiles, labels=labels,
        retbins=True, duplicates="drop",
    )
    # Auffüllen auf die tatsächliche Länge (inkl. NaN-Positionen)
    q_idx = speed.copy().astype(object)
    q_idx[clean.index] = q_cut.astype(object)
    q_idx = q_idx.fillna(-1).astype("int8")

    breaks = [round(float(b), 3) for b in bins]
    # Padding: falls durch duplicates='drop' weniger Bins entstanden
    while len(breaks) < n_quantiles + 1:
        breaks.append(breaks[-1])

    return breaks, q_idx


# ---------------------------------------------------------------------------
# Track-Export
# ---------------------------------------------------------------------------

def export_track_json(
    df_c: pd.DataFrame,
    path: Path,
    *,
    name_prefix: str = "track",
    n_quantiles: int = DEFAULT_QUANTILES,
    suggested_z_offset: float = 0.0,
) -> None:
    """Serialisiert einen Schema-C-DataFrame nach track.json.

    Parameters
    ----------
    df_c : pd.DataFrame
        Schema-C-DataFrame (mindestens timestamp_utc, directional_lat/lon,
        altitude_corrected, speed_kmh).
    path : Path
        Zieldatei (wird überschrieben).
    name_prefix : str
        Anzeigename im Viewer.
    n_quantiles : int
        Anzahl Geschwindigkeits-Quantilklassen.
    suggested_z_offset : float
        Vorgeschlagener Z-Offset in Metern, als Hint fuer den React-Viewer
        (Default-Wert des Offset-Sliders). Wird in ``meta`` exportiert,
        aber NICHT in ``points.alt`` oder ``points.above_terrain`` vorgebacken
        -- der Viewer wendet ihn live auf die Darstellung an, sodass der
        Nutzer interaktiv nachregeln kann.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lat = df_c["directional_latitude"]
    lon = df_c["directional_longitude"]
    alt = df_c.get("altitude_corrected", pd.Series(np.nan, index=df_c.index))
    speed = df_c.get("speed_kmh", pd.Series(np.nan, index=df_c.index))
    dist = df_c.get("distance_m", pd.Series(np.nan, index=df_c.index))
    terrain = df_c.get("terrain_elevation", pd.Series(np.nan, index=df_c.index))
    # above_terrain wird hier NEUTRAL (ohne vorgebackenen Offset) berechnet,
    # damit der React-Viewer den Offset live anpassen kann. Der spaltenwert
    # ``track_above_terrain`` aus enrich_terrain_elevation enthaelt den
    # Python-seitigen Offset und wird hier bewusst ignoriert.
    if alt is not None and terrain is not None:
        above = alt.astype("Float64") - terrain.astype("Float64")
    else:
        above = pd.Series(np.nan, index=df_c.index)
    fix_quality = df_c.get("gga_gps_quality", pd.Series(np.nan, index=df_c.index))
    num_sats = df_c.get("gga_num_sats", pd.Series(np.nan, index=df_c.index))
    hdop = df_c.get("gga_hdop", pd.Series(np.nan, index=df_c.index))
    vdop = df_c.get("gsa_vdop", pd.Series(np.nan, index=df_c.index))

    # Timestamps → Unix ms (int)
    ts = pd.to_datetime(df_c["timestamp_utc"], utc=True)
    ts_ms = (ts.astype("int64") // 1_000_000).tolist()

    # Quantile (Speed + Höhe)
    breaks, q_idx = _compute_quantile_breaks(speed, n_quantiles)
    alt_breaks, alt_q_idx = _compute_quantile_breaks(alt, n_quantiles)

    # Bounds
    bounds = {
        "lon_min": round(float(lon.min()), 6),
        "lat_min": round(float(lat.min()), 6),
        "lon_max": round(float(lon.max()), 6),
        "lat_max": round(float(lat.max()), 6),
    }

    # Meta
    total_dist = float(dist.sum()) if dist.notna().any() else 0.0
    duration_s = 0.0
    if len(ts) >= 2:
        duration_s = (ts.iloc[-1] - ts.iloc[0]).total_seconds()

    track_mode = _detect_track_mode(df_c)
    has_terrain = terrain.notna().any()

    payload = {
        "meta": {
            "name": name_prefix,
            "source_type": "nmea",          # wird ggf. von Aufrufer überschrieben
            "n_points": len(df_c),
            "total_distance_m": round(total_dist, 1),
            "duration_s": round(duration_s, 1),
            "timestamp_start_utc": ts.iloc[0].isoformat() if len(ts) else None,
            "timestamp_end_utc": ts.iloc[-1].isoformat() if len(ts) else None,
            "bounds": bounds,
            "track_mode": track_mode,
            "has_terrain": bool(has_terrain),
            "has_satellites": False,        # wird von export_satellite_json gesetzt
            # Vorschlag fuer den Offset-Slider im Viewer. Nicht in alt/above
            # vorgebacken -- der Viewer wendet es als initialen Slider-Wert an.
            "suggested_z_offset_m": round(float(suggested_z_offset), 2),
        },
        "quantile_breaks": {
            "speed_kmh": breaks,
            "altitude_m": alt_breaks,
            "n_quantiles": n_quantiles,
        },
        "points": {
            "lat":          _safe_float_list(lat, 7),
            "lon":          _safe_float_list(lon, 7),
            "alt":          _safe_float_list(alt, 1),
            "terrain_elev": _safe_float_list(terrain, 1),
            "above_terrain": _safe_float_list(above, 1),
            "speed_kmh":    _safe_float_list(speed, 2),
            "distance_m":   _safe_float_list(dist, 1),
            "timestamp_ms": ts_ms,
            "speed_q_idx":  q_idx.tolist(),
            "alt_q_idx":    alt_q_idx.tolist(),
            "fix_quality":  _safe_list(fix_quality, dtype=int),
            "num_sats":     _safe_list(num_sats, dtype=int),
            "hdop":         _safe_float_list(hdop, 1),
            "vdop":         _safe_float_list(vdop, 1),
        },
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, allow_nan=False, separators=(",", ":"))

    size_kb = path.stat().st_size / 1024
    print(f"track.json geschrieben: {path} ({size_kb:.0f} KB, {len(df_c)} Punkte)")


# ---------------------------------------------------------------------------
# Satelliten-Export
# ---------------------------------------------------------------------------

def export_satellite_json(
    df_c: pd.DataFrame,
    df_raw: pd.DataFrame,
    path: Path,
) -> bool:
    """Serialisiert GSV-Satellitendaten nach satellites.json.

    Parameters
    ----------
    df_c : pd.DataFrame
        Schema-C-DataFrame (für Timestamps).
    df_raw : pd.DataFrame
        Schema-A-DataFrame (mit gsv_satellites-Spalte).
    path : Path
        Zieldatei.

    Returns
    -------
    bool
        True wenn Satellitendaten vorhanden und geschrieben, sonst False.
    """
    from ..processing.gsv_align import align_satellites_to_track

    path = Path(path)

    if df_raw is None or "gsv_satellites" not in df_raw.columns:
        return False

    aligned = align_satellites_to_track(df_c, df_raw)
    if aligned.empty:
        return False

    # Talker-IDs ermitteln
    talkers = sorted(aligned["talker_id"].unique().tolist())

    # Pro Talker: deduplizierte Burst-Liste + Lookup-Array (track_idx → burst_idx)
    bursts_by_talker: dict = {}
    burst_idx_by_track: dict = {}
    n_track = len(df_c)

    for talker in talkers:
        sub = aligned[aligned["talker_id"] == talker].sort_values("track_idx")

        # Deduplizierte Bursts (gleiche gsv_timestamp → selber Eintrag)
        seen_ts: dict = {}
        burst_list = []
        for _, row in sub.iterrows():
            ts_key = str(row["gsv_timestamp"])
            if ts_key not in seen_ts:
                seen_ts[ts_key] = len(burst_list)
                sats = row["satellites"] if isinstance(row["satellites"], list) else []
                # Satelliten als kompakte Listen [prn, el, az, snr]
                sat_rows = [
                    [
                        s.get("prn"),
                        round(float(s["elevation"]), 1) if s.get("elevation") is not None else None,
                        round(float(s["azimuth"]), 1)   if s.get("azimuth")   is not None else None,
                        round(float(s["snr"]), 0)        if s.get("snr")       is not None else None,
                    ]
                    for s in sats
                ]
                ts_ms = int(pd.to_datetime(row["gsv_timestamp"], utc=True).timestamp() * 1000)
                burst_list.append({"ts_ms": ts_ms, "sats": sat_rows})

        bursts_by_talker[talker] = burst_list

        # Lookup: track_idx → burst_idx (-1 = kein Burst)
        lookup = [-1] * n_track
        for _, row in sub.iterrows():
            t_idx = int(row["track_idx"])
            ts_key = str(row["gsv_timestamp"])
            if 0 <= t_idx < n_track:
                lookup[t_idx] = seen_ts.get(ts_key, -1)
        burst_idx_by_track[talker] = lookup

    payload = {
        "talkers": talkers,
        "bursts_by_talker": bursts_by_talker,
        "burst_idx_by_track": burst_idx_by_track,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, allow_nan=False, separators=(",", ":"))

    total_bursts = sum(len(v) for v in bursts_by_talker.values())
    size_kb = path.stat().st_size / 1024
    print(f"satellites.json geschrieben: {path} ({size_kb:.0f} KB, "
          f"{len(talkers)} Talker, {total_bursts} Bursts)")
    return True
