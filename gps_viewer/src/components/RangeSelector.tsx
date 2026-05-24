/**
 * RangeSelector -- UI fuer Cut-Range-Selektion (Trimming + Multi-Cut).
 *
 * Layout
 * ------
 * Sitzt ueber dem TrackSlider und besteht aus:
 *   * Einer horizontalen Track-Leiste (gleiche Breite wie der Slider darunter),
 *     auf der die Cut-Ranges als rote, halbtransparente Balken liegen.
 *   * Pro Range zwei Drag-Handles (Start und Ende), die die Range-Grenzen
 *     verschieben.
 *   * Buttons:
 *       - "+ Cut" fuegt einen neuen Range um die aktuelle Slider-Position herum ein.
 *       - "Reset" loescht alle Ranges.
 *       - "Export Ranges" laedt eine ranges.json mit den Cut-Definitionen herunter.
 *
 * Interaktion
 * -----------
 *   * Klick auf einen Handle + Drag verschiebt die Grenze.
 *   * Klick auf den X-Button entfernt den Range.
 *   * Klick auf den roten Balken (zwischen den Handles) tut nichts (passive
 *     Anzeige) -- der Active-Slider darunter bleibt bedienbar.
 *
 * Pixel-Mapping: ``pxPerPoint = trackWidthPx / (n - 1)``. Der Handle-Index
 * wird waehrend des Drags aus ``clientX`` zurueckgerechnet.
 */

import { useCallback, useRef, useState } from "react";
import type { CutRange, RangeSelectionApi } from "../hooks/useRangeSelection";

interface Props {
  totalPoints: number;
  activeIdx: number;
  api: RangeSelectionApi;
}

const TRACK_HEIGHT = 18;
const HANDLE_WIDTH = 10;

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

  return (
    <div style={containerStyle}>
      <div style={leftCtrlsStyle}>
        <button onClick={handleAdd} style={buttonStyle} title="Cut-Range um aktuelle Slider-Position einfuegen">
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
        {api.ranges.map((r) => (
          <RangeBar
            key={r.id}
            range={r}
            totalPoints={totalPoints}
            onMove={(start, end) => api.updateRange(r.id, { start, end }, totalPoints)}
            onRemove={() => api.removeRange(r.id)}
            xToIdx={xToIdx}
          />
        ))}
      </div>

      <div style={countStyle}>
        {api.ranges.length === 0
          ? <span style={{ color: "#555" }}>keine Cuts</span>
          : <span>{api.ranges.length} Cut{api.ranges.length > 1 ? "s" : ""}</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// RangeBar: ein einzelner Cut-Range mit zwei Drag-Handles
// ---------------------------------------------------------------------------

interface RangeBarProps {
  range: CutRange;
  totalPoints: number;
  onMove: (start: number, end: number) => void;
  onRemove: () => void;
  xToIdx: (clientX: number) => number;
}

function RangeBar({ range, totalPoints, onMove, onRemove, xToIdx }: RangeBarProps) {
  // Drag-State: welche Seite wird gerade gezogen, und der "andere" feste Wert
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
    try { (e.target as HTMLElement).releasePointerCapture(e.pointerId); } catch {}
    setDragging(null);
  }, [dragging]);

  return (
    <div style={{
      position: "absolute",
      left: `${leftPct}%`,
      width: `${widthPct}%`,
      top: 0, bottom: 0,
      background: "rgba(220, 70, 70, 0.45)",
      borderTop: "1px solid #c44",
      borderBottom: "1px solid #c44",
      pointerEvents: "none",
    }}>
      {/* Start-Handle (linke Kante) */}
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
      {/* End-Handle (rechte Kante) */}
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
