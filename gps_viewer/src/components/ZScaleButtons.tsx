interface Props {
  value: number;
  options: number[];
  onChange: (v: number) => void;
}

/**
 * Kompakte Button-Gruppe für die Z-Exaggeration. Im gleichen Pill-Stil wie
 * die ToggleSwitches darüber.
 */
export function ZScaleButtons({ value, options, onChange }: Props) {
  const H = 28;

  return (
    <div
      style={{
        display: "flex",
        height: H,
        background: "rgba(0,0,0,0.65)",
        border: "1px solid rgba(255,255,255,0.15)",
        borderRadius: H / 2,
        overflow: "hidden",
        userSelect: "none",
      }}
      title="Höhen-Übertreibung"
    >
      {options.map((v) => {
        const active = v === value;
        return (
          <div
            key={v}
            onClick={() => onChange(v)}
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 11,
              fontWeight: 600,
              cursor: "pointer",
              background: active
                ? "linear-gradient(180deg, #5a5a8f, #3d3d6b)"
                : "transparent",
              color: active ? "#fff" : "#bbb",
              transition: "background 120ms",
              minWidth: 0,
            }}
          >
            {v}×
          </div>
        );
      })}
    </div>
  );
}
