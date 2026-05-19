import type { DemLod } from "../types";

export async function loadDemLod(
  lodIndex: number,
  prefix: string
): Promise<DemLod | null> {
  const url = `/data/${prefix}_dem_lod${lodIndex}.json`;
  const res = await fetch(url);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`dem_lod${lodIndex}.json Fehler (${res.status})`);
  return res.json();
}
