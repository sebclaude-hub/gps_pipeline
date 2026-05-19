"""Satelliten-Konstellation pro Track-Punkt anheften.

Für jeden Schema-C-Track-Punkt wird die zuletzt empfangene GSV-Multi-Sentence-
Group **pro Konstellation (Talker-ID)** ermittelt — also: "was war zu dem
Zeitpunkt am Himmel?" mit Forward-Fill der letzten gültigen Werte, falls in
dem Moment selbst kein neuer GSV-Burst angekommen ist.

Hintergrund
-----------
GSV-Sätze kommen typischerweise alle 1–5 Sekunden, während Positions-Sätze
mit ~10 Hz fließen. Heißt: pro Track-Punkt ist meist *kein* aktueller
GSV-Burst da, sondern einer ein paar Hundert Millisekunden bis Sekunden vorher.
Diese Funktion macht das Mapping einheitlich.

Bei Multi-Constellation-Empfängern liefert jeder Talker (GP, GL, GA, GB, …)
eigene GSV-Sätze. Die werden hier **getrennt** behandelt — pro Track-Punkt
gibt es eine Zeile *pro Talker* im Output. Das vermeidet das Vermischen von
PRN-Nummern aus verschiedenen Systemen (PRNs sind nur innerhalb einer
Konstellation eindeutig).

Datenfluss
----------
Eingabe:
  * ``df_c`` (Schema C): eine Zeile pro Track-Timestamp
  * ``df_raw`` (Schema A): GSV-Zeilen mit ``talker_id``, ``timestamp_utc``,
    ``gsv_satellites``

Ausgabe: Long-format DataFrame mit den Spalten

  track_idx        : int       — Index im df_c (zum Verknüpfen)
  track_timestamp  : datetime  — Zeit des Track-Punktes
  talker_id        : str       — z.B. "GP", "GL", "GA"
  gsv_timestamp    : datetime  — Zeit des verwendeten GSV-Bursts
  satellites       : list[dict] — Liste der sichtbaren Satelliten
  age_seconds      : float32   — Track-Timestamp minus GSV-Timestamp

Zeilen vor dem ersten GSV-Burst eines Talkers tauchen im Output **nicht** auf
(merge_asof mit direction='backward' liefert dort NaN, das filtern wir).
"""

from typing import List

import pandas as pd


_OUTPUT_COLUMNS = [
    "track_idx",
    "track_timestamp",
    "talker_id",
    "gsv_timestamp",
    "satellites",
    "age_seconds",
]


def align_satellites_to_track(
    df_c: pd.DataFrame,
    df_raw: pd.DataFrame,
) -> pd.DataFrame:
    """Heftet jeden Track-Punkt mit dem zuletzt gültigen GSV-Burst zusammen.

    Pro Track-Punkt und pro Talker-ID eine Zeile. Die ``satellites``-Spalte
    enthält die Liste der zum Zeitpunkt zuletzt sichtbaren Satelliten dieser
    Konstellation.

    Parameters
    ----------
    df_c : pd.DataFrame
        Schema-C-DataFrame. Muss mindestens die Spalte ``timestamp_utc``
        enthalten. Der DataFrame-Index wird als ``track_idx`` im Output
        verwendet — der ist im aktuellen Pipeline-Stack ein einfacher
        RangeIndex 0..n-1.
    df_raw : pd.DataFrame
        Schema-A-DataFrame mit GSV-Zeilen. Muss die Spalten
        ``sentence_type``, ``talker_id``, ``timestamp_utc`` und
        ``gsv_satellites`` enthalten.

    Returns
    -------
    pd.DataFrame
        Long-format DataFrame nach ``_OUTPUT_COLUMNS``. Leer, wenn keine
        GSV-Daten vorhanden sind. Sortiert nach (track_idx, talker_id).

    Notes
    -----
    Ein leerer GSV-Burst (``num_sv_in_view = 0`` → leere Satellitenliste)
    wird genauso behandelt wie ein "normaler" Burst: er bleibt der "zuletzt
    gültige" für die folgenden Track-Punkte. Das ist absichtlich — wenn der
    Empfänger meldet "ich sehe gerade nichts", ist das eine relevante
    Information, kein Datenverlust. In der Visualisierung führt das zu einem
    leeren Polar-Plot, was den Zustand korrekt abbildet.
    """
    # Eingangsprüfungen — schadlose No-Ops bei degenerierten Inputs.
    if df_c.empty:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    required_raw_cols = {"sentence_type", "talker_id", "timestamp_utc",
                         "gsv_satellites"}
    missing = required_raw_cols - set(df_raw.columns)
    if missing:
        print(f"align_satellites_to_track: df_raw fehlen Spalten {missing}. "
              f"Kein Alignment möglich.")
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    if "timestamp_utc" not in df_c.columns:
        print("align_satellites_to_track: df_c fehlt timestamp_utc.")
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    # 1. GSV-Zeilen rausziehen, ungültige Timestamps verwerfen
    gsv = df_raw[df_raw["sentence_type"] == "GSV"].copy()
    gsv = gsv.dropna(subset=["timestamp_utc"])
    if gsv.empty:
        print("align_satellites_to_track: Keine GSV-Zeilen mit gültigem "
              "Timestamp im df_raw. Output ist leer.")
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    # 2. Track-Tabelle vorbereiten
    track = pd.DataFrame({
        "track_idx": df_c.index.to_numpy(),
        "track_timestamp": pd.to_datetime(df_c["timestamp_utc"], utc=True).to_numpy(),
    })
    # merge_asof verlangt sortierte Schlüssel und keine NaT
    track = track.dropna(subset=["track_timestamp"])
    track = track.sort_values("track_timestamp", kind="stable").reset_index(drop=True)
    if track.empty:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    # 3. Pro Talker-ID separat asof-mergen
    # Grund: merge_asof's by-Parameter würde voraussetzen, dass beide DFs
    # die by-Spalte haben — df_c hat aber keine talker_id (Position ist
    # talker-unabhängig). Pro Talker einzeln zu mergen ist klarer und
    # vermeidet Sortier-Klimmzüge.
    talker_ids: List[str] = sorted(
        gsv["talker_id"].dropna().astype(str).unique().tolist()
    )
    if not talker_ids:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    parts: List[pd.DataFrame] = []
    for talker in talker_ids:
        gsv_t = gsv.loc[gsv["talker_id"] == talker,
                        ["timestamp_utc", "gsv_satellites"]].copy()
        gsv_t = gsv_t.rename(columns={
            "timestamp_utc": "gsv_timestamp",
            "gsv_satellites": "satellites",
        })
        # GSV-Timestamps können prinzipiell duplizieren (mehrere Bursts
        # im selben Tick, sollte aber selten sein). Behalte den letzten —
        # das ist der zeitlich aktuellste Stand.
        gsv_t = gsv_t.sort_values("gsv_timestamp", kind="stable")
        gsv_t = gsv_t.drop_duplicates(subset="gsv_timestamp", keep="last")
        # Datetime-Typ konsistent zu track halten
        gsv_t["gsv_timestamp"] = pd.to_datetime(gsv_t["gsv_timestamp"], utc=True)

        merged = pd.merge_asof(
            track,
            gsv_t,
            left_on="track_timestamp",
            right_on="gsv_timestamp",
            direction="backward",
        )
        merged["talker_id"] = talker
        # age in Sekunden — schmaler Float reicht, wird nur für Anzeige genutzt
        age = (merged["track_timestamp"] - merged["gsv_timestamp"]).dt.total_seconds()
        merged["age_seconds"] = age.astype("float32")
        # Zeilen vor dem ersten Burst dieses Talkers raus (NaT in gsv_timestamp)
        merged = merged.dropna(subset=["gsv_timestamp"])
        parts.append(merged)

    if not parts:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    out = pd.concat(parts, ignore_index=True)
    out = out[_OUTPUT_COLUMNS]
    out = out.sort_values(["track_idx", "talker_id"], kind="stable").reset_index(drop=True)

    n_track_pts = out["track_idx"].nunique()
    print(f"Satelliten-Alignment: {len(out)} Zeilen für {n_track_pts} Track-Punkte "
          f"× {len(talker_ids)} Konstellation(en) ({', '.join(talker_ids)}).")
    return out
