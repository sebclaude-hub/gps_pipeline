"""Schema-A → Schema-B: GGA, RMC, VTG pro Timestamp zusammenführen.

Eingabe: Schema-A-DataFrame, gefiltert. Eine Zeile pro NMEA-Satz.
Ausgabe: Schema-B-DataFrame. **Eine Zeile pro Timestamp.**

Hintergrund
-----------
Der Empfänger sendet pro Sample-Tick typischerweise drei Sätze:
  * RMC: Position + Zeit + Geschwindigkeit (knots)
  * GGA: Position + Höhe + Fix-Qualität
  * VTG: Geschwindigkeit (knots und km/h) + Kurs

Alle drei haben denselben ``timestamp_utc``. Für nachgelagerte Analysen
wollen wir aber eine Zeile pro Timestamp, mit allen relevanten Werten in
gleichen Spalten. Diese Funktion macht den Pivot.

Strategie
---------
* Basis sind die GGA-Zeilen (Position + Höhe sind die primäre Quelle).
* Pro Timestamp die Geschwindigkeit aus RMC und VTG dazumergen.
* Höhe = altitude + geo_separation (GGA-konform, gibt Höhe über WGS84-Ellipsoid).
* Lücken in Höhe und Geschwindigkeit linear interpolieren.
* GSV- und GSA-Zeilen werden hier verworfen (Diagnose-Daten).
"""

import pandas as pd


# Schema-B-Spalten, die in dieser Reihenfolge im Output stehen:
_SCHEMA_B_COLUMNS = [
    "timestamp_utc",
    "directional_latitude",
    "directional_longitude",
    "altitude_corrected",
    "speed_kmh",
    "speed_knots",
    # Diagnose-Felder (optional — NaN wenn Empfänger sie nicht liefert)
    "gga_gps_quality",
    "gga_num_sats",
    "gga_hdop",
    "gsa_vdop",
    "gsa_fix_type",
]


def consolidate(df: pd.DataFrame) -> pd.DataFrame:
    """Konsolidiert Schema-A → Schema-B (eine Zeile pro Timestamp).

    Verwendet GGA-Zeilen als Basis (Position + Höhe), mergt RMC-Geschwindigkeit
    und VTG-Geschwindigkeit pro Timestamp dazu. Interpoliert Lücken linear.

    Parameters
    ----------
    df : pd.DataFrame
        Schema-A-DataFrame, typischerweise nach filter_invalid().

    Returns
    -------
    pd.DataFrame
        Schema-B-DataFrame mit den Spalten in _SCHEMA_B_COLUMNS.
        Standard-RangeIndex 0..n-1.
    """
    if df.empty:
        return pd.DataFrame(columns=_SCHEMA_B_COLUMNS)

    # 1. Basis aus GGA-Zeilen
    gga = df[df["sentence_type"] == "GGA"].copy()
    if gga.empty:
        print("Warnung: Keine GGA-Zeilen im DataFrame. Schema-B-Ausgabe ist leer.")
        return pd.DataFrame(columns=_SCHEMA_B_COLUMNS)

    # Höhe = altitude über MSL (= NN-Bezug). Die Geoid-Trennung wird NICHT
    # addiert, weil deutsche/europäische DEMs (z.B. DGM, Copernicus EU-DEM)
    # ebenfalls NN-bezogen sind. Wer ellipsoidische Höhe braucht, kann
    # gga_altitude + gga_geo_separation selbst bilden.
    # Float32 reicht für Höhe (Auflösung ~0.1 m bei 8000 m über NN — mehr als
    # der Sensor liefert).
    gga["altitude_corrected"] = gga["gga_altitude"].astype("float32")

    base = gga[["timestamp_utc", "directional_latitude", "directional_longitude",
                "altitude_corrected"]].copy()

    # Falls mehrere GGA pro Timestamp existieren (sollte nach Filter selten sein):
    # nimm den ersten. drop_duplicates ist hier defensiv.
    base = base.drop_duplicates(subset="timestamp_utc", keep="first")

    # 2. RMC-Geschwindigkeit pro Timestamp dazu
    rmc = (df[df["sentence_type"] == "RMC"]
           [["timestamp_utc", "rmc_speed_knots"]]
           .drop_duplicates(subset="timestamp_utc", keep="first"))

    # 3. VTG-Geschwindigkeit pro Timestamp dazu
    vtg = (df[df["sentence_type"] == "VTG"]
           [["timestamp_utc", "vtg_speed_knots", "vtg_speed_kmph"]]
           .drop_duplicates(subset="timestamp_utc", keep="first"))

    # 3b. GGA-Diagnosefelder (Fix-Qualität, Anzahl Sats, HDOP)
    gga_diag_cols = [c for c in ("gga_gps_quality", "gga_num_sats", "gga_hdop")
                     if c in df.columns]
    if gga_diag_cols:
        gga_diag = (df[df["sentence_type"] == "GGA"]
                    [["timestamp_utc"] + gga_diag_cols]
                    .drop_duplicates(subset="timestamp_utc", keep="first"))
    else:
        gga_diag = None

    # 3c. GSA-Diagnosefelder (VDOP, Fix-Typ)
    gsa_diag_cols = [c for c in ("gsa_vdop", "gsa_fix_type")
                     if c in df.columns]
    if gsa_diag_cols and "GSA" in df["sentence_type"].values:
        gsa_diag = (df[df["sentence_type"] == "GSA"]
                    [["timestamp_utc"] + gsa_diag_cols]
                    .drop_duplicates(subset="timestamp_utc", keep="first"))
    else:
        gsa_diag = None

    # Mergen — LEFT JOIN, weil GGA die Basis ist
    result = base.merge(rmc, on="timestamp_utc", how="left")
    result = result.merge(vtg, on="timestamp_utc", how="left")
    if gga_diag is not None:
        result = result.merge(gga_diag, on="timestamp_utc", how="left")
    if gsa_diag is not None:
        result = result.merge(gsa_diag, on="timestamp_utc", how="left")

    # 4. Vereinheitlichte Geschwindigkeitsspalten
    #    - speed_knots: bevorzugt aus RMC, Fallback VTG
    #    - speed_kmh: aus VTG; wenn nicht vorhanden, aus speed_knots umrechnen
    # Float32 reicht (Sensor-Auflösung typisch ~0.01 m/s).
    result["speed_knots"] = (
        result["rmc_speed_knots"].astype("float32")
        .combine_first(result["vtg_speed_knots"].astype("float32"))
    ).astype("float32")
    result["speed_kmh"] = result["vtg_speed_kmph"].astype("float32")
    # Fehlende speed_kmh aus speed_knots berechnen (1 kn = 1.852 km/h)
    fill_mask = result["speed_kmh"].isna() & result["speed_knots"].notna()
    result.loc[fill_mask, "speed_kmh"] = result.loc[fill_mask, "speed_knots"] * 1.852

    # 5. Lücken in Höhe und Geschwindigkeit linear interpolieren
    for col in ("altitude_corrected", "speed_kmh", "speed_knots"):
        # `limit_direction='both'` füllt auch am Anfang/Ende falls dort NaN steht
        result[col] = result[col].interpolate(method="linear", limit_direction="both")

    # 6. Sortieren, nur vorhandene Schema-B-Spalten behalten, RangeIndex aufsetzen
    result = result.sort_values("timestamp_utc", kind="stable").reset_index(drop=True)
    present = [c for c in _SCHEMA_B_COLUMNS if c in result.columns]
    result = result[present]

    print(f"Konsolidiert: {len(result)} Zeilen (Schema B).")
    return result
