/**
 * useCharts -- laedt Karten-Overlay-Manifest + alle PNGs nebenlaeufig.
 *
 * Lifecycle:
 *   1. Manifest holen (charts.json). Wenn 404 oder leere Liste: nichts tun.
 *   2. Fuer jedes Overlay parallel das PNG laden.
 *   3. State: ``ready`` mit allen geladenen Bildern, oder ``error``.
 *
 * Wir laden alle Bilder gleichzeitig (Promise.all). Bei wenigen Overlays
 * ist das schneller als sequentielles Laden; bei sehr vielen wuerde man auf
 * Lazy-Loading umstellen. Realistisches Limit: ~20 Karten.
 */

import { useEffect, useState } from "react";
import { loadChartsManifest, loadChartImage } from "../api/loadCharts";
import type { ChartOverlay } from "../utils/chartMesh";

export interface LoadedChart {
  overlay: ChartOverlay;
  image: HTMLImageElement;
}

interface State {
  charts: LoadedChart[];
  loading: boolean;
  error: string | null;
}

export function useCharts(): State {
  const [charts, setCharts] = useState<LoadedChart[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    loadChartsManifest()
      .then(async (overlays) => {
        if (overlays.length === 0) {
          if (!cancelled) {
            setCharts([]);
            setLoading(false);
          }
          return;
        }

        // Bilder parallel laden, einzelne Fehler tolerieren -- ein kaputtes
        // PNG soll nicht die anderen Overlays blockieren.
        const results = await Promise.allSettled(
          overlays.map(async (overlay) => {
            const image = await loadChartImage(overlay.image);
            return { overlay, image };
          })
        );

        if (cancelled) return;

        const ready: LoadedChart[] = [];
        for (const r of results) {
          if (r.status === "fulfilled") ready.push(r.value);
          else console.warn("Chart-Load:", r.reason);
        }

        setCharts(ready);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(String(err));
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, []);

  return { charts, loading, error };
}
