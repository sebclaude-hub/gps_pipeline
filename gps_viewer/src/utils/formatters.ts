/** Hilfsfunktionen für Anzeige-Formatierung */

export function formatSpeed(kmh: number | null): string {
  if (kmh === null || kmh === undefined) return "–";
  return `${kmh.toFixed(1)} km/h`;
}

export function formatAltitude(m: number | null): string {
  if (m === null || m === undefined) return "–";
  return `${Math.round(m)} m`;
}

export function formatDistance(m: number | null): string {
  if (m === null || m === undefined) return "–";
  if (m >= 1000) return `${(m / 1000).toFixed(2)} km`;
  return `${Math.round(m)} m`;
}

export function formatDuration(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  if (h > 0) return `${h}h ${m}min`;
  if (m > 0) return `${m}min ${sec}s`;
  return `${sec}s`;
}

export function formatTimestamp(ms: number): string {
  const d = new Date(ms);
  return d.toUTCString().replace("GMT", "UTC");
}
