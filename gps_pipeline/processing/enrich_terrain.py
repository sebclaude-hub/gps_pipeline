"""Anreichern eines Track-DataFrames um DEM-Höhendaten.

Erzeugt neue Spalten:
  * ``terrain_elevation`` — DEM-Höhe an Track-Position (Meter)
  * ``track_above_terrain`` — Track-Höhe minus Terrain-Höhe (Meter)

Beide Spalten sind NaN, wenn der Track-Punkt außerhalb des DEMs liegt
oder kein DEM-Wert verfügbar ist.

Voraussetzungen
---------------
* DataFrame muss Schema B oder C entsprechen (Spalten ``directional_latitude``,
  ``directional_longitude``, ``altitude_corrected``).
* DEM-Datei muss in EPSG:4326 (WGS84 Lat/Lon) sein.

Höhen-Bezug
-----------
``track_above_terrain`` ist nur sinnvoll, wenn Track-Höhe und DEM-Höhe
denselben Bezug haben. Bei unterschiedlichen Bezügen (z.B. ellipsoidische
GPS-Höhe vs. NN-bezogenes DEM) bringt der React-Viewer einen interaktiven
Z-Offset-Slider mit, der pro Anzeige korrigiert. Der ``track_z_offset``-
Parameter dieser Funktion erlaubt zusätzlich ein vorgebackenes Offset
für den Plotly-HTML-Pfad.
"""

from typing import Optional

import pandas as pd

from ..terrain.dem import sample_dem_at_points


def enrich_terrain_elevation(
    df: pd.DataFrame,
    dem_paths,
    *,
    track_z_offset: float = 0.0,
) -> pd.DataFrame:
    """Reichert einen Schema-B/C-DataFrame um Terrain-Höhe und Differenz an.

    Bei mehreren DEM-Tiles wird pro Track-Punkt automatisch das passende Tile
    verwendet (siehe ``sample_dem_at_points``).

    Parameters
    ----------
    df : pd.DataFrame
        Schema-B/C-DataFrame.
    dem_paths : str, Path, or iterable
        Ein Pfad oder eine Liste von DEM-Dateien.
    track_z_offset : float
        Offset, der vor der Differenz-Berechnung auf die Track-Höhe addiert
        wird. Nützlich, wenn Track und DEM unterschiedliche Höhen-Bezüge
        haben. Default 0.

    Returns
    -------
    pd.DataFrame
        Kopie des Eingabe-DataFrames mit zwei zusätzlichen Spalten:
        ``terrain_elevation`` und ``track_above_terrain``. Bei Fehler
        (DEM nicht ladbar) sind beide Spalten NaN.
    """
    result = df.copy()
    result["terrain_elevation"] = pd.NA
    result["track_above_terrain"] = pd.NA

    if "directional_latitude" not in df.columns or "directional_longitude" not in df.columns:
        print("DataFrame hat keine directional_latitude/longitude-Spalten.")
        return result

    elevations = sample_dem_at_points(
        df["directional_latitude"].to_numpy(),
        df["directional_longitude"].to_numpy(),
        dem_paths,
    )
    if elevations is None:
        return result

    result["terrain_elevation"] = elevations
    if "altitude_corrected" in df.columns:
        adjusted_track = df["altitude_corrected"].astype("Float64") + track_z_offset
        result["track_above_terrain"] = adjusted_track - elevations

    n_valid = result["terrain_elevation"].notna().sum()
    print(f"Terrain-Anreicherung: {n_valid} von {len(result)} Punkten "
          f"haben DEM-Daten.")
    if "altitude_corrected" in df.columns and n_valid > 0:
        agl = result["track_above_terrain"].dropna()
        if len(agl) > 0:
            print(f"  Höhe über Grund: Min {agl.min():.1f} m, "
                  f"Median {agl.median():.1f} m, Max {agl.max():.1f} m")

    return result
