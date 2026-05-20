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
export function makeTerrainLayer(dem: DemLod, altBase: number = 0, zScale: number = 1) {
  const mesh = gridToMesh(dem.grid, altBase, zScale);

  // deck.gl SimpleMeshLayer erwartet ein Mesh-Objekt mit
  // { attributes: { positions }, indices }
  const deckMesh = {
    attributes: {
      positions: { value: mesh.positions, size: 3 },
    },
    indices: { value: mesh.indices, size: 1 },
  };

  // Mesh-Positionen sind in Metern relativ zu mesh.anchor (lng/lat).
  return new SimpleMeshLayer({
    id: `terrain-lod${dem.lod}`,
    data: [{ position: [mesh.anchor[0], mesh.anchor[1], 0] }],
    mesh: deckMesh,
    getPosition: (d: any) => d.position,
    getColor: TERRAIN_COLOR,
    // material:false → flat shading, nimmt direkt getColor.
    // Echtes Material braucht eine LightingEffect (nicht eingerichtet),
    // sonst rendert deck.gl die Fläche schwarz.
    material: false,
    pickable: false,
    wireframe: false,
  });
}
