import { useState, useEffect } from "react";
import { loadSatellites } from "../api/loadSatellites";
import type { SatelliteData } from "../types";

interface State {
  data: SatelliteData | null;
  loading: boolean;
}

export function useSatelliteData(enabled: boolean): State {
  const [state, setState] = useState<State>({ data: null, loading: false });

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setState((s) => ({ ...s, loading: true }));
    loadSatellites()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false });
      })
      .catch(() => {
        if (!cancelled) setState({ data: null, loading: false });
      });
    return () => { cancelled = true; };
  }, [enabled]);

  return state;
}
