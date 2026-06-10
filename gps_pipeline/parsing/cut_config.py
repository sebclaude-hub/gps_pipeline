"""Parser fuer Schnittanweisungen ``<basename>.cuts.json``.

Konzept
-------
Der React-Viewer exportiert keine getrimmten Daten, sondern eine kompakte
Anweisung, welche Index-Bereiche beim NAECHSTEN Pipeline-Lauf aus den
Originaldaten geschnitten werden sollen, plus optional einen
Hoehen-Anzeigeoffset fuer den Viewer. Diese Datei liegt im selben
Verzeichnis wie die Quelldatei und traegt deren vollstaendigen Dateinamen
plus ``.cuts.json``::

    data/2026-05-02_16-54-51_rx_log.txt              # Original
    data/2026-05-02_16-54-51_rx_log.txt.cuts.json    # Schnittanweisung

Anweisungen deaktivieren: Datei umbenennen (z.B. ``.cuts.json.disabled``)
und erneut ``python -m gps_pipeline`` ausfuehren.

Format
------
::

    {
      "source": "2026-05-02_16-54-51_rx_log.txt",
      "n_points_reference": 24138,
      "z_offset_m": 7,
      "cut_ranges": [
        {"start": 0,     "end": 49,    "mode": "trim"},
        {"start": 200,   "end": 350,   "mode": "bridge"},
        {"start": 600,   "end": 700,   "mode": "gap"},
        {"start": 24100, "end": 24137, "mode": "trim"}
      ],
      "created_at": "2026-05-25T17:30:00Z"
    }

Modi
----
* ``trim``      -- Punkte entfernen, Timestamps unveraendert.
                   Wird vom System fuer Edge-Cuts (start=0 oder end=N-1)
                   IMMER forciert, egal was die Datei angibt.
* ``gap``       -- Punkte entfernen, Timestamps unveraendert. Im Track
                   bleibt eine sichtbare Luecke; der Viewer warnt im Banner.
* ``bridge``    -- "Ueberbruecken": Punkte entfernen UND alle nachfolgenden
                   Timestamps nach vorne verschieben (Brueckenzeit aus
                   Nachbarschafts-Speed). Erzeugt zusammenhaengende
                   Zeitachse, Sats werden mit-verschoben. Banner als
                   Warnung. Intention ist Transparenz, NICHT Verbergen
                   (frueher irrefuehrend "synthetic"/"privacy" genannt).

z_offset_m
----------
Reine Anzeige: gibt dem React-Viewer den Default-Wert fuer den Hoehen-
Offset-Slider vor. Die Track-Daten selbst werden NICHT modifiziert --
der Wert legt nur fest, wie hoch der Track ueber Grund dargestellt wird,
damit "Track-Sharing" mit korrigierter Hoehenanzeige bequem wird.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

CutMode = Literal["trim", "gap", "bridge"]
_VALID_MODES: tuple[CutMode, ...] = ("trim", "gap", "bridge")


@dataclass(frozen=True)
class CutSpec:
    """Eine einzelne Schnittanweisung: Index-Bereich [start, end] + Modus."""
    start: int
    end: int
    mode: CutMode

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < 0:
            raise ValueError(f"Negative Indizes: {self}")
        if self.start > self.end:
            raise ValueError(f"start > end: {self}")
        if self.mode not in _VALID_MODES:
            raise ValueError(
                f"Unbekannter Modus '{self.mode}', erwartet: {_VALID_MODES}")


@dataclass
class CutConfig:
    """Eine ``.cuts.json`` als Python-Objekt."""
    source: str
    """Dateiname (mit Endung) der Quelldatei -- nur informativ."""

    n_points_reference: Optional[int]
    """Anzahl der Punkte des Tracks zum Zeitpunkt der Cut-Erstellung.
    Wird gegen ``len(df_c)`` validiert, um Off-by-One-Fehler durch
    Pipeline-Aenderungen abzufangen. None bedeutet: keine Validierung."""

    cut_ranges: list[CutSpec]
    """Alle Schnittbereiche, sortiert nach Start-Index."""

    z_offset_m: Optional[float] = None
    """Vorgeschlagener Hoehen-Offset fuer den Viewer-Slider (Default-Wert
    beim Laden des Tracks). Reine Anzeige -- die Daten werden nicht
    modifiziert. ``None`` heisst: keine Anweisung enthalten,
    Viewer startet bei 0."""

    created_at: Optional[str] = None
    """ISO-8601-Zeitstempel, wann der Viewer die Datei geschrieben hat."""

    def has_any_directive(self) -> bool:
        """True, wenn die Datei tatsaechlich etwas ausloest (Cuts oder
        Z-Offset). Bei leerer Anweisung ist Anwenden ein No-Op."""
        if self.cut_ranges:
            return True
        if self.z_offset_m is not None and self.z_offset_m != 0:
            return True
        return False

    def force_edge_trim(self, n_points: int) -> "CutConfig":
        """Erzeugt eine neue Config, in der Edge-Cuts (start=0 oder
        end=n-1) zwangsweise auf ``mode='trim'`` gesetzt sind.

        Begruendung: Bei einem Cut am Anfang oder Ende gibt es nichts
        zu "ueberbruecken" (kein vorheriger / nachfolgender Punkt).
        gap und bridge sind dort semantisch identisch zu trim --
        wir vereinheitlichen das, damit der Banner-Code nicht
        irrefuehrend warnt.
        """
        if n_points <= 0:
            return self
        last_idx = n_points - 1
        new_ranges: list[CutSpec] = []
        for spec in self.cut_ranges:
            is_edge = (spec.start <= 0) or (spec.end >= last_idx)
            if is_edge and spec.mode != "trim":
                new_ranges.append(CutSpec(
                    start=spec.start, end=spec.end, mode="trim"))
            else:
                new_ranges.append(spec)
        return CutConfig(
            source=self.source,
            n_points_reference=self.n_points_reference,
            cut_ranges=new_ranges,
            z_offset_m=self.z_offset_m,
            created_at=self.created_at,
        )


def load_cut_config(path: Path) -> CutConfig:
    """Liest und validiert eine ``.cuts.json``-Datei.

    Wirft ``FileNotFoundError`` wenn die Datei fehlt; ``ValueError`` bei
    Schema-Fehlern (fehlende Felder, ungueltige Modi, kaputte Ranges).
    """
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    source = payload.get("source")
    if not isinstance(source, str) or not source:
        raise ValueError(f"{path.name}: 'source' fehlt oder ist leer.")

    n_ref = payload.get("n_points_reference")
    if n_ref is not None and not isinstance(n_ref, int):
        raise ValueError(
            f"{path.name}: 'n_points_reference' muss int sein, "
            f"ist {type(n_ref).__name__}.")

    raw_ranges = payload.get("cut_ranges", [])
    if not isinstance(raw_ranges, list):
        raise ValueError(f"{path.name}: 'cut_ranges' muss eine Liste sein.")

    cut_ranges: list[CutSpec] = []
    for i, r in enumerate(raw_ranges):
        if not isinstance(r, dict):
            raise ValueError(
                f"{path.name}: cut_ranges[{i}] muss ein Objekt sein.")
        try:
            spec = CutSpec(
                start=int(r["start"]),
                end=int(r["end"]),
                mode=r.get("mode", "trim"),
            )
        except (KeyError, ValueError, TypeError) as e:
            raise ValueError(
                f"{path.name}: cut_ranges[{i}] ungueltig: {e}") from e
        cut_ranges.append(spec)

    cut_ranges.sort(key=lambda r: r.start)

    raw_z = payload.get("z_offset_m")
    z_offset_m: Optional[float] = None
    if raw_z is not None:
        try:
            z_offset_m = float(raw_z)
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"{path.name}: 'z_offset_m' muss eine Zahl sein.") from e

    return CutConfig(
        source=source,
        n_points_reference=n_ref,
        cut_ranges=cut_ranges,
        z_offset_m=z_offset_m,
        created_at=payload.get("created_at"),
    )


def find_cut_config(source_path: Path) -> Optional[Path]:
    """Sucht die zur Quelldatei gehoerende ``.cuts.json`` und gibt ihren
    Pfad zurueck, oder ``None`` wenn keine vorhanden ist.

    Konvention: ``<source>.cuts.json`` neben der Quelldatei. Etwaige
    ``.cuts.json.disabled``-Dateien werden ignoriert (so kann der User
    Cuts temporaer deaktivieren, ohne sie zu loeschen).
    """
    source_path = Path(source_path)
    candidate = source_path.with_name(source_path.name + ".cuts.json")
    if candidate.is_file():
        return candidate
    return None
