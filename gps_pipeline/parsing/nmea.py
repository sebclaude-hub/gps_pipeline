"""NMEA-Logfile parsen mit pynmea2.

Diese Modul-Verantwortung: Datei einlesen, Zeilen zu pynmea2-Sentence-Objekten
machen, Fehler einzelner Zeilen tolerieren (Logfiles haben oft kaputte Zeilen
am Anfang/Ende). Keine DataFrame-Erstellung — das ist Aufgabe des nächsten Moduls.

Standard-Ausgabe: Liste von pynmea2.NMEASentence-Objekten in Original-Reihenfolge.
"""

from typing import Dict, List, Set

import pynmea2


def parse_nmea_file(file_path: str, verbose: bool = False) -> List[pynmea2.NMEASentence]:
    """Liest eine NMEA-Datei zeilenweise und gibt geparste Messages zurück.

    Zeilen, die nicht parsbar sind, werden übersprungen (Logfile-Anfang
    enthält oft kaputte Bruchstücke). Bei ``verbose=True`` werden alle
    Fehler gemeldet, sonst nur die Anzahl am Ende.

    Parameters
    ----------
    file_path : str
        Pfad zur NMEA-Logdatei.
    verbose : bool
        Wenn True: jede fehlerhafte Zeile einzeln melden.

    Returns
    -------
    list of pynmea2.NMEASentence
        Geparste Messages in Original-Reihenfolge.
    """
    parsed: List[pynmea2.NMEASentence] = []
    parse_errors = 0
    unexpected_errors = 0

    print(f"Lese NMEA-Daten aus {file_path} ...")

    with open(file_path, "r", encoding="utf-8") as nmea_file:
        for line in nmea_file:
            line = line.strip()
            if not line:
                continue

            try:
                msg = pynmea2.parse(line)
                parsed.append(msg)
            except pynmea2.ParseError as e:
                parse_errors += 1
                if verbose:
                    print(f"  ParseError: '{line[:60]}...' — {e}")
            except Exception as e:
                unexpected_errors += 1
                if verbose:
                    print(f"  Unexpected: '{line[:60]}...' — {e}")

    print(f"Geparst: {len(parsed)} Nachrichten "
          f"(ParseErrors: {parse_errors}, Sonstige Fehler: {unexpected_errors})")
    return parsed


def count_message_types(messages: List[pynmea2.NMEASentence]) -> Dict[str, int]:
    """Zählt die Vorkommen pro Satz-Typ (z.B. {'RMC': 588, 'GGA': 588, ...})."""
    counts: Dict[str, int] = {}
    for msg in messages:
        counts[msg.sentence_type] = counts.get(msg.sentence_type, 0) + 1
    return counts


def get_field_names(messages: List[pynmea2.NMEASentence]) -> Dict[str, Set[str]]:
    """Sammelt alle vorkommenden Feldnamen pro Satz-Typ.

    Diagnose-Hilfe: zeigt, welche Felder pynmea2 für die geparsten Satz-Typen
    bietet. Nützlich, wenn man mit einem neuen Empfänger-Modell anfängt und
    nicht weiß, welche Spalten überhaupt zu erwarten sind.
    """
    field_names: Dict[str, Set[str]] = {}
    for msg in messages:
        st = msg.sentence_type
        if st not in field_names:
            field_names[st] = set()
        # msg.fields = Liste von Tupeln (Beschreibung, Attributname, [Konverter])
        for field in msg.fields:
            field_names[st].add(field[1])
    return field_names
