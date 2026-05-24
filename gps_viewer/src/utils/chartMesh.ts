/**
 * chartMesh -- Erzeugt ein triangulares Mesh fuer ein Karten-Overlay,
 * das auf das DEM-Gelaende "gedrapt" wird (Vertex-Z = Terrain-Hoehe).
 *
 * Konzept
 * -------
 * Eine Karten-Konfig liefert vier Eckkoordinaten (TL, TR, BL, BR) in WGS84.
 * Wir spannen ein gleichmaessiges N x N-Gitter ueber diesem Viereck (bilineare
 * Interpolation der Eckpunkte) und sampeln fuer jeden Vertex die DEM-Hoehe.
 * Die UV-Koordinaten ergeben sich trivial aus der Gitterposition (u = col/(N-1),
 * v = row/(N-1)) -- so legt sich das PNG passgenau auf die vier Ecken.
 *
 * Wenn kein DEM verfuegbar ist, faellt das Mesh auf eine flache Ebene bei
 * ``elevation_m`` zurueck (aus der Karten-Konfig).
 *
 * Mesh-Positionen sind, wie bei demMesh, in Meter-Offsets vom Bounds-Center
 * angegeben -- der SimpleMeshLayer-Anker ist ``[lon_center, lat_center]``.
 * Damit Karte, Terrain und Track im selben Raum liegen, MUSS hier dieselbe
 * Z-Exaggeration (altBase, zScale) wie in demMesh / TrackViewer verwendet werden.
 */

import type { DemGrid } from "../types";
import { sampleDem } from "./demMesh";

export interface ChartOverlay {
  name: string;
  image: string;                  // URL zum PNG, relativ zum data/-Mount
  corner_tl: [number, number];    // [lon, lat]
  corner_tr: [number, number];
  corner_bl: [number, number];
  corner_br: [number, number];
  elevation_m: number;            // Fallback-Hoehe, wenn kein DEM
}

export interface ChartMesh {
  /** Mesh-Vertex-Positionen: [x, y, z, x, y, z, ...] in Meter-Offsets vom Anker. */
  positions: Float32Array;
  /** UV-Koordinaten pro Vertex: [u, v, u, v, ...] in [0,1]. */
  texCoords: Float32Array;
  /** Triangle-Indizes (zwei Dreiecke pro Gitterzelle). */
  indices: Uint32Array;
  /** Anker-Position fuer SimpleMeshLayer.getPosition (Lon/Lat). */
  anchor: [number, number];
}

/** Subdivision des Karten-Gitters. 32 x 32 = 1024 Vertices, ausreichend
 *  fuer typische Anflugkarten (1-3 km Ausdehnung) bei DEM-Aufloesungen
 *  von 10-50 m/px. Bei groesseren Karten ggf. hochsetzen. */
const DEFAULT_SUBDIV = 32;

/**
 * Bilineare Interpolation der vier Eckkoordinaten ueber dem [0,1] x [0,1]
 * UV-Raum. u = 0 ist links, v = 0 ist oben.
 *
 *   TL ---- TR
 *   |        |
 *   BL ---- BR
 */
function lerpCorners(
  chart: ChartOverlay,
  u: number,
  v: number,
): [number, number] {
  const [tlx, tly] = chart.corner_tl;
  const [trx, try_] = chart.corner_tr;
  const [blx, bly] = chart.corner_bl;
  const [brx, bry] = chart.corner_br;

  // Erst horizontal (entlang u) interpolieren, dann vertikal (entlang v).
  const topX  = tlx + (trx - tlx) * u;
  const topY  = tly + (try_ - tly) * u;
  const botX  = blx + (brx - blx) * u;
  const botY  = bly + (bry - bly) * u;

  const lon = topX + (botX - topX) * v;
  const lat = topY + (botY - topY) * v;
  return [lon, lat];
}

/**
 * Baut ein gedraptes Mesh fuer einen Chart-Overlay.
 *
 * @param chart       Die Chart-Konfig (Ecken + Fallback-Hoehe).
 * @param demGrid     DEM-Gitter zum Hoehensampeln, oder null fuer Flach-Mesh.
 * @param altBase     Basis-Hoehe fuer die Z-Exaggeration (wie im TrackViewer).
 * @param zScale      Z-Skalierungsfaktor (wie im TrackViewer).
 * @param subdivision Gitter-Aufloesung (N x N Vertices). Default 32.
 */
export function buildChartMesh(
  chart: ChartOverlay,
  demGrid: DemGrid | null,
  altBase: number = 0,
  zScale: number = 1,
  subdivision: number = DEFAULT_SUBDIV,
): ChartMesh {
  const N = Math.max(2, subdivision);

  // Anker: Schwerpunkt der vier Ecken in Lon/Lat -- Meter-Offsets relativ dazu.
  const lon_center =
    (chart.corner_tl[0] + chart.corner_tr[0] +
     chart.corner_bl[0] + chart.corner_br[0]) / 4;
  const lat_center =
    (chart.corner_tl[1] + chart.corner_tr[1] +
     chart.corner_bl[1] + chart.corner_br[1]) / 4;

  // Equirektangulare Approximation -- konsistent mit demMesh.
  const m_per_lon = 111320 * Math.cos((lat_center * Math.PI) / 180);
  const m_per_lat = 110540;

  const positions = new Float32Array(N * N * 3);
  const texCoords = new Float32Array(N * N * 2);

  let pIdx = 0;
  let tIdx = 0;
  for (let r = 0; r < N; r++) {
    const v = r / (N - 1);                // 0 (oben) -> 1 (unten)
    for (let c = 0; c < N; c++) {
      const u = c / (N - 1);              // 0 (links) -> 1 (rechts)

      const [lon, lat] = lerpCorners(chart, u, v);

      // Hoehe: DEM-Sample wenn verfuegbar, sonst Fallback.
      let elev = chart.elevation_m;
      if (demGrid) {
        const sampled = sampleDem(demGrid, lon, lat);
        if (sampled !== null) elev = sampled;
      }

      positions[pIdx++] = (lon - lon_center) * m_per_lon;
      positions[pIdx++] = (lat - lat_center) * m_per_lat;
      positions[pIdx++] = altBase + (elev - altBase) * zScale;

      // UV-Konvention von BitmapLayer/SimpleMeshLayer: v=0 ist UNTEN im Bild.
      // Unser Iterations-v=0 ist OBEN -> wir spiegeln: texV = 1 - v.
      texCoords[tIdx++] = u;
      texCoords[tIdx++] = 1 - v;
    }
  }

  // Triangle-Indizes: 2 Dreiecke pro Gitterzelle, gleiche Topologie wie demMesh.
  const nCells = (N - 1) * (N - 1);
  const indices = new Uint32Array(nCells * 6);
  let iIdx = 0;
  for (let r = 0; r < N - 1; r++) {
    for (let c = 0; c < N - 1; c++) {
      const tl = r * N + c;
      const tr = tl + 1;
      const bl = tl + N;
      const br = bl + 1;
      indices[iIdx++] = tl;
      indices[iIdx++] = bl;
      indices[iIdx++] = tr;
      indices[iIdx++] = tr;
      indices[iIdx++] = bl;
      indices[iIdx++] = br;
    }
  }

  return {
    positions,
    texCoords,
    indices,
    anchor: [lon_center, lat_center],
  };
}
