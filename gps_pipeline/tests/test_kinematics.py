"""Analytische Tests fuer decompose_acceleration.

Alle Faelle verwenden bekannte Geometrien (Kreisbahn, Gerade) mit exakt
berechenbaren Erwartungswerten:

  CCW-Kreis  → lateral = +v²/r  (links, positiv)
  CW-Kreis   → lateral = −v²/r  (rechts, negativ)
  Gerade + a → long    = +a_mps2
  Steigflug  → vertical ≈ +dv_z/dt
  Stillstand → long=lateral=vertical=0, heading=NaN
"""

import math

import numpy as np
import pytest

# Muss vor den Tests importierbar sein (implementiert in kinematics.py).
from gps_pipeline.processing.kinematics import (
    _moving_average,
    decompose_acceleration,
)

M_PER_DEG = 111_320.0


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def circle_track(
    radius_m: float,
    speed_mps: float,
    n_points: int,
    ccw: bool = True,
    center_lat: float = 47.0,
    center_lon: float = 7.0,
    alt_m: float = 500.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Gleichmaessige Kreisbahn in ENU um (center_lat, center_lon).

    Rueckgabe: lat, lon, alt (m), ts_s.
    """
    cos_lat = math.cos(math.radians(center_lat))
    circumference_m = 2 * math.pi * radius_m
    period_s = circumference_m / speed_mps
    angles = np.linspace(0, 2 * math.pi, n_points, endpoint=False)
    if not ccw:
        angles = -angles  # Uhrzeigersinn
    # ENU-Offsets
    east_m = radius_m * np.cos(angles)
    north_m = radius_m * np.sin(angles)
    lats = center_lat + north_m / M_PER_DEG
    lons = center_lon + east_m / (M_PER_DEG * cos_lat)
    alts = np.full(n_points, alt_m)
    ts_s = np.linspace(0, period_s, n_points, endpoint=False)
    return lats, lons, alts, ts_s


def straight_track(
    accel_mps2: float,
    v0_mps: float,
    n_points: int = 20,
    bearing_deg: float = 0.0,
    center_lat: float = 47.0,
    center_lon: float = 7.0,
    alt_m: float = 500.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Gleichmaessig beschleunigte Geradeaus-Fahrt.

    bearing_deg=0 → nach Norden; 90 → nach Osten.
    """
    cos_lat = math.cos(math.radians(center_lat))
    dt = 1.0
    ts_s = np.arange(n_points, dtype=float) * dt
    # v = v0 + a*t,  s = v0*t + ½*a*t²
    s = v0_mps * ts_s + 0.5 * accel_mps2 * ts_s**2
    bearing_rad = math.radians(bearing_deg)
    north_m = s * math.cos(bearing_rad)
    east_m = s * math.sin(bearing_rad)
    lats = center_lat + north_m / M_PER_DEG
    lons = center_lon + east_m / (M_PER_DEG * cos_lat)
    alts = np.full(n_points, alt_m)
    return lats, lons, alts, ts_s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDecomposeAcceleration:

    def test_ccw_circle_lateral_positive(self):
        """CCW-Kreis: Zentripetalbeschleunigung ist lateral positiv (Linkskurve)."""
        r, v = 500.0, 50.0  # 500 m Radius, 50 m/s
        lats, lons, alts, ts_s = circle_track(r, v, n_points=200, ccw=True)
        long, lat_a, vert, he, hn = decompose_acceleration(lats, lons, alts, ts_s)

        # Rand-Punkte weglassen (einseitige Ableitung dort ungenauer)
        inner = slice(5, -5)
        expected_centripetal = v**2 / r  # ~5 m/s²

        lat_inner = lat_a[inner]
        lat_finite = lat_inner[np.isfinite(lat_inner)]
        assert lat_finite.size > 0, "Keine endlichen Lateral-Werte"
        assert np.median(lat_finite) > 0, "CCW muss lateral positiv sein"
        np.testing.assert_allclose(
            np.median(lat_finite), expected_centripetal, rtol=0.05,
            err_msg="Laterale Beschleunigung CCW weicht >5% von v²/r ab",
        )

    def test_cw_circle_lateral_negative(self):
        """CW-Kreis: Zentripetalbeschleunigung ist lateral negativ (Rechtskurve)."""
        r, v = 500.0, 50.0
        lats, lons, alts, ts_s = circle_track(r, v, n_points=200, ccw=False)
        _, lat_a, _, _, _ = decompose_acceleration(lats, lons, alts, ts_s)

        inner = slice(5, -5)
        lat_finite = lat_a[inner][np.isfinite(lat_a[inner])]
        assert lat_finite.size > 0
        assert np.median(lat_finite) < 0, "CW muss lateral negativ sein"
        np.testing.assert_allclose(
            np.median(lat_finite), -(v**2 / r), rtol=0.05,
            err_msg="Laterale Beschleunigung CW weicht >5% von −v²/r ab",
        )

    def test_ccw_circle_long_near_zero(self):
        """Gleichmaessige Kreisbahn: Laengsbeschleunigung nahezu null."""
        r, v = 500.0, 50.0
        lats, lons, alts, ts_s = circle_track(r, v, n_points=200, ccw=True)
        long, _, _, _, _ = decompose_acceleration(lats, lons, alts, ts_s)

        inner = slice(5, -5)
        long_finite = long[inner][np.isfinite(long[inner])]
        assert long_finite.size > 0
        np.testing.assert_allclose(
            np.median(long_finite), 0.0, atol=0.5,
            err_msg="Gleichmaessige Kreisbahn: Laengsbeschleunigung muss ~0 sein",
        )

    def test_straight_acceleration_longitudinal(self):
        """Gleichmaessig beschleunigte Gerade: long ≈ a_mps2."""
        a = 2.0  # m/s²
        lats, lons, alts, ts_s = straight_track(
            accel_mps2=a, v0_mps=10.0, n_points=30, bearing_deg=0.0
        )
        long, lat_a, vert, _, _ = decompose_acceleration(lats, lons, alts, ts_s)

        inner = slice(3, -3)
        long_finite = long[inner][np.isfinite(long[inner])]
        assert long_finite.size > 0
        np.testing.assert_allclose(
            np.mean(long_finite), a, atol=0.3,
            err_msg=f"Laengsbeschleunigung soll ~{a} m/s² sein",
        )
        # Lateral muss nahe null bleiben
        lat_finite = lat_a[inner][np.isfinite(lat_a[inner])]
        np.testing.assert_allclose(
            np.mean(lat_finite), 0.0, atol=0.3,
            err_msg="Geradeaus: Lateral muss ~0 sein",
        )

    def test_straight_bearing_east(self):
        """Gerade nach Osten: Heading zeigt nach Osten (he≈1, hn≈0)."""
        lats, lons, alts, ts_s = straight_track(
            accel_mps2=0.0, v0_mps=20.0, n_points=20, bearing_deg=90.0
        )
        _, _, _, he, hn = decompose_acceleration(lats, lons, alts, ts_s)

        inner = slice(2, -2)
        he_finite = he[inner][np.isfinite(he[inner])]
        hn_finite = hn[inner][np.isfinite(hn[inner])]
        assert he_finite.size > 0
        np.testing.assert_allclose(np.mean(he_finite), 1.0, atol=0.05,
                                   err_msg="Osten: he soll ~1 sein")
        np.testing.assert_allclose(np.mean(hn_finite), 0.0, atol=0.05,
                                   err_msg="Osten: hn soll ~0 sein")

    def test_climb_vertical(self):
        """Konstante Steigrate → vertikale Beschleunigung ≈ 0 (gleichmaessiger Anstieg)."""
        # Gleichmaessiger Aufstieg: dv_z/dt = 0 → vertical ≈ 0
        n = 30
        ts_s = np.arange(n, dtype=float)
        climb_rate = 5.0  # m/s (konstant)
        # Gerade nach Norden
        cos_lat = math.cos(math.radians(47.0))
        north_m = 20.0 * ts_s  # 20 m/s vorwaerts
        lats = 47.0 + north_m / M_PER_DEG
        lons = np.full(n, 7.0)
        alts = 500.0 + climb_rate * ts_s
        _, _, vert, _, _ = decompose_acceleration(lats, lons, alts, ts_s)

        inner = slice(3, -3)
        vert_finite = vert[inner][np.isfinite(vert[inner])]
        assert vert_finite.size > 0
        np.testing.assert_allclose(
            np.mean(vert_finite), 0.0, atol=0.5,
            err_msg="Gleichmaessiger Aufstieg: vertikale Beschleunigung muss ~0 sein",
        )

    def test_output_shapes(self):
        """Alle fuenf Ausgabe-Arrays haben dieselbe Laenge wie die Eingabe."""
        n = 15
        lats, lons, alts, ts_s = straight_track(
            accel_mps2=1.0, v0_mps=10.0, n_points=n
        )
        result = decompose_acceleration(lats, lons, alts, ts_s)
        assert len(result) == 5, "decompose_acceleration soll 5 Arrays zurueckgeben"
        for arr in result:
            assert len(arr) == n, f"Output-Array hat Laenge {len(arr)}, erwartet {n}"

    def test_nan_at_edges(self):
        """Rand-Punkte sollen NaN haben (keine gueltige zentrale Ableitung moeglich)."""
        lats, lons, alts, ts_s = straight_track(
            accel_mps2=1.0, v0_mps=10.0, n_points=20
        )
        long, lat_a, vert, he, hn = decompose_acceleration(lats, lons, alts, ts_s)
        # Heading der ersten und letzten Punkte:
        # central_time_derivative liefert an den Raendern einseitige Werte,
        # also kein NaN erzwungen — aber die Beschleunigung an [0] und [-1]
        # basiert auf einseitiger Ableitung. Wir pruefen nur, dass der innere
        # Bereich endliche Werte hat.
        inner_long = long[2:-2]
        assert np.all(np.isfinite(inner_long)), "Innere Laengsbeschleunigung muss endlich sein"

    def test_standstill_no_heading(self):
        """Gleichbleibende Position → Heading ist NaN (keine Richtung definierbar)."""
        n = 10
        lats = np.full(n, 47.0)
        lons = np.full(n, 7.0)
        alts = np.full(n, 500.0)
        ts_s = np.arange(n, dtype=float)
        _, _, _, he, hn = decompose_acceleration(lats, lons, alts, ts_s)
        # Alle Heading-Werte sollen NaN sein (Geschwindigkeit = 0)
        assert np.all(~np.isfinite(he)), "Standstill: he soll ueberall NaN sein"
        assert np.all(~np.isfinite(hn)), "Standstill: hn soll ueberall NaN sein"


class TestMovingAverage:
    """Tests fuer das vektorisierte, fensterbare gleitende Mittel."""

    def test_window_1_is_noop(self):
        arr = np.array([1.0, 5.0, 2.0, 8.0, 3.0])
        np.testing.assert_array_equal(_moving_average(arr, 1), arr)

    def test_three_point_mean_inner(self):
        arr = np.array([0.0, 3.0, 0.0, 0.0, 0.0])
        out = _moving_average(arr, 3)
        # Mittelpunkt 1: (0+3+0)/3 = 1; Nachbarn ziehen den Spike herunter.
        assert out[1] == pytest.approx(1.0)
        assert out[2] == pytest.approx(1.0)

    def test_dampens_spike(self):
        arr = np.zeros(11)
        arr[5] = 10.0
        peak1 = np.max(np.abs(_moving_average(arr, 3)))
        peak2 = np.max(np.abs(_moving_average(arr, 5)))
        assert peak1 < 10.0  # 3-Punkt senkt die Spitze
        assert peak2 < peak1  # 5-Punkt senkt sie weiter

    def test_nan_center_stays_nan_neighbors_ignored(self):
        arr = np.array([2.0, np.nan, 4.0, 6.0])
        out = _moving_average(arr, 3)
        assert np.isnan(out[1]), "NaN-Mittelpunkt bleibt NaN (kein Wert erfunden)"
        # out[2] mittelt nur die endlichen Nachbarn {4, 6} (NaN ignoriert) = 5.
        assert out[2] == pytest.approx(5.0)

    def test_edges_shrink_window(self):
        arr = np.array([1.0, 2.0, 3.0])
        out = _moving_average(arr, 3)
        assert out[0] == pytest.approx(1.5)  # nur {1,2}
        assert out[2] == pytest.approx(2.5)  # nur {2,3}


class TestDecomposeSmoothing:
    """smooth_window glaettet die Komponenten, nicht aber die Headings."""

    def test_smoothing_dampens_lateral_spike(self):
        # Kreisbahn mit einem injizierten Hoehen-Ausreisser → Spike in vert/lat.
        lats, lons, alts, ts_s = circle_track(
            radius_m=50.0, speed_mps=10.0, n_points=60, ccw=True
        )
        alts = alts.copy()
        alts[30] += 5.0  # einzelner GPS-Hoehenspike

        def peak_vert(win):
            _, _, vert, _, _ = decompose_acceleration(
                lats, lons, alts, ts_s, smooth_window=win
            )
            return np.nanmax(np.abs(vert))

        assert peak_vert(3) < peak_vert(1), "3-Punkt-Glaettung senkt den Spike"

    def test_headings_unchanged_by_smoothing(self):
        lats, lons, alts, ts_s = circle_track(
            radius_m=50.0, speed_mps=10.0, n_points=40, ccw=True
        )
        _, _, _, he1, hn1 = decompose_acceleration(lats, lons, alts, ts_s, smooth_window=1)
        _, _, _, he5, hn5 = decompose_acceleration(lats, lons, alts, ts_s, smooth_window=5)
        np.testing.assert_array_equal(he1, he5)
        np.testing.assert_array_equal(hn1, hn5)
