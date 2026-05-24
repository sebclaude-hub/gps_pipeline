"""apply_cuts -- Cuts aus dem React-Viewer auf einen Feather-Track anwenden
und einen neuen Viewer-Output erzeugen.

Round-Trip-Workflow
-------------------
1. Im React-Viewer Cuts definieren -> Export -> ``cut_ranges.json``
   (Browser-Download). Datei nach ``data/`` verschieben.
2. Dieses CLI hier ausfuehren:

    python -m gps_pipeline.apply_cuts \\
        --feather output/track.feather \\
        --output  output_trimmed/ \\
        --dem     data/dem.tif \\
        --charts  data/

   ``--ranges`` ist optional; ohne Angabe wird ``data/cut_ranges.json``
   gesucht.

3. ``python view.py output_trimmed`` -- der getrimmte Track ist drin.

Limitierungen
-------------
* Schema-A-Daten (NMEA-Rohsaetze inkl. Satelliten) werden NICHT mitgetrimmt.
  Der getrimmte Output enthaelt deshalb keine ``satellites.json``.
  Wer Satelliten im getrimmten Output braucht, muss den Originalpfad
  (Quelldatei + Cuts) verwenden -- das ist ein eigener Workflow, der in
  einer spaeteren Iteration kommen kann.
* Cuts werden 1:1 als Index-Bereiche im Schema-C-DataFrame interpretiert.
  ``cut_ranges.json`` enthaelt deren ``total_points`` -- wird gegen
  ``len(df)`` validiert, um Off-by-One-Fehler durch fehlende Synchronisation
  abzufangen.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from .api import export_for_viewer
from .dataframe_io.feather import load_df
from .parsing.chart import find_charts
from .processing.trim import load_cut_ranges, trim_track


def apply_cuts(
    feather_path: Path,
    ranges_path: Path,
    output_dir: Path,
    *,
    dem_paths: Optional[list[Path]] = None,
    chart_dir: Optional[Path] = None,
    source_type: str = "nmea",
    name_prefix: Optional[str] = None,
) -> Path:
    """Laedt Feather, wendet cut_ranges.json an, schreibt Viewer-ready-Output.

    Returns den Output-Pfad.
    """
    feather_path = Path(feather_path)
    ranges_path = Path(ranges_path)
    output_dir = Path(output_dir)

    if not feather_path.is_file():
        raise FileNotFoundError(f"Feather-Datei nicht gefunden: {feather_path}")
    if not ranges_path.is_file():
        raise FileNotFoundError(f"Cut-Ranges-Datei nicht gefunden: {ranges_path}")

    df = load_df(str(feather_path))
    cuts = load_cut_ranges(ranges_path)
    n_before = len(df)

    # Off-by-One-Check: cut_ranges.json hat ``total_points`` als Validierung.
    import json
    payload = json.loads(ranges_path.read_text(encoding="utf-8"))
    expected = payload.get("total_points")
    if expected is not None and expected != n_before:
        print(f"Warnung: cut_ranges.json wurde fuer einen Track mit "
              f"{expected} Punkten erstellt, das Feather hat {n_before}. "
              f"Indizes koennten verschoben sein -- bitte pruefen.")

    trimmed = trim_track(df, cuts)
    if trimmed.empty:
        print("Nach dem Trimmen ist nichts mehr uebrig. Abbruch.")
        sys.exit(2)

    charts = find_charts(chart_dir) if chart_dir else []
    if charts:
        print(f"Karten-Overlays gefunden: {[c.name for c in charts]}")

    if name_prefix is None:
        name_prefix = f"{feather_path.stem}_trimmed"

    # Derivation-Metadaten fuer den Viewer-Banner: kennzeichnet diesen
    # Track als bearbeitete Version eines anderen.
    derivation = {
        "type": "trimmed",
        "source_name": feather_path.stem,
        "n_cuts": len(cuts),
        "n_points_removed": n_before - len(trimmed),
        "n_points_before": n_before,
        "n_points_after": len(trimmed),
    }

    return export_for_viewer(
        trimmed, output_dir,
        name_prefix=name_prefix,
        df_raw=None,                 # Satelliten werden nicht mitgetrimmt
        dem_paths=dem_paths,
        charts=charts,
        source_type=source_type,
        derivation=derivation,
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m gps_pipeline.apply_cuts",
        description="Wendet Cut-Ranges aus dem React-Viewer auf einen "
                    "Feather-Track an und schreibt einen neuen Viewer-Output.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Beispiel:
  python -m gps_pipeline.apply_cuts \\
      --feather output/test.feather \\
      --ranges  output/ranges.json \\
      --output  output_trimmed/ \\
      --dem     data/dem.tif \\
      --charts  data/

Danach: python view.py output_trimmed
""",
    )
    p.add_argument("--feather", required=True, type=Path,
                   help="Pfad zur bestehenden track.feather (Schema-C)")
    p.add_argument("--ranges", type=Path, default=None,
                   help="Pfad zur cut_ranges.json (Export aus dem React-"
                        "Viewer). Default: data/cut_ranges.json")
    p.add_argument("--output", required=True, type=Path,
                   help="Ziel-Output-Verzeichnis (wird neu angelegt)")
    p.add_argument("--dem", action="append", type=Path, default=None,
                   metavar="PATH",
                   help="Optional: DEM-GeoTIFF (mehrfach moeglich fuer "
                        "Multi-Tile)")
    p.add_argument("--charts", type=Path, default=None,
                   metavar="DIR",
                   help="Optional: Verzeichnis mit PNG+TXT-Karten-Overlays")
    p.add_argument("--source-type", default="nmea",
                   choices=["nmea", "gpx", "kml"],
                   help="Quellformat (Default: nmea)")
    p.add_argument("--name-prefix", default=None,
                   help="Anzeigename im Viewer (Default: <feather>_trimmed)")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    ranges_path = args.ranges
    if ranges_path is None:
        # Default-Ort fuer cut_ranges.json: data/ (gleicher Ordner wie
        # alle anderen Eingabedaten). Der Viewer-Export landet vom
        # Browser-Download zunaechst in Downloads, wird aber per Hand
        # nach data/ verschoben -- das ist der "kanonische" Ort.
        ranges_path = Path("data") / "cut_ranges.json"
        if not ranges_path.is_file():
            print(f"Keine --ranges-Datei angegeben und "
                  f"{ranges_path} existiert nicht.")
            print("cut_ranges.json bitte aus den Downloads nach data/ "
                  "verschieben oder --ranges explizit angeben.")
            sys.exit(2)
        print(f"Nutze Default-Ranges-Datei: {ranges_path}")
    apply_cuts(
        feather_path=args.feather,
        ranges_path=ranges_path,
        output_dir=args.output,
        dem_paths=args.dem,
        chart_dir=args.charts,
        source_type=args.source_type,
        name_prefix=args.name_prefix,
    )


if __name__ == "__main__":
    main()
