"""DEM in 3 LOD-Stufen als JSON für den React-Viewer exportieren.

LOD 0: fein  (~10 m/px)  — bei Zoom > 11
LOD 1: mittel (~50 m/px) — bei Zoom 8–11
LOD 2: grob  (~200 m/px) — bei Zoom < 8

Output-Datei: {name_prefix}_dem_lod{i}.json

JSON-Schema entspricht DemLod (types.ts):
  { lod, bounds: { lon_min, lat_min, lon_max, lat_max },
    grid: { n_rows, n_cols, lat_min, lat_max, lon_min, lon_max,
            elevations: (number | null)[] } }
"""

import json
import math
from pathlib import Path
from typing import Optional

import numpy as np

# (lod_index, target_pixel_size_m, max_pixels_per_axis)
_LOD_SPECS = [
    (0,  10, 2000),
    (1,  50, 1000),
    (2, 200,  500),
]


def export_dem_lods(
    dem_paths: list,
    bounds: tuple,
    output_dir: Path,
    name_prefix: str,
) -> list:
    """Exportiert ein oder mehrere DEM-GeoTIFFs in 3 Auflösungsstufen.

    Parameters
    ----------
    dem_paths : list of Path-like
        GeoTIFF-Quelldateien.
    bounds : tuple
        (lon_min, lat_min, lon_max, lat_max) — Track-Bounding-Box.
    output_dir : Path
        Zielverzeichnis.
    name_prefix : str
        Präfix für die Output-Dateinamen.

    Returns
    -------
    list[int]
        Indizes der erfolgreich geschriebenen LOD-Stufen.
    """
    from ..terrain.dem import load_dem

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    lon_min, lat_min, lon_max, lat_max = bounds
    track_bounds = {
        "lon_min": lon_min,
        "lat_min": lat_min,
        "lon_max": lon_max,
        "lat_max": lat_max,
    }

    written: list = []

    for lod_idx, pixel_size_m, max_px in _LOD_SPECS:
        # Bei mehreren DEM-Files: alle laden und das mit der größten Fläche
        # (= meisten Pixeln) für dieses LOD verwenden. Bei einem einzigen
        # GeoTIFF ist das trivial.
        best: Optional[dict] = None
        for dem_path in dem_paths:
            result = load_dem(
                str(dem_path),
                bounds=bounds,
                target_pixel_size_m=pixel_size_m,
                max_pixels_per_axis=max_px,
                dem_smooth=1.0,
            )
            if result is None:
                continue
            if best is None or result["elevations"].size > best["elevations"].size:
                best = result

        if best is None:
            print(f"DEM LOD {lod_idx}: keine Daten verfügbar, übersprungen.")
            continue

        lats: np.ndarray = best["lats"]   # 1D, aufsteigend
        lons: np.ndarray = best["lons"]   # 1D
        elev: np.ndarray = best["elevations"]  # 2D (n_rows, n_cols)

        n_rows, n_cols = elev.shape

        # Flat-Array zeilenweise (row-major); NaN → null
        flat: list = []
        for val in elev.ravel():
            fval = float(val)
            flat.append(None if math.isnan(fval) else round(fval, 1))

        payload = {
            "lod": lod_idx,
            "bounds": track_bounds,
            "grid": {
                "n_rows":      n_rows,
                "n_cols":      n_cols,
                "lat_min":     round(float(lats.min()), 6),
                "lat_max":     round(float(lats.max()), 6),
                "lon_min":     round(float(lons.min()), 6),
                "lon_max":     round(float(lons.max()), 6),
                "elevations":  flat,
            },
        }

        out_path = output_dir / f"{name_prefix}_dem_lod{lod_idx}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, allow_nan=False, separators=(",", ":"))

        size_kb = out_path.stat().st_size / 1024
        print(
            f"DEM LOD {lod_idx} geschrieben: {out_path.name} "
            f"({size_kb:.0f} KB, {n_rows}×{n_cols})"
        )
        written.append(lod_idx)

    return written
