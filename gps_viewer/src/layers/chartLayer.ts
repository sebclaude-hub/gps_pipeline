/**
 * chartLayer -- rendert einen Karten-Overlay als gedraptes, texturiertes Mesh.
 *
 * Verwendet SimpleMeshLayer (wie der Terrain-Layer), aber mit:
 *  - Per-Vertex UV-Koordinaten (texCoords)
 *  - PNG-Textur (Browser-Image, von loadChartImage geladen)
 *
 * Ergebnis: das PNG legt sich passgenau ueber die vier Eckkoordinaten und
 * folgt dabei den Hoehen des DEMs ("draping").
 *
 * Z-Exaggeration: muss im Aufruf identisch zum Terrain/Track sein, sonst
 * "schwebt" die Karte ueber/unter dem Gelaende.
 */

import { SimpleMeshLayer } from "@deck.gl/mesh-layers";
import type { DemGrid } from "../types";
import { buildChartMesh, type ChartOverlay } from "../utils/chartMesh";

/** Hellweisses, vollopakes Tint -- die Textur dominiert die Farbe. */
const TINT: [number, number, number, number] = [255, 255, 255, 255];

export function makeChartLayer(
  chart: ChartOverlay,
  image: HTMLImageElement | ImageBitmap,
  demGrid: DemGrid | null,
  altBase: number = 0,
  zScale: number = 1,
) {
  const mesh = buildChartMesh(chart, demGrid, altBase, zScale);

  // deck.gl-Mesh-Struktur mit per-Vertex Attributen.
  // ``texCoords`` ist das Standard-Attribut, das der eingebaute Mesh-Layer-
  // Shader fuer ``texture`` benoetigt.
  const deckMesh = {
    attributes: {
      positions: { value: mesh.positions, size: 3 },
      texCoords: { value: mesh.texCoords, size: 2 },
    },
    indices: { value: mesh.indices, size: 1 },
  };

  return new SimpleMeshLayer({
    id: `chart-${chart.name}`,
    data: [{ position: [mesh.anchor[0], mesh.anchor[1], 0] }],
    mesh: deckMesh,
    texture: image,
    getPosition: (d: any) => d.position,
    getColor: TINT,
    // material:false -> Flat-Shading; mit LightingEffect (nicht eingerichtet)
    // wuerde die Karte sonst abgedunkelt erscheinen.
    material: false,
    pickable: false,
    wireframe: false,
  });
}
