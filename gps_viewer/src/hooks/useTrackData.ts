import { useState, useEffect } from "react";
import { loadTrack } from "../api/loadTrack";
import type { TrackData } from "../types";

interface State {
  data: TrackData | null;
  loading: boolean;
  error: string | null;
}

export function useTrackData(): State {
  const [state, setState] = useState<State>({
    data: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    loadTrack()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: null });
      })
      .catch((err) => {
        if (!cancelled)
          setState({ data: null, loading: false, error: String(err) });
      });
    return () => { cancelled = true; };
  }, []);

  return state;
}
