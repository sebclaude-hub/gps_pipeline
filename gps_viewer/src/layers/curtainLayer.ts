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
import type { TrackData, DemGrid, ColorMode } from "../types";
import { plasmaColor, type Rgba } from "../utils/colorMap";
import { sampleDem } from "../utils/demMesh";

export interface CurtainSegment {
  /** 4-Punkt 3D-Footprint (eps-Streifen perpendikular, z = Boden-Höhe) */
  footprint: [number, number, number][];
  /** Höhe der Wand in m (top - base, bereits Z-exaggeriert) */
  height: number;
  /** Mittlerer Rang [0,1] des Segments (für die Farbgebung). */
  t: number;
  /** Rohe mittlere Track-Hoehe MSL in Metern (ohne Z-Offset, ohne
   *  Z-Skalierung). Wird fuer regelbasierte Faerbung gebraucht. */
  altMslRaw: number | null;
  /** Rohe mittlere Hoehe ueber Grund in Metern (ohne Z-Offset, ohne
   *  Z-Skalierung). null wenn kein Terrain-Wert. */
  altAglRaw: number | null;
}

// --- Klassifikations-Schwellen (Meter) -----------------------------------
const FT = 0.3048;
const FLIGHT_AGL_LOW   = 500  * FT;   // 152.4 m -- rot unter dieser Hoehe
const FLIGHT_AGL_MID   = 1000 * FT;   // 304.8 m -- orange darunter
const FLIGHT_MSL_LOW   = 5000 * FT;   // 1524 m  -- tuerkis darunter
const DRONE_AGL_LIMIT  = 100;          // 100 m

const COL_RED:       Rgba = [220,  60,  60, 200];
const COL_ORANGE:    Rgba = [240, 150,  40, 200];
const COL_TURQUOISE: Rgba = [ 60, 190, 190, 200];
const COL_BLUE:      Rgba = [ 70, 120, 220, 200];
const COL_GREY:      Rgba = [150, 150, 150, 180];

/**
 * Faerbe-Logik fuer den Flug-Modus. Reihenfolge ist wichtig: erst AGL
 * checken (rot/orange), dann MSL.
 */
function flightColor(altMsl: number | null, altAgl: number | null): Rgba {
  if (altAgl !== null) {
    if (altAgl < FLIGHT_AGL_LOW)  return COL_RED;
    if (altAgl < FLIGHT_AGL_MID)  return COL_ORANGE;
  }
  if (altMsl !== null && altMsl < FLIGHT_MSL_LOW) return COL_TURQUOISE;
  return COL_BLUE;
}

function droneColor(altAgl: number | null): Rgba {
  if (altAgl === null) return COL_GREY;
  return altAgl <= DRONE_AGL_LIMIT ? COL_BLUE : COL_RED;
}

/** Maximalabstand (Grad) zwischen zwei aufeinanderfolgenden Track-Punkten,
 *  bevor wir den Curtain in Sub-Segmente zerlegen. ~0.0009 deg ≈ 100 m
 *  am Aequator (in DE etwas weniger nord-suedlich, etwas mehr ost-westlich).
 *  Bei Schnitten (gap/synthetic) sind die Sprunge oft km-gross -- diese
 *  Schwelle filtert nur die echt grossen Luecken heraus, ohne den normalen
 *  ~5m-Spacing zu beruehren. */
const SUBDIVIDE_THRESHOLD_DEG = 0.0009;
/** Maximalanzahl Sub-Segmente pro Track-Punkt-Paar (Schutz vor Endlos-
 *  Subdivision bei extrem langen Luecken). */
const MAX_SUBDIVISIONS = 200;

export function buildCurtainSegments(
  track: TrackData,
  demGrid: DemGrid | null,
  rankPositions: number[],
  altBase: number = 0,
  zScale: number = 1,
  zOffset: number = 0,
): CurtainSegment[] {
  const { lat, lon, alt, terrain_elev } = track.points;
  const n = lat.length;
  const segments: CurtainSegment[] = [];

  // Zwei verschiedene Z-Transformationen:
  //   exagTrack   verschiebt + skaliert die Track-Hoehe (Vorhang-Oberkante)
  //   exagTerrain skaliert nur die Terrain-Hoehe (Vorhang-Unterkante)
  // Der Z-Offset wirkt damit ausschliesslich auf den Track. Das Terrain
  // bleibt an seiner echten Position (das Terrain-Mesh nutzt ja auch
  // exagTerrain-Formel).
  const exagTrack = (h: number) => altBase + ((h + zOffset) - altBase) * zScale;
  const exagTerrain = (h: number) => altBase + (h - altBase) * zScale;
  const EPS = 1e-6; // grad ≈ 11 cm — gibt earcut eine triangulierbare XY-Fläche

  /** Hilfsfunktion: erzeugt ein Curtain-Segment fuer ein Sub-Stueck
   *  zwischen den (interpolierten) Punkten A und B. Terrain wird per
   *  sampleDem am tatsaechlichen Sub-Punkt geholt, damit der Vorhang
   *  dem Gelaende folgt statt eine konstante Boden-Hoehe zu zeigen. */
  function pushSeg(
    lon_a: number, lat_a: number, alt_a_raw: number,
    lon_b: number, lat_b: number, alt_b_raw: number,
    terr_a_raw: number | null, terr_b_raw: number | null,
    t: number,
  ) {
    const dx = lon_b - lon_a;
    const dy = lat_b - lat_a;
    const len = Math.hypot(dx, dy) || 1;
    const px = (-dy / len) * EPS;
    const py = ( dx / len) * EPS;

    const top = (exagTrack(alt_a_raw) + exagTrack(alt_b_raw)) / 2;

    // Boden: bevorzugt sampleDem am Sub-Punkt (gibt feines Terrain-
    // Profil zurueck), fallback auf interpolierte terrain_elev-Werte,
    // letzter Fallback auf 0 MSL.
    let bot: number;
    if (demGrid) {
      const b_a = sampleDem(demGrid, lon_a, lat_a);
      const b_b = sampleDem(demGrid, lon_b, lat_b);
      if (b_a !== null && b_b !== null) {
        bot = exagTerrain((b_a + b_b) / 2);
      } else if (terr_a_raw !== null && terr_b_raw !== null) {
        bot = exagTerrain((terr_a_raw + terr_b_raw) / 2);
      } else {
        bot = 0;
      }
    } else if (terr_a_raw !== null && terr_b_raw !== null) {
      bot = exagTerrain((terr_a_raw + terr_b_raw) / 2);
    } else {
      bot = 0;
    }

    const base = Math.min(top, bot);
    const height = Math.abs(top - bot);

    // Rohe Mittel-Hoehen fuer die regelbasierte Faerbung.
    const altMslRaw = (alt_a_raw + alt_b_raw) / 2;
    let altAglRaw: number | null = null;
    if (terr_a_raw !== null && terr_b_raw !== null) {
      altAglRaw = altMslRaw - (terr_a_raw + terr_b_raw) / 2;
    } else if (demGrid) {
      const b_a = sampleDem(demGrid, lon_a, lat_a);
      const b_b = sampleDem(demGrid, lon_b, lat_b);
      if (b_a !== null && b_b !== null) altAglRaw = altMslRaw - (b_a + b_b) / 2;
    }

    segments.push({
      footprint: [
        [lon_a + px, lat_a + py, base],
        [lon_b + px, lat_b + py, base],
        [lon_b - px, lat_b - py, base],
        [lon_a - px, lat_a - py, base],
      ],
      height,
      t,
      altMslRaw,
      altAglRaw,
    });
  }

  for (let i = 0; i < n - 1; i++) {
    const lat_i  = lat[i],    lon_i  = lon[i];
    const lat_i1 = lat[i + 1], lon_i1 = lon[i + 1];
    const alt_i_raw  = alt[i]     ?? altBase;
    const alt_i1_raw = alt[i + 1] ?? altBase;
    const terr_i_raw  = terrain_elev[i]     ?? null;
    const terr_i1_raw = terrain_elev[i + 1] ?? null;

    const t_i  = rankPositions[i];
    const t_i1 = rankPositions[i + 1];
    let tSeg: number;
    if (Number.isNaN(t_i) && Number.isNaN(t_i1)) tSeg = NaN;
    else if (Number.isNaN(t_i)) tSeg = t_i1;
    else if (Number.isNaN(t_i1)) tSeg = t_i;
    else tSeg = (t_i + t_i1) / 2;

    // Distanz in Grad (grob, reicht fuer Subdivision-Entscheidung).
    const dLon = lon_i1 - lon_i;
    const dLat = lat_i1 - lat_i;
    const distDeg = Math.hypot(dLon, dLat);

    if (distDeg <= SUBDIVIDE_THRESHOLD_DEG) {
      // Normales kurzes Segment: ein Curtain-Stueck.
      pushSeg(
        lon_i, lat_i, alt_i_raw,
        lon_i1, lat_i1, alt_i1_raw,
        terr_i_raw, terr_i1_raw,
        tSeg,
      );
      continue;
    }

    // Lange Luecke (z.B. nach Gap/Synthetic-Cut): in Sub-Segmente
    // zerlegen, damit der Vorhang dem Gelaende-Profil folgt statt
    // eine breite Rechteckwand zu zeigen.
    const nSub = Math.min(
      MAX_SUBDIVISIONS,
      Math.max(2, Math.ceil(distDeg / SUBDIVIDE_THRESHOLD_DEG)),
    );
    for (let k = 0; k < nSub; k++) {
      const a = k / nSub;
      const b = (k + 1) / nSub;
      const lon_a = lon_i + dLon * a;
      const lat_a = lat_i + dLat * a;
      const lon_b = lon_i + dLon * b;
      const lat_b = lat_i + dLat * b;
      const alt_a = alt_i_raw  + (alt_i1_raw - alt_i_raw)  * a;
      const alt_b = alt_i_raw  + (alt_i1_raw - alt_i_raw)  * b;
      // terrain_elev: lieber an den Subpunkten neu sampeln; falls kein
      // demGrid vorhanden, interpoliere zwischen den Endwerten.
      const terr_a = (terr_i_raw !== null && terr_i1_raw !== null)
        ? terr_i_raw + (terr_i1_raw - terr_i_raw) * a
        : terr_i_raw;
      const terr_b = (terr_i_raw !== null && terr_i1_raw !== null)
        ? terr_i_raw + (terr_i1_raw - terr_i_raw) * b
        : terr_i1_raw;
      pushSeg(lon_a, lat_a, alt_a, lon_b, lat_b, alt_b, terr_a, terr_b, tSeg);
    }
  }
  return segments;
}

const FALLBACK: Rgba = [150, 150, 150, 180];

export function makeCurtainLayer(
  segments: CurtainSegment[],
  colorMode: ColorMode,
  zOffset: number = 0,
) {
  const getColor = (d: CurtainSegment): Rgba => {
    if (colorMode === "flight") {
      // Z-Offset wird auf beide Hoehen aufaddiert -- er bewegt den Track,
      // also auch die effektiv darzustellende Klassen-Hoehe.
      const msl = d.altMslRaw !== null ? d.altMslRaw + zOffset : null;
      const agl = d.altAglRaw !== null ? d.altAglRaw + zOffset : null;
      return flightColor(msl, agl);
    }
    if (colorMode === "drone") {
      const agl = d.altAglRaw !== null ? d.altAglRaw + zOffset : null;
      return droneColor(agl);
    }
    // speed / altitude: continuous Plasma per Rang.
    return Number.isNaN(d.t) ? FALLBACK : plasmaColor(d.t, 200);
  };

  return new SolidPolygonLayer({
    id: "curtain",
    data: segments,
    getPolygon: (d: CurtainSegment) => d.footprint,
    extruded: true,
    getElevation: (d: CurtainSegment) => d.height,
    getFillColor: getColor,
    material: false,
    wireframe: false,
    pickable: false,
    updateTriggers: {
      getFillColor: [colorMode, zOffset],
    },
  });
}
