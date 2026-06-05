"""Abgeleitete Kinematik & Energie fuer die Farbgebung im Viewer.

WARUM hier (Python) und nicht im Viewer
---------------------------------------
Die Pipeline rechnet, der React-Viewer rendert nur. Beschleunigung, Energiehoehe
und deren Aenderung sind ABGELEITETE Groessen (zeitliche Ableitungen), die nicht
direkt in den GPS/NMEA-Daten stehen. Sie werden hier numpy-vektorisiert berechnet
und als fertige Per-Punkt-Arrays ins track.json exportiert; der Viewer mappt sie
nur noch auf Farbe.

WICHTIG — 3D, nicht 2D
----------------------
``speed_kmh`` ist die HORIZONTALE Grundgeschwindigkeit (NMEA bzw. geodaetische
2D-Distanz/dt). Fuer eine ehrliche kinetische Energie / Beschleunigung muss die
vertikale Rate d(alt)/dt dazu:  v3D = sqrt(v_h^2 + v_z^2).

Alle Funktionen sind NaN-sicher (fehlende Hoehe/Geschwindigkeit → NaN im
Ergebnis; ``allow_nan=False`` im JSON-Dump wandelt das ueber _safe_float_list zu
null um). Eingaben sind numpy-Arrays; ``ts_s`` sind Sekunden (float).
"""

from __future__ import annotations

import numpy as np

G = 9.80665  # Normfallbeschleunigung (m/s^2)
_MPS_PER_KMH = 1.0 / 3.6


def central_time_derivative(values: np.ndarray, ts_s: np.ndarray) -> np.ndarray:
    """d(values)/dt: zentrale Differenz im Inneren, einseitig an den Raendern.

    Ergebnis ist NaN, wo ein benoetigter Nachbarwert fehlt oder dt<=0 ist
    (Duplikat-/nicht-monotone Zeitstempel). Vorzeichenbehaftet.
    """
    values = np.asarray(values, dtype=float)
    ts_s = np.asarray(ts_s, dtype=float)
    n = values.shape[0]
    out = np.full(n, np.nan)
    if n < 2:
        return out

    idx = np.arange(n)
    lo = np.clip(idx - 1, 0, n - 1)  # i-1 (bzw. i am linken Rand → vorwaerts)
    hi = np.clip(idx + 1, 0, n - 1)  # i+1 (bzw. i am rechten Rand → rueckwaerts)
    dt = ts_s[hi] - ts_s[lo]
    with np.errstate(invalid="ignore", divide="ignore"):
        out = (values[hi] - values[lo]) / dt
    out[~(dt > 0)] = np.nan  # dt<=0 oder dt NaN
    return out


def vertical_speed(alt: np.ndarray, ts_s: np.ndarray) -> np.ndarray:
    """Vertikale Geschwindigkeit (m/s) aus d(alt)/dt. Fehlt eine Hoehe oder ist
    dt<=0, faellt die Stelle auf 0 zurueck (→ 2D-Verhalten dort), statt das ganze
    v3D zu killen."""
    vz = central_time_derivative(alt, ts_s)
    return np.where(np.isfinite(vz), vz, 0.0)


def speed_3d(speed_kmh: np.ndarray, alt: np.ndarray, ts_s: np.ndarray) -> np.ndarray:
    """3D-Geschwindigkeit (m/s) = sqrt(v_h^2 + v_z^2). NaN ohne Horizontaltempo."""
    vh = np.asarray(speed_kmh, dtype=float) * _MPS_PER_KMH
    vz = vertical_speed(alt, ts_s)
    return np.sqrt(vh * vh + vz * vz)  # NaN, wo vh NaN (speed fehlt)


def acceleration_3d(
    speed_kmh: np.ndarray, alt: np.ndarray, ts_s: np.ndarray
) -> np.ndarray:
    """Tangential-Beschleunigung (m/s^2) = d(v3D)/dt. + beschleunigen, − bremsen."""
    return central_time_derivative(speed_3d(speed_kmh, alt, ts_s), ts_s)


def energy_height(
    speed_kmh: np.ndarray, alt: np.ndarray, ts_s: np.ndarray, g: float = G
) -> np.ndarray:
    """Spezifische Energiehoehe H = h + v3D^2/(2g) (m), massenunabhaengig — die
    Hoehe, auf die der Koerper stiege, wuerde er seine kinetische Energie ganz in
    Hoehe umsetzen. NaN, wo Hoehe ODER Geschwindigkeit fehlt."""
    alt = np.asarray(alt, dtype=float)
    v3 = speed_3d(speed_kmh, alt, ts_s)
    return alt + (v3 * v3) / (2.0 * g)


def energy_rate(
    speed_kmh: np.ndarray, alt: np.ndarray, ts_s: np.ndarray
) -> np.ndarray:
    """Energieaenderungsrate dH/dt (m/s) — in der Luftfahrt die 'spezifische
    Ueberschussleistung' Ps. + Energiegewinn, − Verlust. Kunstflug-Kennzahl."""
    return central_time_derivative(energy_height(speed_kmh, alt, ts_s), ts_s)


def robust_symmetric_scale(values: np.ndarray, p: float = 0.98) -> float:
    """Robuste, symmetrische Skala fuer signierte Groessen: p-Perzentil der
    Betraege (Default 98 %), damit ein einzelner GPS-Spike die Farbskala nicht
    zusammendrueckt. Immer > 0 (Fallback 1.0)."""
    mags = np.abs(np.asarray(values, dtype=float))
    mags = mags[np.isfinite(mags)]
    if mags.size == 0:
        return 1.0
    perc = float(np.percentile(mags, p * 100.0))
    if perc > 0:
        return perc
    mx = float(mags.max())
    return mx if mx > 0 else 1.0
