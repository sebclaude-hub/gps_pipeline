interface Props<T extends string> {
  value: T;
  options: [T, T];
  labels: [string, string];
  onChange: (v: T) => void;
  title?: string;
}

/**
 * Generischer Pill-Switch mit zwei Labels. Der Knubbel gleitet zwischen
 * den Optionen, das aktive Label ist weiß, das inaktive grau.
 */
export function ToggleSwitch<T extends string>({
  value, options, labels, onChange, title,
}: Props<T>) {
  const isLeft = value === options[0];

  const W = 140;
  const H = 28;
  const THUMB_W = W / 2;

  return (
    <div
      onClick={() => onChange(isLeft ? options[1] : options[0])}
      style={{
        width: W,
        height: H,
        background: "rgba(0,0,0,0.65)",
        border: "1px solid rgba(255,255,255,0.15)",
        borderRadius: H / 2,
        cursor: "pointer",
        userSelect: "none",
        overflow: "hidden",
        position: "relative",
      }}
      role="switch"
      aria-checked={!isLeft}
      title={title}
    >
      <div
        style={{
          position: "absolute",
          top: 2,
          left: isLeft ? 2 : W - THUMB_W - 2,
          width: THUMB_W,
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
          justifyContent: "space-around",
          fontSize: 11,
          fontWeight: 600,
          pointerEvents: "none",
        }}
      >
        <span style={{ color: isLeft ? "#fff" : "#bbb", flex: 1, textAlign: "center" }}>
          {labels[0]}
        </span>
        <span style={{ color: !isLeft ? "#fff" : "#bbb", flex: 1, textAlign: "center" }}>
          {labels[1]}
        </span>
      </div>
    </div>
  );
}
