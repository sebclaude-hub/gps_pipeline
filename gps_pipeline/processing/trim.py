"""Track-Trimming: definierte Index-Bereiche aus einem Track entfernen.

Verwendungsablauf
-----------------
1. Der React-Viewer exportiert eine ``ranges.json`` mit Cut-Range-Definitionen
   (siehe ``RangeSelector``-Komponente).
2. Diese Datei wird per ``load_cut_ranges()`` eingelesen.
3. ``trim_track(df, ranges)`` gibt einen neuen DataFrame zurueck, der die
   Zeilen ausserhalb der Cut-Ranges enthaelt -- in originaler Reihenfolge und
   mit originalen Timestamps.

Trimming nimmt die Originaldaten ernst: Timestamps werden NICHT verschoben
und keine Punkte erfunden. Wer zeitliche Luecken "schliessen" will, nutzt
stattdessen ``processing.synthetic.create_synthetic_track``.

JSON-Format (vom Viewer geschrieben)
------------------------------------
::

    {
      "total_points":  580,            # zur Validierung
      "cut_ranges": [
        {"start": 0,   "end": 49},     # Anfang weg
        {"start": 200, "end": 350},    # Zwischenstopp weg
        {"start": 540, "end": 579}     # Ende weg
      ],
      "created_at": "2026-05-24T12:34:56Z"
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CutRange:
    """Ein zu entfernender Index-Bereich [start, end] (beide inklusive)."""
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < 0:
            raise ValueError(f"Negative Indizes: {self}")
        if self.start > self.end:
            raise ValueError(f"start > end: {self}")


def load_cut_ranges(path: Path) -> list[CutRange]:
    """Liest ranges.json und gibt eine Liste von ``CutRange`` zurueck.

    Tolerant: ueberlappende Ranges werden nicht zusammengefuehrt (das
    passiert in ``trim_track`` automatisch), aber Tippfehler im Schema
    werfen ``ValueError``.
    """
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload.get("cut_ranges", [])
    ranges: list[CutRange] = []
    for r in raw:
        ranges.append(CutRange(start=int(r["start"]), end=int(r["end"])))
    return ranges


def trim_track(
    df: pd.DataFrame,
    cut_ranges: list[CutRange],
) -> pd.DataFrame:
    """Entfernt alle Zeilen, deren Position-Index in einem Cut-Range liegt.

    Parameters
    ----------
    df : pd.DataFrame
        Schema-C-DataFrame (oder beliebiger DataFrame mit RangeIndex).
        Der DataFrame wird nicht modifiziert; eine Kopie wird zurueckgegeben.
    cut_ranges : list of CutRange
        Zu entfernende Index-Bereiche, beide Grenzen inklusive.

    Returns
    -------
    pd.DataFrame
        Neuer DataFrame mit reset RangeIndex (0..m-1). Spalten und Dtypes
        bleiben unveraendert.
    """
    n = len(df)
    if n == 0:
        return df.copy()

    # Boolesche Maske: True = behalten
    keep = np.ones(n, dtype=bool)
    for r in cut_ranges:
        lo = max(0, r.start)
        hi = min(n - 1, r.end)
        if lo <= hi:
            keep[lo:hi + 1] = False

    trimmed = df.iloc[keep].reset_index(drop=True)
    print(f"trim_track: {n} -> {len(trimmed)} Punkte "
          f"({n - len(trimmed)} entfernt, {len(cut_ranges)} Cut-Range(s))")
    return trimmed
