import { useMemo } from "react";
import { getDefaultPalette } from "../utils/quantile";
import type { QuantileBreaks } from "../types";

interface Props {
  breaks: QuantileBreaks;
}

export function ColorLegend({ breaks }: Props) {
  const { speed_kmh, n_quantiles } = breaks;
  const palette = useMemo(() => getDefaultPalette(n_quantiles), [n_quantiles]);

  return (
    <div style={{
      position: "absolute", top: 12, right: 12,
      background: "rgba(0,0,0,0.65)",
      borderRadius: 6, padding: "8px 12px",
      color: "#ddd", fontSize: 11,
      pointerEvents: "none",
    }}>
      <div style={{ marginBottom: 4, fontWeight: 600 }}>Geschwindigkeit</div>
      {palette.map((color, i) => {
        const lo = speed_kmh[i]?.toFixed(0) ?? "–";
        const hi = speed_kmh[i + 1]?.toFixed(0) ?? "–";
        const [r, g, b, a] = color;
        return (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
            <div style={{
              width: 14, height: 14, borderRadius: 2,
              background: `rgba(${r},${g},${b},${a / 255})`,
            }} />
            <span>{lo}–{hi} km/h</span>
          </div>
        );
      })}
    </div>
  );
}
