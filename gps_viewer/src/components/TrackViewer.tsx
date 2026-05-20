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
import { computeRankPositions, plasmaColor, type Rgba } from "../utils/colorMap";

interface Props {
  track: TrackData;
  dem: DemLod | null;
  activeIdx: number;
  colorMode: ColorMode;
  onZoomChange?: (zoom: number) => void;
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

export function TrackViewer({ track, dem, activeIdx, colorMode, onZoomChange }: Props) {
  const [viewState, setViewState] = useState<ViewState>(
    () => buildInitialViewState(track)
  );

  const Z_SCALE = 15;
  const altBase = useMemo(() => {
    const alts = track.points.alt.filter((a): a is number => a !== null);
    return alts.length > 0 ? Math.min(...alts) : 0;
  }, [track]);
  const exagAlt = useCallback(
    (alt: number | null) => altBase + ((alt ?? altBase) - altBase) * Z_SCALE,
    [altBase]
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
    [track, dem, rankPositions, altBase]
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

    if (dem) result.push(makeTerrainLayer(dem));

    result.push(makeCurtainLayer(curtainSegments, colorMode));

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

    return result;
  }, [dem, curtainSegments, pathSegments, activePt, colorMode, exagAlt, activeIdx]);

  const handleViewStateChange = useCallback(({ viewState: vs }: any) => {
    setViewState(vs);
    onZoomChange?.(vs.zoom);
  }, [onZoomChange]);

  return (
    <DeckGL
      views={new MapView({ id: "map", repeat: false })}
      viewState={viewState}
      controller={{ dragRotate: true, touchRotate: true }}
      layers={layers}
      onViewStateChange={handleViewStateChange}
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
