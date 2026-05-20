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

__all__ = [
    "process_nmea",
    "process_gpx",
    "process_kml",
    "render_visualizations",
    "render_comparison",
    "export_for_viewer",
]
