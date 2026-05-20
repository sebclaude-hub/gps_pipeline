/**
 * Vorhang-Layer: senkrechte Wand vom GPS-Track bis zum Boden.
 *
 * Implementierung: SolidPolygonLayer mit `extruded: true`. Das Polygon ist
 * ein super-dünner XY-Streifen zwischen Track-Punkt i und i+1 (Breite ~11 cm
 * via perpendikularem Offset, damit earcut eine Fläche zum Triangulieren hat).
 * `getElevation` extrudiert den Streifen pro Segment auf die durchschnittliche
 * Track-Höhe — daraus entsteht eine vertikale Wand vom Boden bis zum Track.
 *
 * Limitierung: pro Segment konstante Höhe (Top horizontal). Bei den ~5 m
 * Abstand zwischen GPS-Punkten kaum sichtbar; bei großen Sprüngen entstehen
 * Treppen-Stufen.
 *
 * Farbe: Plasma-Verlauf über den Rang des aktiven Werts (Speed oder Höhe).
 */

import { SolidPolygonLayer } from "@deck.gl/layers";
import type { TrackData, DemGrid } from "../types";
import { plasmaColor, type Rgba } from "../utils/colorMap";
import { sampleDem } from "../utils/demMesh";

export interface CurtainSegment {
  /** 4-Punkt 3D-Footprint (eps-Streifen perpendikular, z = Boden-Höhe) */
  footprint: [number, number, number][];
  /** Höhe der Wand in m (top - base, bereits Z-exaggeriert) */
  height: number;
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
  const EPS = 1e-6; // grad ≈ 11 cm — gibt earcut eine triangulierbare XY-Fläche

  for (let i = 0; i < n - 1; i++) {
    const lat_i  = lat[i],    lon_i  = lon[i];
    const lat_i1 = lat[i + 1], lon_i1 = lon[i + 1];
    const alt_i  = exag(alt[i]  ?? altBase);
    const alt_i1 = exag(alt[i + 1] ?? altBase);

    // Perpendikularer XY-Offset
    const dx = lon_i1 - lon_i;
    const dy = lat_i1 - lat_i;
    const len = Math.hypot(dx, dy) || 1;
    const px = (-dy / len) * EPS;
    const py = ( dx / len) * EPS;

    // Boden-Höhe (Terrain wenn vorhanden, sonst 0 MSL)
    let bot: number;
    if (terrain_elev[i] !== null && terrain_elev[i] !== undefined) {
      const b_i = exag(terrain_elev[i]!);
      const b_i1 = exag(terrain_elev[i + 1] ?? terrain_elev[i]!);
      bot = (b_i + b_i1) / 2;
    } else if (demGrid) {
      const b_i  = sampleDem(demGrid, lon_i,  lat_i)  ?? altBase;
      const b_i1 = sampleDem(demGrid, lon_i1, lat_i1) ?? altBase;
      bot = exag((b_i + b_i1) / 2);
    } else {
      bot = 0;
    }

    const top = (alt_i + alt_i1) / 2;

    const t_i  = rankPositions[i];
    const t_i1 = rankPositions[i + 1];
    let tSeg: number;
    if (Number.isNaN(t_i) && Number.isNaN(t_i1)) tSeg = NaN;
    else if (Number.isNaN(t_i)) tSeg = t_i1;
    else if (Number.isNaN(t_i1)) tSeg = t_i;
    else tSeg = (t_i + t_i1) / 2;

    segments.push({
      footprint: [
        [lon_i  + px, lat_i  + py, bot],
        [lon_i1 + px, lat_i1 + py, bot],
        [lon_i1 - px, lat_i1 - py, bot],
        [lon_i  - px, lat_i  - py, bot],
      ],
      height: Math.max(0, top - bot),
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
    getPolygon: (d: CurtainSegment) => d.footprint,
    extruded: true,
    getElevation: (d: CurtainSegment) => d.height,
    // Polygon enthält Z=base in jedem Punkt → Boden-Position wird respektiert,
    // getElevation gibt die Wand-Höhe darüber an.
    getFillColor: (d: CurtainSegment) =>
      Number.isNaN(d.t) ? FALLBACK : plasmaColor(d.t, 200),
    material: false,
    wireframe: false,
    pickable: false,
    updateTriggers: {
      getFillColor: [colorMode],
    },
  });
}
