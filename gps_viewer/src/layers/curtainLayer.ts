/**
 * Vorhang-Layer: senkrechte Flächen vom GPS-Track bis zum Terrain.
 *
 * Für jedes Track-Segment [i → i+1] wird ein Viereck (Quad) erzeugt:
 *
 *   top_i    [lon_i,   lat_i,   alt_i]   ──  top_{i+1}  [lon_{i+1}, lat_{i+1}, alt_{i+1}]
 *      │                                                          │
 *   bot_i  [lon_i,   lat_i,  terrain_i]  ──  bot_{i+1} [lon_{i+1}, lat_{i+1}, terrain_{i+1}]
 *
 * Farbe: Plasma-Verlauf über den Rang des aktiven Werts (Speed oder Höhe).
 */

import { SolidPolygonLayer } from "@deck.gl/layers";
import type { TrackData, DemGrid } from "../types";
import { plasmaColor, type Rgba } from "../utils/colorMap";
import { sampleDem } from "../utils/demMesh";

export interface CurtainSegment {
  polygon: [number, number, number][];
  /** Mittlerer Rang [0,1] des Segments (für die Farbgebung). */
  t: number;
}

export function buildCurtainSegments(
  track: TrackData,
  demGrid: DemGrid | null,
  rankPositions: number[],
  altBase: number = 0,
  zScale: number = 1,
): CurtainSegment[] {
  const { lat, lon, alt, terrain_elev } = track.points;
  const n = lat.length;
  const segments: CurtainSegment[] = [];

  const exag = (h: number) => altBase + (h - altBase) * zScale;

  for (let i = 0; i < n - 1; i++) {
    const lat_i  = lat[i],    lon_i  = lon[i];
    const lat_i1 = lat[i + 1], lon_i1 = lon[i + 1];
    const alt_i  = exag(alt[i]  ?? altBase);
    const alt_i1 = exag(alt[i + 1] ?? altBase);

    let bot_i: number, bot_i1: number;
    if (terrain_elev[i] !== null && terrain_elev[i] !== undefined) {
      bot_i  = exag(terrain_elev[i]!);
      bot_i1 = exag(terrain_elev[i + 1] ?? terrain_elev[i]!);
    } else if (demGrid) {
      bot_i  = exag(sampleDem(demGrid, lon_i,  lat_i)  ?? altBase);
      bot_i1 = exag(sampleDem(demGrid, lon_i1, lat_i1) ?? altBase);
    } else {
      bot_i  = 0;
      bot_i1 = 0;
    }

    const t_i  = rankPositions[i];
    const t_i1 = rankPositions[i + 1];
    let tSeg: number;
    if (Number.isNaN(t_i) && Number.isNaN(t_i1)) tSeg = NaN;
    else if (Number.isNaN(t_i)) tSeg = t_i1;
    else if (Number.isNaN(t_i1)) tSeg = t_i;
    else tSeg = (t_i + t_i1) / 2;

    segments.push({
      polygon: [
        [lon_i,  lat_i,  alt_i],
        [lon_i1, lat_i1, alt_i1],
        [lon_i1, lat_i1, bot_i1],
        [lon_i,  lat_i,  bot_i],
      ],
      t: tSeg,
    });
  }
  return segments;
}

const FALLBACK: Rgba = [150, 150, 150, 180];

export function makeCurtainLayer(segments: CurtainSegment[], colorMode: string) {
  return new SolidPolygonLayer({
    id: "curtain",
    data: segments,
    getPolygon: (d: CurtainSegment) => d.polygon,
    getFillColor: (d: CurtainSegment) =>
      Number.isNaN(d.t) ? FALLBACK : plasmaColor(d.t, 200),
    material: false,
    extruded: false,
    _normalize: false,
    pickable: false,
    updateTriggers: {
      getFillColor: [colorMode],
    },
  });
}
