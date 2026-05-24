/**
 * InfoModeButtons -- 3-Wege-Pill-Switch fuer den Anzeige-Modus der Punkt-Info.
 *
 * Optionen:
 *   - "panel"   : rechtsseitiges InfoPanel (Default, voller Datensatz)
 *   - "tooltip" : Floating-Tooltip am Cursor (minimal -- Zeit/Speed/Hoehe)
 *   - "both"    : beides gleichzeitig
 *
 * Visueller Stil ist identisch zu ZScaleButtons, damit die Toggle-Spalte
 * konsistent bleibt.
 */

export type InfoMode = "panel" | "tooltip" | "both";

interface Props {
  value: InfoMode;
  onChange: (v: InfoMode) => void;
}

const OPTIONS: { value: InfoMode; label: string }[] = [
  { value: "panel",   label: "Panel" },
  { value: "tooltip", label: "Tip" },
  { value: "both",    label: "Beide" },
];

export function InfoModeButtons({ value, onChange }: Props) {
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
      title="Punkt-Info anzeigen als"
    >
      {OPTIONS.map((opt) => {
        const active = opt.value === value;
        return (
          <div
            key={opt.value}
            onClick={() => onChange(opt.value)}
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 11,
              fontWeight: 600,
              cursor: "pointer",
              padding: "0 10px",
              background: active
                ? "linear-gradient(180deg, #5a5a8f, #3d3d6b)"
                : "transparent",
              color: active ? "#fff" : "#bbb",
              transition: "background 120ms",
              minWidth: 0,
            }}
          >
            {opt.label}
          </div>
        );
      })}
    </div>
  );
}
