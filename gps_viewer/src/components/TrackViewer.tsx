/**
 * 3D-Track-Viewer: deck.gl-Canvas mit Vorhang, Terrain und Positions-Marker.
 */
import { useCallback, useMemo, useState } from "react";
import DeckGL from "deck.gl";
import { MapView } from "@deck.gl/core";
import { ScatterplotLayer, PathLayer, LineLayer } from "@deck.gl/layers";

import type { TrackData, DemLod, ViewState, ColorMode } from "../types";
import { buildCurtainSegments, makeCurtainLayer } from "../layers/curtainLayer";
import { makeTerrainLayer } from "../layers/terrainLayer";
import { makeChartLayer } from "../layers/chartLayer";
import type { LoadedChart } from "../hooks/useCharts";
import type { CutRange } from "../hooks/useRangeSelection";
import { accelerationColor, plasmaColor, quantileLinearPositions, type Rgba } from "../utils/colorMap";
import { colorScaleFor } from "../utils/colorScale";
import { formatSpeed, formatAltitude, formatTimestamp } from "../utils/formatters";

interface Props {
  track: TrackData;
  dem: DemLod | null;
  activeIdx: number;
  colorMode: ColorMode;
  showCurtain: boolean;
  /** Karten-Overlays, die auf das DEM gedrapt werden. Leeres Array = aus. */
  charts: LoadedChart[];
  /** Sichtbarkeit aller Charts (UI-Toggle). */
  showCharts: boolean;
  zScale: number;
  onZoomChange?: (zoom: number) => void;
  /** Wird aufgerufen, wenn der Nutzer im Track-Plot einen Punkt anklickt
   *  oder mit dem Mauszeiger ueberfaehrt. Setzt typischerweise activeIdx. */
  onPointPick?: (idx: number) => void;
  /** Wenn true, erscheint beim Hover ein Floating-Tooltip am Cursor mit
   *  Zeit/Speed/Hoehe. Unabhaengig vom rechtsseitigen InfoPanel. */
  showTooltip?: boolean;
  /** Cut-Ranges, die rot ueber dem Track hervorgehoben werden. Leeres
   *  Array oder undefined -> keine Hervorhebung. */
  cutRanges?: CutRange[];
  /** Z-Offset in Metern, der auf alle Track-Hoehen vor der Z-Exaggeration
   *  angewendet wird. Wird vom OffsetSlider gespeist. Default 0. */
  zOffset?: number;
  /** G-Vektor-Pfeile am aktiven Punkt anzeigen (Laengs=gruen, Quer=orange, Vertikal=blau). */
  showGVec?: boolean;
}

function buildInitialViewState(track: TrackData): ViewState {
  const { lon_min, lat_min, lon_max, lat_max } = track.meta.bounds;
  return {
    longitude: (lon_min + lon_max) / 2,
    latitude: (lat_min + lat_max) / 2,
    zoom: 10,
    pitch: 45,
    bearing: 0,
  };
}

const FALLBACK: Rgba = [150, 150, 150, 180];

const M_PER_DEG = 111_320;
// Massstab: 1 m/s² = 30 m Pfeillaenge in Bodenprojektionsdistanz.
const ARROW_SCALE = 30;

export function TrackViewer({ track, dem, activeIdx, colorMode, showCurtain, charts, showCharts, zScale, onZoomChange, onPointPick, showTooltip = false, cutRanges = [], zOffset = 0, showGVec = false }: Props) {
  const [viewState, setViewState] = useState<ViewState>(
    () => buildInitialViewState(track)
  );

  const Z_SCALE = zScale;
  const altBase = useMemo(() => {
    const alts = track.points.alt.filter((a): a is number => a !== null);
    return alts.length > 0 ? Math.min(...alts) : 0;
  }, [track]);
  // Track-Hoehen-Transform: erst Offset addieren (verschiebt die Track-
  // Linie relativ zum DEM nach oben/unten), dann Z-Exaggeration. altBase
  // bleibt am Originalboden des Tracks, damit der Exag-Bezug stabil ist.
  const exagAlt = useCallback(
    (alt: number | null) => altBase + ((alt ?? altBase) + zOffset - altBase) * Z_SCALE,
    [altBase, Z_SCALE, zOffset]
  );

  // Track-Linie: bei "flight" und "drone" bleibt sie immer auf
  // Speed-Plasma (Schwellen-Klassifikation passiert nur am Curtain).
  // Fuer "speed"/"altitude" folgt sie dem Mode.
  const trackColorMode: ColorMode =
    (colorMode === "flight" || colorMode === "drone") ? "speed" : colorMode;

  // Farb-Position pro Punkt: quantil-entzerrt (s. quantileLinearPosition). Werte
  // + Grenzen je Modus liefert colorScaleFor — alles aus der Pipeline (JSON),
  // der Viewer rechnet nicht. Deckt speed/altitude/altitude_gnd/energy ab.
  const rankPositions = useMemo(() => {
    const { values, breaks } = colorScaleFor(track, trackColorMode);
    return quantileLinearPositions(values, breaks);
  }, [track, colorMode]);

  // Vorzeichenbehafteter Kanal (accel ODER energy_rate) — die Pipeline liefert
  // die Rohwerte + die robuste Skala; der Viewer normiert nur raw/scale → [−1,1]
  // fuer die YlOrRd/YlGnBu-Farbgebung. signedRaw für den Tooltip.
  const { signedRaw, signedNorm, signedUnit } = useMemo(() => {
    const raw =
      colorMode === "accel"
        ? track.points.accel_mps2 ?? null
        : colorMode === "energy_rate"
          ? track.points.energy_rate_mps ?? null
          : null;
    if (!raw) return { signedRaw: null, signedNorm: null, signedUnit: "" };
    const scale =
      (colorMode === "accel"
        ? track.scales?.accel_mps2
        : track.scales?.energy_rate_mps) || 1;
    const norm = raw.map((v) =>
      v === null ? null : Math.max(-1, Math.min(1, v / scale)),
    );
    return { signedRaw: raw, signedNorm: norm, signedUnit: colorMode === "accel" ? "m/s²" : "m/s" };
  }, [track, colorMode]);

  const curtainSegments = useMemo(
    () => buildCurtainSegments(track, dem?.grid ?? null, rankPositions, altBase, Z_SCALE, zOffset, signedNorm),
    [track, dem, rankPositions, altBase, Z_SCALE, zOffset, signedNorm]
  );

  // Track-Segmente als individuelle Paths (für farbige PathLayer). Pro Segment:
  // Rang t (speed/altitude/energy/...) und Signed-Wert signedN (accel/energy_rate).
  const pathSegments = useMemo(() => {
    const { lon, lat, alt } = track.points;
    const mean2 = (a: number | null, b: number | null): number => {
      const av = a === null || Number.isNaN(a) ? null : a;
      const bv = b === null || Number.isNaN(b) ? null : b;
      if (av === null && bv === null) return NaN;
      if (av === null) return bv as number;
      if (bv === null) return av;
      return (av + bv) / 2;
    };
    const segs: { path: [number, number, number][]; t: number; signedN: number }[] = [];
    for (let i = 0; i < lon.length - 1; i++) {
      segs.push({
        path: [
          [lon[i],     lat[i],     exagAlt(alt[i])],
          [lon[i + 1], lat[i + 1], exagAlt(alt[i + 1])],
        ],
        t: mean2(rankPositions[i], rankPositions[i + 1]),
        signedN: signedNorm ? mean2(signedNorm[i], signedNorm[i + 1]) : NaN,
      });
    }
    return segs;
  }, [track, rankPositions, signedNorm, exagAlt]);

  const activePt = useMemo(() => {
    const { lon, lat, alt } = track.points;
    const idx = Math.max(0, Math.min(activeIdx, lon.length - 1));
    return [{
      lon: lon[idx],
      lat: lat[idx],
      alt: alt[idx] ?? 0,
      t: rankPositions[idx],
    }];
  }, [track, activeIdx, rankPositions]);

  // Pro Cut-Range eine zusammenhaengende Punktfolge zwischen [start, end].
  // Wird als roter PathLayer ueber dem normalen Track gerendert, damit
  // der Nutzer sieht, welche Track-Segmente entfernt werden.
  const cutPaths = useMemo(() => {
    if (cutRanges.length === 0) return [];
    const { lon, lat, alt } = track.points;
    const n = lon.length;
    // Farben pro Cut-Mode (passend zu RangeSelector). RGBA-Tupel fuer deck.gl.
    const colorByMode: Record<CutRange["mode"], [number, number, number, number]> = {
      trim:      [220, 60, 60, 230],
      gap:       [70, 180, 90, 230],
      bridge:    [80, 130, 220, 230],
    };
    return cutRanges
      .map((r) => {
        const lo = Math.max(0, r.start);
        const hi = Math.min(n - 1, r.end);
        if (hi < lo) return null;
        const path: [number, number, number][] = [];
        for (let i = lo; i <= hi; i++) {
          path.push([lon[i], lat[i], exagAlt(alt[i])]);
        }
        return { id: r.id, path, color: colorByMode[r.mode] };
      })
      .filter((x): x is { id: string; path: [number, number, number][]; color: [number, number, number, number] } => x !== null);
  }, [cutRanges, track, exagAlt]);

  // G-Vektor-Pfeile am aktiven Punkt (Laengs=gruen, Quer=orange, Vertikal=blau).
  const gVecArrows = useMemo(() => {
    const pts = track.points;
    if (
      !showGVec ||
      !Array.isArray(pts.accel_long_mps2) ||
      !Array.isArray(pts.accel_lateral_mps2) ||
      !Array.isArray(pts.accel_vertical_mps2) ||
      !Array.isArray(pts.accel_heading_e) ||
      !Array.isArray(pts.accel_heading_n)
    ) return [];

    const idx = Math.max(0, Math.min(activeIdx, pts.lon.length - 1));
    const lon0 = pts.lon[idx];
    const lat0 = pts.lat[idx];
    const alt0 = exagAlt(pts.alt[idx]);
    const cosLat = Math.cos((lat0 * Math.PI) / 180);

    const he = pts.accel_heading_e[idx];
    const hn = pts.accel_heading_n[idx];
    const aLong = pts.accel_long_mps2[idx];
    const aLat = pts.accel_lateral_mps2[idx];
    const aVert = pts.accel_vertical_mps2[idx];

    if (
      he === null || hn === null ||
      !Number.isFinite(he as number) || !Number.isFinite(hn as number)
    ) return [];

    const arrows: { from: [number, number, number]; to: [number, number, number]; color: [number, number, number, number] }[] = [];

    // Laengsbeschleunigung (gruen): entlang Heading
    if (aLong !== null && Number.isFinite(aLong as number)) {
      const dm = (aLong as number) * ARROW_SCALE;
      arrows.push({
        from: [lon0, lat0, alt0],
        to: [
          lon0 + (he as number) * dm / (M_PER_DEG * cosLat),
          lat0 + (hn as number) * dm / M_PER_DEG,
          alt0,
        ],
        color: [50, 220, 80, 255],
      });
    }

    // Querbeschleunigung (orange): senkrecht zur Fahrtrichtung (+links)
    if (aLat !== null && Number.isFinite(aLat as number)) {
      const dm = (aLat as number) * ARROW_SCALE;
      // perpendicular CCW: (-hn, he)
      arrows.push({
        from: [lon0, lat0, alt0],
        to: [
          lon0 + (-(hn as number)) * dm / (M_PER_DEG * cosLat),
          lat0 + (he as number) * dm / M_PER_DEG,
          alt0,
        ],
        color: [230, 140, 30, 255],
      });
    }

    // Vertikalbeschleunigung (blau): hoch/runter (mit Z-Exaggeration)
    if (aVert !== null && Number.isFinite(aVert as number)) {
      const dz = (aVert as number) * ARROW_SCALE * Z_SCALE;
      arrows.push({
        from: [lon0, lat0, alt0],
        to: [lon0, lat0, alt0 + dz],
        color: [80, 160, 240, 255],
      });
    }

    return arrows;
  }, [track, activeIdx, showGVec, exagAlt, Z_SCALE]);

  const layers = useMemo(() => {
    const result = [];

    if (dem) result.push(makeTerrainLayer(dem, altBase, Z_SCALE));

    // Chart-Overlays vor Curtain/Track rendern, damit sie unter dem Track liegen.
    // Bei mehreren Charts sind sie additiv -- ueberlappende PNGs ueberblenden
    // sich entsprechend ihrer Alpha-Kanaele.
    if (showCharts && charts.length > 0) {
      for (const ch of charts) {
        result.push(makeChartLayer(ch.overlay, ch.image, dem?.grid ?? null,
                                   altBase, Z_SCALE));
      }
    }

    if (showCurtain) result.push(makeCurtainLayer(curtainSegments, colorMode, zOffset));

    result.push(new PathLayer({
      id: "track-path",
      data: pathSegments,
      getPath: (d: any) => d.path,
      getColor: (d: any) =>
        (colorMode === "accel" || colorMode === "energy_rate")
          ? (Number.isNaN(d.signedN) ? FALLBACK : accelerationColor(d.signedN, 255))
          : (Number.isNaN(d.t) ? FALLBACK : plasmaColor(d.t, 255)),
      getWidth: 2,
      widthUnits: "pixels",
      pickable: false,
      updateTriggers: {
        getColor: [colorMode],
      },
    }));

    // Cut-Hervorhebung: rote Linien ueber dem normalen Track. Etwas dicker
    // gezeichnet, damit man die Plasma-Farbgebung darunter nicht mit der
    // Cut-Markierung verwechselt.
    if (cutPaths.length > 0) {
      result.push(new PathLayer({
        id: "cut-paths",
        data: cutPaths,
        getPath: (d: any) => d.path,
        getColor: (d: any) => d.color,
        getWidth: 5,
        widthUnits: "pixels",
        pickable: false,
        updateTriggers: {
          getPath: [cutPaths],
          getColor: [cutPaths],
        },
      }));
    }

    result.push(new ScatterplotLayer({
      id: "active-point",
      data: activePt,
      getPosition: (d: any) => [d.lon, d.lat, exagAlt(d.alt)],
      getRadius: 6,
      radiusUnits: "pixels",
      getFillColor: (d: any) => Number.isNaN(d.t) ? FALLBACK : plasmaColor(d.t, 255),
      getLineColor: [255, 255, 255, 230],
      lineWidthMinPixels: 2,
      stroked: true,
      pickable: false,
      updateTriggers: {
        getFillColor: [colorMode, activeIdx],
        getPosition: [activeIdx],
      },
    }));

    // G-Vektor-Pfeile: Laengs (gruen), Quer (orange), Vertikal (blau).
    if (gVecArrows.length > 0) {
      result.push(new LineLayer({
        id: "gvec-arrows",
        data: gVecArrows,
        getSourcePosition: (d: any) => d.from,
        getTargetPosition: (d: any) => d.to,
        getColor: (d: any) => d.color,
        getWidth: 3,
        widthUnits: "pixels",
        pickable: false,
        updateTriggers: {
          getSourcePosition: [activeIdx, showGVec],
          getTargetPosition: [activeIdx, showGVec],
        },
      }));
    }

    // Unsichtbarer Pickable-Layer ueber dem Track, damit der Nutzer mit
    // Maus/Touch einen einzelnen Punkt selektieren kann (synchronisiert
    // Slider, InfoPanel und Skyplot). PathLayer selbst ist nicht
    // pickbar-per-Punkt, daher dieser zusaetzliche Layer.
    //
    // Wir setzen alpha = 0, damit der Layer optisch nicht stoert; deck.gl
    // pickt trotzdem, weil die Picking-Engine eine separate Off-Screen-
    // Pass nutzt, die Alpha ignoriert.
    if (onPointPick) {
      const pickRadius = 6; // px -- grossere Toleranz fuer einfacheres Treffen
      result.push(new ScatterplotLayer({
        id: "track-pick",
        data: track.points.lat.map((_la, i) => i),
        getPosition: (i: any) => {
          const idx = i as number;
          return [
            track.points.lon[idx],
            track.points.lat[idx],
            exagAlt(track.points.alt[idx]),
          ];
        },
        getRadius: pickRadius,
        radiusUnits: "pixels",
        getFillColor: [0, 0, 0, 0],   // unsichtbar
        pickable: true,
        onHover: (info: any) => {
          if (info.object !== undefined && info.object !== null) {
            onPointPick(info.object as number);
          }
        },
        updateTriggers: {
          getPosition: [zScale, altBase],
        },
      }));
    }

    return result;
  }, [dem, curtainSegments, pathSegments, activePt, colorMode, showCurtain,
      charts, showCharts, altBase, Z_SCALE, exagAlt, activeIdx, track, onPointPick,
      cutPaths, gVecArrows, showGVec]);

  const handleViewStateChange = useCallback(({ viewState: vs }: any) => {
    setViewState(vs);
    onZoomChange?.(vs.zoom);
  }, [onZoomChange]);

  // Tooltip-Renderer: deck.gl ruft das mit dem PickInfo des aktuell
  // gehoverten Layers auf. Wir filtern explizit auf "track-pick" (unser
  // unsichtbarer Pickable-Layer), damit andere Layers (Terrain, Charts)
  // keinen Tooltip ausloesen.
  const getTooltip = useCallback((info: any) => {
    if (!showTooltip) return null;
    if (!info || info.layer?.id !== "track-pick") return null;
    const idx = info.object as number | undefined;
    if (idx === undefined || idx === null) return null;

    const ts    = track.points.timestamp_ms[idx];
    const speed = track.points.speed_kmh[idx] ?? null;
    const alt   = track.points.alt[idx]       ?? null;
    const terr  = track.points.terrain_elev[idx] ?? null;
    // Live mit dem aktuellen Offset rechnen -- nicht das gespeicherte
    // above_terrain aus JSON nehmen (das ignoriert den Slider).
    const above = (alt !== null && terr !== null) ? (alt + zOffset - terr) : null;
    // MSL-Anzeige enthaelt den Slider-Wert, damit "Hoehe" mit dem
    // sichtbaren Z-Wert in der 3D-Szene uebereinstimmt.
    const altShown = (alt !== null) ? alt + zOffset : null;

    const isBridged = track.points.is_bridged?.[idx] ?? false;

    // Minimal-HTML -- nur die wichtigsten Werte, damit der Tooltip kompakt
    // bleibt und den Blick auf den Track nicht zu sehr verdeckt.
    const lines: string[] = [];
    if (ts) lines.push(formatTimestamp(ts));
    lines.push(formatSpeed(speed));
    lines.push(`MSL ${formatAltitude(altShown)}`);
    if (above !== null) lines.push(`ueG ${above.toFixed(0)} m`);
    // Aktiver Signed-Modus: Beschl. (m/s²) bzw. ΔEnergie (m/s), Pipeline-gerechnet.
    const sr = signedRaw ? (signedRaw[idx] ?? null) : null;
    if (sr !== null && Number.isFinite(sr)) {
      const lbl = colorMode === "accel" ? "Beschl." : "ΔEnergie";
      lines.push(`${lbl} ${sr >= 0 ? "+" : "−"}${Math.abs(sr).toFixed(1)} ${signedUnit}`);
    }
    if (isBridged) lines.push('<span style="color:#f4c0c0">&#9888; Zeitstempel verschoben</span>');

    return {
      html: lines.map((l) => `<div>${l}</div>`).join(""),
      style: {
        background: "rgba(20, 20, 28, 0.92)",
        color: "#eee",
        fontSize: "11px",
        fontFamily: "system-ui, sans-serif",
        padding: "6px 8px",
        borderRadius: "4px",
        border: "1px solid rgba(255,255,255,0.15)",
        boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
        // pointerEvents: none ist deck.gl-Default -- wir bleiben passiv.
      },
    };
  }, [showTooltip, track, zOffset, signedRaw, signedUnit, colorMode]);

  return (
    <DeckGL
      views={new MapView({ id: "map", repeat: false })}
      viewState={viewState}
      controller={{ dragRotate: true, touchRotate: true }}
      layers={layers}
      onViewStateChange={handleViewStateChange}
      getTooltip={getTooltip}
      style={{ position: "relative", width: "100%", height: "100%" }}
    >
      <div style={{
        position: "absolute", bottom: 8, right: 8,
        color: "#aaa", fontSize: 11, pointerEvents: "none",
      }}>
        {track.meta.name} · {track.meta.n_points} Punkte
      </div>
    </DeckGL>
  );
}
