/**
 * InfoPanel: zeigt Messwerte des aktuell aktiven Track-Punktes.
 */
import type { TrackData } from "../types";
import { formatSpeed, formatAltitude, formatTimestamp } from "../utils/formatters";

const FIX_LABELS: Record<number, string> = {
  0: "Kein Fix",
  1: "GPS",
  2: "DGPS",
  3: "PPS",
  4: "RTK Fix",
  5: "RTK Float",
  6: "Geschätzt",
  7: "Manuell",
  8: "Simuliert",
};

interface Props {
  track: TrackData;
  activeIdx: number;
}

export function InfoPanel({ track, activeIdx }: Props) {
  const pts = track.points;
  const idx = Math.max(0, Math.min(activeIdx, pts.lat.length - 1));

  const lat       = pts.lat[idx];
  const lon       = pts.lon[idx];
  const alt       = pts.alt[idx] ?? null;
  const above     = pts.above_terrain?.[idx] ?? null;
  const speed     = pts.speed_kmh[idx] ?? null;
  const ts        = pts.timestamp_ms[idx];
  const fix       = pts.fix_quality?.[idx] ?? null;
  const numSats   = pts.num_sats?.[idx] ?? null;
  const hdop      = pts.hdop?.[idx] ?? null;
  const vdop      = pts.vdop?.[idx] ?? null;
  const total     = pts.lat.length;

  return (
    <div style={panelStyle}>
      <div style={titleStyle}>Punkt-Info</div>
      <table style={tableStyle}>
        <tbody>
          <Row label="Punkt #"  value={`${idx + 1} / ${total}`} />
          <Row label="Zeit"     value={ts ? formatTimestamp(ts) : "–"} />
          <Row label="Position" value={
            lat !== null && lon !== null
              ? `${lat.toFixed(6)}° N\n${lon.toFixed(6)}° E`
              : "–"
          } multiline />
          <Row label="Höhe MSL"    value={formatAltitude(alt)} />
          <Row label="Höhe ü.Grd"  value={above !== null ? `${above.toFixed(0)} m` : "–"} />
          <Row label="Geschw."     value={formatSpeed(speed)} />
          <RowDivider />
          <Row label="Fix"         value={fix !== null ? (FIX_LABELS[fix] ?? `${fix}`) : "–"} />
          <Row label="Satelliten"  value={numSats !== null ? `${numSats}` : "–"} />
          <Row label="HDOP"        value={hdop !== null ? hdop.toFixed(1) : "–"} />
          <Row label="VDOP"        value={vdop !== null ? vdop.toFixed(1) : "–"} />
        </tbody>
      </table>
    </div>
  );
}

function Row({ label, value, multiline }: {
  label: string;
  value: string;
  multiline?: boolean;
}) {
  return (
    <tr>
      <td style={labelStyle}>{label}</td>
      <td style={valueStyle}>
        {multiline
          ? value.split("\n").map((line, i) => <div key={i}>{line}</div>)
          : value}
      </td>
    </tr>
  );
}

function RowDivider() {
  return (
    <tr>
      <td colSpan={2} style={{ borderTop: "1px solid #2a2a2a", padding: "3px 0" }} />
    </tr>
  );
}

const panelStyle: React.CSSProperties = {
  width: "100%",
  marginTop: 16,
  borderTop: "1px solid #2a2a2a",
  paddingTop: 12,
};
const titleStyle: React.CSSProperties = {
  color: "#888",
  fontSize: 11,
  marginBottom: 8,
};
const tableStyle: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: 12,
};
const labelStyle: React.CSSProperties = {
  color: "#666",
  paddingRight: 8,
  paddingBottom: 4,
  verticalAlign: "top",
  whiteSpace: "nowrap",
  width: "50%",
};
const valueStyle: React.CSSProperties = {
  color: "#ccc",
  paddingBottom: 4,
  verticalAlign: "top",
};
