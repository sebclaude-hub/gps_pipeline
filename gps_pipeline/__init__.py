"""gps_pipeline — Modulare Verarbeitung und Visualisierung von GPS-Tracks.

Siehe README.md für die Pipeline-Architektur und Beispiele.
"""

from .api import (
    process_nmea,
    process_gpx,
    process_kml,
    render_visualizations,
    render_comparison,
    export_for_viewer,
)
from .parsing.chart import ChartOverlay, find_charts
from .processing.trim import CutRange, trim_track, load_cut_ranges
from .processing.synthetic import (
    create_synthetic_track, save_synthetic, SyntheticMeta,
)

__all__ = [
    "process_nmea",
    "process_gpx",
    "process_kml",
    "render_visualizations",
    "render_comparison",
    "export_for_viewer",
    "ChartOverlay",
    "find_charts",
    "CutRange",
    "trim_track",
    "load_cut_ranges",
    "create_synthetic_track",
    "save_synthetic",
    "SyntheticMeta",
]
