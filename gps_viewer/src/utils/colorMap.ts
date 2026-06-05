/**
 * Kontinuierlicher Plasma-Farbverlauf basierend auf Rang-Normalisierung.
 *
 * Statt diskrete Quantil-Klassen zu färben, bekommt jeder Punkt eine
 * individuelle Farbe nach seinem Rang innerhalb der Werte-Verteilung:
 *   t = rank(value) / (N - 1)
 *   color = interpolatePlasma(t)
 *
 * Das ergibt einen gleichmäßigen Farbverlauf entlang des Tracks und ist
 * robust gegen Extremwerte (Ausreißer verzerren die Farbskala nicht).
 */
import { interpolatePlasma } from "d3-scale-chromatic";

export type Rgba = [number, number, number, number];

function parseRgb(s: string): [number, number, number] {
  // Hex: #rgb oder #rrggbb
  if (s.startsWith("#")) {
    const hex = s.slice(1);
    if (hex.length === 3) {
      return [
        parseInt(hex[0] + hex[0], 16),
        parseInt(hex[1] + hex[1], 16),
        parseInt(hex[2] + hex[2], 16),
      ];
    }
    if (hex.length === 6) {
      return [
        parseInt(hex.slice(0, 2), 16),
        parseInt(hex.slice(2, 4), 16),
        parseInt(hex.slice(4, 6), 16),
      ];
    }
  }
  // rgb(r, g, b) / rgba(r, g, b, a)
  const m = s.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
  if (m) return [parseInt(m[1]), parseInt(m[2]), parseInt(m[3])];
  return [128, 128, 128];
}

/** Plasma-Farbe für t ∈ [0,1]. */
export function plasmaColor(t: number, alpha = 220): Rgba {
  const clamped = Math.max(0, Math.min(1, t));
  const [r, g, b] = parseRgb(interpolatePlasma(clamped));
  return [r, g, b, alpha];
}

/**
 * Berechnet pro Index eine normalisierte Rang-Position [0,1].
 * Gleiche Werte bekommen denselben Rang (average rank).
 * NaN/null → NaN im Ergebnis.
 */
export function computeRankPositions(values: (number | null)[]): number[] {
  const n = values.length;
  const result = new Array<number>(n);

  const indexed: { idx: number; v: number }[] = [];
  for (let i = 0; i < n; i++) {
    const v = values[i];
    if (v === null || v === undefined || Number.isNaN(v)) {
      result[i] = NaN;
    } else {
      indexed.push({ idx: i, v });
    }
  }

  indexed.sort((a, b) => a.v - b.v);
  const m = indexed.length;
  if (m <= 1) {
    for (const e of indexed) result[e.idx] = 0.5;
    return result;
  }

  // Average-Rank bei Gleichwerten
  let i = 0;
  while (i < m) {
    let j = i;
    while (j < m && indexed[j].v === indexed[i].v) j++;
    const avgRank = (i + j - 1) / 2; // 0-basiert
    const t = avgRank / (m - 1);
    for (let k = i; k < j; k++) result[indexed[k].idx] = t;
    i = j;
  }
  return result;
}

/**
 * Quantil-entzerrte Farb-Position [0,1] eines Einzelwerts.
 *
 * WARUM (statt reinem Rang oben): Bei Autofahrten liegen sehr viele Punkte in
 * einem schmalen Wertefenster (z.B. ~120 km/h). Reiner Rang spreizt sie zwar,
 * kennt aber keine Klassengrenzen, die die Legende anzeigen kann. Hier bekommt
 * jedes der k Quantile einen GLEICH langen Farb-Abschnitt (1/k), und INNERHALB
 * eines Quantils werden die Werte LINEAR (auf die Abschnittslänge normiert)
 * verteilt. So bleibt der Cluster entzerrt sichtbar, gleiche Werte = gleiche
 * Farbe, und die Legende kann die echten Quantilgrenzen (mit Wertbezug) zeigen.
 *
 * `breaks` = k+1 Quantilgrenzen (inkl. min/max), wie sie das Backend liefert
 * (können aufgefüllte Duplikate enthalten → degenerierte Bins → 0.5).
 */
export function quantileLinearPosition(v: number, breaks: number[]): number {
  const k = breaks.length - 1;
  if (k < 1) return 0.5;
  if (v <= breaks[0]) return 0;
  if (v >= breaks[k]) return 1;
  let i = 0;
  while (i < k - 1 && v > breaks[i + 1]) i++;
  const lo = breaks[i];
  const hi = breaks[i + 1];
  const within = hi > lo ? Math.max(0, Math.min(1, (v - lo) / (hi - lo))) : 0.5;
  return (i + within) / k;
}

/** Array-Variante; null/NaN → NaN. */
export function quantileLinearPositions(
  values: (number | null)[],
  breaks: number[],
): number[] {
  return values.map((v) =>
    v === null || !Number.isFinite(v)
      ? NaN
      : quantileLinearPosition(v as number, breaks),
  );
}

/** Hilfsfunktion: rgba-String für CSS aus einer Rgba-Tupel. */
export function rgbaCss(c: Rgba): string {
  return `rgba(${c[0]},${c[1]},${c[2]},${c[3] / 255})`;
}

/** CSS linear-gradient String (Plasma, von t=0 unten bis t=1 oben). */
export function plasmaGradientCss(steps = 16, alpha = 220): string {
  const stops: string[] = [];
  for (let i = 0; i < steps; i++) {
    const t = i / (steps - 1);
    stops.push(`${rgbaCss(plasmaColor(t, alpha))} ${(t * 100).toFixed(1)}%`);
  }
  return `linear-gradient(to top, ${stops.join(", ")})`;
}
