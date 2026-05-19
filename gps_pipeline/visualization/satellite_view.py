"""Polar-Plot ("Himmelskuppel") der aktuell sichtbaren Satelliten.

Eingabe: Schema-A-DataFrame (siehe parsing/nmea_to_dataframe.py).
Aus diesem werden die GSV-Zeilen genutzt — eine Zeile pro Multi-Sentence-
Group, mit fertiger Satellitenliste in der Spalte ``gsv_satellites``.

Anzeigelogik
------------
* Per Default die **zeitlich letzten** GSV-Gruppen werden gezeigt (eine pro
  Talker-ID, also pro Konstellation). Multi-Constellation-Empfänger geben
  GPS, GLONASS, Galileo, BeiDou usw. parallel aus — diese werden mit
  unterschiedlichen Marker-Formen unterschieden.
* Polar-Koordinaten: Azimuth als Winkel (0° = Norden, 90° = Osten),
  Elevation als Radius (90° im Zentrum = Zenit, 0° am Rand = Horizont).
* Markergröße proportional zur Signalstärke (SNR), Farbe ebenfalls.
"""

from typing import Dict, Optional

import pandas as pd
import plotly.graph_objects as go


# Talker-ID → Menschenname und Marker-Symbol für die Legende.
# Symbole müssen aus dem in Plotly für Scatterpolar gültigen Satz stammen.
_TALKER_LABELS: Dict[str, Dict[str, str]] = {
    "GP": {"name": "GPS", "symbol": "circle"},
    "GL": {"name": "GLONASS", "symbol": "square"},
    "GA": {"name": "Galileo", "symbol": "diamond"},
    "GB": {"name": "BeiDou", "symbol": "triangle-up"},
    "BD": {"name": "BeiDou", "symbol": "triangle-up"},      # alternatives Kürzel
    "GQ": {"name": "QZSS", "symbol": "x"},
    "GI": {"name": "NavIC", "symbol": "star"},
    "GN": {"name": "Multi-GNSS", "symbol": "cross"},
}


def visualize_satellites(
    df: pd.DataFrame,
    *,
    timestamp: Optional[pd.Timestamp] = None,
    title: Optional[str] = None,
) -> Optional[go.Figure]:
    """Polar-Plot der zum gegebenen Zeitpunkt sichtbaren Satelliten.

    Parameters
    ----------
    df : pd.DataFrame
        Schema-A-DataFrame, der GSV-Zeilen mit ``gsv_satellites``-Spalte enthält.
        Üblicherweise vor (oder nach) filter_invalid übergeben — Filter
        entfernt typischerweise keine GSV-Zeilen.
    timestamp : pd.Timestamp, optional
        Welcher Zeitpunkt soll dargestellt werden? Default: der letzte
        GSV-Timestamp im DataFrame. Wird der genaue Timestamp nicht gefunden,
        wird der zeitlich nächstgelegene verwendet.
    title : str, optional
        Plot-Titel. Default: automatisch mit Timestamp.

    Returns
    -------
    plotly.graph_objects.Figure or None
        None, wenn keine GSV-Zeilen vorhanden sind.
    """
    gsv = df[df["sentence_type"] == "GSV"].copy()
    if gsv.empty:
        print("Keine GSV-Zeilen im DataFrame. Satellite-View nicht möglich.")
        return None

    # Zielzeitpunkt bestimmen
    if timestamp is None:
        target_ts = gsv["timestamp_utc"].dropna().max()
        if pd.isna(target_ts):
            print("Keine GSV-Zeile mit gültigem Timestamp. Satellite-View nicht möglich.")
            return None
    else:
        # Nächstgelegener gültiger Timestamp
        valid = gsv["timestamp_utc"].dropna()
        if valid.empty:
            return None
        diffs = (valid - timestamp).abs()
        target_ts = valid.iloc[diffs.argmin()]

    # Alle GSV-Gruppen mit diesem Timestamp (potenziell mehrere bei Multi-Constellation)
    same_ts = gsv[gsv["timestamp_utc"] == target_ts]
    if same_ts.empty:
        print(f"Keine GSV-Daten zum Zeitpunkt {target_ts}.")
        return None

    fig = go.Figure()

    # Pro Konstellation eine Spur, damit die Legende sortiert ist
    for _, row in same_ts.iterrows():
        talker = row["talker_id"]
        meta = _TALKER_LABELS.get(talker, {"name": talker, "symbol": "circle-open"})
        sats = row.get("gsv_satellites", [])
        if not sats:
            continue

        # Daten extrahieren, nur Satelliten mit gültiger Elevation und Azimuth
        rs = []
        thetas = []
        sizes = []
        colors = []
        texts = []
        for sat in sats:
            elev = sat.get("elevation")
            az = sat.get("azimuth")
            snr = sat.get("snr")
            prn = sat.get("prn")
            if elev is None or az is None:
                continue
            # Polar-Konvention: Zenith (90°) ist im Zentrum, Horizont (0°) am Rand.
            # → r = 90 - elevation
            rs.append(90 - elev)
            thetas.append(az)
            if snr is not None and snr > 0:
                sizes.append(max(8, min(snr * 0.6, 30)))
                colors.append(snr)
            else:
                sizes.append(8)
                colors.append(0)
            texts.append(
                f"PRN {prn}<br>Elev: {elev}°<br>Azimuth: {az}°<br>"
                f"SNR: {snr if snr is not None else 'N/A'} dB"
            )

        if not rs:
            continue

        fig.add_trace(go.Scatterpolar(
            r=rs,
            theta=thetas,
            mode="markers+text",
            marker=dict(
                size=sizes,
                color=colors,
                colorscale="Viridis",
                cmin=0,
                cmax=50,
                symbol=meta["symbol"],
                line=dict(width=1, color="black"),
            ),
            text=[str(sat.get("prn", "")) for sat in sats if sat.get("elevation") is not None and sat.get("azimuth") is not None],
            textposition="middle center",
            textfont=dict(size=9),
            hovertext=texts,
            hoverinfo="text",
            name=f"{meta['name']} ({len(rs)} sats)",
        ))

    if not fig.data:
        print(f"Keine darstellbaren Satellitendaten zum Zeitpunkt {target_ts}.")
        return None

    auto_title = title or f"Satellitenverteilung am {target_ts}"
    fig.update_layout(
        title=auto_title,
        polar=dict(
            radialaxis=dict(
                range=[0, 90],
                tickmode="array",
                tickvals=[0, 30, 60, 90],
                ticktext=["90°", "60°", "30°", "0°"],  # Beschriftung Elevation
                angle=90,
            ),
            angularaxis=dict(
                tickmode="array",
                tickvals=[0, 90, 180, 270],
                ticktext=["N", "O", "S", "W"],
                direction="clockwise",
                rotation=90,  # 0° (N) nach oben
            ),
        ),
        showlegend=True,
        height=650,
        width=700,
    )
    return fig
