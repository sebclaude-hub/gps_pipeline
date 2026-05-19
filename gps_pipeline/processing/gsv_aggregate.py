"""GSV-Sätze über mehrere NMEA-Zeilen zu einer Satellitenliste aggregieren.

Hintergrund
-----------
GSV-Sätze (Satellites in View) transportieren maximal 4 Satelliten pro Zeile.
Bei vielen sichtbaren Satelliten verteilt der Empfänger die Information auf
mehrere Zeilen, gekennzeichnet durch ``num_messages`` und ``msg_num``::

    $GPGSV,3,1,12,...   ← 3 Sätze total, ich bin Satz 1, 12 Satelliten in View
    $GPGSV,3,2,12,...   ← Satz 2
    $GPGSV,3,3,12,...   ← Satz 3 (mit Rest)

Bei Multi-Constellation-Empfängern kommen mehrere Sequenzen parallel mit
unterschiedlichen Talker-IDs (``$GP`` für GPS, ``$GL`` für GLONASS, ``$GA``
für Galileo, ``$GB`` für BeiDou, ``$GQ`` für QZSS, ``$GI`` für NavIC).
Diese müssen pro Konstellation getrennt aggregiert werden, weil PRN-Nummern
nur innerhalb einer Konstellation eindeutig sind.

GSV-Sätze selbst haben **keinen eigenen Timestamp**. Wir ordnen sie dem
zuletzt im Stream gesehenen Timestamp von RMC bzw. GGA zu.

Edge case: ``$GPGSV,1,1,00*79`` bedeutet "0 Satelliten in View" und wird
als Eintrag mit leerer Satellitenliste durchgereicht (kein Crash).
"""

import datetime as _dt
from typing import Any, Dict, List, Optional

import pynmea2

from ..utils.safe_convert import safe_convert


def _extract_sv_tuples(msg: pynmea2.types.talker.GSV) -> List[Dict[str, Any]]:
    """Extrahiert bis zu 4 Satelliten-Dicts aus einem einzelnen GSV-Satz.

    Felder, die der Empfänger leer lässt (etwa SNR, wenn der Satellit unter
    der Schwelle ist), werden zu None.
    """
    sats: List[Dict[str, Any]] = []
    # pynmea2 nummeriert die vier Satelliten-Felder 1..4 mit Suffixen
    for n in range(1, 5):
        prn_attr = f"sv_prn_num_{n}"
        if not hasattr(msg, prn_attr):
            continue
        prn = safe_convert(getattr(msg, prn_attr, None), int)
        if prn is None:
            continue  # leere Stelle in der Vierergruppe
        sats.append({
            "prn": prn,
            "elevation": safe_convert(getattr(msg, f"elevation_deg_{n}", None), int),
            "azimuth": safe_convert(getattr(msg, f"azimuth_{n}", None), int),
            "snr": safe_convert(getattr(msg, f"snr_{n}", None), int),
        })
    return sats


def _derive_timestamp(msg: pynmea2.NMEASentence,
                     last_rmc_date: Optional[_dt.date]) -> Optional[_dt.datetime]:
    """Erzeugt einen vollständigen UTC-Timestamp aus einem RMC- oder GGA-Satz.

    RMC bringt Datum und Zeit mit. GGA hat nur Zeit; das Datum kommt vom
    zuletzt empfangenen RMC. Wenn noch kein RMC-Datum bekannt ist, gibt
    diese Funktion None zurück.
    """
    if isinstance(msg, pynmea2.types.talker.RMC):
        if msg.datestamp and msg.timestamp:
            return _dt.datetime.combine(msg.datestamp, msg.timestamp,
                                        tzinfo=_dt.timezone.utc)
    elif isinstance(msg, pynmea2.types.talker.GGA):
        if last_rmc_date and msg.timestamp:
            return _dt.datetime.combine(last_rmc_date, msg.timestamp,
                                        tzinfo=_dt.timezone.utc)
    return None


def aggregate_gsv(messages: List[pynmea2.NMEASentence]) -> List[Dict[str, Any]]:
    """Aggregiert GSV-Sätze zu Multi-Sentence-Groups.

    Geht den Message-Stream einmal durch und sammelt aufeinanderfolgende
    GSV-Sätze derselben Konstellation (Talker-ID) zu einer Liste von
    Satelliten. Jede fertige Gruppe wird als Dict zurückgegeben:

        {
            "timestamp_utc": datetime,           # zuletzt gesehener Timestamp
            "talker_id": "GP",                   # Konstellations-Kürzel
            "num_sv_in_view": 12,                # Wert aus dem GSV-Header
            "satellites": [{prn, elevation, azimuth, snr}, ...]
        }

    Parameters
    ----------
    messages : list of pynmea2.NMEASentence
        Roher Message-Stream aus parse_nmea_file().

    Returns
    -------
    list of dict
        Ein Eintrag pro abgeschlossene GSV-Multi-Sentence-Group.
    """
    out: List[Dict[str, Any]] = []

    # State, der durch den Stream geführt wird:
    last_timestamp: Optional[_dt.datetime] = None
    last_rmc_date: Optional[_dt.date] = None

    # Akkumulator für laufende Multi-Sentence-Group:
    current_group: List[Dict[str, Any]] = []
    current_talker: Optional[str] = None
    current_total: Optional[int] = None  # erwartete num_messages der Gruppe

    def _finalize_group():
        """Aktuelle Akku-Gruppe als out-Eintrag wegspeichern, falls nicht leer."""
        nonlocal current_group, current_talker, current_total
        if current_talker is not None:
            out.append({
                "timestamp_utc": last_timestamp,
                "talker_id": current_talker,
                "num_sv_in_view": len(current_group),
                "satellites": current_group,
            })
        current_group = []
        current_talker = None
        current_total = None

    for msg in messages:
        # Timestamp-State aktualisieren bei RMC/GGA
        if isinstance(msg, pynmea2.types.talker.RMC):
            if msg.datestamp:
                last_rmc_date = msg.datestamp
            ts = _derive_timestamp(msg, last_rmc_date)
            if ts:
                last_timestamp = ts
            continue
        if isinstance(msg, pynmea2.types.talker.GGA):
            ts = _derive_timestamp(msg, last_rmc_date)
            if ts:
                last_timestamp = ts
            continue

        # Nur GSV-Sätze interessieren ab hier
        if not isinstance(msg, pynmea2.types.talker.GSV):
            continue

        talker = msg.talker  # "GP", "GL", "GA", ...
        num_messages = safe_convert(getattr(msg, "num_messages", None), int)
        msg_num = safe_convert(getattr(msg, "msg_num", None), int)
        num_sv_in_view = safe_convert(getattr(msg, "num_sv_in_view", None), int, default=0)

        # Edge case: leere GSV-Sequenz (z.B. "$GPGSV,1,1,00")
        if num_sv_in_view == 0:
            _finalize_group()  # falls noch was offen war
            out.append({
                "timestamp_utc": last_timestamp,
                "talker_id": talker,
                "num_sv_in_view": 0,
                "satellites": [],
            })
            continue

        # Neue Multi-Sentence-Group beginnt: vorherige (ggf. unvollständig) abschließen
        if msg_num == 1 or talker != current_talker:
            _finalize_group()
            current_talker = talker
            current_total = num_messages

        # Satelliten dieses Satzes anhängen
        current_group.extend(_extract_sv_tuples(msg))

        # Letzter Satz der Gruppe? Dann abschließen.
        if num_messages is not None and msg_num == num_messages:
            _finalize_group()

    # Falls am Ende noch eine Gruppe offen ist (Logfile bricht mittendrin ab):
    _finalize_group()

    return out
