import type { SatelliteData } from "../types";

export async function loadSatellites(): Promise<SatelliteData | null> {
  const res = await fetch("/data/satellites.json");
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`satellites.json Fehler (${res.status})`);
  return res.json();
}
