"""Zentrale Konfiguration und Defaults für die GPS-Track-Pipeline.

Alle einstellbaren Werte werden hier gesammelt. Module greifen entweder
direkt darauf zu oder referenzieren sie als Default in Funktionssignaturen.
"""

# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

# GGA-Fix-Qualitäten, die als unbrauchbar verworfen werden:
#   0 = Invalid / kein Fix
#   5 = Float RTK (für viele Anwendungen zu ungenau)
EXCLUDE_GGA_QUALITIES = [0, 5]

# GSA-Fix-Typ 1 = "no fix", wird entfernt
EXCLUDE_GSA_FIX_TYPES = [1]


# ---------------------------------------------------------------------------
# GGA/RMC-Konsistenzprüfung
# ---------------------------------------------------------------------------

# Toleranzen für den Mismatch-Check zwischen GGA und zeitnahem RMC.
# Position in Grad; bei 50° N entspricht 1e-6° ≈ 7 cm.
POSITION_MISMATCH_TOLERANCE_DEG = 1e-6

# Zeit-Mismatch wird als Bool berechnet (timestamp identisch?), keine Toleranz.


# ---------------------------------------------------------------------------
# Visualisierung 3D
# ---------------------------------------------------------------------------

DEFAULT_QUANTILES = 5
DEFAULT_COLORSCALE = "Plasma"
AVAILABLE_COLORSCALES = ["Plasma", "Viridis", "Cividis", "Turbo", "Inferno"]

# Z-Achsen-Überhöhung als ehrlicher Multiplikator. 1.0 = maßstabstreu
# (1 m Höhe sieht aus wie 1 m horizontal). Bei den meisten GPS-Tracks ist
# das visuell zu zurückhaltend — Auto/Rad braucht 20–50, Bergtour 5–10,
# Flug 1–3 (echte Höhe schon dominant).
DEFAULT_Z_EXAGGERATION = 1.0


# ---------------------------------------------------------------------------
# Terrain (DEM + Satellitentextur)
# ---------------------------------------------------------------------------

DEFAULT_TILE_ZOOM = 15
MAX_TILES_WARNING = 100  # ab dieser Anzahl Tiles wird gewarnt

# ArcGIS World Imagery — kostenlos für nicht-kommerzielle Nutzung.
# Reihenfolge: bei Ausfall der ersten URL wird die zweite probiert.
SATELLITE_TILE_URLS = [
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
]


# ---------------------------------------------------------------------------
# Diagnose
# ---------------------------------------------------------------------------

VERBOSE_QUANTILE_DEBUG = False  # Ausführliche Quantil-Verteilungs-Prints


# ---------------------------------------------------------------------------
# DEM (Höhenmodell)
# ---------------------------------------------------------------------------

# Sigma für Gaussian-Smoothing des DEMs (in Pixel-Einheiten).
# Reduziert Zackigkeit, die in DSMs (Digital Surface Models) durch
# Gebäudekanten und Vegetation entsteht.
#   0 oder None    — Glättung deaktiviert, Originalwerte unverändert
#   1.0            — sehr leichtes Smoothing (Default), kaum sichtbar
#   2.0–3.0        — deutlich geglättet, gut für stark verbaute Bereiche
#   > 5            — sehr starke Glättung, kann markante Höhenmerkmale verlieren
DEM_SMOOTH = 1.0

# Ziel-Pixelgröße in Metern für die DEM-Visualisierung.
# Bei feineren DEMs wird downsampled; bei gröberen bleibt die DEM-eigene
# Auflösung erhalten (keine künstliche Interpolation).
DEM_TARGET_PIXEL_SIZE_M = 50

# Harte Obergrenze pro Achse — Schutz vor Browser-Crashes bei großen Bereichen.
# Plotly verträgt ~2000×2000 noch gut. Bei riesigen Tracks (kontinental)
# wird die effektive Auflösung dadurch beschränkt.
DEM_MAX_PIXELS_PER_AXIS = 2000

# Obergrenze für die geschätzte HTML-Dateigröße in Megabyte. Wird die
# Schätzung überschritten, reduziert der Code die DEM-Auflösung automatisch
# und gibt eine Warnung aus. Auf schwachen Systemen ggf. herabsetzen,
# auf starken Systemen kann man bis ~200 hochziehen.
DEM_MAX_HTML_MB = 100

# (Auto-Offset-Diagnose wurde entfernt -- der React-Viewer bringt einen
# interaktiven Z-Offset-Slider mit, und Schnittanweisungen koennen einen
# vorgeschlagenen Offset mitliefern. Wer den Plotly-HTML-Pfad nutzt und
# einen Offset braucht, gibt ihn explizit per Parameter an
# render_visualizations / visualize_3d.)
