import { useState, useEffect, useTransition } from "react";
import { loadDemLod } from "../api/loadDemLod";
import type { DemLod } from "../types";

// deck.gl Zoom → LOD-Index
// Zoom < 8:  LOD 2 (200 m/px, grob)
// Zoom 8–11: LOD 1 (50 m/px, mittel)
// Zoom > 11: LOD 0 (10 m/px, fein)
function zoomToLod(zoom: number, availableLods: number[]): number {
  let wanted: number;
  if (zoom > 11) wanted = 0;
  else if (zoom >= 8) wanted = 1;
  else wanted = 2;

  // Feinste verfügbare LOD-Stufe ≥ wanted
  const candidates = availableLods.filter((l) => l >= wanted);
  if (candidates.length > 0) return Math.min(...candidates);
  // Fallback: gröbste verfügbare
  return Math.max(...availableLods);
}

interface State {
  demLod: DemLod | null;
  activeLod: number | null;
  loading: boolean;
}

export function useDemLod(
  zoom: number,
  availableLods: number[],
  demPrefix: string
): State {
  const [loadedLods, setLoadedLods] = useState<Map<number, DemLod>>(new Map());
  const [activeLod, setActiveLod] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [, startTransition] = useTransition();

  useEffect(() => {
    if (availableLods.length === 0) return;
    const wanted = zoomToLod(zoom, availableLods);
    if (loadedLods.has(wanted)) {
      startTransition(() => setActiveLod(wanted));
      return;
    }

    let cancelled = false;
    setLoading(true);
    loadDemLod(wanted, demPrefix)
      .then((lod) => {
        if (cancelled || !lod) return;
        setLoadedLods((prev) => new Map(prev).set(wanted, lod));
        startTransition(() => {
          setActiveLod(wanted);
          setLoading(false);
        });
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [zoom, availableLods, demPrefix]);

  const demLod = activeLod !== null ? (loadedLods.get(activeLod) ?? null) : null;
  return { demLod, activeLod, loading };
}
