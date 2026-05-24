/**
 * 3D-Track-Viewer: deck.gl-Canvas mit Vorhang, Terrain und Positions-Marker.
 */
import { useCallback, useMemo, useState } from "react";
import DeckGL from "deck.gl";
import { MapView } from "@deck.gl/core";
import { ScatterplotLayer, PathLayer } from "@deck.gl/layers";

import type { TrackData, DemLod, ViewState, ColorMode } from "../types";
import { buildCurtainSegments, makeCurtainLayer } from "../layers/curtainLayer";
import { makeTerrainLayer } from "../layers/terrainLayer";
import { makeChartLayer } from "../layers/chartLayer";
import type { LoadedChart } from "../hooks/useCharts";
import { computeRankPositions, plasmaColor, type Rgba } from "../utils/colorMap";
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

export function TrackViewer({ track, dem, activeIdx, colorMode, showCurtain, charts, showCharts, zScale, onZoomChange, onPointPick, showTooltip = false }: Props) {
  const [viewState, setViewState] = useState<ViewState>(
    () => buildInitialViewState(track)
  );

  const Z_SCALE = zScale;
  const altBase = useMemo(() => {
    const alts = track.points.alt.filter((a): a is number => a !== null);
    return alts.length > 0 ? Math.min(...alts) : 0;
  }, [track]);
  const exagAlt = useCallback(
    (alt: number | null) => altBase + ((alt ?? altBase) - altBase) * Z_SCALE,
    [altBase, Z_SCALE]
  );

  // Rang-Position pro Punkt für den aktiven Color-Mode
  const rankPositions = useMemo(() => {
    const values = colorMode === "speed"
      ? track.points.speed_kmh
      : track.points.alt;
    return computeRankPositions(values);
  }, [track, colorMode]);

  const curtainSegments = useMemo(
    () => buildCurtainSegments(track, dem?.grid ?? null, rankPositions, altBase, Z_SCALE),
    [track, dem, rankPositions, altBase, Z_SCALE]
  );

  // Track-Segmente als individuelle Paths (für farbige PathLayer)
  const pathSegments = useMemo(() => {
    const { lon, lat, alt } = track.points;
    const segs: { path: [number, number, number][]; t: number }[] = [];
    for (let i = 0; i < lon.length - 1; i++) {
      const t_i  = rankPositions[i];
      const t_i1 = rankPositions[i + 1];
      let t: number;
      if (Number.isNaN(t_i) && Number.isNaN(t_i1)) t = NaN;
      else if (Number.isNaN(t_i)) t = t_i1;
      else if (Number.isNaN(t_i1)) t = t_i;
      else t = (t_i + t_i1) / 2;
      segs.push({
        path: [
          [lon[i],     lat[i],     exagAlt(alt[i])],
          [lon[i + 1], lat[i + 1], exagAlt(alt[i + 1])],
        ],
        t,
      });
    }
    return segs;
  }, [track, rankPositions, exagAlt]);

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

    if (showCurtain) result.push(makeCurtainLayer(curtainSegments, colorMode));

    result.push(new PathLayer({
      id: "track-path",
      data: pathSegments,
      getPath: (d: any) => d.path,
      getColor: (d: any) => Number.isNaN(d.t) ? FALLBACK : plasmaColor(d.t, 255),
      getWidth: 2,
      widthUnits: "pixels",
      pickable: false,
      updateTriggers: {
        getColor: [colorMode],
      },
    }));

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
      charts, showCharts, altBase, Z_SCALE, exagAlt, activeIdx, track, onPointPick]);

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
    const above = track.points.above_terrain?.[idx] ?? null;

    // Minimal-HTML -- nur die wichtigsten Werte, damit der Tooltip kompakt
    // bleibt und den Blick auf den Track nicht zu sehr verdeckt.
    const lines: string[] = [];
    if (ts) lines.push(formatTimestamp(ts));
    lines.push(formatSpeed(speed));
    lines.push(`MSL ${formatAltitude(alt)}`);
    if (above !== null) lines.push(`ueG ${above.toFixed(0)} m`);

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
  }, [showTooltip, track]);

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
