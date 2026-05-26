/**
 * Terrain-Mesh-Layer: zeigt das DEM als triangulierte Fläche.
 *
 * Nutzt SimpleMeshLayer von deck.gl mit vorberechneten Positionen und Indizes
 * aus demMesh.ts. Bei LOD-Wechsel wird einfach ein neuer Layer mit neuer ID
 * instanziiert — deck.gl diffed automatisch.
 *
 * Färbung: hypsometrisch pro Vertex (Tiefland-Grün → Schnee-Weiß je nach
 * Höhe). Berechnet in ``demMesh.ts`` aus den rohen DEM-Werten.
 */

import { SimpleMeshLayer } from "@deck.gl/mesh-layers";
import type { DemLod } from "../types";
import { gridToMesh } from "../utils/demMesh";

/** Erzeugt einen SimpleMeshLayer für das übergebene DEM. */
export function makeTerrainLayer(dem: DemLod, altBase: number = 0, zScale: number = 1) {
  const mesh = gridToMesh(dem.grid, altBase, zScale);

  // SimpleMeshLayer-Vertex-Farben via RGBA-Attribut. Uint8 + normalized=true:
  // der Shader dividiert pro Komponente durch 255. Kein Lighting (material=false)
  // -> die Vertex-Farben gehen 1:1 in den Pixel.
  const deckMesh = {
    attributes: {
      positions: { value: mesh.positions, size: 3 },
      colors:    { value: mesh.colors,    size: 4, normalized: true },
    },
    indices: { value: mesh.indices, size: 1 },
  };

  // Mesh-Positionen sind in Metern relativ zu mesh.anchor (lng/lat).
  return new SimpleMeshLayer({
    id: `terrain-lod${dem.lod}`,
    data: [{ position: [mesh.anchor[0], mesh.anchor[1], 0] }],
    mesh: deckMesh,
    getPosition: (d: any) => d.position,
    // Wenn das Mesh ein colors-Attribut mitbringt, ignoriert SimpleMeshLayer
    // den getColor-Wert. Wir setzen ihn trotzdem als Fallback, falls das
    // Mesh keine Vertex-Farben hat (z.B. nach Refactor).
    getColor: [180, 168, 140, 220],
    // material:false → flat shading, nimmt direkt die Vertex-Farben.
    // Echtes Material braucht eine LightingEffect (nicht eingerichtet),
    // sonst rendert deck.gl die Fläche schwarz.
    material: false,
    pickable: false,
    wireframe: false,
  });
}
