import { useState, useCallback } from "react";
import { useTrackData } from "./hooks/useTrackData";
import { useSatelliteData } from "./hooks/useSatelliteData";
import { useDemLod } from "./hooks/useDemLod";
import { TrackViewer } from "./components/TrackViewer";
import { SkyPlot } from "./components/SkyPlot";
import { TrackSlider } from "./components/TrackSlider";
import { ColorLegend } from "./components/ColorLegend";
import { ColorModeToggle } from "./components/ColorModeToggle";
import { InfoPanel } from "./components/InfoPanel";
import type { ColorMode } from "./types";
import { formatDuration, formatDistance } from "./utils/formatters";

// Manifest-Daten werden von view.py als inline-Script injiziert
declare global {
  interface Window {
    __GPS_MANIFEST__?: {
      dem_lods: number[];
      dem_prefix: string;
    };
  }
}

const DEM_LODS: number[] = window.__GPS_MANIFEST__?.dem_lods ?? [];
const DEM_PREFIX: string = window.__GPS_MANIFEST__?.dem_prefix ?? "track";

export default function App() {
  const { data: track, loading: trackLoading, error } = useTrackData();
  const [activeIdx, setActiveIdx] = useState(0);
  const [zoom, setZoom] = useState(10);
  const [colorMode, setColorMode] = useState<ColorMode>("speed");

  const hasSat = track?.meta.has_satellites ?? false;
  const { data: satData } = useSatelliteData(hasSat);
  const { demLod } = useDemLod(zoom, DEM_LODS, DEM_PREFIX);

  const handleZoom = useCallback((z: number) => setZoom(z), []);

  if (trackLoading) {
    return (
      <div style={centerStyle}>
        <div style={{ color: "#888", fontSize: 16 }}>Track wird geladen…</div>
      </div>
    );
  }
  if (error || !track) {
    return (
      <div style={centerStyle}>
        <div style={{ color: "#f88", fontSize: 14 }}>
          Fehler: {error ?? "track.json nicht gefunden"}<br />
          <span style={{ color: "#666", fontSize: 12 }}>
            Starte den Viewer mit <code>python view.py</code>
          </span>
        </div>
      </div>
    );
  }

  const meta = track.meta;

  return (
    <div style={rootStyle}>
      <div style={headerStyle}>
        <span style={{ fontWeight: 600, fontSize: 15 }}>{meta.name}</span>
        <span style={{ color: "#888", fontSize: 12 }}>
          {meta.source_type.toUpperCase()} ·{" "}
          {formatDistance(meta.total_distance_m)} ·{" "}
          {formatDuration(meta.duration_s)} ·{" "}
          {meta.track_mode === "flight" ? "✈ Flug" : "🚗 Boden"}
          {meta.has_terrain && " · Terrain"}
        </span>
      </div>

      <div style={contentStyle}>
        <div style={{ flex: 1, position: "relative", minWidth: 0 }}>
          <TrackViewer
            track={track}
            dem={demLod}
            activeIdx={activeIdx}
            colorMode={colorMode}
            onZoomChange={handleZoom}
          />
          <ColorModeToggle value={colorMode} onChange={setColorMode} />
          <ColorLegend breaks={track.quantile_breaks} colorMode={colorMode} />
        </div>

        <div style={sidePanelStyle}>
          {hasSat && (
            <>
              <div style={{ color: "#888", fontSize: 11, marginBottom: 6 }}>
                Satellitenkonstellation
              </div>
              <SkyPlot satData={satData} trackIdx={activeIdx} />
              {satData && (
                <div style={{ color: "#556", fontSize: 10, marginTop: 4 }}>
                  {satData.talkers.join(" / ")}
                </div>
              )}
            </>
          )}
          <InfoPanel track={track} activeIdx={activeIdx} />
        </div>
      </div>

      <TrackSlider
        track={track}
        activeIdx={activeIdx}
        onChange={setActiveIdx}
      />
    </div>
  );
}

const rootStyle: React.CSSProperties = {
  display: "flex", flexDirection: "column",
  width: "100vw", height: "100vh",
  background: "#0d0d0d", color: "#eee",
  fontFamily: "system-ui, sans-serif", overflow: "hidden",
};
const headerStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 16,
  padding: "6px 16px", background: "#181818",
  borderBottom: "1px solid #2a2a2a", flexShrink: 0,
};
const contentStyle: React.CSSProperties = {
  display: "flex", flex: 1, minHeight: 0, overflow: "hidden",
};
const sidePanelStyle: React.CSSProperties = {
  width: 300, flexShrink: 0, background: "#111",
  borderLeft: "1px solid #2a2a2a", padding: 16,
  display: "flex", flexDirection: "column", alignItems: "center",
  overflowY: "auto",
};
const centerStyle: React.CSSProperties = {
  display: "flex", width: "100vw", height: "100vh",
  alignItems: "center", justifyContent: "center", background: "#0d0d0d",
};
