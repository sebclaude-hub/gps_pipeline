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
  /** Normalen (für Beleuchtung, optional berechnet) */
  normals?: Float32Array;
}

export function gridToMesh(grid: DemGrid): DemMesh {
  const { n_rows, n_cols, lat_min, lat_max, lon_min, lon_max, elevations } = grid;

  const positions = new Float32Array(n_rows * n_cols * 3);
  let pIdx = 0;

  for (let r = 0; r < n_rows; r++) {
    const lat = lat_min + (r / Math.max(n_rows - 1, 1)) * (lat_max - lat_min);
    for (let c = 0; c < n_cols; c++) {
      const lon = lon_min + (c / Math.max(n_cols - 1, 1)) * (lon_max - lon_min);
      const elev = elevations[r * n_cols + c];
      positions[pIdx++] = lon;
      positions[pIdx++] = lat;
      positions[pIdx++] = elev ?? 0;
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

  return { positions, indices };
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
