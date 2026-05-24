import { useState, useCallback } from "react";
import { useTrackData } from "./hooks/useTrackData";
import { useSatelliteData } from "./hooks/useSatelliteData";
import { useDemLod } from "./hooks/useDemLod";
import { useCharts } from "./hooks/useCharts";
import { TrackViewer } from "./components/TrackViewer";
import { SkyPlot } from "./components/SkyPlot";
import { TrackSlider } from "./components/TrackSlider";
import { ColorLegend } from "./components/ColorLegend";
import { ToggleSwitch } from "./components/ToggleSwitch";
import { ZScaleButtons } from "./components/ZScaleButtons";
import { InfoPanel } from "./components/InfoPanel";
import { InfoModeButtons, type InfoMode } from "./components/InfoModeButtons";
import { RangeSelector } from "./components/RangeSelector";
import { useRangeSelection } from "./hooks/useRangeSelection";
import type { ColorMode } from "./types";

type CurtainMode = "on" | "off";
type ChartsMode = "on" | "off";
const Z_OPTIONS = [1, 2, 3, 5, 7.5, 10];
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
  const [curtainMode, setCurtainMode] = useState<CurtainMode>("on");
  const [chartsMode, setChartsMode] = useState<ChartsMode>("on");
  const [zScale, setZScale] = useState<number>(3);
  // "both" als Default: Panel rechts UND Tooltip am Cursor. Wer es minimaler
  // mag, schaltet auf "panel" oder "tooltip" um.
  const [infoMode, setInfoMode] = useState<InfoMode>("both");

  const hasSat = track?.meta.has_satellites ?? false;
  const { data: satData } = useSatelliteData(hasSat);
  const { demLod } = useDemLod(zoom, DEM_LODS, DEM_PREFIX);
  // Karten-Overlays werden unabhaengig vom Track geladen. Wenn keine
  // charts.json existiert, kommt eine leere Liste zurueck (kein Fehler).
  const { charts } = useCharts();
  // Cut-Range-Auswahl fuer Trimming/Multi-Cut. Lebt im Top-Level-State,
  // damit z.B. Markierungen im Track-Plot spaeter darauf zugreifen koennen.
  const rangeApi = useRangeSelection();

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
            showCurtain={curtainMode === "on"}
            charts={charts}
            showCharts={chartsMode === "on"}
            zScale={zScale}
            onZoomChange={handleZoom}
            onPointPick={setActiveIdx}
            showTooltip={infoMode === "tooltip" || infoMode === "both"}
          />
          <div style={togglesStyle}>
            <ToggleSwitch<ColorMode>
              value={colorMode}
              options={["speed", "altitude"]}
              labels={["km/h", "Höhe"]}
              onChange={setColorMode}
              title="Farbgebung umschalten"
            />
            <ToggleSwitch<CurtainMode>
              value={curtainMode}
              options={["on", "off"]}
              labels={["Vorhang", "aus"]}
              onChange={setCurtainMode}
              title="Vorhang ein- oder ausblenden"
            />
            {/* Karten-Toggle nur einblenden, wenn ueberhaupt Overlays
                geladen wurden -- spart Platz im UI, wenn keine vorhanden sind. */}
            {charts.length > 0 && (
              <ToggleSwitch<ChartsMode>
                value={chartsMode}
                options={["on", "off"]}
                labels={[`Karten (${charts.length})`, "aus"]}
                onChange={setChartsMode}
                title="Karten-Overlays ein- oder ausblenden"
              />
            )}
            <InfoModeButtons value={infoMode} onChange={setInfoMode} />
            <ZScaleButtons value={zScale} options={Z_OPTIONS} onChange={setZScale} />
          </div>
          {/* Legende dynamisch positionieren: 12px Top + (Anzahl Toggle-Reihen
              * 36px Hoehe inkl. Gap). Charts-Toggle ist optional, InfoMode
              und ZScale immer da, plus zwei Top-Toggles. */}
          <ColorLegend
            breaks={track.quantile_breaks}
            colorMode={colorMode}
            topOffset={12 + (charts.length > 0 ? 5 : 4) * 36}
          />
        </div>

        {/* Side-Panel komplett ausblenden, wenn nichts darin steht
            (kein Skyplot + InfoMode === "tooltip"). Spart 300px Bildbreite
            fuer den Track. */}
        {(hasSat || infoMode !== "tooltip") && (
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
          {/* InfoPanel nur in den Modi "panel" und "both" anzeigen --
              im reinen "tooltip"-Modus erscheint die Info ausschliesslich
              schwebend am Cursor. */}
          {(infoMode === "panel" || infoMode === "both") && (
            <InfoPanel track={track} activeIdx={activeIdx} />
          )}
        </div>
        )}
      </div>

      <RangeSelector
        totalPoints={track.points.lat.length}
        activeIdx={activeIdx}
        api={rangeApi}
      />
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
const togglesStyle: React.CSSProperties = {
  position: "absolute", top: 12, right: 12,
  display: "flex", flexDirection: "column", gap: 8,
  zIndex: 10,
};
const centerStyle: React.CSSProperties = {
  display: "flex", width: "100vw", height: "100vh",
  alignItems: "center", justifyContent: "center", background: "#0d0d0d",
};
