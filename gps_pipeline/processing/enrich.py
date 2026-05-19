"""Schema-B → Schema-C: Geodätische Distanzen und Geschwindigkeiten anreichern.

Eingabe: Schema-B-DataFrame (eine Zeile pro Timestamp).
Ausgabe: Schema-C-DataFrame mit zusätzlichen Spalten:
  * ``distance_m``: geodätische Distanz zum vorherigen Punkt (Meter)
  * ``speed_geodesic_kmh``, ``speed_geodesic_knots``: aus distance/dt
  * ``speed_diff_kmh``, ``speed_diff_knots``: geodesic minus GPS-Wert
    (Sanity-Check; sollte nahe 0 sein)

Implementierungsnotizen
-----------------------
* Geodätische Distanz via ``geopy.distance.geodesic`` (Karney's Vincenty-
  Variante), rechnet auf dem WGS84-Ellipsoid und ist für unsere Zwecke
  exakt.
* NaN-Behandlung: fehlt eine Koordinate oder ein Timestamp in der Sequenz,
  liefert dieser Schritt NaN für distance/speed an dieser Stelle.
* Duplikate (zwei Zeilen mit identischem Timestamp): Zeitdifferenz wird 0,
  was zu Division durch Null führen würde. Wir setzen dort NaN, nicht
  Inf — Plotly stellt NaN als Lücke dar, was ehrlicher ist.
* Erste Zeile hat keinen Vorgänger → distance/speed = NaN.
"""

import numpy as np
import pandas as pd
from geopy.distance import geodesic


_KNOTS_PER_MPS = 1.94384  # 1 m/s = 1.94384 Knoten
_KMH_PER_MPS = 3.6        # 1 m/s = 3.6 km/h


def _calc_geodesic_distance(lat1, lon1, lat2, lon2):
    """Geodätische Distanz in Metern; NaN wenn irgendein Wert fehlt."""
    if pd.isna(lat1) or pd.isna(lon1) or pd.isna(lat2) or pd.isna(lon2):
        return np.nan
    return geodesic((lat1, lon1), (lat2, lon2)).meters


def enrich_speed(df: pd.DataFrame) -> pd.DataFrame:
    """Reichert Schema-B-DataFrame um Distanz und geodätische Geschwindigkeit an.

    Parameters
    ----------
    df : pd.DataFrame
        Schema-B-DataFrame (eine Zeile pro Timestamp).

    Returns
    -------
    pd.DataFrame
        Schema-C-DataFrame. Standard-RangeIndex 0..n-1.
    """
    if df.empty:
        return df.copy()

    result = df.copy()

    # Sicher sortieren (sollte schon sortiert sein, aber Doppel-Check schadet nicht)
    result = result.sort_values("timestamp_utc", kind="stable").reset_index(drop=True)

    n = len(result)
    distances = np.full(n, np.nan)
    speeds_kmh = np.full(n, np.nan)
    speeds_knots = np.full(n, np.nan)

    # Iteration über aufeinanderfolgende Paare. Erste Zeile bekommt NaN
    # (kein Vorgänger). Bei NaN-Koordinaten oder Duplikat-Timestamps bleibt
    # ebenfalls NaN stehen.
    lats = result["directional_latitude"].to_numpy()
    lons = result["directional_longitude"].to_numpy()
    ts = result["timestamp_utc"].to_numpy()

    for i in range(1, n):
        # Zeitdifferenz in Sekunden
        dt_ns = ts[i] - ts[i - 1]
        dt_s = dt_ns / np.timedelta64(1, "s")

        if not np.isfinite(dt_s) or dt_s <= 0.0:
            # Duplikat oder nicht-monotone Zeitstempel: NaN setzen
            continue

        dist = _calc_geodesic_distance(lats[i - 1], lons[i - 1], lats[i], lons[i])
        if np.isnan(dist):
            continue

        distances[i] = dist
        speed_mps = dist / dt_s
        speeds_kmh[i] = speed_mps * _KMH_PER_MPS
        speeds_knots[i] = speed_mps * _KNOTS_PER_MPS

    # Float32 für Sensordaten: Distanz mit ~0.01-m-Auflösung, Speed mit
    # ~0.01-km/h-Auflösung — beides liegt weit über dem GPS-Rauschen
    result["distance_m"] = distances.astype(np.float32)
    result["speed_geodesic_kmh"] = speeds_kmh.astype(np.float32)
    result["speed_geodesic_knots"] = speeds_knots.astype(np.float32)

    # Wenn die gemeldete Geschwindigkeit (aus GPS/NMEA/GPX) durchgehend fehlt
    # — wie bei KML-Tracks der Fall — füllen wir sie aus der geodätischen
    # Berechnung auf. Das macht color_by='speed_kmh' für alle Track-Quellen
    # benutzbar, ohne dass jeder Aufrufer wissen muss, welche Spalte da ist.
    if result["speed_kmh"].isna().all():
        result["speed_kmh"] = result["speed_geodesic_kmh"]
        result["speed_knots"] = result["speed_geodesic_knots"]

    # Differenzen zum GPS-Speed (NaN-sicher: pandas behandelt NaN korrekt).
    # Cast auf float32 weil Eingaben float32 sind und sonst pandas auf
    # float64 hochpromotet.
    result["speed_diff_kmh"] = (result["speed_geodesic_kmh"] - result["speed_kmh"]).astype(np.float32)
    result["speed_diff_knots"] = (result["speed_geodesic_knots"] - result["speed_knots"]).astype(np.float32)

    print(f"Angereichert: {n} Zeilen (Schema C). "
          f"Distanz total: {np.nansum(distances):.1f} m. "
          f"Max geodesic speed: {np.nanmax(speeds_kmh):.1f} km/h.")
    return result
