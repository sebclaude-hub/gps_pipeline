"""Synthetic-Track-Generator: Cut-Ranges entfernen UND Zeitachse "fluessig"
schliessen, indem die Luecken interpoliert ueberbrueckt werden.

Anwendungsfall
--------------
Autofahrt mit Ladepausen. Fuer reine Fahrzeit-/Strecken-Auswertung soll der
Track aussehen, als haette es die Pausen nie gegeben:

* Die Pausen-Punkte werden entfernt.
* Die Zeit zwischen "Abfahrt" und "Auffahrt" wird aus der erwarteten
  Geschwindigkeit (gemittelt aus den ``interp_n`` Messpunkten links und
  rechts der Pause) und der geodaetischen Distanz zwischen den beiden
  Randpunkten der Pause neu berechnet.
* Alle nachfolgenden Zeitstempel werden entsprechend nach vorne geschoben,
  damit eine zusammenhaengende Zeitachse entsteht.

WICHTIG -- Gueltigkeit
----------------------
Der synthetische Track hat **gefaelschte Zeitstempel**. Damit:

* GSV-/Satellitendaten sind NICHT mehr gueltig (sie sind an die echten
  Zeitstempel gebunden) und werden in der zugehoerigen ``meta.json``
  ausdruecklich als nicht verfuegbar markiert.
* Die Ergebnis-Datei wird IMMER mit einem Suffix gespeichert
  (``<name>_synthetic.feather``), niemals in-place.
* Die Spalte ``is_synthetic`` markiert pro Zeile, ob der Zeitstempel
  modifiziert wurde (True = nicht mehr Original-Messung).

Fuer alle anderen Auswertungen (Strecke, Geschwindigkeit, Hoehenprofil,
Visualisierung) bleibt der Track sinnvoll nutzbar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

try:
    from geopy.distance import geodesic
except ImportError:  # pragma: no cover -- geopy ist Pipeline-Dependency
    geodesic = None  # type: ignore[assignment]

from .trim import CutRange


@dataclass
class SyntheticMeta:
    """Metadaten ueber die Synthese-Operation. Wird zusaetzlich als
    JSON-Sidecar abgelegt, damit der Ursprung des synthetischen Tracks
    rekonstruierbar bleibt."""
    source_name: str
    cut_ranges: list[CutRange]
    interp_n: int
    created_at: str
    n_points_original: int
    n_points_synthetic: int
    total_time_shift_s: float

    def to_dict(self) -> dict:
        return {
            "source_name":          self.source_name,
            "cut_ranges":           [{"start": r.start, "end": r.end}
                                     for r in self.cut_ranges],
            "interp_n":             self.interp_n,
            "created_at":           self.created_at,
            "n_points_original":    self.n_points_original,
            "n_points_synthetic":   self.n_points_synthetic,
            "total_time_shift_s":   self.total_time_shift_s,
            "warning":              "Zeitstempel sind synthetisch -- "
                                    "Satellitendaten (GSV) sind NICHT gueltig.",
        }


def _avg_speed_kmh_around(
    df: pd.DataFrame,
    cut_start: int,
    cut_end: int,
    n: int,
) -> float:
    """Mittlere Geschwindigkeit der ``n`` Messpunkte links und rechts der
    Cut-Range. Faellt auf den Median des gesamten Tracks zurueck, wenn nicht
    genug Punkte verfuegbar sind oder alle Speed-Werte NaN."""
    left_lo = max(0, cut_start - n)
    left_hi = cut_start
    right_lo = cut_end + 1
    right_hi = min(len(df), cut_end + 1 + n)

    speeds = pd.concat([
        df["speed_kmh"].iloc[left_lo:left_hi],
        df["speed_kmh"].iloc[right_lo:right_hi],
    ]).dropna()

    if not speeds.empty:
        return float(speeds.mean())
    # Fallback: Median des ganzen Tracks
    full = df["speed_kmh"].dropna()
    if not full.empty:
        return float(full.median())
    # Letzter Strohhalm: 50 km/h (vermeidet Division durch 0)
    return 50.0


def create_synthetic_track(
    df_c: pd.DataFrame,
    cut_ranges: list[CutRange],
    *,
    interp_n: int = 10,
    source_name: str = "track",
) -> tuple[pd.DataFrame, SyntheticMeta]:
    """Entfernt Cut-Ranges und verschiebt nachfolgende Zeitstempel so,
    dass eine zusammenhaengende Zeitachse entsteht.

    Parameters
    ----------
    df_c : pd.DataFrame
        Schema-C-DataFrame mit ``timestamp_utc``, ``directional_latitude``,
        ``directional_longitude``, ``speed_kmh``.
    cut_ranges : list of CutRange
        Index-Bereiche, die rausgeschnitten werden sollen.
    interp_n : int
        Anzahl der Mess-Punkte links und rechts der Pause, aus denen die
        durchschnittliche Geschwindigkeit fuer die Brueckenzeit ermittelt
        wird. Default 10 (= ~10 Sekunden bei 1 Hz-GPS).
    source_name : str
        Name fuer die Metadaten (zur Rueckverfolgung).

    Returns
    -------
    (df_synth, meta)
        ``df_synth``: neuer DataFrame mit RangeIndex und zusaetzlicher
        Spalte ``is_synthetic`` (True wenn der Zeitstempel der Zeile
        verschoben wurde).
        ``meta``: SyntheticMeta-Objekt zur Persistierung.
    """
    if geodesic is None:
        raise ImportError("geopy ist nicht installiert -- create_synthetic_track "
                          "benoetigt geopy.distance.geodesic")

    n = len(df_c)
    if n == 0:
        raise ValueError("Leerer DataFrame, nichts zu synthetisieren.")

    # Cut-Ranges nach Startindex sortieren (Stabilitaet beim Verschieben).
    cuts = sorted(cut_ranges, key=lambda r: r.start)

    # Boolean-Maske + Zeitverschiebung pro Zeile berechnen.
    keep = np.ones(n, dtype=bool)
    # Pro Zeile in Sekunden: kumulierte Verschiebung der Zeitachse.
    time_shift_s = np.zeros(n, dtype=float)
    # Pro Zeile: Wurde ihr Timestamp veraendert?
    is_synth = np.zeros(n, dtype=bool)

    ts = pd.to_datetime(df_c["timestamp_utc"], utc=True)
    lat = df_c["directional_latitude"].to_numpy()
    lon = df_c["directional_longitude"].to_numpy()

    total_shift = 0.0  # akkumuliert ueber alle Cuts hinweg

    for r in cuts:
        lo = max(0, r.start)
        hi = min(n - 1, r.end)
        if lo > hi:
            continue
        keep[lo:hi + 1] = False

        # Tatsaechliche Dauer der Pause aus den Originalzeitstempeln.
        # Wenn die Cut-Range am Rand liegt, bleibt nichts zu ueberbruecken.
        if lo == 0 or hi == n - 1:
            # Pures Trimming am Rand: kein Time-Bridging noetig, keine
            # Verschiebung der spaeteren Zeitstempel.
            continue

        # Wichtig: die Pause ist die ZEITLUECKE zwischen "letztem Punkt vor Cut"
        # (Index lo-1) und "erstem Punkt nach Cut" (Index hi+1) -- nicht innerhalb
        # des Cuts. Sonst kappen wir nur den Cut-Bereich selbst und nicht den
        # echten Zeit-Sprung dazwischen.
        pause_duration_s = (ts.iloc[hi + 1] - ts.iloc[lo - 1]).total_seconds()

        # Geodaetische Distanz von Punkt vor Cut zu Punkt nach Cut.
        before_lat, before_lon = lat[lo - 1], lon[lo - 1]
        after_lat,  after_lon  = lat[hi + 1], lon[hi + 1]
        bridge_dist_m = geodesic((before_lat, before_lon),
                                 (after_lat,  after_lon)).meters

        # Erwartete Brueckenzeit aus mittlerer Speed der Nachbarschaft.
        avg_kmh = _avg_speed_kmh_around(df_c, lo, hi, interp_n)
        avg_ms = max(avg_kmh / 3.6, 0.1)  # mind. 0.1 m/s, sonst Division-Bombe
        bridge_duration_s = bridge_dist_m / avg_ms

        # Differenz: tatsaechliche Pause vs. erwartete Brueckenzeit.
        # Diese Differenz wird aus der Zeitachse aller spaeteren Punkte
        # subtrahiert (Zeitstempel ruecken vor).
        shift_s = pause_duration_s - bridge_duration_s
        total_shift += shift_s

        # Alle Zeilen nach dem Cut werden um shift_s vorgeschoben und als
        # "synthetisch" markiert. Innerhalb des Cuts: ohnehin entfernt.
        time_shift_s[hi + 1:] += shift_s
        is_synth[hi + 1:] = True

        print(f"  Cut [{r.start}..{r.end}]: Pause {pause_duration_s:.0f}s, "
              f"Brueckenfahrt ~{bridge_duration_s:.0f}s "
              f"(avg {avg_kmh:.1f} km/h, dist {bridge_dist_m:.0f}m) "
              f"-> Verschiebung {shift_s:+.0f}s")

    # Neuer DataFrame: Zeilen filtern + Zeitstempel anpassen + is_synthetic
    df_synth = df_c.iloc[keep].copy().reset_index(drop=True)

    # Zeitstempel: Original minus kumulierte Verschiebung (positiv = vorruecken).
    # Ueber pandas arbeiten, damit UTC-Timezone und Nullable-Dtypes erhalten
    # bleiben (numpy-Subtraktion auf objekt-dtype-Arrays scheitert).
    shift_td = pd.to_timedelta(time_shift_s, unit="s")
    shifted_full = ts - shift_td
    df_synth["timestamp_utc"] = shifted_full[keep].reset_index(drop=True)
    df_synth["is_synthetic"] = is_synth[keep]

    # Diagnostische Spalten, die mit Original-Timestamps verknuepft sind
    # (Satellitenzahlen, HDOP, ...) bleiben numerisch erhalten, sind aber
    # streng genommen nur fuer die ECHTEN Zeitstempel gueltig. Wir lassen
    # sie drin, damit Visualisierung sie zeigen kann, aber die Warnung
    # steht in der meta.json.

    meta = SyntheticMeta(
        source_name=source_name,
        cut_ranges=list(cuts),
        interp_n=interp_n,
        created_at=pd.Timestamp.utcnow().isoformat(),
        n_points_original=n,
        n_points_synthetic=len(df_synth),
        total_time_shift_s=round(total_shift, 1),
    )

    print(f"create_synthetic_track: {n} -> {len(df_synth)} Punkte, "
          f"Zeitachse um {total_shift:.0f}s verkuerzt")

    return df_synth, meta


def save_synthetic(
    df_synth: pd.DataFrame,
    meta: SyntheticMeta,
    base_path: Path,
) -> tuple[Path, Path]:
    """Speichert synthetischen DataFrame + Sidecar-Metadaten.

    ``base_path`` ist der Pfad OHNE Suffix. Es entstehen:
      * ``<base_path>_synthetic.feather`` -- der DataFrame
      * ``<base_path>_synthetic.meta.json`` -- die Sidecar-Metadaten

    Das Suffix "_synthetic" ist erzwungen, damit der Ursprung visuell klar
    ist und ein versehentliches Ueberschreiben der Originaldaten ausgeschlossen.
    """
    from ..dataframe_io.feather import save_df

    base_path = Path(base_path)
    # Erzwingen: Suffix "_synthetic" einbauen.
    if not base_path.name.endswith("_synthetic"):
        feather_path = base_path.with_name(base_path.name + "_synthetic.feather")
    else:
        feather_path = base_path.with_suffix(".feather")

    meta_path = feather_path.with_suffix(".meta.json")

    save_df(df_synth, feather_path)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta.to_dict(), f, indent=2)

    print(f"Synthetic-Track geschrieben: {feather_path}")
    print(f"  Metadaten: {meta_path}")
    return feather_path, meta_path
