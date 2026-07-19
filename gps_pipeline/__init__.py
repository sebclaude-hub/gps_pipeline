"""gps_pipeline — Modulare Verarbeitung und Visualisierung von GPS-Tracks.

Siehe README.md für die Pipeline-Architektur und Beispiele.
"""

from .api import (
    process_nmea,
    process_gpx,
    process_kml,
    process_igc,
    render_visualizations,
    render_comparison,
    export_for_viewer,
    apply_sidecar_cuts,
)
from .parsing.chart import ChartOverlay, find_charts
from .parsing.cut_config import (
    CutSpec, CutConfig, load_cut_config, find_cut_config,
)
from .processing.apply_cut_config import apply_cut_config
from .processing.merge import MergeResult, merge_tracks
from .export.gpx_export import write_gpx

__all__ = [
    "process_nmea",
    "process_gpx",
    "process_kml",
    "process_igc",
    "render_visualizations",
    "render_comparison",
    "export_for_viewer",
    "apply_sidecar_cuts",
    "ChartOverlay",
    "find_charts",
    "CutSpec",
    "CutConfig",
    "load_cut_config",
    "find_cut_config",
    "apply_cut_config",
    "MergeResult",
    "merge_tracks",
    "write_gpx",
]
