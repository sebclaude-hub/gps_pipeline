import { useCallback, useEffect, useRef, useState } from "react";
import type { TrackData } from "../types";
import { formatTimestamp, formatSpeed, formatAltitude } from "../utils/formatters";

interface Props {
  track: TrackData;
  activeIdx: number;
  onChange: (idx: number) => void;
}

export function TrackSlider({ track, activeIdx, onChange }: Props) {
  const [playing, setPlaying] = useState(false);
  const rafRef = useRef<number | null>(null);
  const lastTickRef = useRef<number>(0);
  const n = track.points.lat.length;

  // Playback: ~30 Punkte/Sekunde
  const POINTS_PER_SEC = 30;

  const tick = useCallback((now: number) => {
    const elapsed = now - lastTickRef.current;
    if (elapsed >= 1000 / POINTS_PER_SEC) {
      lastTickRef.current = now;
      onChange(Math.min(activeIdx + 1, n - 1));
      if (activeIdx >= n - 1) {
        setPlaying(false);
        return;
      }
    }
    rafRef.current = requestAnimationFrame(tick);
  }, [activeIdx, n, onChange]);

  useEffect(() => {
    if (playing) {
      lastTickRef.current = performance.now();
      rafRef.current = requestAnimationFrame(tick);
    }
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [playing, tick]);

  const pts = track.points;
  const ts = pts.timestamp_ms[activeIdx];
  const speed = pts.speed_kmh[activeIdx];
  const alt = pts.alt[activeIdx];

  return (
    <div style={{
      padding: "8px 16px",
      background: "#111",
      borderTop: "1px solid #333",
      display: "flex",
      flexDirection: "column",
      gap: 4,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button
          onClick={() => {
            if (activeIdx >= n - 1) onChange(0);
            setPlaying((p) => !p);
          }}
          style={{
            background: "#333", color: "#eee", border: "none",
            borderRadius: 4, padding: "2px 10px", cursor: "pointer", fontSize: 16,
          }}
        >
          {playing ? "⏸" : "▶"}
        </button>
        <input
          type="range"
          min={0}
          max={n - 1}
          value={activeIdx}
          onChange={(e) => onChange(Number(e.target.value))}
          style={{ flex: 1, accentColor: "#7b61ff" }}
        />
        <span style={{ color: "#888", fontSize: 11, minWidth: 60, textAlign: "right" }}>
          {activeIdx + 1} / {n}
        </span>
      </div>
      <div style={{ display: "flex", gap: 20, color: "#aaa", fontSize: 12 }}>
        <span>⏱ {ts ? formatTimestamp(ts) : "–"}</span>
        <span>🚀 {formatSpeed(speed ?? null)}</span>
        <span>⛰ {formatAltitude(alt ?? null)}</span>
      </div>
    </div>
  );
}
