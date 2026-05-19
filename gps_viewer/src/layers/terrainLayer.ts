/**
 * Terrain-Mesh-Layer: zeigt das DEM als triangulierte Fläche.
 *
 * Nutzt SimpleMeshLayer von deck.gl mit vorberechneten Positionen und Indizes
 * aus demMesh.ts. Bei LOD-Wechsel wird einfach ein neuer Layer mit neuer ID
 * instanziiert — deck.gl diffed automatisch.
 */

import { SimpleMeshLayer } from "@deck.gl/mesh-layers";
import type { DemLod } from "../types";
import { gridToMesh } from "../utils/demMesh";

// Terrain-Farbe: sanftes Grau-Beige
const TERRAIN_COLOR: [number, number, number, number] = [180, 168, 140, 220];

/** Erzeugt einen SimpleMeshLayer für das übergebene DEM. */
export function makeTerrainLayer(dem: DemLod) {
  const mesh = gridToMesh(dem.grid);

  // deck.gl SimpleMeshLayer erwartet ein Mesh-Objekt mit
  // { attributes: { positions }, indices }
  const deckMesh = {
    attributes: {
      positions: { value: mesh.positions, size: 3 },
    },
    indices: { value: mesh.indices, size: 1 },
  };

  return new SimpleMeshLayer({
    id: `terrain-lod${dem.lod}`,
    data: [{ position: [0, 0, 0] }],
    mesh: deckMesh,
    getPosition: () => [0, 0, 0],
    getColor: TERRAIN_COLOR,
    getTranslation: [0, 0, 0],
    material: {
      ambient: 0.6,
      diffuse: 0.6,
      shininess: 4,
    },
    pickable: false,
    wireframe: false,
  });
}
