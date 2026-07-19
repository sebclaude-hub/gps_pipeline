"""GPX-Writer: Schema-B/C-DataFrames -> GPX-Datei.

Gegenstueck zu ``parsing/gpx.py`` -- primaer fuer den Track-Merge
(``processing/merge.py``), dessen Ergebnis als normale Quelldatei in ``data/``
landet und beim naechsten Pipeline-Lauf mitverarbeitet wird.

Format: GPX 1.1 im GPX/1/1-Namespace -- ``parse_gpx_file`` ist
namespace-strikt auf GPX/1/1, ein 1.0-Dokument wuerde dort zu 0 Punkten
parsen. ``<hdop>`` ist in 1.1 regulaer erlaubt; ``<speed>`` (m/s) als
direktes ``<trkpt>``-Kind ist zwar erst ab GPX 1.0 schema-valide, aber
genau die Konvention, die SkyDemon & Co. in 1.1-Dateien verwenden -- und
die ``parse_gpx_file`` (und Traxel) explizit lesen. Jedes Segment wird ein
eigenes ``<trkseg>`` -- so bleibt die Nahtstelle zwischen zusammengefuegten
Tracks im Dateiformat sichtbar (der Parser flacht sie wieder ab).
"""

from pathlib import Path
from typing import Iterable, Optional, Sequence, Union
from xml.sax.saxutils import escape

import pandas as pd


def _fmt(value: float, decimals: int) -> str:
    """Float ohne ueberfluessige Nullen (7.0 -> "7", 7.50 -> "7.5")."""
    s = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _trkpt_lines(df: pd.DataFrame) -> Iterable[str]:
    lat = df["directional_latitude"]
    lon = df["directional_longitude"]
    ts = pd.to_datetime(df["timestamp_utc"], utc=True)
    alt = df.get("altitude_corrected")
    speed = df.get("speed_kmh")
    hdop = df.get("gga_hdop")

    for i in range(len(df)):
        la, lo, t = lat.iloc[i], lon.iloc[i], ts.iloc[i]
        if pd.isna(la) or pd.isna(lo) or pd.isna(t):
            continue  # ohne Koordinaten/Zeit kein gueltiger GPX-Trackpoint
        parts = [f'    <trkpt lat="{_fmt(float(la), 7)}" lon="{_fmt(float(lo), 7)}">']
        if alt is not None and pd.notna(alt.iloc[i]):
            parts.append(f"<ele>{_fmt(float(alt.iloc[i]), 2)}</ele>")
        parts.append(f"<time>{t.isoformat().replace('+00:00', 'Z')}</time>")
        if speed is not None and pd.notna(speed.iloc[i]):
            # GPX erwartet m/s; mm/s-Aufloesung reicht (mehr liefert die Quelle nicht).
            parts.append(f"<speed>{_fmt(float(speed.iloc[i]) / 3.6, 3)}</speed>")
        if hdop is not None and pd.notna(hdop.iloc[i]):
            parts.append(f"<hdop>{_fmt(float(hdop.iloc[i]), 2)}</hdop>")
        parts.append("</trkpt>")
        yield "".join(parts)


def write_gpx(
    segments: Union[pd.DataFrame, Sequence[pd.DataFrame]],
    path: Path,
    *,
    name: Optional[str] = None,
) -> Path:
    """Schreibt Track-Segmente als GPX-1.0-Datei (ein ``<trkseg>`` je Segment).

    Parameters
    ----------
    segments : pd.DataFrame oder Sequenz von DataFrames
        Schema-B/C-Daten; ein einzelner DataFrame wird zu einem Segment.
        Typisch: ``MergeResult.segments`` aus ``merge_tracks``.
    path : Path
        Zieldatei (z.B. ``data/a+b.gpx``).
    name : str, optional
        ``<name>`` des Tracks; Default ist der Dateiname ohne Endung.
    """
    if isinstance(segments, pd.DataFrame):
        segments = [segments]
    path = Path(path)
    track_name = escape(name if name is not None else path.stem)

    seg_blocks = []
    n_points = 0
    for seg in segments:
        lines = list(_trkpt_lines(seg))
        if not lines:
            continue
        n_points += len(lines)
        seg_blocks.append("  <trkseg>\n" + "\n".join(lines) + "\n  </trkseg>")

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="gps_pipeline" '
        'xmlns="http://www.topografix.com/GPX/1/1">\n'
        f"<trk><name>{track_name}</name>\n"
        + "\n".join(seg_blocks)
        + "\n</trk>\n</gpx>\n"
    )
    path.write_text(xml, encoding="utf-8")
    print(f"GPX geschrieben: {path} ({n_points} Punkte, {len(seg_blocks)} Segmente)")
    return path
