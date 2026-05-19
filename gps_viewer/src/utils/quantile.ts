/**
 * Plasma-Farbpalette für Quantil-Indizes.
 * Farben von d3-scale-chromatic interpolatePlasma, vorberechnet für 5 Klassen.
 * RGBA-Tupel mit leichter Transparenz (alpha=210) für den Vorhang-Effekt.
 */
import { interpolatePlasma } from "d3-scale-chromatic";

/** Parst "rgb(r, g, b)" → [r, g, b] */
function parseRgb(rgb: string): [number, number, number] {
  const m = rgb.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
  if (!m) return [128, 128, 128];
  return [parseInt(m[1]), parseInt(m[2]), parseInt(m[3])];
}

/** Baut eine RGBA-Palette für n Quantilklassen. */
export function buildPalette(nQuantiles: number, alpha = 210): [number, number, number, number][] {
  return Array.from({ length: nQuantiles }, (_, i) => {
    const t = nQuantiles === 1 ? 0.5 : i / (nQuantiles - 1);
    const [r, g, b] = parseRgb(interpolatePlasma(t));
    return [r, g, b, alpha] as [number, number, number, number];
  });
}

/** Singleton-Palette (5 Klassen, Default). */
let _defaultPalette: [number, number, number, number][] | null = null;
export function getDefaultPalette(nQuantiles = 5): [number, number, number, number][] {
  if (!_defaultPalette || _defaultPalette.length !== nQuantiles) {
    _defaultPalette = buildPalette(nQuantiles);
  }
  return _defaultPalette;
}

/** Gibt die RGBA-Farbe für einen Quantil-Index zurück. -1 → grau. */
export function quantileColor(
  idx: number,
  palette: [number, number, number, number][]
): [number, number, number, number] {
  if (idx < 0 || idx >= palette.length) return [150, 150, 150, 180];
  return palette[idx];
}
