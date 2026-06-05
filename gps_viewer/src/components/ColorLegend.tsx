import { useMemo } from "react";
import type { ColorMode, TrackData } from "../types";
import {
  accelGradientCss,
  plasmaColor,
  quantileLinearPosition,
  rgbaCss,
} from "../utils/colorMap";
import { colorScaleFor } from "../utils/colorScale";

interface Props {
  track: TrackData;
  colorMode: ColorMode;
  /** Pixel-Abstand vom oberen Rand. Wird von App.tsx je nach Anzahl der
   *  sichtbaren Toggles gesetzt, damit die Legende nicht ueberlappt. */
  topOffset?: number;
}

const GRADIENT_META: Partial<Record<ColorMode, { label: string; unit: string }>> = {
  speed: { label: "Geschwindigkeit", unit: "km/h" },
  altitude: { label: "Höhe (MSL)", unit: "m" },
  altitude_gnd: { label: "Höhe (GND)", unit: "m" },
  energy: { label: "Energiehöhe", unit: "m" },
};

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

// Hex-Strings spiegeln die Rgba-Konstanten aus curtainLayer.ts wider.
const FLIGHT_CLASSES = [
  { color: "#dc3c3c", label: "< 500 ft GND" },
  { color: "#f09628", label: "< 1000 ft GND" },
  { color: "#3cbebe", label: "< 5000 ft MSL" },
  { color: "#4678dc", label: "darueber" },
];
const DRONE_CLASSES = [
  { color: "#4678dc", label: "<= 100 m GND" },
  { color: "#dc3c3c", label: "darueber" },
];

function ClassLegend({ topOffset, label, classes }: {
  topOffset: number; label: string;
  classes: { color: string; label: string }[];
}) {
  return (
    <div style={{
      position: "absolute", top: topOffset, right: 12,
      background: "rgba(0,0,0,0.65)",
      borderRadius: 6, padding: "10px 12px",
      color: "#ddd", fontSize: 11,
      pointerEvents: "none",
    }}>
      <div style={{ marginBottom: 6, fontWeight: 600 }}>{label}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {classes.map((c, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{
              width: 14, height: 12,
              background: c.color, borderRadius: 2,
              border: "1px solid rgba(255,255,255,0.12)",
            }} />
            <span style={{ whiteSpace: "nowrap" }}>{c.label}</span>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 6, color: "#888", fontSize: 10 }}>
        Vorhang-Faerbung
      </div>
    </div>
  );
}

export function ColorLegend({ track, colorMode, topOffset = 124 }: Props) {
  // Gradient-Modi (speed/altitude/altitude_gnd/energy): Grenzen + gestauchter
  // Verlauf + Tick-Positionen. IMMER aufgerufen (keine bedingten Hooks); null
  // fuer Klassen-/Signed-Modi. Werte/Grenzen kommen aus der Pipeline (JSON).
  const grad = useMemo(() => {
    const meta = GRADIENT_META[colorMode];
    if (!meta) return null;
    const values = colorScaleFor(track, colorMode).breaks;
    if (!values || values.length < 2) return null;
    const positions = distributeTicks(values, 0.10);
    const min = values[0];
    const max = values[values.length - 1];
    const span = max - min || 1;
    const steps = 28;
    const stops: string[] = [];
    for (let i = 0; i < steps; i++) {
      const f = i / (steps - 1);
      const v = min + f * span;
      const pos = quantileLinearPosition(v, values);
      stops.push(`${rgbaCss(plasmaColor(pos, 230))} ${(f * 100).toFixed(1)}%`);
    }
    const gradient = `linear-gradient(to top, ${stops.join(", ")})`;
    return { ...meta, values, positions, gradient };
  }, [track, colorMode]);

  // Klassen-Legenden fuer die regelbasierten Modi.
  if (colorMode === "flight") {
    return <ClassLegend topOffset={topOffset} label="Flug" classes={FLIGHT_CLASSES} />;
  }
  if (colorMode === "drone") {
    return <ClassLegend topOffset={topOffset} label="Drohne" classes={DRONE_CLASSES} />;
  }

  // Signierte Modi (accel / energy_rate): horizontaler YlOrRd/YlGnBu-Verlauf.
  if (colorMode === "accel" || colorMode === "energy_rate") {
    const title = colorMode === "accel" ? "Beschleunigung" : "Energieänderung";
    const [left, right] =
      colorMode === "accel" ? ["− Bremsen", "Beschl. +"] : ["− verliert", "gewinnt +"];
    return (
      <div style={{
        position: "absolute", top: topOffset, right: 12,
        background: "rgba(0,0,0,0.65)",
        borderRadius: 6, padding: "10px 12px",
        color: "#ddd", fontSize: 11, pointerEvents: "none",
      }}>
        <div style={{ marginBottom: 6, fontWeight: 600 }}>{title}</div>
        <div style={{
          width: 160, height: 10, borderRadius: 2,
          background: accelGradientCss(),
          border: "1px solid rgba(255,255,255,0.12)",
        }} />
        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, color: "#aaa", fontSize: 10 }}>
          <span>{left}</span><span>{right}</span>
        </div>
      </div>
    );
  }

  if (!grad) return null;

  const HEIGHT = 180;
  const BAR_W = 14;

  // Gradient-Legende auf linearer Werteachse, Obergrenzen-Labels (Mindestabstand).
  return (
    <div style={{
      position: "absolute", top: topOffset, right: 12,
      background: "rgba(0,0,0,0.65)",
      borderRadius: 6, padding: "10px 12px",
      color: "#ddd", fontSize: 11,
      pointerEvents: "none",
    }}>
      <div style={{ marginBottom: 6, fontWeight: 600 }}>{grad.label}</div>
      <div style={{ display: "flex", alignItems: "stretch", gap: 6 }}>
        <div style={{
          width: BAR_W, height: HEIGHT,
          borderRadius: 3,
          background: grad.gradient,
          border: "1px solid rgba(255,255,255,0.12)",
        }} />
        <div style={{ position: "relative", height: HEIGHT, width: 64 }}>
          {grad.values.map((v, i) => {
            if (i === 0) return null; // nur Obergrenzen
            const top = (1 - grad.positions[i]) * HEIGHT;
            return (
              <div key={i} style={{
                position: "absolute", top: top - 7, left: 0,
                display: "flex", alignItems: "center", gap: 4, whiteSpace: "nowrap",
              }}>
                <div style={{ width: 6, height: 1, background: "#888" }} />
                <span style={{ fontVariantNumeric: "tabular-nums" }}>{v.toFixed(0)}</span>
              </div>
            );
          })}
        </div>
      </div>
      <div style={{ marginTop: 6, color: "#888", fontSize: 10 }}>{grad.unit}</div>
    </div>
  );
}
