"""Ungültige NMEA-Einträge aus dem Roh-DataFrame entfernen.

Eingabe: Schema-A-DataFrame (siehe parsing/nmea_to_dataframe.py).
Ausgabe: Schema-A-DataFrame mit weniger Zeilen.

Filterstrategie, in dieser Reihenfolge:
  1. Alle Zeilen vor dem ersten gültigen RMC (status='A') wegwerfen
     — der Empfänger braucht typischerweise einige Sekunden bis zum Fix,
     in dieser Zeit sind die Positionsdaten Müll.
  2. GGA-Sätze mit ungültiger Fix-Qualität (0 = no fix, 5 = float RTK)
     entfernen.
  3. RMC- und VTG-Sätze ohne Anker zu einem gültigen GGA wegwerfen
     (verwaiste Geschwindigkeitsdaten).
  4. GSA-Sätze mit Fix-Typ 1 (no fix) entfernen.

Was nicht gefiltert wird:
  * GSV-Aggregat-Zeilen — die liefern Diagnosedaten unabhängig von der
    Position und können auch dann interessant sein, wenn der Fix gerade
    schwankt.
"""

from typing import Optional

import pandas as pd

from ..config import EXCLUDE_GGA_QUALITIES, EXCLUDE_GSA_FIX_TYPES


def _drop_before_first_valid_rmc(df: pd.DataFrame) -> pd.DataFrame:
    """Entfernt alle Zeilen mit Timestamp vor dem ersten RMC mit status='A'.

    Zeilen ohne Timestamp (NaT) bleiben erhalten — sie können nicht zeitlich
    eingeordnet werden, und ihre Entfernung wäre vorschnell.
    """
    valid_rmc = df[(df["sentence_type"] == "RMC") & (df["rmc_status"] == "A")]
    if valid_rmc.empty:
        print("Warnung: Kein gültiger RMC-Satz (status='A') gefunden. "
              "Filter 'vor erstem Fix' wird übersprungen.")
        return df

    first_ts = valid_rmc["timestamp_utc"].min()
    if pd.isna(first_ts):
        print("Warnung: Erster gültiger RMC hat keinen Timestamp. "
              "Filter 'vor erstem Fix' wird übersprungen.")
        return df

    keep = (df["timestamp_utc"] >= first_ts) | df["timestamp_utc"].isna()
    n_removed = (~keep).sum()
    if n_removed > 0:
        print(f"Filter: {n_removed} Zeilen vor erstem gültigen RMC ({first_ts}) entfernt.")
    return df[keep].copy()


def _drop_invalid_gga(df: pd.DataFrame) -> pd.DataFrame:
    """GGA-Sätze mit Fix-Qualität in EXCLUDE_GGA_QUALITIES entfernen."""
    bad = (df["sentence_type"] == "GGA") & df["gga_gps_quality"].isin(EXCLUDE_GGA_QUALITIES)
    n_removed = bad.sum()
    if n_removed > 0:
        print(f"Filter: {n_removed} GGA-Zeilen mit ungültiger Fix-Qualität entfernt.")
    return df[~bad].copy()


def _drop_unlinked_rmc_vtg(df: pd.DataFrame) -> pd.DataFrame:
    """RMC/VTG entfernen, die keinen passenden gültigen GGA-Timestamp haben.

    Begründung: RMC und VTG transportieren Geschwindigkeit/Kurs, aber ohne
    eine zugehörige GGA-Position (mit gutem Fix) sind die Werte schwer
    verifizierbar. Sie werden deshalb verworfen.
    """
    valid_gga_ts = df.loc[
        (df["sentence_type"] == "GGA")
        & ~df["gga_gps_quality"].isin(EXCLUDE_GGA_QUALITIES),
        "timestamp_utc",
    ].dropna().unique()

    rmc_vtg = df["sentence_type"].isin(["RMC", "VTG"])
    bad = rmc_vtg & ~df["timestamp_utc"].isin(valid_gga_ts)
    n_removed = bad.sum()
    if n_removed > 0:
        print(f"Filter: {n_removed} RMC/VTG-Zeilen ohne GGA-Anker entfernt.")
    return df[~bad].copy()


def _drop_invalid_gsa(df: pd.DataFrame) -> pd.DataFrame:
    """GSA-Sätze mit Fix-Typ in EXCLUDE_GSA_FIX_TYPES (default: 1 = no fix) entfernen."""
    bad = (df["sentence_type"] == "GSA") & df["gsa_fix_type"].isin(EXCLUDE_GSA_FIX_TYPES)
    n_removed = bad.sum()
    if n_removed > 0:
        print(f"Filter: {n_removed} GSA-Zeilen mit Fix-Typ 1 (no fix) entfernt.")
    return df[~bad].copy()


def filter_invalid(df: pd.DataFrame) -> pd.DataFrame:
    """Wendet alle Filter in fester Reihenfolge an.

    Eingabe und Ausgabe: Schema-A-DataFrame.
    Standard-RangeIndex wird am Ende neu aufgesetzt.
    """
    if df.empty:
        return df

    print(f"\nStarte Filter ({len(df)} Zeilen Eingabe).")
    n_before = len(df)

    df = _drop_before_first_valid_rmc(df)
    df = _drop_invalid_gga(df)
    df = _drop_unlinked_rmc_vtg(df)
    df = _drop_invalid_gsa(df)

    df = df.reset_index(drop=True)
    print(f"Filter fertig: {n_before} -> {len(df)} Zeilen ({n_before - len(df)} entfernt).\n")
    return df
