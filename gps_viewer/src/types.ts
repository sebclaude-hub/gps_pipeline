// ---------------------------------------------------------------------------
// Gemeinsame TypeScript-Typen für den GPS-Track-Viewer
// ---------------------------------------------------------------------------

export interface TrackBounds {
  lon_min: number;
  lat_min: number;
  lon_max: number;
  lat_max: number;
}

export interface TrackMeta {
  name: string;
  source_type: "nmea" | "gpx" | "kml" | "igc";
  n_points: number;
  total_distance_m: number;
  duration_s: number;
  timestamp_start_utc: string | null;
  timestamp_end_utc: string | null;
  bounds: TrackBounds;
  track_mode: "flight" | "ground";
  has_terrain: boolean;
  has_satellites: boolean;
  /** Default-Wert des Hoehen-Offset-Sliders. Kommt aus der
   *  Schnittanweisung (``z_offset_m``) oder ist 0. */
  suggested_z_offset_m?: number;
  /** Dateiname (mit Endung) der Quelldatei. Wird vom Viewer in die
   *  ``<source>.cuts.json`` geschrieben, die beim Export gespeichert wird. */
  source_file?: string | null;
  /** Legacy-Feld -- frueher fuer das DerivationBanner verwendet. Wird
   *  vom aktuellen Frontend ignoriert (Synthetic-Warnung erscheint
   *  punktgenau im InfoPanel). Bleibt im Type, damit aeltere track.json
   *  ohne Warnung gelesen werden koennen. */
  derivation?: unknown;
}

export interface QuantileBreaks {
  speed_kmh: number[];
  altitude_m: number[];
  /** Hoehe ueber Grund (AGL) — fuer "altitude_gnd". Optional (aeltere JSON). */
  altitude_gnd_m?: number[];
  /** Spezifische Energiehoehe — fuer "energy". Optional (aeltere JSON). */
  energy_height_m?: number[];
  n_quantiles: number;
}

export type ColorMode =
  | "speed"
  | "altitude"
  | "altitude_gnd"
  | "flight"
  | "drone"
  | "accel"
  | "energy"
  | "energy_rate";

export interface TrackPoints {
  lat: number[];
  lon: number[];
  alt: (number | null)[];
  terrain_elev: (number | null)[];
  above_terrain: (number | null)[];
  speed_kmh: (number | null)[];
  distance_m: (number | null)[];
  // Abgeleitete Groessen aus der Pipeline (Python). Optional → aeltere
  // track.json ohne diese Felder bleiben ladbar (Modi dann ausgegraut).
  accel_mps2?: (number | null)[];
  energy_height_m?: (number | null)[];
  energy_rate_mps?: (number | null)[];
  // G-Vektor-Zerlegung (ENU): Laengs/Quer/Vertikal + Heading-Einheitsvektor.
  accel_long_mps2?: (number | null)[];
  accel_lateral_mps2?: (number | null)[];
  accel_vertical_mps2?: (number | null)[];
  accel_heading_e?: (number | null)[];
  accel_heading_n?: (number | null)[];
  timestamp_ms: number[];
  speed_q_idx: number[];
  alt_q_idx: number[];
  // Diagnosefelder (optional — null wenn Empfänger sie nicht liefert)
  fix_quality?: (number | null)[];
  num_sats?: (number | null)[];
  hdop?: (number | null)[];
  vdop?: (number | null)[];
  /** True wenn der Timestamp dieses Punktes durch einen synthetic-Cut
   *  verschoben wurde. Pro-Punkt-Warnung im InfoPanel. */
  is_synthetic?: boolean[];
}

export interface TrackData {
  meta: TrackMeta;
  quantile_breaks: QuantileBreaks;
  points: TrackPoints;
  /** Robuste symmetrische Skalen der signierten Groessen (Pipeline-gerechnet);
   *  der Viewer normiert raw/scale → [−1,1]. Optional (aeltere JSON). */
  scales?: { accel_mps2: number; energy_rate_mps: number; gvec_mps2?: number };
}

// ---------------------------------------------------------------------------
// DEM-LOD
// ---------------------------------------------------------------------------

export interface DemGrid {
  n_rows: number;
  n_cols: number;
  lat_min: number;
  lat_max: number;
  lon_min: number;
  lon_max: number;
  elevations: (number | null)[];
}

export interface DemLod {
  lod: number;
  bounds: TrackBounds;
  grid: DemGrid;
}

// ---------------------------------------------------------------------------
// Satelliten-Daten
// ---------------------------------------------------------------------------

// Satellit: [prn, elevation_deg, azimuth_deg, snr] — null = fehlend
export type SatRow = [number | null, number | null, number | null, number | null];

export interface GsvBurst {
  ts_ms: number;
  sats: SatRow[];
}

export interface SatelliteData {
  talkers: string[];
  bursts_by_talker: Record<string, GsvBurst[]>;
  burst_idx_by_track: Record<string, number[]>;
}

// ---------------------------------------------------------------------------
// Manifest
// ---------------------------------------------------------------------------

export interface Manifest {
  track: string;
  satellites: string | null;
  dem_lods: number[];
  dem_prefix: string;
  /** Pfad zu charts.json oder null, wenn keine Karten-Overlays exportiert wurden. */
  charts?: string | null;
  viewer_version: string;
}

// ---------------------------------------------------------------------------
// Viewer-State
// ---------------------------------------------------------------------------

export interface ViewState {
  longitude: number;
  latitude: number;
  zoom: number;
  pitch: number;
  bearing: number;
  minZoom?: number;
  maxZoom?: number;
}
