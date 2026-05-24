/**
 * RangeSelector -- UI fuer Cut-Range-Selektion (Trimming + Multi-Cut).
 *
 * Eigenschaften der UI
 * --------------------
 *   * Horizontale "Cut-Leiste" parallel zum TrackSlider darunter
 *   * Cut-Bars in Rot, mit Index-Label "Cut 1", "Cut 2", ...
 *     (sortiert nach Position auf dem Track, nicht nach Anlege-Reihenfolge).
 *   * Bei Cuts am Track-Anfang (start === 0) bzw. -Ende (end === N-1):
 *     Label-Wechsel zu "Trim Start" bzw. "Trim Ende" und der aeussere
 *     Drag-Handle entfaellt, weil dieser Rand fix am Track-Rand klebt.
 *   * Cuts duerfen sich NICHT ueberlappen (im Hook garantiert).
 *   * "+ Cut" deaktiviert, wenn es um die aktuelle Slider-Position herum
 *     keine Luecke mehr gibt.
 *   * "Reset" loescht alle Cuts; "Export" laedt ranges.json herunter.
 */

import { useCallback, useMemo, useRef, useState } from "react";
import type { CutRange, RangeSelectionApi } from "../hooks/useRangeSelection";

interface Props {
  totalPoints: number;
  activeIdx: number;
  api: RangeSelectionApi;
}

const TRACK_HEIGHT = 18;
const HANDLE_WIDTH = 10;

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
      label = `Cut ${cutCounter}`;
    }
    return { ...r, label, trimStart, trimEnd };
  });
}

// ---------------------------------------------------------------------------
// Hauptkomponente
// ---------------------------------------------------------------------------

export function RangeSelector({ totalPoints, activeIdx, api }: Props) {
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

  const handleExport = useCallback(() => {
    const payload = {
      total_points: totalPoints,
      cut_ranges: api.ranges.map((r) => ({ start: r.start, end: r.end })),
      created_at: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)],
                         { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "ranges.json";
    a.click();
    URL.revokeObjectURL(url);
  }, [api.ranges, totalPoints]);

  // Labelled + sortiert -- benutze ich sowohl unten als auch fuer die
  // Count-Anzeige rechts.
  const labelled = useMemo(
    () => classifyCuts(api.ranges, totalPoints),
    [api.ranges, totalPoints]
  );

  return (
    <div style={containerStyle}>
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
        {api.ranges.length > 0 && (
          <>
            <button onClick={api.clearAll} style={buttonStyle} title="Alle Cuts entfernen">
              Reset
            </button>
            <button onClick={handleExport} style={{ ...buttonStyle, background: "#3a3" }}
                    title="ranges.json herunterladen">
              Export
            </button>
          </>
        )}
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

  const startDrag = useCallback((side: "start" | "end") => (e: React.PointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    setDragging(side);
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging) return;
    const idx = xToIdx(e.clientX);
    if (dragging === "start") onMove(idx, range.end);
    else onMove(range.start, idx);
  }, [dragging, xToIdx, onMove, range.start, range.end]);

  const endDrag = useCallback((e: React.PointerEvent) => {
    if (!dragging) return;
    try { (e.target as HTMLElement).releasePointerCapture(e.pointerId); } catch { /* noop */ }
    setDragging(null);
  }, [dragging]);

  // Schraffur-Muster fuer Trim-Edges -- macht Edge-Cuts visuell klar von
  // Middle-Cuts unterscheidbar.
  const baseBackground = (trimStart || trimEnd)
    ? "repeating-linear-gradient(45deg, rgba(220,70,70,0.55) 0 6px, rgba(220,70,70,0.3) 6px 12px)"
    : "rgba(220, 70, 70, 0.45)";

  return (
    <div style={{
      position: "absolute",
      left: `${leftPct}%`,
      width: `${widthPct}%`,
      top: 0, bottom: 0,
      background: baseBackground,
      borderTop: "1px solid #c44",
      borderBottom: "1px solid #c44",
      pointerEvents: "none",
      overflow: "visible",
    }}>
      {/* Start-Handle -- nicht fuer Trim-Start (linke Kante klebt am Track-Start) */}
      {!trimStart && (
        <div
          onPointerDown={startDrag("start")}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          style={{
            ...handleStyle,
            left: -HANDLE_WIDTH / 2,
            background: dragging === "start" ? "#fff" : "#f55",
          }}
          title={`Start: ${range.start}`}
        />
      )}

      {/* End-Handle -- nicht fuer Trim-Ende */}
      {!trimEnd && (
        <div
          onPointerDown={startDrag("end")}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          style={{
            ...handleStyle,
            right: -HANDLE_WIDTH / 2,
            background: dragging === "end" ? "#fff" : "#f55",
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
        title={`${label} (${range.start}..${range.end})`}
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
  display: "flex", gap: 4, flexShrink: 0,
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
