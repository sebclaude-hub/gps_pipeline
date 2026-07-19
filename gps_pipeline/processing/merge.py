"""Zwei Tracks zu einem zusammenfuegen (Rueckport des Traxel-Merge-Features).

Zwei Faelle, analog zu den Cut-Modi in ``apply_cut_config.py``:

* Disjunkte Zeitbereiche (zweiter Track startet nach Ende des ersten):

  - ``gap``    -- Zeitstempel unveraendert; die Pause zwischen den Tracks
    bleibt als sichtbare Luecke (ehrliche Gesamtzeit).
  - ``bridge`` -- der zweite Track wird zeitlich nach vorne gezogen, sodass
    die Pause durch eine plausible Brueckenzeit ersetzt wird (t = s/v wie
    beim bridge-Cut) -> reine Bewegungszeit.

* Ueberlappende Zeitbereiche: die Reihenfolge legt der Aufrufer fest; der
  zweite Track wird zwingend hinter das Ende des ersten geschoben (``bridge``
  erzwungen -- mit unveraenderten Zeiten gaebe es keinen monotonen
  Zeitverlauf).

Die Funktion arbeitet auf Schema-B- oder Schema-C-DataFrames (benoetigt nur
``timestamp_utc``, ``directional_latitude/longitude``, ``speed_kmh``).
Typischer Workflow: Ergebnis mit ``export.gpx_export.write_gpx`` als GPX in
``data/`` ablegen und den naechsten Pipeline-Lauf normal drueberlaufen lassen
-- so ist die gespeicherte Datei garantiert identisch mit dem, was der Viewer
zeigt (gleiches Prinzip wie in Traxel)::

    from gps_pipeline import process_gpx, process_nmea, merge_tracks, write_gpx

    df_a = process_gpx(Path("data/a.gpx"))
    _, df_b = process_nmea(Path("data/b.txt"))
    res = merge_tracks(df_a, df_b, mode="bridge")
    write_gpx(res.segments, Path("data/a+b.gpx"), name="a+b")

Einschraenkung wie in Traxel: NMEA-Satellitendaten (Schema A / SkyPlot)
ueberleben den Merge nicht -- das GPX enthaelt Position/Zeit/Speed/HDOP.
"""

from dataclasses import dataclass
from typing import Literal

import pandas as pd

try:
    from geopy.distance import geodesic
except ImportError:  # pragma: no cover -- geopy ist Pipeline-Dependency
    geodesic = None  # type: ignore[assignment]

from .apply_cut_config import _avg_speed_kmh_around

JoinMode = Literal["gap", "bridge"]


@dataclass(frozen=True)
class MergeResult:
    """Ergebnis von :func:`merge_tracks`."""

    #: Zusammengefuegter DataFrame (RangeIndex 0..n-1).
    df: pd.DataFrame
    #: Die beiden Segmente in finaler Reihenfolge, Zeit des zweiten ggf.
    #: bereits verschoben — fuer ``write_gpx`` (ein <trkseg> je Segment).
    segments: tuple[pd.DataFrame, ...]
    #: Tatsaechlich angewandter Modus ("gap" wird bei Ueberlappung zu "bridge").
    effective_mode: JoinMode
    #: Zeitverschiebung des zweiten Tracks in Sekunden. Positiv = nach vorne
    #: gezogen (frueher), negativ = nach hinten geschoben. 0 im gap-Modus.
    shift_s: float


def merge_tracks(
    first: pd.DataFrame,
    second: pd.DataFrame,
    mode: JoinMode = "gap",
    *,
    interp_n: int = 10,
) -> MergeResult:
    """Fuegt ``second`` hinter ``first`` an (Reihenfolge bestimmt der Aufrufer,
    typisch: fruehere Startzeit zuerst). Beide DataFrames bleiben unveraendert.

    Parameters
    ----------
    first, second : pd.DataFrame
        Schema-B- oder Schema-C-Tracks (eine Zeile pro Zeitstempel).
    mode : "gap" | "bridge"
        Umgang mit der Pause zwischen den Tracks (nur bei disjunkten Zeiten
        frei waehlbar; bei Ueberlappung wird "bridge" erzwungen).
    interp_n : int
        Nachbarschaftsgroesse fuer die Brueckenzeit (wie apply_cut_config).
    """
    if mode not in ("gap", "bridge"):
        raise ValueError(f"Unbekannter Merge-Modus: {mode!r} (gap|bridge)")

    if first.empty or second.empty:
        segments = tuple(s.reset_index(drop=True) for s in (first, second) if not s.empty)
        df = (pd.concat(segments, ignore_index=True)
              if segments else first.iloc[0:0].copy())
        return MergeResult(df=df, segments=segments, effective_mode=mode, shift_s=0.0)

    ts_first = pd.to_datetime(first["timestamp_utc"], utc=True)
    ts_second = pd.to_datetime(second["timestamp_utc"], utc=True)
    first_end = ts_first.iloc[-1]
    second_start = ts_second.iloc[0]

    # Ueberlappung (oder verkehrte Reihenfolge) -> Zeit MUSS verschoben werden.
    overlap = second_start <= first_end
    effective_mode: JoinMode = "bridge" if overlap else mode

    shift_s = 0.0
    if effective_mode == "bridge":
        if geodesic is None:
            raise ImportError(
                "geopy ist nicht installiert -- bridge-Modus benoetigt "
                "geopy.distance.geodesic.")
        # Brueckenzeit wie beim bridge-Cut: t = s/v ueber die Nahtstelle, v aus
        # den bis zu interp_n Nachbarpunkten beidseits. _avg_speed_kmh_around
        # mit LEEREM Cut-Bereich (end = start-1) liefert genau diese Nachbarn.
        n_first = len(first)
        combined_speed = pd.DataFrame({
            "speed_kmh": pd.concat(
                [first["speed_kmh"], second["speed_kmh"]], ignore_index=True
            ),
        })
        bridge_m = geodesic(
            (float(first["directional_latitude"].iloc[-1]),
             float(first["directional_longitude"].iloc[-1])),
            (float(second["directional_latitude"].iloc[0]),
             float(second["directional_longitude"].iloc[0])),
        ).meters
        avg_kmh = _avg_speed_kmh_around(combined_speed, n_first, n_first - 1, interp_n)
        avg_ms = max(avg_kmh / 3.6, 0.1)
        bridge_s = bridge_m / avg_ms

        new_second_start = first_end + pd.Timedelta(seconds=bridge_s)
        shift_s = (second_start - new_second_start).total_seconds()
        print(f"Merge bridge: Naht {bridge_m:.0f}m, Brueckenfahrt ~{bridge_s:.0f}s "
              f"(avg {avg_kmh:.1f} km/h) -> zweiter Track {shift_s:+.0f}s verschoben")
    else:
        pause_s = (second_start - first_end).total_seconds()
        print(f"Merge gap: Pause von {pause_s:.0f}s bleibt als Luecke erhalten")

    second_shifted = second.reset_index(drop=True)
    if shift_s != 0.0:
        second_shifted = second_shifted.copy()
        second_shifted["timestamp_utc"] = (
            pd.to_datetime(second_shifted["timestamp_utc"], utc=True)
            - pd.Timedelta(seconds=shift_s)
        )

    segments = (first.reset_index(drop=True), second_shifted)
    df = pd.concat(segments, ignore_index=True)
    print(f"Merge: {len(first)} + {len(second)} Punkte -> {len(df)} "
          f"(Modus {effective_mode})")
    return MergeResult(
        df=df,
        segments=segments,
        effective_mode=effective_mode,
        shift_s=round(shift_s, 1),
    )
