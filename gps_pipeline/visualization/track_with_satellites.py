"""3D-Track + synchronisierte Satellitenkonstellation, skalierungs-resilient.

Ablöser der vorigen Frame-basierten Variante. Hintergrund: Plotly-Frames
duplizieren pro Frame die kompletten Trace-Daten, was bei langen Tracks
(>10k Punkte) zu HTML-Dateien im dreistelligen Megabyte-Bereich führt.

Hier wird ein anderer Ansatz gewählt:

* Initialer Plotly-Plot mit drei Trace-Klassen — Track-Linie (statisch),
  Aktiver Marker (1-Punkt, wird per JS verschoben), Polar-Traces (einer
  pro Talker-ID, werden per JS umgefüllt).
* Sat-Daten werden **einmal** als JS-Objekt im HTML eingebettet, mit
  deduplizierten Bursts plus einer ``track_idx → burst_idx`` Lookup-Liste
  pro Talker. Damit ist die Daten-Größe ~linear in der Anzahl Bursts
  (typisch wenige Tausend pro Stunde), nicht in der Anzahl Track-Punkte.
* Ein HTML-Range-Slider plus Klick-Handler im 3D-Plot lösen Updates aus,
  die per ``Plotly.restyle`` die wenigen variablen Felder aktualisieren.

Größenordnungen
---------------
580er-Testfile (Frame-Variante): ~80 KB. Hier: ~150 KB (Initial-Overhead
ist ein bisschen größer, aber kein Frame-Overhead). Bei 60k Track-Punkten
und 4 Konstellationen: schätzungsweise 5–10 MB — unabhängig davon, wie
fein der Slider läuft, weil der Slider nichts kostet außer einem
DOM-Element.

Datenfluss
----------
1. ``align_satellites_to_track`` liefert die long-format Alignment-Tabelle.
2. ``_build_payload`` dedupliziert Bursts pro Talker und baut die
   ``track_idx → burst_idx`` Lookup-Liste.
3. ``_build_initial_figure`` setzt den Plotly-Plot auf (mit leeren Polar-
   Traces, aber allen statischen Marker-Eigenschaften).
4. ``_build_html`` baut die finale Single-File-HTML aus Plot-Div, Slider,
   Annotation-Div und JS-Handler.
"""

import html as _html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..config import (
    AVAILABLE_COLORSCALES,
    DEFAULT_COLORSCALE,
    DEFAULT_QUANTILES,
    DEFAULT_Z_EXAGGERATION,
)
from ..processing.gsv_align import align_satellites_to_track
from .three_d import (
    _add_terrain_surface,
    _equirectangular_meters,
    _make_hover_text,
    _quantile_color_indices,
)


# Talker-ID → Klarname + Marker-Symbol.
_TALKER_LABELS: Dict[str, Dict[str, str]] = {
    "GP": {"name": "GPS", "symbol": "circle"},
    "GL": {"name": "GLONASS", "symbol": "square"},
    "GA": {"name": "Galileo", "symbol": "diamond"},
    "GB": {"name": "BeiDou", "symbol": "triangle-up"},
    "BD": {"name": "BeiDou", "symbol": "triangle-up"},
    "GQ": {"name": "QZSS", "symbol": "x"},
    "GI": {"name": "NavIC", "symbol": "star"},
    "GN": {"name": "Multi-GNSS", "symbol": "cross"},
}


# ---------------------------------------------------------------------------
# 1. Payload-Aufbereitung
# ---------------------------------------------------------------------------

def _build_payload(df_c: pd.DataFrame, df_raw: pd.DataFrame) -> Dict[str, Any]:
    """Baut die kompakte JS-Datenstruktur.

    Returns
    -------
    dict mit Schlüsseln:
        talkers : list[str]
        bursts_by_talker : dict[str, list[dict]]
            Pro Talker eine chronologisch sortierte Liste von Bursts.
            Jeder Burst: {"ts_ms": int (Unix ms), "sats": list[list]}
            Wobei jedes Sat-Element = [elevation, azimuth, snr_or_None, prn_or_None]
        burst_idx_by_track : dict[str, list[int]]
            Pro Talker eine Liste der Länge len(df_c). Eintrag i ist der
            Burst-Index in bursts_by_talker[talker], oder -1 wenn vor erstem
            Burst dieses Talkers.
        track_timestamps_ms : list[int or None]
            Track-Zeitstempel in Unix-ms, für die Anzeige.
    """
    aligned = align_satellites_to_track(df_c, df_raw)
    n_track = len(df_c)
    talkers: List[str] = (
        sorted(aligned["talker_id"].unique().tolist())
        if not aligned.empty else []
    )

    bursts_by_talker: Dict[str, List[dict]] = {}
    burst_idx_by_track: Dict[str, List[int]] = {}

    for talker in talkers:
        rows = aligned[aligned["talker_id"] == talker]
        # Dedup: gleiche gsv_timestamp = gleicher Burst (forward-fill wiederholt
        # sich pro Track-Punkt, aber die zugrundeliegenden Daten sind identisch).
        unique_bursts = (
            rows.drop_duplicates(subset="gsv_timestamp", keep="first")
                .sort_values("gsv_timestamp")
                .reset_index(drop=True)
        )

        burst_list: List[dict] = []
        burst_ts_to_idx: Dict[pd.Timestamp, int] = {}
        for j, br in unique_bursts.iterrows():
            sats_compact: List[list] = []
            for sat in (br["satellites"] or []):
                el = sat.get("elevation")
                az = sat.get("azimuth")
                snr = sat.get("snr")
                prn = sat.get("prn")
                if el is None or az is None:
                    continue
                try:
                    el_f = float(el)
                    az_f = float(az)
                except (TypeError, ValueError):
                    continue
                snr_v = float(snr) if snr is not None else None
                prn_v = int(prn) if prn is not None else None
                sats_compact.append([el_f, az_f, snr_v, prn_v])
            burst_list.append({
                "ts_ms": int(br["gsv_timestamp"].timestamp() * 1000),
                "sats": sats_compact,
            })
            burst_ts_to_idx[br["gsv_timestamp"]] = j

        bursts_by_talker[talker] = burst_list

        # Pro Track-Idx den Burst-Index hinterlegen
        track_to_burst: Dict[int, int] = {}
        for _, r in rows.iterrows():
            track_to_burst[int(r["track_idx"])] = burst_ts_to_idx[r["gsv_timestamp"]]
        burst_idx_by_track[talker] = [
            track_to_burst.get(i, -1) for i in range(n_track)
        ]

    # Track-Timestamps in Unix-ms
    track_ts = pd.to_datetime(df_c["timestamp_utc"], utc=True, errors="coerce")
    track_ts_ms: List[Optional[int]] = []
    for t in track_ts:
        if pd.notna(t):
            track_ts_ms.append(int(t.timestamp() * 1000))
        else:
            track_ts_ms.append(None)

    return {
        "talkers": talkers,
        "bursts_by_talker": bursts_by_talker,
        "burst_idx_by_track": burst_idx_by_track,
        "track_timestamps_ms": track_ts_ms,
    }


# ---------------------------------------------------------------------------
# 2. Initiale Plotly-Figure
# ---------------------------------------------------------------------------

def _build_initial_figure(
    df_c: pd.DataFrame,
    talkers: List[str],
    *,
    color_by: str,
    n_quantiles: int,
    z_exaggeration: float,
    colorscale: str,
    dem_data: Optional[Dict[str, np.ndarray]],
    terrain_colorscale: str,
    terrain_opacity: float,
    track_z_offset: float,
    title: Optional[str],
) -> Tuple[go.Figure, Dict[str, int]]:
    """Baut den Initial-Plot.

    Returns
    -------
    (fig, trace_indices)
        trace_indices = {
            "track": int,       # 3D-Track-Linie (für plotly_click)
            "active": int,      # 1-Punkt aktiver Marker
            "polar_start": int, # Index des ersten Polar-Trace; weitere folgen
        }
    """
    ref_lat = float(df_c["directional_latitude"].mean())
    ref_lon = float(df_c["directional_longitude"].mean())
    track_x, track_y = _equirectangular_meters(
        df_c["directional_latitude"].to_numpy(),
        df_c["directional_longitude"].to_numpy(),
        ref_lat, ref_lon,
    )
    track_z = df_c["altitude_corrected"].to_numpy().astype(float) + track_z_offset

    color_norm = _quantile_color_indices(df_c[color_by], n_quantiles)
    hover = _make_hover_text(df_c)

    fig = make_subplots(
        rows=1, cols=2,
        specs=[[{"type": "scene"}, {"type": "polar"}]],
        column_widths=[0.62, 0.38],
        subplot_titles=("3D-Track", "Sichtbare Satelliten (Skyplot)"),
        horizontal_spacing=0.05,
    )

    trace_indices: Dict[str, int] = {}
    next_idx = 0

    # 1. Optional: Terrain als Erstes (damit Track darüber liegt)
    if dem_data is not None:
        _add_terrain_surface(
            fig, dem_data, terrain_colorscale, terrain_opacity,
            ref_lat=ref_lat, ref_lon=ref_lon,
        )
        # _add_terrain_surface fügt eine Trace hinzu — zählen.
        next_idx = len(fig.data)

    # 2. Track-Linie
    fig.add_trace(
        go.Scatter3d(
            x=track_x, y=track_y, z=track_z,
            mode="lines+markers",
            line=dict(width=4, color="rgba(120,120,120,0.4)"),
            marker=dict(
                size=4,
                color=color_norm,
                colorscale=colorscale,
                colorbar=dict(title=color_by, x=0.55, len=0.7),
                cmin=0, cmax=max(1, n_quantiles - 1),
                showscale=True,
            ),
            text=hover,
            hovertemplate="%{text}<extra></extra>",
            name="Track",
            showlegend=False,
        ),
        row=1, col=1,
    )
    trace_indices["track"] = next_idx
    next_idx += 1

    # 3. Aktiver Marker (1-Punkt, wird per JS verschoben)
    fig.add_trace(
        go.Scatter3d(
            x=[track_x[0]], y=[track_y[0]], z=[track_z[0]],
            mode="markers",
            marker=dict(size=14, color="#ff3b3b",
                        line=dict(color="#ffffff", width=2),
                        symbol="diamond"),
            name="Aktueller Punkt",
            showlegend=False,
            hoverinfo="skip",
        ),
        row=1, col=1,
    )
    trace_indices["active"] = next_idx
    next_idx += 1

    # 4. Polar-Traces — einer pro Talker, initial leer.
    # Hier setzen wir alle STATISCHEN Eigenschaften (colorscale, cmin/cmax,
    # symbol, line, textposition). Bei späteren restyle-Aufrufen werden nur
    # die dynamischen Felder (r, theta, marker.size, marker.color, text,
    # hovertext) überschrieben.
    trace_indices["polar_start"] = next_idx
    for talker in talkers:
        meta = _TALKER_LABELS.get(talker, {"name": talker, "symbol": "circle-open"})
        fig.add_trace(
            go.Scatterpolar(
                r=[], theta=[],
                mode="markers+text",
                marker=dict(
                    size=[],
                    color=[],
                    colorscale="Viridis",
                    cmin=0, cmax=50,
                    symbol=meta["symbol"],
                    line=dict(color="#222", width=1),
                ),
                text=[],
                textposition="top center",
                textfont=dict(size=9),
                hovertext=[],
                hoverinfo="text",
                name=meta["name"],
                showlegend=True,
            ),
            row=1, col=2,
        )
        next_idx += 1

    # 5. Layout
    x_range = float(np.nanmax(track_x) - np.nanmin(track_x)) or 1.0
    y_range = float(np.nanmax(track_y) - np.nanmin(track_y)) or 1.0
    z_range = float(np.nanmax(track_z) - np.nanmin(track_z)) or 1.0
    horizontal = max(x_range, y_range)
    z_aspect = max(0.05, min(1.0, (z_range / horizontal) * z_exaggeration))

    fig.update_layout(
        title=title or "GPS-Track mit synchroner Satellitenkonstellation",
        scene=dict(
            xaxis=dict(title="Ost (m)"),
            yaxis=dict(title="Nord (m)"),
            zaxis=dict(title="Höhe (m MSL)"),
            aspectmode="manual",
            aspectratio=dict(
                x=x_range / horizontal,
                y=y_range / horizontal,
                z=z_aspect,
            ),
        ),
        polar=dict(
            radialaxis=dict(
                range=[0, 90],
                tickmode="array",
                tickvals=[0, 30, 60, 90],
                ticktext=["90°", "60°", "30°", "0°"],
                angle=90,
                tickangle=90,
            ),
            angularaxis=dict(
                direction="clockwise",
                rotation=90,
                tickmode="array",
                tickvals=[0, 90, 180, 270],
                ticktext=["N", "O", "S", "W"],
            ),
        ),
        legend=dict(x=1.0, y=0.05, xanchor="right"),
        margin=dict(l=10, r=10, t=60, b=10),
    )
    return fig, trace_indices


# ---------------------------------------------------------------------------
# 3. HTML zusammenbauen
# ---------------------------------------------------------------------------

# JS-Snippet als Template. Wird mit `.format()` mit den nötigen Werten gefüllt.
# Achtung: alle wörtlichen geschweiften Klammern in JS-Code-Bereichen sind
# doppelt ({{ und }}), damit .format() sie als Literale belässt.
_JS_TEMPLATE = """
(function() {{
    const PAYLOAD = {payload_json};
    const TRACK_CURVE = {track_curve};
    const ACTIVE_CURVE = {active_curve};
    const POLAR_START = {polar_start};
    const PLOT_DIV_ID = {plot_div_id_json};
    const SLIDER_ID = {slider_id_json};
    const ANNO_ID = {anno_id_json};

    const NAME_MAP = {name_map_json};

    let lastIdx = -1;

    function pad2(n) {{ return String(n).padStart(2, '0'); }}
    function pad3(n) {{ return String(n).padStart(3, '0'); }}

    function formatTs(ms) {{
        if (ms === null || ms === undefined) return 'N/A';
        const d = new Date(ms);
        return pad2(d.getUTCHours()) + ':' + pad2(d.getUTCMinutes()) + ':'
             + pad2(d.getUTCSeconds()) + '.' + pad3(d.getUTCMilliseconds())
             + ' UTC';
    }}

    function escapeHtml(s) {{
        return String(s).replace(/[&<>"']/g, function(c) {{
            return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c];
        }});
    }}

    function buildPolarUpdate(burst) {{
        const rs = [], thetas = [], sizes = [], colors = [];
        const labels = [], hovers = [];
        for (let i = 0; i < burst.sats.length; i++) {{
            const s = burst.sats[i];
            const el = s[0], az = s[1], snr = s[2], prn = s[3];
            rs.push(90 - el);
            thetas.push(az);
            const snrVal = (snr === null || snr === undefined) ? 0 : snr;
            sizes.push(Math.max(8, Math.min(22, 8 + snrVal * 0.28)));
            colors.push(snrVal);
            labels.push(prn !== null && prn !== undefined ? String(prn) : '');
            const snrStr = (snr === null || snr === undefined) ? '—' : Math.round(snr);
            const prnStr = (prn === null || prn === undefined) ? '?' : prn;
            hovers.push('PRN ' + prnStr + '<br>Elevation: ' + Math.round(el) + '°'
                + '<br>Azimuth: ' + Math.round(az) + '°<br>SNR: ' + snrStr + ' dB-Hz');
        }}
        return {{r: rs, theta: thetas, sizes: sizes, colors: colors,
                labels: labels, hovers: hovers}};
    }}

    function updateView(trackIdx) {{
        if (trackIdx === lastIdx) return;
        lastIdx = trackIdx;

        const gd = document.getElementById(PLOT_DIV_ID);
        if (!gd || !gd.data) return;

        // Aktiver Marker: Position aus Track-Trace lesen
        const track = gd.data[TRACK_CURVE];
        const ax = track.x[trackIdx];
        const ay = track.y[trackIdx];
        const az = track.z[trackIdx];

        // Polar-Updates pro Talker sammeln
        const polarUpdates = {{
            r: [], theta: [],
            'marker.size': [], 'marker.color': [],
            text: [], hovertext: []
        }};
        const polarTraceIdx = [];

        const trackTsMs = PAYLOAD.track_timestamps_ms[trackIdx];
        let annoLines = ['<b>Track-Punkt ' + trackIdx + '</b>'];
        if (trackTsMs !== null && trackTsMs !== undefined) {{
            annoLines.push(formatTs(trackTsMs));
        }}
        annoLines.push('');
        let anyBurst = false;

        for (let t = 0; t < PAYLOAD.talkers.length; t++) {{
            const talker = PAYLOAD.talkers[t];
            const burstIdx = PAYLOAD.burst_idx_by_track[talker][trackIdx];
            polarTraceIdx.push(POLAR_START + t);

            if (burstIdx === -1) {{
                polarUpdates.r.push([]);
                polarUpdates.theta.push([]);
                polarUpdates['marker.size'].push([]);
                polarUpdates['marker.color'].push([]);
                polarUpdates.text.push([]);
                polarUpdates.hovertext.push([]);
                continue;
            }}
            anyBurst = true;

            const burst = PAYLOAD.bursts_by_talker[talker][burstIdx];
            const u = buildPolarUpdate(burst);
            polarUpdates.r.push(u.r);
            polarUpdates.theta.push(u.theta);
            polarUpdates['marker.size'].push(u.sizes);
            polarUpdates['marker.color'].push(u.colors);
            polarUpdates.text.push(u.labels);
            polarUpdates.hovertext.push(u.hovers);

            const name = NAME_MAP[talker] || talker;
            const ageS = (trackTsMs !== null && trackTsMs !== undefined)
                ? ((trackTsMs - burst.ts_ms) / 1000).toFixed(1)
                : '?';
            annoLines.push(escapeHtml(name) + ': ' + burst.sats.length
                + ' Sats (GSV ' + ageS + 's alt)');
        }}

        if (!anyBurst) {{
            annoLines.push('<i>Kein GSV-Burst bisher</i>');
        }}

        // Restyle alle Polar-Traces in einem Call (effizienter)
        if (polarTraceIdx.length > 0) {{
            Plotly.restyle(gd, polarUpdates, polarTraceIdx);
        }}
        // Aktiver Marker
        Plotly.restyle(gd, {{x: [[ax]], y: [[ay]], z: [[az]]}}, [ACTIVE_CURVE]);
        // Annotation
        document.getElementById(ANNO_ID).innerHTML = annoLines.join('<br>');
    }}

    function init() {{
        const slider = document.getElementById(SLIDER_ID);
        const gd = document.getElementById(PLOT_DIV_ID);

        slider.addEventListener('input', function(e) {{
            updateView(parseInt(e.target.value, 10));
        }});

        if (gd && typeof gd.on === 'function') {{
            gd.on('plotly_click', function(eventData) {{
                if (!eventData || !eventData.points || !eventData.points.length) return;
                const pt = eventData.points[0];
                if (pt.curveNumber !== TRACK_CURVE) return;
                slider.value = pt.pointIndex;
                updateView(pt.pointIndex);
            }});
        }}

        // Initial-Render auf Index 0
        updateView(0);
    }}

    // Plotly braucht einen Moment, bis gd.on verfügbar ist — auf
    // DOMContentLoaded plus minimalen Tick warten.
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', function() {{
            setTimeout(init, 0);
        }});
    }} else {{
        setTimeout(init, 0);
    }}
}})();
"""


def _build_html(
    fig: go.Figure,
    payload: Dict[str, Any],
    trace_indices: Dict[str, int],
    n_track_pts: int,
    title: str,
) -> str:
    """Baut die finale HTML-Datei mit Plot, Slider, Annotation und JS-Handler."""
    plot_div_id = "gps-track-plot"
    slider_id = "track-slider"
    anno_id = "status-annotation"

    # Plot-Div + Plotly-Script. include_plotlyjs='cdn' lädt das JS aus
    # dem CDN — spart ~3 MB pro HTML-Datei. full_html=False, weil wir den
    # Rahmen selbst bauen.
    plot_html = fig.to_html(
        include_plotlyjs="cdn",
        full_html=False,
        div_id=plot_div_id,
    )

    # Name-Map für die Annotation (nur die Talker, die wir tatsächlich haben)
    name_map = {t: _TALKER_LABELS.get(t, {"name": t})["name"]
                for t in payload["talkers"]}

    js = _JS_TEMPLATE.format(
        payload_json=json.dumps(payload, separators=(",", ":")),
        track_curve=trace_indices["track"],
        active_curve=trace_indices["active"],
        polar_start=trace_indices["polar_start"],
        plot_div_id_json=json.dumps(plot_div_id),
        slider_id_json=json.dumps(slider_id),
        anno_id_json=json.dumps(anno_id),
        name_map_json=json.dumps(name_map),
    )

    # Letzter Track-Index = n - 1
    slider_max = max(0, n_track_pts - 1)

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <title>{_html.escape(title)}</title>
  <style>
    html, body {{ margin: 0; padding: 0; font-family: sans-serif; }}
    #plot-container {{ padding: 8px; }}
    #controls {{
      display: flex; gap: 16px; align-items: flex-start;
      padding: 8px 16px; border-top: 1px solid #ddd; background: #fafafa;
    }}
    #slider-container {{ flex: 3; min-width: 0; }}
    #slider-container label {{
      display: block; font-size: 12px; color: #555; margin-bottom: 4px;
      font-family: monospace;
    }}
    #{slider_id} {{ width: 100%; }}
    #{anno_id} {{
      flex: 1; min-width: 240px; max-width: 420px;
      padding: 8px 10px; border: 1px solid #888; background: #fff;
      font-family: monospace; font-size: 12px; line-height: 1.5;
      white-space: nowrap;
    }}
  </style>
</head>
<body>
  <div id="plot-container">{plot_html}</div>
  <div id="controls">
    <div id="slider-container">
      <label for="{slider_id}">Track-Punkt-Index (0 … {slider_max})</label>
      <input id="{slider_id}" type="range" min="0" max="{slider_max}"
             value="0" step="1" />
    </div>
    <div id="{anno_id}"></div>
  </div>
  <script>{js}</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# 4. Öffentliche API
# ---------------------------------------------------------------------------

def render_track_with_satellites(
    df_c: pd.DataFrame,
    df_raw: pd.DataFrame,
    output_path,
    *,
    color_by: str = "speed_kmh",
    n_quantiles: int = DEFAULT_QUANTILES,
    z_exaggeration: float = DEFAULT_Z_EXAGGERATION,
    colorscale: str = DEFAULT_COLORSCALE,
    title: Optional[str] = None,
    dem_data: Optional[Dict[str, np.ndarray]] = None,
    terrain_colorscale: str = "Viridis",
    terrain_opacity: float = 0.7,
    track_z_offset: float = 0.0,
) -> bool:
    """Erzeugt eine HTML-Datei mit 3D-Track + synchroner Satellitenkonstellation.

    Eine HTML-Datei, die sich beliebig lang am Slider durchscrollen lässt —
    Datengröße skaliert mit Anzahl GSV-Bursts, nicht mit Anzahl Track-Punkten.

    Parameters
    ----------
    df_c : pd.DataFrame
        Schema-C-DataFrame (eine Zeile pro Track-Timestamp).
    df_raw : pd.DataFrame
        Schema-A-DataFrame mit GSV-Zeilen.
    output_path : Path or str
        Pfad der zu schreibenden HTML-Datei.
    color_by, n_quantiles, z_exaggeration, colorscale, title, dem_data,
    terrain_colorscale, terrain_opacity, track_z_offset
        Wie in :func:`three_d.visualize_3d`.

    Returns
    -------
    bool
        True wenn geschrieben, False wenn nichts zu schreiben war (leere
        Inputs).
    """
    output_path = Path(output_path)

    if df_c.empty:
        print("render_track_with_satellites: df_c ist leer, nichts zu tun.")
        return False
    if colorscale not in AVAILABLE_COLORSCALES:
        print(f"Warnung: Colorscale '{colorscale}' nicht in AVAILABLE_COLORSCALES. "
              f"Fallback auf {DEFAULT_COLORSCALE}.")
        colorscale = DEFAULT_COLORSCALE
    if color_by not in df_c.columns:
        raise ValueError(
            f"color_by-Spalte '{color_by}' nicht im DataFrame. "
            f"Verfügbar: {list(df_c.columns)}"
        )

    # 1. Daten-Payload aufbereiten
    payload = _build_payload(df_c, df_raw)

    # 2. Initial-Plot bauen
    fig, trace_indices = _build_initial_figure(
        df_c, payload["talkers"],
        color_by=color_by,
        n_quantiles=n_quantiles,
        z_exaggeration=z_exaggeration,
        colorscale=colorscale,
        dem_data=dem_data,
        terrain_colorscale=terrain_colorscale,
        terrain_opacity=terrain_opacity,
        track_z_offset=track_z_offset,
        title=title,
    )

    # 3. HTML zusammenbauen
    html_str = _build_html(
        fig, payload, trace_indices,
        n_track_pts=len(df_c),
        title=title or "GPS-Track mit Satellitenkonstellation",
    )

    output_path.write_text(html_str, encoding="utf-8")
    size_mb = output_path.stat().st_size / (1024 * 1024)
    n_bursts = sum(len(b) for b in payload["bursts_by_talker"].values())
    print(f"render_track_with_satellites: {output_path} ({size_mb:.2f} MB, "
          f"{len(df_c)} Track-Punkte, {n_bursts} Bursts, "
          f"{len(payload['talkers'])} Konstellation(en))")
    return True
