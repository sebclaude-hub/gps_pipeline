"""Wendet eine ``CutConfig`` auf einen frisch geparsten Track an.

Diese Funktion ist der zentrale Punkt, an dem Schnittanweisungen aus dem
React-Viewer in der Pipeline wirksam werden. Sie operiert auf beiden
DataFrame-Schemata:

* Schema C (``df_c`` -- eine Zeile pro konsolidiertem Trackpunkt) --
  Cut-Ranges sind Indices in dieses DataFrame.
* Schema A (``df_raw`` -- eine Zeile pro NMEA-Satz, optional) --
  wird ueber Timestamps mit-gefiltert/-geshiftet.

Drei Schnitt-Modi
-----------------
* ``trim``      -- Punkte entfernen, Timestamps unveraendert. Wird vom
                   System fuer Edge-Cuts (Anfang/Ende) IMMER forciert.
* ``gap``       -- Punkte entfernen, Timestamps unveraendert. Im Track
                   bleibt eine sichtbare Luecke.
* ``synthetic`` -- Punkte entfernen UND alle nachfolgenden Timestamps
                   nach vorne verschieben. Brueckenzeit aus
                   Nachbarschafts-Speed (siehe
                   ``processing.synthetic.create_synthetic_track``).

Derivation-Output
-----------------
Die Funktion liefert zusaetzlich ein ``derivation``-Dict, das vom
Viewer als Banner angezeigt wird:

* Nur trim-Cuts -> ``None`` (kein Banner -- Muell-Entfernung am Rand
  ist unauffaellig).
* Mindestens ein gap-Cut, kein synthetic -> Info-Banner.
* Mindestens ein synthetic-Cut (auch in Mischung) -> Warn-Banner
  ("Zeitstempel verschoben, GSV-Bursts unter verschobenen Zeitstempeln").
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

try:
    from geopy.distance import geodesic
except ImportError:  # pragma: no cover -- geopy ist Pipeline-Dependency
    geodesic = None  # type: ignore[assignment]

from ..parsing.cut_config import CutConfig, CutSpec


def _avg_speed_kmh_around(
    df_c: pd.DataFrame,
    cut_start: int,
    cut_end: int,
    n: int,
) -> float:
    """Mittlere Geschwindigkeit der ``n`` Messpunkte links und rechts der
    Cut-Range. Faellt auf den Median des gesamten Tracks zurueck, sonst
    auf 50 km/h (vermeidet Division durch 0)."""
    left_lo = max(0, cut_start - n)
    left_hi = cut_start
    right_lo = cut_end + 1
    right_hi = min(len(df_c), cut_end + 1 + n)

    speeds = pd.concat([
        df_c["speed_kmh"].iloc[left_lo:left_hi],
        df_c["speed_kmh"].iloc[right_lo:right_hi],
    ]).dropna()
    if not speeds.empty:
        return float(speeds.mean())
    full = df_c["speed_kmh"].dropna()
    if not full.empty:
        return float(full.median())
    return 50.0


def _compute_synthetic_shift_s(
    df_c: pd.DataFrame,
    spec: CutSpec,
    ts: pd.Series,
    lat: np.ndarray,
    lon: np.ndarray,
    interp_n: int,
) -> float:
    """Wie viele Sekunden muss die Zeitachse nach diesem Cut nach vorne
    geschoben werden? = tatsaechliche Pausenzeit - erwartete Brueckenzeit.

    Erwartet einen Cut mitten im Track (nicht am Rand).
    """
    if geodesic is None:
        raise ImportError(
            "geopy ist nicht installiert -- synthetic-Modus benoetigt "
            "geopy.distance.geodesic.")

    lo, hi = spec.start, spec.end

    # Tatsaechliche Pausenzeit zwischen "letztem behaltenen Punkt vor Cut"
    # und "erstem behaltenen Punkt nach Cut".
    pause_s = (ts.iloc[hi + 1] - ts.iloc[lo - 1]).total_seconds()

    # Geodaetische Distanz zwischen den beiden Randpunkten.
    bridge_m = geodesic(
        (lat[lo - 1], lon[lo - 1]),
        (lat[hi + 1], lon[hi + 1]),
    ).meters

    avg_kmh = _avg_speed_kmh_around(df_c, lo, hi, interp_n)
    avg_ms = max(avg_kmh / 3.6, 0.1)
    bridge_s = bridge_m / avg_ms

    shift_s = pause_s - bridge_s
    print(f"  Cut [{lo}..{hi}] synthetic: Pause {pause_s:.0f}s, "
          f"Brueckenfahrt ~{bridge_s:.0f}s "
          f"(avg {avg_kmh:.1f} km/h, dist {bridge_m:.0f}m) "
          f"-> Verschiebung {shift_s:+.0f}s")
    return shift_s


def apply_cut_config(
    df_raw: Optional[pd.DataFrame],
    df_c: pd.DataFrame,
    config: CutConfig,
    *,
    interp_n: int = 10,
    source_name: Optional[str] = None,
) -> tuple[Optional[pd.DataFrame], pd.DataFrame, Optional[dict]]:
    """Wendet ``config`` auf ``df_c`` (und optional ``df_raw``) an.

    Parameters
    ----------
    df_raw : pd.DataFrame, optional
        Schema-A-DataFrame (eine Zeile pro NMEA-Satz). Wird ueber
        ``timestamp_utc`` synchron zu ``df_c`` gefiltert/geshiftet.
        Kann ``None`` sein (z.B. bei GPX/KML-Quellen).
    df_c : pd.DataFrame
        Schema-C-DataFrame mit ``timestamp_utc``,
        ``directional_latitude``, ``directional_longitude``, ``speed_kmh``.
    config : CutConfig
        Schnittanweisung aus dem Viewer.
    interp_n : int
        Nachbarschaftsgroesse fuer die Brueckenzeit-Berechnung
        (Default 10).
    source_name : str, optional
        Name fuer das Derivation-Banner. Default: ``config.source``.

    Returns
    -------
    (df_raw_new, df_c_new, derivation)
        Die neuen DataFrames (RangeIndex frisch gesetzt) und das
        Derivation-Dict fuer das Viewer-Banner. ``df_raw_new`` ist None
        wenn ``df_raw`` None war.
    """
    n_c_before = len(df_c)
    if n_c_before == 0:
        return df_raw, df_c, None

    # Edge-Cuts zwingen wir auf 'trim': bei einem Cut am Anfang oder
    # Ende gibt es nichts zu ueberbruecken (kein Punkt davor/danach).
    config = config.force_edge_trim(n_c_before)

    # Optional: Validierung der Punktzahl gegen die im Viewer gespeicherte.
    if (config.n_points_reference is not None
            and config.n_points_reference != n_c_before):
        print(f"Warnung: cuts.json wurde fuer einen Track mit "
              f"{config.n_points_reference} Punkten erstellt, "
              f"der aktuelle Track hat {n_c_before}. Indizes koennten "
              f"verschoben sein -- bitte pruefen.")

    if not config.cut_ranges:
        return df_raw, df_c, None

    ts_c = pd.to_datetime(df_c["timestamp_utc"], utc=True)
    lat = df_c["directional_latitude"].to_numpy()
    lon = df_c["directional_longitude"].to_numpy()

    # Pro Schema-C-Zeile: behalten? + akkumulierter Shift nach diesem Punkt?
    keep_c = np.ones(n_c_before, dtype=bool)
    shift_after_idx_s = np.zeros(n_c_before, dtype=float)
    is_synth = np.zeros(n_c_before, dtype=bool)

    # Fuer df_raw-Filter: Liste der (ts_lo, ts_hi)-Intervalle, die gedroppt
    # werden. Wir filtern df_raw spaeter ueber Timestamps, nicht ueber Index.
    drop_intervals: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    # Fuer df_raw-Shift: Liste der (ts_after, shift_s) -- alle df_raw-Zeilen
    # mit ts >= ts_after kriegen shift_s subtrahiert. ts_after = ts[hi+1].
    shift_breakpoints: list[tuple[pd.Timestamp, float]] = []

    counts = {"trim": 0, "gap": 0, "synthetic": 0}
    total_shift = 0.0

    for spec in config.cut_ranges:
        lo = max(0, spec.start)
        hi = min(n_c_before - 1, spec.end)
        if lo > hi:
            continue

        keep_c[lo:hi + 1] = False
        counts[spec.mode] += 1

        # ts_lo / ts_hi -- die Zeitstempel der Randpunkte des Cuts (inkl.).
        ts_lo_cut = ts_c.iloc[lo]
        ts_hi_cut = ts_c.iloc[hi]
        if pd.notna(ts_lo_cut) and pd.notna(ts_hi_cut):
            drop_intervals.append((ts_lo_cut, ts_hi_cut))

        if spec.mode != "synthetic":
            continue

        # Edge-Synthetic kann es nach force_edge_trim nicht mehr geben.
        # Defensive: trotzdem skippen.
        if lo == 0 or hi == n_c_before - 1:
            continue

        shift_s = _compute_synthetic_shift_s(
            df_c, spec, ts_c, lat, lon, interp_n)
        total_shift += shift_s
        shift_after_idx_s[hi + 1:] += shift_s
        is_synth[hi + 1:] = True
        # Shift wirkt ab dem ersten behaltenen Punkt nach dem Cut.
        ts_after = ts_c.iloc[hi + 1]
        if pd.notna(ts_after):
            shift_breakpoints.append((ts_after, shift_s))

    # ----- Schema C anwenden -----
    df_c_new = df_c.iloc[keep_c].copy().reset_index(drop=True)
    if any(shift_after_idx_s != 0):
        shift_td = pd.to_timedelta(shift_after_idx_s, unit="s")
        shifted = ts_c - shift_td
        df_c_new["timestamp_utc"] = shifted[keep_c].reset_index(drop=True)
    # is_synthetic IMMER als Spalte setzen (False fuer alle, wenn kein
    # synthetic-Cut). Erleichtert dem Frontend die Logik.
    df_c_new["is_synthetic"] = is_synth[keep_c]

    print(f"apply_cut_config: {n_c_before} -> {len(df_c_new)} Punkte "
          f"(trim={counts['trim']}, gap={counts['gap']}, "
          f"synthetic={counts['synthetic']})")

    # ----- Schema A anwenden (sofern vorhanden) -----
    df_raw_new: Optional[pd.DataFrame] = None
    if df_raw is not None and not df_raw.empty:
        df_raw_new = _apply_to_raw(df_raw, drop_intervals, shift_breakpoints)

    # ----- Derivation-Dict bauen -----
    derivation = _build_derivation(
        counts=counts,
        source_name=source_name or config.source,
        n_before=n_c_before,
        n_after=len(df_c_new),
        total_shift_s=total_shift,
    )

    return df_raw_new, df_c_new, derivation


def _apply_to_raw(
    df_raw: pd.DataFrame,
    drop_intervals: list[tuple[pd.Timestamp, pd.Timestamp]],
    shift_breakpoints: list[tuple[pd.Timestamp, float]],
) -> pd.DataFrame:
    """Filtert und shiftet Schema-A-DataFrame ueber Timestamps.

    * Zeilen mit ``timestamp_utc`` in einem Drop-Intervall (inklusive
      beider Grenzen) werden entfernt.
    * Verbleibende Zeilen mit ``timestamp_utc >= ts_after`` kriegen
      die kumulierte Verschiebung subtrahiert (synthetic-Cuts).
    * Zeilen ohne ``timestamp_utc`` (NaT) bleiben unveraendert -- wir
      wissen nicht, wo sie zeitlich hingehoeren.
    """
    if "timestamp_utc" not in df_raw.columns:
        return df_raw.copy().reset_index(drop=True)

    ts_raw = pd.to_datetime(df_raw["timestamp_utc"], utc=True)
    keep = np.ones(len(df_raw), dtype=bool)

    has_ts = ts_raw.notna().to_numpy()
    for ts_lo, ts_hi in drop_intervals:
        in_range = ((ts_raw >= ts_lo) & (ts_raw <= ts_hi)).to_numpy()
        keep &= ~(in_range & has_ts)

    n_before = len(df_raw)
    n_dropped = int((~keep).sum())

    out = df_raw.iloc[keep].copy().reset_index(drop=True)

    if shift_breakpoints:
        # Pro Zeile: kumulierter Shift = Summe aller Breakpoints mit ts_after <= ts.
        # Wir gehen sortiert vor; bei vielen Breakpoints ist O(n*log b) ok.
        ts_out = pd.to_datetime(out["timestamp_utc"], utc=True)
        shift_s = np.zeros(len(out), dtype=float)
        bp_sorted = sorted(shift_breakpoints, key=lambda x: x[0])
        for ts_after, s in bp_sorted:
            mask = (ts_out >= ts_after).to_numpy()
            shift_s[mask] += s
        if np.any(shift_s != 0):
            shift_td = pd.to_timedelta(shift_s, unit="s")
            out["timestamp_utc"] = ts_out - shift_td

    print(f"  df_raw: {n_before} -> {len(out)} Zeilen "
          f"({n_dropped} per Timestamp gedroppt)")
    return out


def _build_derivation(
    *,
    counts: dict,
    source_name: str,
    n_before: int,
    n_after: int,
    total_shift_s: float,
) -> Optional[dict]:
    """Baut das ``meta.derivation``-Dict je nach Cut-Mischung.

    * Nur trim                      -> None  (kein Banner)
    * gap (ohne synthetic)          -> Info-Severity
    * Mit synthetic (auch Mischung) -> Warn-Severity
    """
    n_trim = counts["trim"]
    n_gap = counts["gap"]
    n_synth = counts["synthetic"]
    n_total = n_trim + n_gap + n_synth

    if n_total == 0:
        return None

    base = {
        "source_name": source_name,
        "n_cuts": n_total,
        "n_trim_cuts": n_trim,
        "n_gap_cuts": n_gap,
        "n_synthetic_cuts": n_synth,
        "n_points_before": n_before,
        "n_points_after": n_after,
        "n_points_removed": n_before - n_after,
    }

    if n_synth > 0:
        return {
            **base,
            "type": "synthetic",
            "severity": "warn",
            "total_time_shift_s": round(total_shift_s, 1),
            "warning": ("Zeitstempel wurden verschoben, um Pausen "
                        "auszublenden. Satelliten-Bursts erscheinen unter "
                        "den verschobenen Zeitstempeln."),
        }

    if n_gap > 0:
        return {
            **base,
            "type": "gap",
            "severity": "info",
            "info": ("Im Track sind Luecken (entfernte Punkte). "
                     "Die Geschwindigkeitsanzeige in der Luecke ist "
                     "nicht aussagekraeftig."),
        }

    # Nur trim -- kein Banner.
    return None
