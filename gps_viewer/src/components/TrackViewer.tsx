/**
 * 3D-Track-Viewer: deck.gl-Canvas mit Vorhang, Terrain und Positions-Marker.
 */
import { useCallback, useMemo, useState } from "react";
import DeckGL from "deck.gl";
import { MapView } from "@deck.gl/core";
import { ScatterplotLayer, PathLayer } from "@deck.gl/layers";

import type { TrackData, DemLod, ViewState } from "../types";
import { buildCurtainSegments, makeCurtainLayer } from "../layers/curtainLayer";
import { makeTerrainLayer } from "../layers/terrainLayer";
import { getDefaultPalette, quantileColor } from "../utils/quantile";

interface Props {
  track: TrackData;
  dem: DemLod | null;
  activeIdx: number;
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

export function TrackViewer({ track, dem, activeIdx, onZoomChange }: Props) {
  const [viewState, setViewState] = useState<ViewState>(
    () => buildInitialViewState(track)
  );

  const nQ = track.quantile_breaks.n_quantiles;
  const palette = useMemo(() => getDefaultPalette(nQ), [nQ]);

  // Z-Exaggeration: Höhenunterschiede übertreiben damit sie sichtbar werden.
  // altBase = minimale Höhe im Track; zScale = Übertreibungsfaktor.
  const Z_SCALE = 15;
  const altBase = useMemo(() => {
    const alts = track.points.alt.filter((a): a is number => a !== null);
    return alts.length > 0 ? Math.min(...alts) : 0;
  }, [track]);
  const exagAlt = useCallback(
    (alt: number | null) => altBase + ((alt ?? altBase) - altBase) * Z_SCALE,
    [altBase]
  );

  // Vorhang-Segmente (nur neu berechnen wenn Track oder DEM wechselt)
  const curtainSegments = useMemo(
    () => buildCurtainSegments(track, dem?.grid ?? null, altBase, Z_SCALE),
    [track, dem, altBase]
  );

  // Aktiver Punkt (Positions-Marker)
  const activePt = useMemo(() => {
    const { lon, lat, alt, speed_q_idx } = track.points;
    const idx = Math.max(0, Math.min(activeIdx, lon.length - 1));
    return [{
      lon: lon[idx],
      lat: lat[idx],
      alt: alt[idx] ?? 0,
      qIdx: speed_q_idx[idx],
    }];
  }, [track, activeIdx]);

  const layers = useMemo(() => {
    const result = [];

    // 1. Terrain-Mesh
    if (dem) result.push(makeTerrainLayer(dem));

    // 2. Track-Linie — immer sichtbar (pixel-breit, unabhängig vom Zoom)
    result.push(new PathLayer({
      id: "track-path",
      data: [{
        path: track.points.lon.map((l, i) => [
          l, track.points.lat[i], exagAlt(track.points.alt[i] ?? null),
        ]),
      }],
      getPath: (d: any) => d.path,
      getColor: [180, 180, 180, 120],
      getWidth: 1,
      widthUnits: "pixels",
      pickable: false,
    }));

    // 3. Vorhang — farbcodierte Höhenfläche
    //    Für Flüge: sichtbarer Vorhang (große Höhendifferenz).
    //    Für Boden-Tracks: sehr dünn, wird bei niedrigem Pitch unsichtbar —
    //    ist aber korrekt und wird bei steilem Pitch (60°+) sichtbar.
    result.push(makeCurtainLayer(curtainSegments, nQ));

    // 3. Aktiver Punkt
    result.push(new ScatterplotLayer({
      id: "active-point",
      data: activePt,
      getPosition: (d: any) => [d.lon, d.lat, exagAlt(d.alt)],
      getRadius: 6,
      radiusUnits: "pixels",
      getFillColor: (d: any) => quantileColor(d.qIdx, palette),
      getLineColor: [255, 255, 255, 220],
      lineWidthMinPixels: 2,
      stroked: true,
      pickable: false,
    }));

    return result;
  }, [dem, curtainSegments, nQ, activePt, palette, track]);

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
