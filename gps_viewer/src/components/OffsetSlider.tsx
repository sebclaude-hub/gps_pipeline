/**
 * OffsetSlider -- interaktive Anpassung des Track-Z-Offsets gegen das DEM.
 *
 * Zweck
 * -----
 * Der vom Backend gelieferte Auto-Offset ist nur ein "best guess" (Median +
 * outlier-robustes Clamping). In der Praxis stimmt er oft auf ein paar
 * Meter genau, aber feiner kalibrieren kann der Nutzer mit dem Slider --
 * z.B. anhand eines bekannten Bodenpunkts (Landeschwelle) oder eines
 * ebenen Strassenabschnitts.
 *
 * Aufbau
 * ------
 *   * Slider mit Range [suggested-200, suggested+200] m
 *   * Numerische Anzeige + Eingabe (Edit ueber Doppelklick)
 *   * "Auto"-Button setzt zurueck auf Suggested
 *   * "0"-Button setzt auf 0 (kein Shift -- Track wie original)
 *
 * Schrittweite: 1 m (Standard), 0.1 m bei gedrueckter Shift-Taste.
 */

import { useCallback, useEffect, useState } from "react";

interface Props {
  /** Aktueller Offset-Wert in Metern. */
  value: number;
  /** Vom Backend vorgeschlagener Wert (Auto-Diagnose). */
  suggested: number;
  onChange: (v: number) => void;
}

// ± um den Slider-Default. Klein gehalten (50 m statt 200 m), weil bei
// ~150 px Slider-Breite und Step 0.5 ein 50-m-Range etwa 1.5 px pro
// Schritt liefert -- ueberhaupt erst aimbar. Wer mehr braucht: per
// Doppelklick numerisch eintippen, das hat keine Range-Begrenzung.
const RANGE_M = 50;
const STEP_M = 0.5;        // trifft 7.0, 7.5, 8.0 alle nativ
const FINE_STEP_M = 0.1;   // mit gedrueckter Shift-Taste waehrend des Drags

export function OffsetSlider({ value, suggested, onChange }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>("");

  const min = Math.round(suggested - RANGE_M);
  const max = Math.round(suggested + RANGE_M);

  // Slider-Wert in [min, max] clampen, aber numerische Eingabe darf
  // ausserhalb liegen (z.B. fuer Spezialfaelle).
  const sliderValue = Math.max(min, Math.min(max, value));

  const handleSliderChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(Number(e.target.value));
  }, [onChange]);

  // Shift-Modifier fuer Feinschritt. Die ALTE Implementierung mit React
  // onKeyDown auf dem Slider hat nur bei fokussiertem Slider PLUS aktiver
  // Keyboard-Bedienung gefeuert -- beim Maus-Drag (was der Hauptweg ist)
  // wurde sie nie ausgeloest. Deshalb jetzt auf Window-Level, damit Shift
  // egal wo gedrueckt werden kann (auch waehrend ein Drag laeuft).
  const [step, setStep] = useState<number>(STEP_M);
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Shift") setStep(FINE_STEP_M);
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.key === "Shift") setStep(STEP_M);
    };
    // Sicherheitshalber auch bei Window-Blur zuruecksetzen, sonst klebt
    // der Feinschritt, wenn die Shift-Taste in einem anderen Fenster
    // losgelassen wird.
    const onBlur = () => setStep(STEP_M);
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
    };
  }, []);

  const startEdit = useCallback(() => {
    setDraft(value.toFixed(1));
    setEditing(true);
  }, [value]);
  const commitEdit = useCallback(() => {
    const parsed = parseFloat(draft);
    if (!Number.isNaN(parsed)) onChange(parsed);
    setEditing(false);
  }, [draft, onChange]);
  const cancelEdit = useCallback(() => setEditing(false), []);

  return (
    <div style={containerStyle} title="Track-Hoehen-Offset gegen DEM">
      <div style={labelRowStyle}>
        <span style={{ color: "#bbb", fontSize: 10 }}>Z-Offset</span>
        {editing ? (
          <input
            type="number"
            step="any"
            value={draft}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commitEdit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitEdit();
              else if (e.key === "Escape") cancelEdit();
            }}
            style={inputStyle}
          />
        ) : (
          <span
            style={valueStyle}
            onDoubleClick={startEdit}
            title="Doppelklick zum Bearbeiten"
          >
            {value.toFixed(1)} m
          </span>
        )}
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={sliderValue}
        onChange={handleSliderChange}
        style={sliderInputStyle}
        title={`${min} … ${max} m (Shift = Feinschritt 0.1 m)`}
      />
      <div style={buttonRowStyle}>
        <button
          onClick={() => onChange(suggested)}
          style={smallButtonStyle}
          title={`Zurueck auf Auto-Wert (${suggested.toFixed(1)} m)`}
        >
          Auto
        </button>
        <button
          onClick={() => onChange(0)}
          style={smallButtonStyle}
          title="Kein Offset -- Track bei Originalhoehe"
        >
          0
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const containerStyle: React.CSSProperties = {
  background: "rgba(0,0,0,0.65)",
  border: "1px solid rgba(255,255,255,0.15)",
  borderRadius: 14,
  padding: "6px 10px",
  display: "flex",
  flexDirection: "column",
  gap: 4,
  minWidth: 150,
};

const labelRowStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
};

const valueStyle: React.CSSProperties = {
  color: "#fff",
  fontSize: 12,
  fontWeight: 600,
  fontVariantNumeric: "tabular-nums",
  cursor: "text",
};

const inputStyle: React.CSSProperties = {
  width: 70,
  fontSize: 11,
  background: "#1a1a1a",
  color: "#fff",
  border: "1px solid #333",
  borderRadius: 3,
  padding: "1px 4px",
  fontVariantNumeric: "tabular-nums",
};

const sliderInputStyle: React.CSSProperties = {
  width: "100%",
  accentColor: "#7b61ff",
  margin: 0,
};

const buttonRowStyle: React.CSSProperties = {
  display: "flex", gap: 4, justifyContent: "space-between",
};

const smallButtonStyle: React.CSSProperties = {
  flex: 1,
  background: "#333",
  color: "#ddd",
  border: "1px solid #444",
  borderRadius: 3,
  padding: "1px 6px",
  fontSize: 10,
  cursor: "pointer",
};
