import type { TrackData } from "../types";

export async function loadTrack(): Promise<TrackData> {
  const res = await fetch("/data/track.json");
  if (!res.ok) throw new Error(`track.json nicht gefunden (${res.status})`);
  return res.json();
}
