"""Parser fuer Karten-Overlays (PNG + TXT mit Eckkoordinaten).

Format der .txt-Datei
---------------------
Vier Zeilen mit ``lon lat`` (WGS84, Dezimalgrad) in dieser Reihenfolge:

    1. links oben     (top-left)
    2. rechts oben    (top-right)
    3. links unten    (bottom-left)
    4. rechts unten   (bottom-right)

Zusaetzlich koennen Metadaten als ``key: value`` angegeben werden,
z.B. ``elevation_m: 220`` als Hoehenreferenz (optional, Default 0).

Leerzeilen und Kommentarzeilen (``#``) werden ignoriert.

Beispiel
--------
::

    # EDFG Anflugkarte
    8.5321  50.1234
    8.5489  50.1234
    8.5321  50.1098
    8.5489  50.1098
    elevation_m: 220

Disambiguierung
---------------
Eine .txt-Datei wird nur dann als Karten-Konfig erkannt, wenn neben ihr
eine gleichnamige .png liegt. Andernfalls bleibt sie ein NMEA-Logfile.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ChartOverlay:
    """Eine Karten-Overlay-Definition (PNG + Georeferenzierung)."""

    name: str
    """Anzeigename (= Dateiname ohne Endung)."""

    png_path: Path
    """Pfad zur PNG-Bilddatei."""

    # Vier Ecken im Uhrzeigersinn von oben-links aus.
    # Jeweils [lon, lat] in WGS84 Dezimalgrad.
    corner_tl: tuple[float, float]
    corner_tr: tuple[float, float]
    corner_bl: tuple[float, float]
    corner_br: tuple[float, float]

    elevation_m: float = 0.0
    """Hoehenreferenz in m. Wird nur als Fallback verwendet, wenn kein DEM
    vorhanden ist; mit DEM wird die Karte auf das Gelaende gedrapt."""

    def bounds(self) -> tuple[float, float, float, float]:
        """(lon_min, lat_min, lon_max, lat_max) ueber alle vier Ecken."""
        lons = [self.corner_tl[0], self.corner_tr[0],
                self.corner_bl[0], self.corner_br[0]]
        lats = [self.corner_tl[1], self.corner_tr[1],
                self.corner_bl[1], self.corner_br[1]]
        return (min(lons), min(lats), max(lons), max(lats))


def parse_chart_txt(path: Path) -> Optional[ChartOverlay]:
    """Liest eine .txt-Datei und gibt eine ChartOverlay-Instanz zurueck.

    Returns ``None`` wenn die Datei nicht das Karten-Konfig-Format hat
    (zu wenige Koordinatenzeilen oder Parse-Fehler).
    Diese tolerante Rueckgabe ist wichtig, weil im data/-Ordner auch
    NMEA-Logs als .txt liegen koennen.
    """
    path = Path(path)
    png_path = path.with_suffix(".png")
    if not png_path.is_file():
        # Keine zugehoerige PNG -> ist keine Karten-Konfig.
        return None

    corners: list[tuple[float, float]] = []
    metadata: dict[str, str] = {}

    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            # Metadaten "key: value"
            if ":" in line:
                key, _, value = line.partition(":")
                metadata[key.strip().lower()] = value.strip()
                continue

            # Koordinate "lon lat" oder "lon, lat"
            tokens = line.replace(",", " ").split()
            if len(tokens) < 2:
                continue
            try:
                lon = float(tokens[0])
                lat = float(tokens[1])
            except ValueError:
                # Nicht-numerische Tokens -> wahrscheinlich keine Karte
                return None
            corners.append((lon, lat))
    except OSError:
        return None

    if len(corners) < 4:
        return None
    # Nur die ersten vier Koordinaten beachten.
    tl, tr, bl, br = corners[:4]

    elevation_m = 0.0
    if "elevation_m" in metadata:
        try:
            elevation_m = float(metadata["elevation_m"])
        except ValueError:
            pass

    return ChartOverlay(
        name=path.stem,
        png_path=png_path,
        corner_tl=tl,
        corner_tr=tr,
        corner_bl=bl,
        corner_br=br,
        elevation_m=elevation_m,
    )


def find_charts(input_dir: Path) -> list[ChartOverlay]:
    """Findet alle PNG+TXT-Paare in ``input_dir`` und gibt die geparsten
    Overlays zurueck. PNGs ohne .txt werden ignoriert, .txt ohne PNG bleiben
    als NMEA-Kandidaten uebrig."""
    input_dir = Path(input_dir)
    overlays: list[ChartOverlay] = []
    for png in sorted(input_dir.glob("*.png")):
        txt = png.with_suffix(".txt")
        if not txt.is_file():
            continue
        overlay = parse_chart_txt(txt)
        if overlay is not None:
            overlays.append(overlay)
    return overlays


def is_chart_config(txt_path: Path) -> bool:
    """True, wenn die .txt-Datei zu einer Karten-Konfig (PNG-Sibling
    vorhanden) gehoert. Wird von __main__ verwendet, um Karten-TXTs aus der
    NMEA-Verarbeitung auszuschliessen."""
    return Path(txt_path).with_suffix(".png").is_file()
