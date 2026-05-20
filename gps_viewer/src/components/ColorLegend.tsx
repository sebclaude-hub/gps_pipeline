import { useMemo } from "react";
import type { ColorMode, QuantileBreaks } from "../types";
import { plasmaGradientCss } from "../utils/colorMap";

interface Props {
  breaks: QuantileBreaks;
  colorMode: ColorMode;
}

/**
 * Verteilt Tick-Positionen proportional zu den numerischen Bereichen,
 * erzwingt aber einen Mindestabstand `minGap` ∈ (0,1) zwischen aufeinander-
 * folgenden Ticks, damit Labels lesbar bleiben.
 *
 * Idee: pos_raw_i = (break_i - min) / (max - min). Anschließend „spreizen“
 * wir die Lücken, die kleiner als minGap sind, indem wir die übrigen Lücken
 * proportional komprimieren — und re-skalieren das Ergebnis auf [0,1].
 */
function distributeTicks(breaks: number[], minGap: number): number[] {
  const n = breaks.length;
  if (n < 2) return breaks.map(() => 0);

  const min = breaks[0];
  const max = breaks[n - 1];
  const span = max - min;
  if (span <= 0) {
    return breaks.map((_, i) => i / (n - 1));
  }

  const raw = breaks.map(b => (b - min) / span);
  const gaps = new Array(n - 1).fill(0).map((_, i) => raw[i + 1] - raw[i]);

  // Iterativ: Lücken unter minGap auf minGap heben, Überschuss aus den
  // großen Lücken nehmen — wiederholen bis stabil oder Notbremse.
  const minG = Math.min(minGap, 1 / (n - 1));
  for (let iter = 0; iter < 20; iter++) {
    const small: number[] = [];
    const big: number[] = [];
    let deficit = 0;
    let bigSum = 0;
    for (let i = 0; i < gaps.length; i++) {
      if (gaps[i] < minG) {
        deficit += minG - gaps[i];
        small.push(i);
      } else {
        big.push(i);
        bigSum += gaps[i] - minG;
      }
    }
    if (deficit < 1e-6 || bigSum < 1e-6) break;
    const factor = Math.min(1, bigSum > 0 ? deficit / bigSum : 0);
    for (const i of small) gaps[i] = minG;
    for (const i of big) gaps[i] = gaps[i] - (gaps[i] - minG) * factor;
  }

  // Re-akkumulieren und auf [0,1] normalisieren.
  const positions = [0];
  for (let i = 0; i < gaps.length; i++) {
    positions.push(positions[i] + gaps[i]);
  }
  const total = positions[positions.length - 1];
  return positions.map(p => p / total);
}

export function ColorLegend({ breaks, colorMode }: Props) {
  const isSpeed = colorMode === "speed";
  const values = isSpeed ? breaks.speed_kmh : breaks.altitude_m;
  const unit = isSpeed ? "km/h" : "m";
  const label = isSpeed ? "Geschwindigkeit" : "Höhe";

  const positions = useMemo(() => distributeTicks(values, 0.10), [values]);

  const gradient = useMemo(() => plasmaGradientCss(20, 230), []);

  const HEIGHT = 180;
  const BAR_W = 14;

  return (
    <div style={{
      position: "absolute", top: 124, right: 12,
      background: "rgba(0,0,0,0.65)",
      borderRadius: 6, padding: "10px 12px",
      color: "#ddd", fontSize: 11,
      pointerEvents: "none",
    }}>
      <div style={{ marginBottom: 6, fontWeight: 600 }}>{label}</div>
      <div style={{ display: "flex", alignItems: "stretch", gap: 6 }}>
        <div style={{
          width: BAR_W, height: HEIGHT,
          borderRadius: 3,
          background: gradient,
          border: "1px solid rgba(255,255,255,0.12)",
        }} />
        <div style={{ position: "relative", height: HEIGHT, width: 64 }}>
          {values.map((v, i) => {
            // pos=0 unten, pos=1 oben → top in % = (1 - pos) * 100
            const top = (1 - positions[i]) * HEIGHT;
            return (
              <div
                key={i}
                style={{
                  position: "absolute",
                  top: top - 7,
                  left: 0,
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  whiteSpace: "nowrap",
                }}
              >
                <div style={{
                  width: 6, height: 1, background: "#888",
                }} />
                <span style={{ fontVariantNumeric: "tabular-nums" }}>
                  {v.toFixed(isSpeed ? 0 : 0)}
                </span>
              </div>
            );
          })}
        </div>
      </div>
      <div style={{ marginTop: 6, color: "#888", fontSize: 10 }}>{unit}</div>
    </div>
  );
}
