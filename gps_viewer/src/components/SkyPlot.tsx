/**
 * Polar-Skyplot: zeigt Satellitenpositionen (Azimut/Elevation) als SVG.
 *
 * Azimut 0° = Nord (oben), 90° = Ost (rechts).
 * Elevation 0° = Horizont (außen), 90° = Zenit (mitte).
 * Kreisradius = proportional zu (90° - elevation).
 * Größe des Markers ∝ SNR. Farbe nach Konstellation.
 */
import { useMemo } from "react";
import type { SatelliteData, GsvBurst } from "../types";

const SIZE = 260;
const CX = SIZE / 2;
const CY = SIZE / 2;
const R = SIZE / 2 - 20;

const TALKER_COLORS: Record<string, string> = {
  GP: "#4fc3f7",  // GPS  → hellblau
  GL: "#81c784",  // GLONASS → grün
  GA: "#ffb74d",  // Galileo → orange
  GB: "#f48fb1",  // BeiDou → rosa
};
const DEFAULT_COLOR = "#ce93d8";

function talkerColor(talker: string): string {
  return TALKER_COLORS[talker] ?? DEFAULT_COLOR;
}

function polarToXY(azDeg: number, elDeg: number): [number, number] {
  const az = ((azDeg - 90) * Math.PI) / 180;   // 0°N → links im Kreis
  const r = R * (1 - elDeg / 90);
  return [CX + r * Math.cos(az), CY + r * Math.sin(az)];
}

interface Props {
  satData: SatelliteData | null;
  trackIdx: number;
}

export function SkyPlot({ satData, trackIdx }: Props) {
  const allSats = useMemo(() => {
    if (!satData) return [];
    const result: { x: number; y: number; r: number; color: string; prn: number | null }[] = [];

    for (const talker of satData.talkers) {
      const lookup = satData.burst_idx_by_track[talker];
      if (!lookup) continue;
      const burstIdx = lookup[trackIdx] ?? -1;
      if (burstIdx < 0) continue;
      const burst: GsvBurst = satData.bursts_by_talker[talker][burstIdx];
      if (!burst) continue;

      for (const [prn, el, az, snr] of burst.sats) {
        if (el === null || az === null) continue;
        const [x, y] = polarToXY(az, el);
        const radius = snr !== null ? Math.max(3, Math.min(10, snr / 6)) : 4;
        result.push({ x, y, r: radius, color: talkerColor(talker), prn });
      }
    }
    return result;
  }, [satData, trackIdx]);

  const azLabels = [
    { label: "N", az: 0 },
    { label: "E", az: 90 },
    { label: "S", az: 180 },
    { label: "W", az: 270 },
  ];
  const elRings = [0, 30, 60, 90];

  return (
    <svg
      width={SIZE}
      height={SIZE}
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      style={{ background: "#1a1a2e", borderRadius: 8 }}
    >
      {/* Elevation-Ringe */}
      {elRings.map((el) => (
        <circle
          key={el}
          cx={CX} cy={CY}
          r={R * (1 - el / 90)}
          fill="none"
          stroke="#334"
          strokeWidth={el === 0 ? 1.5 : 0.8}
        />
      ))}
      {/* Elevation-Beschriftung */}
      {[30, 60].map((el) => (
        <text
          key={el}
          x={CX + 4}
          y={CY - R * (1 - el / 90) + 4}
          fill="#556"
          fontSize={9}
        >
          {el}°
        </text>
      ))}
      {/* Azimut-Linien */}
      {[0, 45, 90, 135].map((az) => {
        const rad = ((az - 90) * Math.PI) / 180;
        return (
          <line
            key={az}
            x1={CX + R * Math.cos(rad)}
            y1={CY + R * Math.sin(rad)}
            x2={CX - R * Math.cos(rad)}
            y2={CY - R * Math.sin(rad)}
            stroke="#334"
            strokeWidth={0.8}
          />
        );
      })}
      {/* Himmelsrichtungs-Beschriftung */}
      {azLabels.map(({ label, az }) => {
        const rad = ((az - 90) * Math.PI) / 180;
        return (
          <text
            key={label}
            x={CX + (R + 12) * Math.cos(rad) - 4}
            y={CY + (R + 12) * Math.sin(rad) + 4}
            fill="#889"
            fontSize={11}
            fontWeight="bold"
          >
            {label}
          </text>
        );
      })}
      {/* Satelliten */}
      {allSats.map((s, i) => (
        <circle
          key={i}
          cx={s.x} cy={s.y} r={s.r}
          fill={s.color}
          fillOpacity={0.85}
          stroke="#fff"
          strokeWidth={0.5}
        />
      ))}
      {/* Zenit-Marker */}
      <circle cx={CX} cy={CY} r={2} fill="#556" />

      {/* Legende */}
      {Object.entries(TALKER_COLORS).map(([t, c], i) => (
        <g key={t} transform={`translate(8, ${SIZE - 68 + i * 16})`}>
          <circle cx={5} cy={5} r={4} fill={c} />
          <text x={13} y={9} fill="#889" fontSize={10}>{t}</text>
        </g>
      ))}
      {allSats.length === 0 && (
        <text x={CX} y={CY + 4} textAnchor="middle" fill="#445" fontSize={11}>
          Keine GSV-Daten
        </text>
      )}
    </svg>
  );
}
