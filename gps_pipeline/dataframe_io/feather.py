"""DataFrame-Export und -Import im Feather-Format.

Feather (Arrow IPC v2) ist die schnellste Variante für den temporären
Austausch zwischen Skripten und behält alle Spalten-Typen sauber bei:
datetime mit UTC, Categoricals, nullable Integer (UInt8, Int64), Object-
Spalten mit Listen (z.B. ``gsv_satellites``).

Nicht zur Langzeit-Archivierung gedacht — die Format-Stabilität wird zwar
vom Arrow-Projekt gepflegt, ist aber laut Doku nicht als Lagerformat
versprochen. Für unsere Pipeline ist das egal: wir brauchen das nur, um
einen DataFrame in einem anderen Skript (z.B. Trimming) weiterzuverarbeiten.

Beispiel-Nutzung
----------------
.. code-block:: python

    from gps_pipeline.dataframe_io.feather import save_df, load_df

    # Im Visualisierungs-Skript:
    save_df(df_c, "output/track_2023-09-20.feather")

    # Im Trimming-Skript:
    df = load_df("output/track_2023-09-20.feather")
    df_trimmed = df.loc[100:5000]   # Index 100 bis 5000 behalten
    save_df(df_trimmed, "output/track_2023-09-20_trimmed.feather")
"""

from pathlib import Path
from typing import Union

import pandas as pd


def save_df(df: pd.DataFrame, path: Union[str, Path]) -> None:
    """Schreibt einen DataFrame im Feather-Format auf die Platte.

    Der DataFrame-Index wird mit-serialisiert (als reset_index-Spalte
    'index'), damit beim Laden die Indizes erhalten bleiben. Das ist
    wichtig, weil Hover-Texte den Index als Identifikator nutzen.

    Parameters
    ----------
    df : pd.DataFrame
        Beliebiger DataFrame.
    path : str or Path
        Zielpfad. Endung ``.feather`` wird angefügt, wenn nicht vorhanden.
    """
    p = Path(path)
    if p.suffix.lower() != ".feather":
        p = p.with_suffix(".feather")
    p.parent.mkdir(parents=True, exist_ok=True)

    # Feather kann keinen benannten RangeIndex serialisieren; wir resetten
    # ihn in eine normale Spalte mit dem Standardnamen 'original_index'.
    # Beim Laden wird die wieder zum Index gemacht.
    out = df.reset_index().rename(columns={"index": "original_index"})
    out.to_feather(p)
    print(f"DataFrame geschrieben: {p} ({len(df)} Zeilen, {len(df.columns)} Spalten)")


def load_df(path: Union[str, Path]) -> pd.DataFrame:
    """Lädt einen DataFrame aus einer Feather-Datei.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    pd.DataFrame
        Mit dem ursprünglichen Index, falls beim Speichern mit ``save_df``
        geschrieben.
    """
    p = Path(path)
    df = pd.read_feather(p)
    if "original_index" in df.columns:
        df = df.set_index("original_index")
        df.index.name = None
    print(f"DataFrame gelesen: {p} ({len(df)} Zeilen, {len(df.columns)} Spalten)")
    return df
