import type { ColorMode } from "../types";

interface Props {
  value: ColorMode;
  onChange: (v: ColorMode) => void;
  /** Wenn false (kein DEM geladen), sind Flug- und Drohne-Modus disabled. */
  enableTerrainModes: boolean;
}

const OPTIONS: { value: ColorMode; label: string; needsTerrain: boolean }[] = [
  { value: "speed",    label: "km/h",   needsTerrain: false },
  { value: "altitude", label: "Hoehe",  needsTerrain: false },
  { value: "flight",   label: "Flug",   needsTerrain: true  },
  { value: "drone",    label: "Drohne", needsTerrain: true  },
];

/**
 * Vier-Segment-Pill fuer den Color-Mode. "speed"/"altitude" faerben den
 * Track per Quantil-Plasma (kontinuierlich), "flight"/"drone" lassen die
 * Track-Linie auf Speed-Plasma und faerben nur den Curtain regelbasiert
 * (Schwellen aus den GND/MSL-Hoehen). Letzte beide sind disabled, wenn
 * kein Terrain geladen ist.
 */
export function ColorModeSelect({ value, onChange, enableTerrainModes }: Props) {
  const W = 260;
  const H = 28;
  const SEG_W = W / OPTIONS.length;
  const activeIdx = Math.max(0, OPTIONS.findIndex(o => o.value === value));

  return (
    <div
      style={{
        width: W,
        height: H,
        background: "rgba(0,0,0,0.65)",
        border: "1px solid rgba(255,255,255,0.15)",
        borderRadius: H / 2,
        position: "relative",
        userSelect: "none",
      }}
      role="radiogroup"
      aria-label="Color mode"
    >
      <div
        style={{
          position: "absolute",
          top: 2,
          left: 2 + activeIdx * SEG_W,
          width: SEG_W - 4,
          height: H - 4,
          background: "linear-gradient(180deg, #5a5a8f, #3d3d6b)",
          borderRadius: (H - 4) / 2,
          boxShadow: "0 1px 3px rgba(0,0,0,0.5)",
          transition: "left 180ms cubic-bezier(.4,.0,.2,1)",
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          fontSize: 11,
          fontWeight: 600,
        }}
      >
        {OPTIONS.map((opt, i) => {
          const disabled = opt.needsTerrain && !enableTerrainModes;
          const active = i === activeIdx;
          return (
            <div
              key={opt.value}
              onClick={() => { if (!disabled) onChange(opt.value); }}
              role="radio"
              aria-checked={active}
              aria-disabled={disabled}
              title={disabled
                ? "Benoetigt ein geladenes DEM (Terrain)"
                : `Farbmodus: ${opt.label}`}
              style={{
                flex: 1,
                textAlign: "center",
                color: disabled ? "#555"
                       : active ? "#fff"
                       : "#bbb",
                cursor: disabled ? "not-allowed" : "pointer",
              }}
            >
              {opt.label}
            </div>
          );
        })}
      </div>
    </div>
  );
}
