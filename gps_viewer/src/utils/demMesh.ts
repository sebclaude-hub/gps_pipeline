/**
 * Konvertiert ein reguläres DEM-Grid in ein trianguliertes Mesh.
 *
 * Ausgabe: { positions: Float32Array, indices: Uint32Array }
 * positions: [lon, lat, elev, lon, lat, elev, ...] (row-major)
 * indices: Dreiecke als Uint32-Indizes
 *
 * NaN/null-Werte: auf 0 gesetzt (Meeresspiegel), um Löcher im Mesh zu vermeiden.
 */
import type { DemGrid } from "../types";

export interface DemMesh {
  positions: Float32Array;
  indices: Uint32Array;
  /** Hypsometrische Vertex-Farben (RGB, Uint8). Eine Farbe pro Vertex,
   *  Layout parallel zu ``positions``. Wird vom Terrain-Layer als
   *  Vertex-Attribut an SimpleMeshLayer durchgereicht. */
  colors: Uint8Array;
  /** Anker-Position des Mesh in lng/lat (für SimpleMeshLayer.getPosition). */
  anchor: [number, number];
  /** Normalen (für Beleuchtung, optional berechnet) */
  normals?: Float32Array;
}

// ---------------------------------------------------------------------------
// Hypsometrische Farbskala
// ---------------------------------------------------------------------------
//
// Topografische Faerbung, eng auf Mitteleuropa zugeschnitten: Tiefland
// gruen -> Huegelland gelb -> Mittelgebirge braun -> Hochmittelgebirge
// grau-braun -> Voralpen/Alpen ab 1100m weiss. Alles ueber 1100m bleibt
// auf der letzten Stufe (weiss).
const HYPSO_STOPS: ReadonlyArray<readonly [number, readonly [number, number, number]]> = [
  [   0, [ 90, 145, 110]],   // Tiefland: dunkles Gruen
  [ 120, [165, 195, 130]],   // Flaches Huegelland: helles Gelbgruen
  [ 300, [205, 180, 115]],   // Mittleres Huegelland: gelb-braun
  [ 450, [165, 130,  90]],   // Mittelbergland: braun
  [ 600, [155, 135, 120]],   // Hochmittelgebirge: grau-braun
  [1100, [240, 240, 245]],   // Voralpen/Alpen: weiss
];

/** Liefert eine RGB-Farbe fuer eine gegebene Hoehe (Meter MSL).
 *  Linear interpoliert zwischen den HYPSO_STOPS. */
function hypsoColor(elev: number): [number, number, number] {
  if (elev <= HYPSO_STOPS[0][0]) {
    return [...HYPSO_STOPS[0][1]] as [number, number, number];
  }
  for (let i = 1; i < HYPSO_STOPS.length; i++) {
    const [e1, c1] = HYPSO_STOPS[i];
    if (elev <= e1) {
      const [e0, c0] = HYPSO_STOPS[i - 1];
      const t = (elev - e0) / (e1 - e0);
      return [
        Math.round(c0[0] + (c1[0] - c0[0]) * t),
        Math.round(c0[1] + (c1[1] - c0[1]) * t),
        Math.round(c0[2] + (c1[2] - c0[2]) * t),
      ];
    }
  }
  const last = HYPSO_STOPS[HYPSO_STOPS.length - 1][1];
  return [...last] as [number, number, number];
}

/**
 * Konvertiert ein DEM-Grid zu einem Mesh.
 *
 * Wichtig: SimpleMeshLayer interpretiert die Mesh-Positionen als Meter-Offsets
 * vom getPosition-Anker (auch im LNGLAT-Modus). Wir bauen das Mesh in
 * meter-offsets vom Bounds-Mittelpunkt und geben diesen als `anchor` zurück.
 *
 * Equirectangular-Approximation: gültig für Bereiche bis wenige Grad Ausdehnung.
 */
export function gridToMesh(
  grid: DemGrid,
  altBase: number = 0,
  zScale: number = 1,
): DemMesh {
  const { n_rows, n_cols, lat_min, lat_max, lon_min, lon_max, elevations } = grid;

  const lat_center = (lat_min + lat_max) / 2;
  const lon_center = (lon_min + lon_max) / 2;
  const m_per_lon = 111320 * Math.cos((lat_center * Math.PI) / 180);
  const m_per_lat = 110540;

  const positions = new Float32Array(n_rows * n_cols * 3);
  // RGBA mit Uint8 (0-255). Der Shader normiert via normalized:true.
  const colors = new Uint8Array(n_rows * n_cols * 4);
  let pIdx = 0;
  let cIdx = 0;

  for (let r = 0; r < n_rows; r++) {
    const lat = lat_min + (r / Math.max(n_rows - 1, 1)) * (lat_max - lat_min);
    for (let c = 0; c < n_cols; c++) {
      const lon = lon_min + (c / Math.max(n_cols - 1, 1)) * (lon_max - lon_min);
      const elev = elevations[r * n_cols + c] ?? 0;
      positions[pIdx++] = (lon - lon_center) * m_per_lon;
      positions[pIdx++] = (lat - lat_center) * m_per_lat;
      positions[pIdx++] = altBase + (elev - altBase) * zScale;
      // Hypsometrische Farbe -- anhand der ROHEN Hoehe in Metern,
      // nicht der z-skalierten. Dadurch bleibt die Farbe bei Aenderung
      // der Z-Exaggeration stabil.
      const [cr, cg, cb] = hypsoColor(elev);
      colors[cIdx++] = cr;
      colors[cIdx++] = cg;
      colors[cIdx++] = cb;
      colors[cIdx++] = 220;   // Alpha: leicht durchscheinend wie der frühere Default
    }
  }

  // 2 Dreiecke pro Gitterzelle
  const nCells = (n_rows - 1) * (n_cols - 1);
  const indices = new Uint32Array(nCells * 6);
  let iIdx = 0;

  for (let r = 0; r < n_rows - 1; r++) {
    for (let c = 0; c < n_cols - 1; c++) {
      const tl = r * n_cols + c;
      const tr = tl + 1;
      const bl = tl + n_cols;
      const br = bl + 1;
      // Dreieck 1: tl → bl → tr
      indices[iIdx++] = tl;
      indices[iIdx++] = bl;
      indices[iIdx++] = tr;
      // Dreieck 2: tr → bl → br
      indices[iIdx++] = tr;
      indices[iIdx++] = bl;
      indices[iIdx++] = br;
    }
  }

  return { positions, indices, colors, anchor: [lon_center, lat_center] };
}

/**
 * Bilineare Interpolation: Höhe an Position (lon, lat) im Grid.
 * Gibt null zurück wenn außerhalb des Grid-Bereichs.
 */
export function sampleDem(grid: DemGrid, lon: number, lat: number): number | null {
  const { n_rows, n_cols, lat_min, lat_max, lon_min, lon_max, elevations } = grid;
  if (lon < lon_min || lon > lon_max || lat < lat_min || lat > lat_max) return null;

  const fc = ((lon - lon_min) / (lon_max - lon_min)) * (n_cols - 1);
  const fr = ((lat - lat_min) / (lat_max - lat_min)) * (n_rows - 1);

  const c0 = Math.min(Math.floor(fc), n_cols - 2);
  const r0 = Math.min(Math.floor(fr), n_rows - 2);
  const tc = fc - c0;
  const tr = fr - r0;

  const v00 = elevations[r0 * n_cols + c0] ?? 0;
  const v10 = elevations[r0 * n_cols + c0 + 1] ?? 0;
  const v01 = elevations[(r0 + 1) * n_cols + c0] ?? 0;
  const v11 = elevations[(r0 + 1) * n_cols + c0 + 1] ?? 0;

  return v00 * (1 - tc) * (1 - tr) +
         v10 * tc * (1 - tr) +
         v01 * (1 - tc) * tr +
         v11 * tc * tr;
}
