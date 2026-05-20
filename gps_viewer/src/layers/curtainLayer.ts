/**
 * Vorhang-Layer: senkrechte Flächen vom GPS-Track bis zum Terrain.
 *
 * Für jedes Track-Segment [i → i+1] wird ein Viereck (Quad) erzeugt:
 *
 *   top_i    [lon_i,   lat_i,   alt_i]   ──  top_{i+1}  [lon_{i+1}, lat_{i+1}, alt_{i+1}]
 *      │                                                          │
 *   bot_i  [lon_i,   lat_i,  terrain_i]  ──  bot_{i+1} [lon_{i+1}, lat_{i+1}, terrain_{i+1}]
 *
 * Farbe: Plasma-Palette basierend auf speed_q_idx des Segments.
 * ground-Modus: terrain_elev ≈ alt → keine sichtbare Fläche (0-Höhe).
 */

import { SolidPolygonLayer } from "@deck.gl/layers";
import type { TrackData, DemGrid } from "../types";
import { getDefaultPalette, quantileColor } from "../utils/quantile";
import { sampleDem } from "../utils/demMesh";

export interface CurtainSegment {
  /** 4-Punkt-Polygon: top_i, top_{i+1}, bot_{i+1}, bot_i */
  polygon: [number, number, number][];
  colorIndex: number;
}

/**
 * Baut alle Vorhang-Segmente aus den Track-Daten.
 * @param demGrid  Optional: DEM-Grid für Terrain-Höhe; null → Boden = 0
 * @param altBase  Basis-Höhe für Z-Exaggeration (typisch: min(alt))
 * @param zScale   Höhen-Übertreibungsfaktor (1 = maßstabstreu)
 */
export function buildCurtainSegments(
  track: TrackData,
  demGrid: DemGrid | null,
  altBase: number = 0,
  zScale: number = 1,
): CurtainSegment[] {
  const { lat, lon, alt, terrain_elev, speed_q_idx } = track.points;
  const n = lat.length;
  const segments: CurtainSegment[] = [];

  const exag = (h: number) => altBase + (h - altBase) * zScale;

  for (let i = 0; i < n - 1; i++) {
    const lat_i  = lat[i],    lon_i  = lon[i];
    const lat_i1 = lat[i + 1], lon_i1 = lon[i + 1];
    const alt_i  = exag(alt[i]  ?? altBase);
    const alt_i1 = exag(alt[i + 1] ?? altBase);

    // Terrain-Höhe: bevorzuge vorberechnete terrain_elev, sonst DEM-Sample
    let bot_i: number, bot_i1: number;
    if (terrain_elev[i] !== null && terrain_elev[i] !== undefined) {
      bot_i  = exag(terrain_elev[i]!);
      bot_i1 = exag(terrain_elev[i + 1] ?? terrain_elev[i]!);
    } else if (demGrid) {
      bot_i  = exag(sampleDem(demGrid, lon_i,  lat_i)  ?? altBase);
      bot_i1 = exag(sampleDem(demGrid, lon_i1, lat_i1) ?? altBase);
    } else {
      // Kein Terrain: Vorhang bis MSL = 0. Der Boden wird NICHT exaggeriert,
      // damit er bei 0 bleibt — nur die Oberkante (Track) wird überhöht.
      bot_i  = 0;
      bot_i1 = 0;
    }

    segments.push({
      polygon: [
        [lon_i,  lat_i,  alt_i],
        [lon_i1, lat_i1, alt_i1],
        [lon_i1, lat_i1, bot_i1],
        [lon_i,  lat_i,  bot_i],
      ],
      colorIndex: speed_q_idx[i] ?? -1,
    });
  }
  return segments;
}

/** Erzeugt den deck.gl SolidPolygonLayer für den Vorhang. */
export function makeCurtainLayer(
  segments: CurtainSegment[],
  nQuantiles: number
) {
  const palette = getDefaultPalette(nQuantiles);

  return new SolidPolygonLayer({
    id: "curtain",
    data: segments,
    getPolygon: (d: CurtainSegment) => d.polygon,
    getFillColor: (d: CurtainSegment) => quantileColor(d.colorIndex, palette),
    // Beide Seiten rendern (Vorhang ist von vorne und hinten sichtbar)
    material: false,
    extruded: false,
    _normalize: false,
    pickable: false,
    updateTriggers: {
      getFillColor: [nQuantiles],
    },
  });
}
