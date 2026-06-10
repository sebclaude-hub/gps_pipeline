import type { ColorMode } from "../types";

interface Props {
  value: ColorMode;
  onChange: (v: ColorMode) => void;
  /** Wenn false (kein DEM geladen), sind terrain-abhaengige Modi disabled. */
  enableTerrainModes: boolean;
  /** Wenn false (alte track.json ohne die Felder), sind die abgeleiteten Modi
   *  (Beschl./Energie/ΔEnergie) disabled. */
  enableDerivedModes: boolean;
}

type Need = "terrain" | "derived" | null;

const OPTIONS: { value: ColorMode; label: string; need: Need }[] = [
  { value: "speed",        label: "km/h",     need: null },
  { value: "altitude",     label: "Höhe MSL", need: null },
  { value: "altitude_gnd", label: "Höhe GND", need: "terrain" },
  { value: "flight",       label: "Flug",     need: "terrain" },
  { value: "drone",        label: "Drohne",   need: "terrain" },
  { value: "accel",        label: "Beschl.",  need: "derived" },
  { value: "energy",       label: "Spez. Energie", need: "derived" },
  { value: "energy_rate",  label: "Energierate",   need: "derived" },
];

/**
 * Farbmodus-Auswahl als umbrechende Button-Gruppe (frueher feste 4-Segment-
 * Pille — skaliert nicht auf 8 Modi). "speed"/"altitude"/"altitude_gnd"/"energy"
 * faerben kontinuierlich (Quantil-Plasma), "accel"/"energy_rate" signiert
 * (YlOrRd/YlGnBu), "flight"/"drone" regelbasiert am Vorhang. Terrain-Modi sind
 * ohne DEM disabled, abgeleitete Modi ohne die Pipeline-Felder.
 */
export function ColorModeSelect({ value, onChange, enableTerrainModes, enableDerivedModes }: Props) {
  return (
    <div
      role="radiogroup"
      aria-label="Color mode"
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 4,
        maxWidth: 280,
        justifyContent: "flex-end",
      }}
    >
      {OPTIONS.map((opt) => {
        const disabled =
          (opt.need === "terrain" && !enableTerrainModes) ||
          (opt.need === "derived" && !enableDerivedModes);
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            role="radio"
            aria-checked={active}
            aria-disabled={disabled}
            disabled={disabled}
            onClick={() => { if (!disabled) onChange(opt.value); }}
            title={
              disabled
                ? (opt.need === "terrain"
                    ? "Benoetigt ein geladenes DEM (Terrain)"
                    : "Track ohne abgeleitete Felder (Pipeline neu exportieren)")
                : `Farbmodus: ${opt.label}`
            }
            style={{
              fontSize: 11,
              fontWeight: 600,
              padding: "4px 9px",
              borderRadius: 13,
              border: active ? "1px solid #7a7ad0" : "1px solid rgba(255,255,255,0.15)",
              background: active
                ? "linear-gradient(180deg, #5a5a8f, #3d3d6b)"
                : "rgba(0,0,0,0.55)",
              color: disabled ? "#555" : active ? "#fff" : "#bbb",
              cursor: disabled ? "not-allowed" : "pointer",
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
