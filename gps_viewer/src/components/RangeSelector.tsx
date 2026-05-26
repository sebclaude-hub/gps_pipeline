/**
 * RangeSelector -- UI fuer Cut-Range-Selektion mit drei Modi
 * (trim / gap / synthetic).
 *
 * Eigenschaften der UI
 * --------------------
 *   * Horizontale "Cut-Leiste" parallel zum TrackSlider darunter.
 *   * Cut-Bars sind nach Modus farbcodiert:
 *       trim       (rot, mit Schraffur fuer Edges) -- Muell-Entfernung am Rand
 *       gap        (gruen)   -- Punkte raus, sichtbare Luecke
 *       synthetic  (blau)    -- Punkte raus, Zeitachse zusammenrueckend
 *   * Globaler Pill-Switch "Luecke / Zeit verschieben" entscheidet, was
 *     neue Middle-Cuts werden (und schaltet alle bestehenden Middle-
 *     Cuts mit). Edge-Cuts (start=0 oder end=N-1) bleiben immer trim.
 *   * "+ Cut" deaktiviert, wenn um die aktuelle Slider-Position herum
 *     keine Luecke mehr existiert.
 *   * "Reset" loescht alle Cuts; "Export" laedt
 *     ``<source>.cuts.json`` herunter mit dem neuen Sidecar-Format.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  CutRange, RangeSelectionApi, MiddleMode,
} from "../hooks/useRangeSelection";

interface Props {
  totalPoints: number;
  activeIdx: number;
  api: RangeSelectionApi;
  /** Dateiname (mit Endung) der Quelldatei, in die die Schnittanweisungen
   *  geschrieben werden -- wird in die ``cuts.json`` exportiert und
   *  bestimmt den Download-Dateinamen. Wenn null/leer, ist Export
   *  deaktiviert (Viewer weiss sonst nicht, wohin gespeichert werden soll). */
  sourceFile?: string | null;
  /** Aktueller Hoehen-Anzeigeoffset in m. Wird mit in die ``cuts.json``
   *  geschrieben, damit geteilte Tracks den Slider-Default mitbringen. */
  zOffset?: number;
}

const TRACK_HEIGHT = 18;
const HANDLE_WIDTH = 10;

// Farbpalette pro Modus -- definiert hier zentral, damit Balken, Handles
// und Tooltip-Texte konsistent bleiben.
type ModeStyle = {
  bgSolid: string;
  bgHatched: string;     // fuer Edge-Cuts
  border: string;
  handle: string;
  label: string;
};
const MODE_STYLES: Record<CutRange["mode"], ModeStyle> = {
  trim: {
    bgSolid:   "rgba(220, 70, 70, 0.45)",
    bgHatched: "repeating-linear-gradient(45deg, rgba(220,70,70,0.55) 0 6px, rgba(220,70,70,0.3) 6px 12px)",
    border:    "#c44",
    handle:    "#f55",
    label:     "Trim",
  },
  gap: {
    bgSolid:   "rgba(70, 180, 90, 0.45)",
    bgHatched: "repeating-linear-gradient(45deg, rgba(70,180,90,0.55) 0 6px, rgba(70,180,90,0.3) 6px 12px)",
    border:    "#4a4",
    handle:    "#5d5",
    label:     "Gap",
  },
  synthetic: {
    bgSolid:   "rgba(80, 130, 220, 0.45)",
    bgHatched: "repeating-linear-gradient(45deg, rgba(80,130,220,0.55) 0 6px, rgba(80,130,220,0.3) 6px 12px)",
    border:    "#46c",
    handle:    "#69e",
    label:     "Synth",
  },
};

// ---------------------------------------------------------------------------
// Label-Helfer
// ---------------------------------------------------------------------------

/** Liefert pro Cut sein Anzeige-Label und ob es ein Trim-Edge ist. */
function classifyCuts(
  cuts: CutRange[],
  totalPoints: number,
): Array<CutRange & { label: string; trimStart: boolean; trimEnd: boolean }> {
  const sorted = [...cuts].sort((a, b) => a.start - b.start);
  let cutCounter = 0;
  return sorted.map((r) => {
    const trimStart = r.start === 0;
    const trimEnd = r.end === totalPoints - 1;
    let label: string;
    if (trimStart && trimEnd) label = "Trim Alles";
    else if (trimStart)       label = "Trim Start";
    else if (trimEnd)         label = "Trim Ende";
    else {
      cutCounter += 1;
      const modeLabel = MODE_STYLES[r.mode].label;
      label = `${modeLabel} ${cutCounter}`;
    }
    return { ...r, label, trimStart, trimEnd };
  });
}

// ---------------------------------------------------------------------------
// Hauptkomponente
// ---------------------------------------------------------------------------

export function RangeSelector({ totalPoints, activeIdx, api, sourceFile, zOffset = 0 }: Props) {
  const trackRef = useRef<HTMLDivElement | null>(null);

  /** Bildschirm-X -> Track-Index (clamped). */
  const xToIdx = useCallback((clientX: number): number => {
    const el = trackRef.current;
    if (!el) return 0;
    const rect = el.getBoundingClientRect();
    const px = clientX - rect.left;
    const ratio = Math.max(0, Math.min(1, px / rect.width));
    return Math.round(ratio * (totalPoints - 1));
  }, [totalPoints]);

  const handleAdd = useCallback(() => {
    api.addRange(activeIdx, totalPoints);
  }, [api, activeIdx, totalPoints]);

  const canAdd = api.canAddRange(activeIdx, totalPoints);

  // Hint-State: nach Export einen Popup mit dem fertigen CLI-Befehl
  // einblenden. Verschwindet nach 25 s automatisch oder beim Klick aufs X.
  const [exportHint, setExportHint] = useState<boolean>(false);
  useEffect(() => {
    if (!exportHint) return;
    const t = window.setTimeout(() => setExportHint(false), 25_000);
    return () => window.clearTimeout(t);
  }, [exportHint]);

  // Source-File und daraus abgeleitete Download-/Anweisungs-Dateinamen.
  // Wenn die Quelle nicht bekannt ist, kann auch nicht exportiert werden.
  const sourceKnown = !!(sourceFile && sourceFile.length > 0);
  const effectiveSource = sourceFile ?? "";
  const exportName = sourceKnown
    ? `${effectiveSource}.cuts.json`
    : "(unbekannte Quelle)";

  const hasZOffset = Math.abs(zOffset) >= 0.05;   // rundet 0.0x auf 0
  const canExport = sourceKnown
                    && (api.ranges.length > 0 || hasZOffset);

  const handleExport = useCallback(() => {
    if (!canExport) return;
    const sorted = [...api.ranges].sort((a, b) => a.start - b.start);
    const payload: Record<string, unknown> = {
      source: effectiveSource,
      n_points_reference: totalPoints,
      cut_ranges: sorted.map((r) => ({
        start: r.start, end: r.end, mode: r.mode,
      })),
      created_at: new Date().toISOString(),
    };
    if (hasZOffset) {
      payload.z_offset_m = Math.round(zOffset * 10) / 10;
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)],
                         { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = exportName;
    a.click();
    URL.revokeObjectURL(url);
    setExportHint(true);
  }, [api.ranges, totalPoints, effectiveSource, exportName,
      canExport, zOffset, hasZOffset]);

  // Hinweis-Text fuer den Export-Popup: Anweisungsdatei nach data/
  // verschieben und Pipeline neu laufen lassen.
  const hintCmd = [
    `# 1. ${exportName} aus Downloads nach data/ verschieben`,
    `#    (selber Ordner wie ${effectiveSource || "deine Quelldatei"})`,
    "# 2. Pipeline neu laufen lassen:",
    '$env:PYTHONUTF8 = "1"',
    "python -m gps_pipeline",
    "# 3. Track im Viewer ansehen:",
    `python view.py output/nmea_${(effectiveSource || "track").replace(/\.[^.]+$/, "")}`,
    "",
    "# Schnittanweisungen deaktivieren: Datei umbenennen,",
    `# z.B. ${exportName}.disabled`,
  ].join("\n");

  const copyCmd = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(hintCmd);
    } catch {
      // Clipboard-API kann auf nicht-HTTPS-Origins fehlschlagen --
      // dann muss der Nutzer aus dem <pre>-Block kopieren.
    }
  }, [hintCmd]);

  // Labelled + sortiert -- benutze ich sowohl unten als auch fuer die
  // Count-Anzeige rechts.
  const labelled = useMemo(
    () => classifyCuts(api.ranges, totalPoints),
    [api.ranges, totalPoints]
  );

  const middleCutCount = labelled.filter((r) => !r.trimStart && !r.trimEnd).length;
  const hasAnyCut = labelled.length > 0;

  return (
    <div style={{ ...containerStyle, position: "relative" }}>
      {exportHint && (
        <div style={hintBoxStyle}>
          <div style={hintHeaderStyle}>
            <span>{exportName} heruntergeladen. Naechster Schritt:</span>
            <button
              onClick={() => setExportHint(false)}
              style={hintCloseStyle}
              title="Hinweis schliessen"
            >×</button>
          </div>
          <pre style={hintCmdStyle}>{hintCmd}</pre>
          <div style={hintFooterStyle}>
            <button onClick={copyCmd} style={hintCopyBtnStyle}>
              In Zwischenablage kopieren
            </button>
            <span style={{ color: "#888", fontSize: 10 }}>
              Datei muss neben der Quelldatei in data/ liegen
            </span>
          </div>
        </div>
      )}
      <div style={leftCtrlsStyle}>
        <button
          onClick={handleAdd}
          disabled={!canAdd}
          style={{
            ...buttonStyle,
            opacity: canAdd ? 1 : 0.4,
            cursor: canAdd ? "pointer" : "not-allowed",
          }}
          title={canAdd
            ? "Cut um aktuelle Slider-Position einfuegen"
            : "Keine freie Luecke um die Slider-Position"}
        >
          + Cut
        </button>
        {hasAnyCut && (
          <button onClick={api.clearAll} style={buttonStyle}
                  title="Alle Cuts entfernen">
            Reset
          </button>
        )}
        {(hasAnyCut || hasZOffset) && (
          <button
            onClick={handleExport}
            disabled={!canExport}
            style={{
              ...buttonStyle,
              background: canExport ? "#3a3" : "#333",
              opacity: canExport ? 1 : 0.5,
              cursor: canExport ? "pointer" : "not-allowed",
            }}
            title={canExport
              ? `${exportName} herunterladen`
              : "Export: Quelldatei unbekannt. Verarbeite den Track ueber 'python -m gps_pipeline', damit source_file gesetzt ist."}
          >
            Export
            {hasZOffset && ` (z=${zOffset >= 0 ? "+" : ""}${zOffset.toFixed(1)}m)`}
          </button>
        )}
        <MiddleModeToggle
          value={api.middleMode}
          onChange={(m) => api.setMiddleMode(m, totalPoints)}
          disabled={middleCutCount === 0}
          title={middleCutCount === 0
            ? "Modus fuer kuenftige Middle-Cuts (aktuell keine vorhanden)"
            : `Modus fuer alle ${middleCutCount} Middle-Cut(s)`}
        />
      </div>

      <div ref={trackRef} style={trackStyle}>
        {labelled.map((r) => (
          <RangeBar
            key={r.id}
            range={r}
            label={r.label}
            trimStart={r.trimStart}
            trimEnd={r.trimEnd}
            totalPoints={totalPoints}
            onMove={(start, end) => api.updateRange(r.id, { start, end }, totalPoints)}
            onRemove={() => api.removeRange(r.id)}
            xToIdx={xToIdx}
          />
        ))}
      </div>

      <div style={countStyle}>
        {labelled.length === 0
          ? <span style={{ color: "#555" }}>keine Cuts</span>
          : <span>{labelled.length} Cut{labelled.length > 1 ? "s" : ""}</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MiddleModeToggle -- Pill-Switch "Luecke" <-> "Zeit verschieben"
// ---------------------------------------------------------------------------

interface MiddleModeToggleProps {
  value: MiddleMode;
  onChange: (m: MiddleMode) => void;
  disabled?: boolean;
  title?: string;
}

function MiddleModeToggle({ value, onChange, disabled, title }: MiddleModeToggleProps) {
  const isGap = value === "gap";
  return (
    <div
      style={{
        ...toggleContainerStyle,
        opacity: disabled ? 0.5 : 1,
        cursor: disabled ? "default" : "pointer",
      }}
      title={title}
      onClick={() => {
        if (disabled) return;
        onChange(isGap ? "synthetic" : "gap");
      }}
    >
      <div style={{
        ...toggleKnobStyle,
        left: isGap ? 2 : "calc(50% + 0px)",
        background: isGap
          ? MODE_STYLES.gap.handle
          : MODE_STYLES.synthetic.handle,
      }} />
      <span style={{
        ...toggleLabelStyle,
        color: isGap ? "#fff" : "#888",
        fontWeight: isGap ? 600 : 400,
      }}>
        Luecke
      </span>
      <span style={{
        ...toggleLabelStyle,
        color: !isGap ? "#fff" : "#888",
        fontWeight: !isGap ? 600 : 400,
      }}>
        Zeit verschieben
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// RangeBar -- ein Cut-Balken
// ---------------------------------------------------------------------------

interface RangeBarProps {
  range: CutRange;
  label: string;
  trimStart: boolean;
  trimEnd: boolean;
  totalPoints: number;
  onMove: (start: number, end: number) => void;
  onRemove: () => void;
  xToIdx: (clientX: number) => number;
}

function RangeBar({
  range, label, trimStart, trimEnd,
  totalPoints, onMove, onRemove, xToIdx,
}: RangeBarProps) {
  const [dragging, setDragging] = useState<"start" | "end" | null>(null);

  const leftPct = (range.start / (totalPoints - 1)) * 100;
  const rightPct = (range.end / (totalPoints - 1)) * 100;
  const widthPct = Math.max(0.2, rightPct - leftPct);

  // Aktuelle Range in Refs spiegeln, damit der Window-PointerMove-Handler
  // immer die jeweils neuesten Grenzen sieht, ohne dass sich die
  // useEffect-Listener bei jedem State-Update neu binden.
  const rangeRef = useRef(range);
  rangeRef.current = range;
  const onMoveRef = useRef(onMove);
  onMoveRef.current = onMove;
  const xToIdxRef = useRef(xToIdx);
  xToIdxRef.current = xToIdx;

  const startDrag = useCallback((side: "start" | "end") => (e: React.PointerEvent) => {
    // Kein setPointerCapture mehr -- die Window-Listener kuemmern sich um
    // alle Moves/Ups bis zum Loslassen. Damit ist der Drag robust gegen
    // Verschwinden des Handle-DOM-Knotens, das passiert wenn der Cut
    // gerade zur Trim-Edge wird.
    e.preventDefault();
    e.stopPropagation();
    setDragging(side);
  }, []);

  // Window-Level-Listener fuer die Drag-Bewegung. Vorher hingen sie am
  // Handle selbst -- das war buggy, weil der Handle aus dem DOM
  // verschwindet, sobald der Cut zur Trim-Edge wird. Pointer-Up kam dann
  // nie an, die nachfolgenden Move-Events der ANDEREN Seite des Cuts
  // trafen den verlassenen Drag-State und liessen den Cut auf 0
  // zusammenschnurren.
  useEffect(() => {
    if (!dragging) return;
    const onPointerMove = (e: PointerEvent) => {
      const idx = xToIdxRef.current(e.clientX);
      const r = rangeRef.current;
      if (dragging === "start") onMoveRef.current(idx, r.end);
      else                       onMoveRef.current(r.start, idx);
    };
    const onPointerUp = () => setDragging(null);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerUp);
    };
  }, [dragging]);

  const style = MODE_STYLES[range.mode];
  // Schraffur-Muster fuer Trim-Edges -- macht Edge-Cuts visuell klar von
  // Middle-Cuts unterscheidbar.
  const baseBackground = (trimStart || trimEnd)
    ? style.bgHatched
    : style.bgSolid;

  return (
    <div style={{
      position: "absolute",
      left: `${leftPct}%`,
      width: `${widthPct}%`,
      top: 0, bottom: 0,
      background: baseBackground,
      borderTop: `1px solid ${style.border}`,
      borderBottom: `1px solid ${style.border}`,
      pointerEvents: "none",
      overflow: "visible",
    }}>
      {/* Start-Handle -- nicht fuer Trim-Start (linke Kante klebt am Track-Start).
          Nur onPointerDown am Element; Move/Up haengen am Window (siehe useEffect),
          damit der Drag auch ueberlebt, wenn das Handle waehrenddessen verschwindet. */}
      {!trimStart && (
        <div
          onPointerDown={startDrag("start")}
          style={{
            ...handleStyle,
            left: -HANDLE_WIDTH / 2,
            background: dragging === "start" ? "#fff" : style.handle,
          }}
          title={`Start: ${range.start}`}
        />
      )}

      {/* End-Handle -- nicht fuer Trim-Ende */}
      {!trimEnd && (
        <div
          onPointerDown={startDrag("end")}
          style={{
            ...handleStyle,
            right: -HANDLE_WIDTH / 2,
            background: dragging === "end" ? "#fff" : style.handle,
          }}
          title={`Ende: ${range.end}`}
        />
      )}

      {/* Label im Balken zentriert. Wird ausgeblendet, wenn der Balken sehr
          schmal ist -- dann reicht das Title-Attribut auf den Handles. */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 10,
          fontWeight: 700,
          color: "#fff",
          textShadow: "0 1px 2px rgba(0,0,0,0.7)",
          pointerEvents: "none",
          whiteSpace: "nowrap",
          overflow: "hidden",
        }}
        title={`${label} (${range.start}..${range.end}, mode=${range.mode})`}
      >
        {label}
      </div>

      {/* Entfernen-Button */}
      <button
        onClick={onRemove}
        style={{
          position: "absolute",
          top: -8, right: -8,
          width: 16, height: 16,
          borderRadius: 8,
          background: "#222",
          color: "#fff",
          border: "1px solid #555",
          fontSize: 11,
          cursor: "pointer",
          padding: 0,
          lineHeight: "14px",
          pointerEvents: "auto",
        }}
        title="Diesen Cut entfernen"
      >×</button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const containerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  padding: "4px 16px",
  background: "#0f0f0f",
  borderTop: "1px solid #2a2a2a",
};

const leftCtrlsStyle: React.CSSProperties = {
  display: "flex", gap: 4, flexShrink: 0, alignItems: "center",
};

const trackStyle: React.CSSProperties = {
  position: "relative",
  flex: 1,
  height: TRACK_HEIGHT,
  background: "#1a1a1a",
  borderRadius: 3,
  border: "1px solid #2a2a2a",
};

const handleStyle: React.CSSProperties = {
  position: "absolute",
  top: -2, bottom: -2,
  width: HANDLE_WIDTH,
  cursor: "ew-resize",
  borderRadius: 2,
  pointerEvents: "auto",
  touchAction: "none",
};

const buttonStyle: React.CSSProperties = {
  background: "#333",
  color: "#eee",
  border: "1px solid #444",
  borderRadius: 4,
  padding: "2px 8px",
  fontSize: 11,
  cursor: "pointer",
};

const countStyle: React.CSSProperties = {
  color: "#888", fontSize: 11, minWidth: 60, textAlign: "right",
  flexShrink: 0,
};

// ---- MiddleModeToggle ----

const toggleContainerStyle: React.CSSProperties = {
  position: "relative",
  display: "inline-flex",
  alignItems: "center",
  width: 200,
  height: 24,
  marginLeft: 8,
  borderRadius: 12,
  background: "#1a1a1a",
  border: "1px solid #333",
  padding: "0 4px",
  fontSize: 10,
  userSelect: "none",
};

const toggleKnobStyle: React.CSSProperties = {
  position: "absolute",
  top: 2,
  width: "calc(50% - 2px)",
  height: "calc(100% - 4px)",
  borderRadius: 10,
  transition: "left 0.18s cubic-bezier(0.4, 0.0, 0.2, 1), background 0.18s",
  pointerEvents: "none",
};

const toggleLabelStyle: React.CSSProperties = {
  flex: 1,
  textAlign: "center",
  zIndex: 1,
  transition: "color 0.18s, font-weight 0.18s",
};

// ---------------------------------------------------------------------------
// Export-Hint Popup
// ---------------------------------------------------------------------------

const hintBoxStyle: React.CSSProperties = {
  position: "absolute",
  // ueber der Cut-Leiste schweben, an der rechten Seite (wo der
  // Export-Button bei mehreren Cuts liegt). Boden waere TrackSlider drunter.
  bottom: "calc(100% + 6px)",
  right: 16,
  width: 520,
  background: "rgba(20, 20, 28, 0.96)",
  border: "1px solid rgba(255,255,255,0.18)",
  borderRadius: 8,
  padding: "10px 12px",
  color: "#eee",
  fontSize: 11,
  fontFamily: "system-ui, sans-serif",
  boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
  zIndex: 20,
};

const hintHeaderStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  marginBottom: 6,
  fontWeight: 600,
};

const hintCloseStyle: React.CSSProperties = {
  background: "transparent",
  border: "1px solid #444",
  color: "#bbb",
  borderRadius: 3,
  cursor: "pointer",
  fontSize: 13,
  lineHeight: "14px",
  width: 20,
  height: 20,
  padding: 0,
};

const hintCmdStyle: React.CSSProperties = {
  background: "#0a0a12",
  border: "1px solid #2a2a3a",
  borderRadius: 4,
  padding: "8px 10px",
  fontSize: 11,
  lineHeight: 1.45,
  fontFamily: "ui-monospace, 'Cascadia Code', Consolas, monospace",
  color: "#d8d8e0",
  margin: "4px 0 8px 0",
  overflowX: "auto",
  whiteSpace: "pre",
};

const hintFooterStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 10,
};

const hintCopyBtnStyle: React.CSSProperties = {
  background: "#3a3",
  color: "#fff",
  border: "1px solid #4b4",
  borderRadius: 4,
  padding: "3px 10px",
  fontSize: 11,
  cursor: "pointer",
  fontWeight: 600,
};
