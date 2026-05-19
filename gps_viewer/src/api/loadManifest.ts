import type { Manifest } from "../types";

export async function loadManifest(): Promise<Manifest> {
  const res = await fetch("/data/manifest.json");
  if (!res.ok) throw new Error(`manifest.json nicht gefunden (${res.status})`);
  return res.json();
}
