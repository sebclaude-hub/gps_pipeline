/**
 * chartMesh -- Erzeugt ein triangulares Mesh fuer ein Karten-Overlay,
 * das auf das DEM-Gelaende "gedrapt" wird (Vertex-Z = Terrain-Hoehe).
 *
 * Zwei Aufbau-Strategien
 * ----------------------
 *
 * **Strategie A (bevorzugt): Terrain-Subgrid wiederverwenden.**
 * Wenn ein DEM verfuegbar ist UND die Karten-Bounds axenparallel
 * (lat/lon-aligned) sind, verwenden wir GENAU die DEM-Vertices, die
 * innerhalb der Bounds liegen. Vorteil: Chart-Z und Terrain-Z sind an
 * jedem Vertex identisch, und zwischen Vertices interpolieren beide
 * Meshes identisch -- es kann kein Z-Konflikt entstehen und das Terrain
 * "schaut" nicht zwischen Vertices durch die Karte durch. Aufloesung
 * passt sich automatisch dem aktiven LOD an.
 *
 * **Strategie B (Fallback): Bilineare Eck-Interpolation mit adaptiver
 * Subdivision.** Wird verwendet, wenn kein DEM da ist oder die Karten-
 * Bounds gedreht/skewed sind. Spannt ein N x N-Gitter zwischen den vier
 * Ecken auf, sampelt das DEM (falls vorhanden) pro Vertex. Subdivision
 * skaliert mit Kartengroesse, ~50 m/Vertex, Cap 256.
 *
 * Z-Lift
 * ------
 * Strategie A nutzt identische Vertices wie das Terrain -- ein winziger
 * Lift (0.5 m) reicht, um die GPU-Render-Reihenfolge eindeutig zu machen.
 * Strategie B muss groesser liften (5 m), weil zwischen unterschiedlich
 * dichten Meshes die Z-Interpolation auseinanderdriftet.
 *
 * Mesh-Koordinatensystem
 * ----------------------
 * Positionen sind in Meter-Offsets vom Bounds-Mittelpunkt -- der
 * SimpleMeshLayer-Anker ist ``[lon_center, lat_center]``. Equirektangular
 * vom Bounds-Center, konsistent zu demMesh und curtainLayer.
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
  /** Optionaler Override fuer die Mesh-Subdivision in Strategie B
   *  (axenparalleler Subgrid-Ansatz ignoriert ihn). */
  subdivision?: number | null;
}

export interface ChartMesh {
  positions: Float32Array;
  texCoords: Float32Array;
  indices: Uint32Array;
  anchor: [number, number];
}

// ---------------------------------------------------------------------------
// Konstanten
// ---------------------------------------------------------------------------

const TARGET_METERS_PER_VERTEX = 50;
const SUBDIV_CAP = 256;
const SUBDIV_FLOOR = 8;

/** Z-Lift fuer Strategie A: 0 m, kein Offset noetig.
 *
 *  Wenn alle drei Bedingungen erfuellt sind:
 *    - identische Vertex-Positionen (DEM-Sample),
 *    - identischer Anker + cos(lat)-Faktor (DEM-Center),
 *    - identische Triangulation (gleiche Iterationsreihenfolge wie demMesh)
 *  ist die Chart-Oberflaeche mathematisch identisch zur Terrain-Oberflaeche
 *  -- nicht nur an Vertices, sondern auch in jeder Interpolation dazwischen.
 *  Damit ist klassisches Z-Fighting unmoeglich, und deck.gl rendert die
 *  Karte zuverlaessig oben, weil sie spaeter in der Layer-Liste kommt
 *  (Render-Order-Tiebreak).
 *
 *  Frueher hatte ich hier einen Lift von 0.5 m bis 5 m, weil eine oder
 *  mehrere der drei Bedingungen verletzt waren. Nach dem Fix nicht mehr
 *  noetig -- empirisch bei zScale 1x bis 10x, von extremem Reinzoom bis
 *  Rauszoom auf den ganzen Track kein Flackern. */
const Z_LIFT_SUBGRID_M = 0.0;

/** Z-Lift fuer Strategie B: muss die Interpolationsdifferenzen zwischen
 *  unterschiedlich dichten Meshes ueberbruecken. */
const Z_LIFT_BILINEAR_M = 5.0;

/** Toleranz fuer "axenparallel" -- 1 µ° ≈ 11 cm am Aequator. */
const AXIS_ALIGN_EPS_DEG = 1e-6;

// ---------------------------------------------------------------------------
// Geometrie-Helfer
// ---------------------------------------------------------------------------

/** True, wenn alle vier Karten-Ecken ein achsenparalleles Rechteck in
 *  Lon/Lat bilden (typisch fuer Anflugkarten). */
function isAxisAligned(chart: ChartOverlay): boolean {
  return (
    Math.abs(chart.corner_tl[1] - chart.corner_tr[1]) < AXIS_ALIGN_EPS_DEG &&
    Math.abs(chart.corner_bl[1] - chart.corner_br[1]) < AXIS_ALIGN_EPS_DEG &&
    Math.abs(chart.corner_tl[0] - chart.corner_bl[0]) < AXIS_ALIGN_EPS_DEG &&
    Math.abs(chart.corner_tr[0] - chart.corner_br[0]) < AXIS_ALIGN_EPS_DEG
  );
}

/** Equirektangulare Meter-pro-Grad-Faktoren um die uebergebene Lat. */
function metersPerDegree(latCenterDeg: number): { mpLon: number; mpLat: number } {
  return {
    mpLon: 111320 * Math.cos((latCenterDeg * Math.PI) / 180),
    mpLat: 110540,
  };
}

// ---------------------------------------------------------------------------
// Strategie A: Subgrid des Terrain-Mesh wiederverwenden
// ---------------------------------------------------------------------------

/**
 * Extrahiert genau die DEM-Vertices, die innerhalb der (achsenparallelen)
 * Karten-Bounds liegen, und baut daraus ein Chart-Mesh. UV-Koordinaten
 * leiten sich aus der relativen Position innerhalb der Bounds ab.
 *
 * Gibt ``null`` zurueck, wenn die Karte ausserhalb des DEMs liegt oder
 * der Subgrid zu klein wird (< 2x2 Vertices) -- dann faellt der Aufrufer
 * auf Strategie B zurueck.
 */
function buildFromTerrainSubgrid(
  chart: ChartOverlay,
  demGrid: DemGrid,
  altBase: number,
  zScale: number,
): ChartMesh | null {
  // Karten-Bounding-Box -- bei axenparallelen Karten identisch mit den Ecken.
  const lon_min = Math.min(chart.corner_tl[0], chart.corner_bl[0]);
  const lon_max = Math.max(chart.corner_tr[0], chart.corner_br[0]);
  const lat_min = Math.min(chart.corner_bl[1], chart.corner_br[1]);
  const lat_max = Math.max(chart.corner_tl[1], chart.corner_tr[1]);

  // DEM-Gitterschrittweite (Grad/Vertex).
  const dem_dlat = (demGrid.lat_max - demGrid.lat_min) / Math.max(demGrid.n_rows - 1, 1);
  const dem_dlon = (demGrid.lon_max - demGrid.lon_min) / Math.max(demGrid.n_cols - 1, 1);
  if (dem_dlat <= 0 || dem_dlon <= 0) return null;

  // DEM-Indizes finden, die innerhalb der Bounds liegen. Wir nehmen alle
  // Vertices, die innerhalb oder direkt auf dem Rand der Bounds liegen --
  // ``ceil`` fuer untere, ``floor`` fuer obere Grenze.
  let r_min = Math.ceil((lat_min - demGrid.lat_min) / dem_dlat);
  let r_max = Math.floor((lat_max - demGrid.lat_min) / dem_dlat);
  let c_min = Math.ceil((lon_min - demGrid.lon_min) / dem_dlon);
  let c_max = Math.floor((lon_max - demGrid.lon_min) / dem_dlon);

  // Auf gueltigen DEM-Bereich clampen.
  r_min = Math.max(0, r_min);
  r_max = Math.min(demGrid.n_rows - 1, r_max);
  c_min = Math.max(0, c_min);
  c_max = Math.min(demGrid.n_cols - 1, c_max);

  const N_rows = r_max - r_min + 1;
  const N_cols = c_max - c_min + 1;
  if (N_rows < 2 || N_cols < 2) return null;   // Karte liegt zum Grossteil ausserhalb des DEMs

  // WICHTIG: Anker UND cos(lat)-Faktor muessen exakt mit dem Terrain-Mesh
  // uebereinstimmen, sonst projiziert deck.gl die Chart-Vertices auf leicht
  // verschobene Welt-Positionen relativ zum Terrain (Effekt 0.5-1% bei 0.5°
  // Lat-Differenz zwischen DEM- und Chart-Center). An verschobenen
  // Positionen hat das Terrain dann eine andere Hoehe, und das Chart-Mesh
  // taucht stellenweise darunter -- sieht aus wie Z-Fighting, ist aber
  // ein horizontaler Versatz.
  //
  // Deshalb hier explizit das DEM-Center als Anker und Bezugslat.
  const lon_center = (demGrid.lon_min + demGrid.lon_max) / 2;
  const lat_center = (demGrid.lat_min + demGrid.lat_max) / 2;
  const { mpLon, mpLat } = metersPerDegree(lat_center);

  const positions = new Float32Array(N_rows * N_cols * 3);
  const texCoords = new Float32Array(N_rows * N_cols * 2);

  // Iterationsreihenfolge MUSS exakt mit demMesh.ts uebereinstimmen,
  // sonst geht die Triangulation 90 Grad versetzt:
  //   demMesh: r=0 ist lat_min (Sueden) -- "tl"-Index meint geographisch SW
  //            -- Diagonale laeuft NW-SE
  //   Frueher hier: rr=0 war lat_max (Norden) -- "tl" meinte NW
  //            -- Diagonale lief SW-NE (90 Grad gedreht)
  // Selbst bei identischen Vertices interpolieren die beiden Meshes dann
  // ueber verschiedene Diagonalen -- innerhalb jedes Quads kann der
  // Hoehenunterschied mehrere Meter erreichen, das DEM-Dreieck stoesst
  // dann durch die Karte. Daher: r von r_min nach r_max, wie in demMesh.
  let pIdx = 0;
  let tIdx = 0;
  for (let rr = 0; rr < N_rows; rr++) {
    const r = r_min + rr;
    const lat = demGrid.lat_min + r * dem_dlat;

    for (let cc = 0; cc < N_cols; cc++) {
      const c = c_min + cc;
      const lon = demGrid.lon_min + c * dem_dlon;
      const elev = demGrid.elevations[r * demGrid.n_cols + c] ?? 0;

      positions[pIdx++] = (lon - lon_center) * mpLon;
      positions[pIdx++] = (lat - lat_center) * mpLat;
      positions[pIdx++] = altBase + (elev - altBase) * zScale + Z_LIFT_SUBGRID_M;

      // UV-Mapping innerhalb der Karten-Bounds. Iterationsreihenfolge wirkt
      // sich hier NICHT auf die Orientierung aus -- u/v sind ueber die
      // absolute Geo-Position der Vertices definiert, nicht ueber den
      // Schleifenindex. Beibehalten:
      //   u=0 links (lon_min), u=1 rechts (lon_max)
      //   v=0 oben (lat_max),  v=1 unten (lat_min)
      texCoords[tIdx++] = (lon - lon_min) / (lon_max - lon_min);
      texCoords[tIdx++] = (lat_max - lat) / (lat_max - lat_min);
    }
  }

  // Triangle-Indizes, gleiche Topologie wie demMesh / Strategie B.
  const nCells = (N_rows - 1) * (N_cols - 1);
  const indices = new Uint32Array(nCells * 6);
  let iIdx = 0;
  for (let r = 0; r < N_rows - 1; r++) {
    for (let c = 0; c < N_cols - 1; c++) {
      const tl = r * N_cols + c;
      const tr = tl + 1;
      const bl = tl + N_cols;
      const br = bl + 1;
      indices[iIdx++] = tl;
      indices[iIdx++] = bl;
      indices[iIdx++] = tr;
      indices[iIdx++] = tr;
      indices[iIdx++] = bl;
      indices[iIdx++] = br;
    }
  }

  return { positions, texCoords, indices, anchor: [lon_center, lat_center] };
}

// ---------------------------------------------------------------------------
// Strategie B: Bilineare Interpolation der vier Ecken (Fallback)
// ---------------------------------------------------------------------------

function computeAdaptiveSubdivision(chart: ChartOverlay): number {
  const lonSpan = Math.max(
    Math.abs(chart.corner_tr[0] - chart.corner_tl[0]),
    Math.abs(chart.corner_br[0] - chart.corner_bl[0]),
  );
  const latSpan = Math.max(
    Math.abs(chart.corner_tl[1] - chart.corner_bl[1]),
    Math.abs(chart.corner_tr[1] - chart.corner_br[1]),
  );
  const latCenter =
    (chart.corner_tl[1] + chart.corner_tr[1] +
     chart.corner_bl[1] + chart.corner_br[1]) / 4;
  const { mpLon, mpLat } = metersPerDegree(latCenter);
  const widthM  = lonSpan * mpLon;
  const heightM = latSpan * mpLat;
  const maxM = Math.max(widthM, heightM);
  const raw = Math.ceil(maxM / TARGET_METERS_PER_VERTEX);
  return Math.max(SUBDIV_FLOOR, Math.min(SUBDIV_CAP, raw));
}

/** Bilineare Interpolation der vier Eckkoordinaten ueber (u,v) ∈ [0,1]². */
function lerpCorners(
  chart: ChartOverlay,
  u: number,
  v: number,
): [number, number] {
  const [tlx, tly] = chart.corner_tl;
  const [trx, try_] = chart.corner_tr;
  const [blx, bly] = chart.corner_bl;
  const [brx, bry] = chart.corner_br;
  const topX  = tlx + (trx - tlx) * u;
  const topY  = tly + (try_ - tly) * u;
  const botX  = blx + (brx - blx) * u;
  const botY  = bly + (bry - bly) * u;
  return [
    topX + (botX - topX) * v,
    topY + (botY - topY) * v,
  ];
}

function buildFromBilinearCorners(
  chart: ChartOverlay,
  demGrid: DemGrid | null,
  altBase: number,
  zScale: number,
  subdivision?: number | null,
): ChartMesh {
  const requested = subdivision ?? chart.subdivision ?? computeAdaptiveSubdivision(chart);
  const N = Math.max(2, requested);

  const lon_center =
    (chart.corner_tl[0] + chart.corner_tr[0] +
     chart.corner_bl[0] + chart.corner_br[0]) / 4;
  const lat_center =
    (chart.corner_tl[1] + chart.corner_tr[1] +
     chart.corner_bl[1] + chart.corner_br[1]) / 4;
  const { mpLon, mpLat } = metersPerDegree(lat_center);

  const positions = new Float32Array(N * N * 3);
  const texCoords = new Float32Array(N * N * 2);

  let pIdx = 0;
  let tIdx = 0;
  for (let r = 0; r < N; r++) {
    const v = r / (N - 1);
    for (let c = 0; c < N; c++) {
      const u = c / (N - 1);
      const [lon, lat] = lerpCorners(chart, u, v);

      let elev = chart.elevation_m;
      if (demGrid) {
        const sampled = sampleDem(demGrid, lon, lat);
        if (sampled !== null) elev = sampled;
      }

      positions[pIdx++] = (lon - lon_center) * mpLon;
      positions[pIdx++] = (lat - lat_center) * mpLat;
      positions[pIdx++] = altBase + (elev - altBase) * zScale + Z_LIFT_BILINEAR_M;

      texCoords[tIdx++] = u;
      texCoords[tIdx++] = v;
    }
  }

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

  return { positions, texCoords, indices, anchor: [lon_center, lat_center] };
}

// ---------------------------------------------------------------------------
// Public Entry: buildChartMesh
// ---------------------------------------------------------------------------

/**
 * Baut ein gedraptes Mesh fuer einen Chart-Overlay.
 *
 * Waehlt automatisch Strategie A (Terrain-Subgrid) falls moeglich,
 * sonst B (bilineare Ecken).
 */
export function buildChartMesh(
  chart: ChartOverlay,
  demGrid: DemGrid | null,
  altBase: number = 0,
  zScale: number = 1,
  subdivision?: number | null,
): ChartMesh {
  // Strategie A: nur wenn DEM da UND Karte achsenparallel UND der
  // Nutzer (oder die TXT) keine explizite Subdivision erzwingt
  // (sonst respektieren wir die Override-Wahl mit dem bilinearen Pfad).
  if (demGrid && isAxisAligned(chart) && subdivision == null && chart.subdivision == null) {
    const meshA = buildFromTerrainSubgrid(chart, demGrid, altBase, zScale);
    if (meshA) return meshA;
  }
  return buildFromBilinearCorners(chart, demGrid, altBase, zScale, subdivision);
}
