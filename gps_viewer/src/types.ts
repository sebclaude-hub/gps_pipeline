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
  source_type: "nmea" | "gpx" | "kml";
  n_points: number;
  total_distance_m: number;
  duration_s: number;
  timestamp_start_utc: string | null;
  timestamp_end_utc: string | null;
  bounds: TrackBounds;
  track_mode: "flight" | "ground";
  has_terrain: boolean;
  has_satellites: boolean;
}

export interface QuantileBreaks {
  speed_kmh: number[];
  n_quantiles: number;
}

export interface TrackPoints {
  lat: number[];
  lon: number[];
  alt: (number | null)[];
  terrain_elev: (number | null)[];
  above_terrain: (number | null)[];
  speed_kmh: (number | null)[];
  distance_m: (number | null)[];
  timestamp_ms: number[];
  speed_q_idx: number[];
  // Diagnosefelder (optional — null wenn Empfänger sie nicht liefert)
  fix_quality?: (number | null)[];
  num_sats?: (number | null)[];
  hdop?: (number | null)[];
  vdop?: (number | null)[];
}

export interface TrackData {
  meta: TrackMeta;
  quantile_breaks: QuantileBreaks;
  points: TrackPoints;
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
