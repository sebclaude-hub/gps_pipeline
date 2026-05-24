"""Karten-Overlays in das Viewer-Output-Verzeichnis exportieren.

Kopiert die PNG-Dateien (oder verlinkt sie, falls Symlinks unterstuetzt
werden) und schreibt ``charts.json`` mit den Eckkoordinaten und der
Hoehenreferenz pro Overlay.

JSON-Schema (entspricht ChartOverlay in types.ts)::

    {
      "charts": [
        {
          "name":        "EDFG",
          "image":       "charts/EDFG.png",
          "corner_tl":   [lon, lat],
          "corner_tr":   [lon, lat],
          "corner_bl":   [lon, lat],
          "corner_br":   [lon, lat],
          "elevation_m": 220.0
        }, ...
      ]
    }
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterable

from ..parsing.chart import ChartOverlay


def export_charts(
    charts: Iterable[ChartOverlay],
    output_dir: Path,
) -> list[dict]:
    """Kopiert Chart-PNGs nach ``output_dir/charts/`` und schreibt
    ``charts.json``.

    Returns
    -------
    list[dict]
        Die geschriebenen Eintraege (auch in der JSON-Datei enthalten).
        Leere Liste wenn keine Charts uebergeben.
    """
    output_dir = Path(output_dir)
    charts = list(charts)
    if not charts:
        return []

    images_dir = output_dir / "charts"
    images_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    for ch in charts:
        # PNG ins Output-Verzeichnis kopieren. ``copy2`` erhaelt mtime,
        # damit Browser-Cache deterministisch arbeitet.
        target = images_dir / ch.png_path.name
        try:
            shutil.copy2(ch.png_path, target)
        except OSError as exc:
            print(f"Chart '{ch.name}': Kopieren fehlgeschlagen ({exc}); uebersprungen.")
            continue

        entry = {
            "name":        ch.name,
            "image":       f"charts/{ch.png_path.name}",
            "corner_tl":   [round(ch.corner_tl[0], 7), round(ch.corner_tl[1], 7)],
            "corner_tr":   [round(ch.corner_tr[0], 7), round(ch.corner_tr[1], 7)],
            "corner_bl":   [round(ch.corner_bl[0], 7), round(ch.corner_bl[1], 7)],
            "corner_br":   [round(ch.corner_br[0], 7), round(ch.corner_br[1], 7)],
            "elevation_m": round(float(ch.elevation_m), 2),
        }
        # Optionaler Subdivision-Override -- nur ins JSON, wenn explizit gesetzt.
        if ch.subdivision is not None:
            entry["subdivision"] = int(ch.subdivision)
        entries.append(entry)

    out_path = output_dir / "charts.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"charts": entries}, f, indent=2)

    print(f"charts.json geschrieben: {out_path} ({len(entries)} Overlay(s))")
    return entries
