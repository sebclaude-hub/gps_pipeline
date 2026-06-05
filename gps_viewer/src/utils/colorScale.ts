// ---------------------------------------------------------------------------
// Werte + Quantilgrenzen fuer den aktiven (vorzeichenlosen) Farbmodus an EINER
// Stelle waehlen, damit Track-Faerbung (TrackViewer) und Legende (ColorLegend)
// dieselbe Skala nutzen.
//
// WICHTIG: Hier wird NICHTS gerechnet — alle Werte und Grenzen kommen fertig
// aus der Python-Pipeline (track.json). Der Viewer mappt sie nur auf Farbe.
// ---------------------------------------------------------------------------

import type { ColorMode, TrackData } from "../types";

export interface ColorScale {
  values: (number | null)[];
  breaks: number[];
}

export function colorScaleFor(track: TrackData, mode: ColorMode): ColorScale {
  const qb = track.quantile_breaks;
  switch (mode) {
    case "altitude":
      return { values: track.points.alt, breaks: qb.altitude_m };
    case "altitude_gnd":
      return { values: track.points.above_terrain, breaks: qb.altitude_gnd_m ?? [] };
    case "energy":
      return { values: track.points.energy_height_m ?? [], breaks: qb.energy_height_m ?? [] };
    default:
      // speed (auch fuer flight/drone/accel/energy_rate, die ihre Faerbung
      // separat regeln) → Speed-Skala.
      return { values: track.points.speed_kmh, breaks: qb.speed_kmh };
  }
}
