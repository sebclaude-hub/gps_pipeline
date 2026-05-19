"""Robuste Typkonvertierung mit Fallback bei ungültigen Werten.

NMEA-Felder kommen häufig als leere Strings oder None zurück, wenn der
Empfänger gerade keinen Wert hat. Die Konvertierung soll dann einen
Default zurückgeben statt zu crashen.
"""

from typing import Any, Callable


def safe_convert(value: Any, conversion_func: Callable, default: Any = None) -> Any:
    """Konvertiert ``value`` mit ``conversion_func``, gibt ``default`` bei Fehlern.

    Behandelt explizit ``None`` und leere Strings als "kein Wert".
    Fängt ``ValueError`` und ``TypeError`` aus der Konvertierung ab.

    Beispiel:
        >>> safe_convert("3.14", float)
        3.14
        >>> safe_convert("", float, default=0.0)
        0.0
        >>> safe_convert(None, int)  # gibt None zurück
    """
    if value is None or value == "":
        return default
    try:
        return conversion_func(value)
    except (ValueError, TypeError):
        return default
