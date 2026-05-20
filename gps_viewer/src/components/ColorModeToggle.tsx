import type { ColorMode } from "../types";

interface Props {
  value: ColorMode;
  onChange: (mode: ColorMode) => void;
}

/**
 * Moderner Schiebe-Switch mit zwei Labels.
 * Der Knubbel gleitet zwischen "km/h" und "Höhe".
 */
export function ColorModeToggle({ value, onChange }: Props) {
  const isSpeed = value === "speed";

  const W = 140;
  const H = 28;
  const THUMB_W = W / 2;

  return (
    <div
      onClick={() => onChange(isSpeed ? "altitude" : "speed")}
      style={{
        position: "absolute",
        top: 12,
        right: 12,
        width: W,
        height: H,
        background: "rgba(0,0,0,0.65)",
        border: "1px solid rgba(255,255,255,0.15)",
        borderRadius: H / 2,
        cursor: "pointer",
        userSelect: "none",
        overflow: "hidden",
      }}
      role="switch"
      aria-checked={!isSpeed}
      title="Farbgebung umschalten"
    >
      {/* Knubbel */}
      <div
        style={{
          position: "absolute",
          top: 2,
          left: isSpeed ? 2 : W - THUMB_W - 2,
          width: THUMB_W,
          height: H - 4,
          background: "linear-gradient(180deg, #5a5a8f, #3d3d6b)",
          borderRadius: (H - 4) / 2,
          boxShadow: "0 1px 3px rgba(0,0,0,0.5)",
          transition: "left 180ms cubic-bezier(.4,.0,.2,1)",
        }}
      />
      {/* Labels */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-around",
          fontSize: 11,
          fontWeight: 600,
          pointerEvents: "none",
        }}
      >
        <span style={{ color: isSpeed ? "#fff" : "#bbb", flex: 1, textAlign: "center" }}>
          km/h
        </span>
        <span style={{ color: !isSpeed ? "#fff" : "#bbb", flex: 1, textAlign: "center" }}>
          Höhe
        </span>
      </div>
    </div>
  );
}
