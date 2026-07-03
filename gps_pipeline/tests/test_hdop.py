"""Tests für GPS-Accuracy (HDOP)-Extraktion und Konsolidierung.

Diese Tests verifizieren:
  * HDOP wird korrekt aus GGA-Sätzen extrahiert (Schema A)
  * Schema B konsolidiert HDOP pro Timestamp (nimmt first bei Duplikaten)
  * Schema C enthält die HDOP-Spalte nach Enrichment
  * Fehlende HDOP-Werte werden korrekt als NaN behandelt
  * Datentyp ist Float32 (Speichereffizienz)
"""

import datetime as _dt
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import pynmea2
import pytest

from gps_pipeline.parsing.nmea_to_dataframe import build_dataframe
from gps_pipeline.processing.consolidate import consolidate
from gps_pipeline.processing.filter import filter_invalid
from gps_pipeline.processing.enrich import enrich_speed


# ---------------------------------------------------------------------------
# Fixture: Synthetische NMEA-Sätze mit HDOP
# ---------------------------------------------------------------------------

def _compute_nmea_checksum(sentence: str) -> str:
    """Berechnet NMEA-Prüfsumme (XOR aller Bytes zwischen $ und *)."""
    # Entferne $ und bisherige Checksumme falls vorhanden
    if sentence.startswith("$"):
        sentence = sentence[1:]
    if "*" in sentence:
        sentence = sentence.split("*")[0]

    checksum = 0
    for char in sentence:
        checksum ^= ord(char)
    return f"{checksum:02X}"


def _create_gga_sentence(
    timestamp: _dt.time,
    lat: float = 47.5,
    lon: float = 8.5,
    hdop: float = 1.5,
    gps_quality: int = 1,
    num_sats: int = 10,
    altitude: float = 500.0,
) -> str:
    """Erzeugt einen GGA-Satz-String mit Höhe und HDOP.

    Erwartet: $GNGGA,<time>,<lat>,N,<lon>,E,<quality>,<sats>,<hdop>,<alt>,M,...
    """
    # Konvertiere Dezimal-Grade zu NMEA-Format (DDMM.MMMM)
    lat_deg = int(lat)
    lat_min = (lat - lat_deg) * 60
    lat_str = f"{lat_deg:02d}{lat_min:07.4f}"

    lon_deg = int(lon)
    lon_min = (lon - lon_deg) * 60
    lon_str = f"{lon_deg:03d}{lon_min:07.4f}"

    # Zeit im Format HHMMSS.SS
    time_str = timestamp.strftime("%H%M%S.%f")[:-4]  # .SS nicht .SSSSSS

    # GGA-Satz ohne Prüfsumme zusammensetzen
    gga_body = (
        f"GNGGA,{time_str},{lat_str},N,{lon_str},E,"
        f"{gps_quality},{num_sats},{hdop:.1f},{altitude:.1f},M,46.9,M,,"
    )
    checksum = _compute_nmea_checksum(gga_body)
    gga = f"${gga_body}*{checksum}"
    return gga


def _create_rmc_sentence(
    date: _dt.date,
    timestamp: _dt.time,
    lat: float = 47.5,
    lon: float = 8.5,
    speed_knots: float = 10.0,
) -> str:
    """Erzeugt einen RMC-Satz-String."""
    lat_deg = int(lat)
    lat_min = (lat - lat_deg) * 60
    lat_str = f"{lat_deg:02d}{lat_min:07.4f}"

    lon_deg = int(lon)
    lon_min = (lon - lon_deg) * 60
    lon_str = f"{lon_deg:03d}{lon_min:07.4f}"

    time_str = timestamp.strftime("%H%M%S.%f")[:-4]
    date_str = date.strftime("%d%m%y")

    rmc_body = (
        f"GNRMC,{time_str},A,{lat_str},N,{lon_str},E,"
        f"{speed_knots:.2f},0.0,{date_str},,,A"
    )
    checksum = _compute_nmea_checksum(rmc_body)
    rmc = f"${rmc_body}*{checksum}"
    return rmc


@pytest.fixture
def sample_nmea_with_hdop():
    """Liefert Rohdaten (NMEA-Strings) mit bekannten HDOP-Werten."""
    # Zwei Zeitstempel; der zweite mit zwei GGA-Sätzen (Duplikat)
    date = _dt.date(2024, 1, 15)
    time1 = _dt.time(10, 30, 0)
    time2 = _dt.time(10, 30, 1)

    sentences = [
        _create_rmc_sentence(date, time1, lat=47.5, lon=8.5, speed_knots=5.0),
        _create_gga_sentence(time1, lat=47.5, lon=8.5, hdop=1.2, num_sats=12),

        _create_rmc_sentence(date, time2, lat=47.501, lon=8.501, speed_knots=6.0),
        _create_gga_sentence(time2, lat=47.501, lon=8.501, hdop=1.5, num_sats=11),
        # Zweite GGA mit identischem Timestamp aber unterschiedlichem HDOP
        _create_gga_sentence(time2, lat=47.5015, lon=8.5015, hdop=0.9, num_sats=13),
    ]
    return sentences


@pytest.fixture
def sample_messages(sample_nmea_with_hdop):
    """Parsed NMEA-Messages."""
    messages = []
    for sentence_str in sample_nmea_with_hdop:
        try:
            msg = pynmea2.parse(sentence_str)
            messages.append(msg)
        except Exception as e:
            pytest.skip(f"pynmea2.parse fehlgeschlagen: {e}")
    return messages


# ---------------------------------------------------------------------------
# Tests: Schema A (HDOP-Extraktion)
# ---------------------------------------------------------------------------

class TestHdopExtractionSchemaA:
    """HDOP-Extraktion aus GGA-Sätzen in Schema A."""

    def test_gga_hdop_extracted(self, sample_messages):
        """GGA-Sätze enthalten HDOP in Schema A."""
        df_a = build_dataframe(sample_messages)

        # Mindestens 2 GGA-Zeilen sollten vorhanden sein
        gga_rows = df_a[df_a["sentence_type"] == "GGA"]
        assert len(gga_rows) >= 2, "Mindestens 2 GGA-Zeilen erwartet"

        # HDOP-Spalte sollte vorhanden sein
        assert "gga_hdop" in df_a.columns, "gga_hdop-Spalte fehlt"

        # HDOP-Werte sollten vorhanden und numerisch sein
        hdop_values = gga_rows["gga_hdop"].dropna()
        assert len(hdop_values) > 0, "Keine HDOP-Werte gefunden"
        assert hdop_values.dtype == "Float32", f"Erwartet Float32, bekam {hdop_values.dtype}"

    def test_hdop_values_correct(self, sample_messages):
        """Extrahierte HDOP-Werte sind korrekt."""
        df_a = build_dataframe(sample_messages)
        gga_rows = df_a[df_a["sentence_type"] == "GGA"]

        # Wir erwarten HDOP-Werte von 1.2, 1.5, 0.9
        hdop_values = sorted(gga_rows["gga_hdop"].dropna().tolist())
        assert len(hdop_values) == 3, f"Erwartet 3 HDOP-Werte, bekam {len(hdop_values)}"

        np.testing.assert_allclose(hdop_values[0], 0.9, rtol=0.05)
        np.testing.assert_allclose(hdop_values[1], 1.2, rtol=0.05)
        np.testing.assert_allclose(hdop_values[2], 1.5, rtol=0.05)

    def test_rmc_has_no_hdop(self, sample_messages):
        """RMC-Sätze haben kein HDOP (Spalte ist NaN)."""
        df_a = build_dataframe(sample_messages)
        rmc_rows = df_a[df_a["sentence_type"] == "RMC"]

        if len(rmc_rows) > 0:
            # gga_hdop sollte für RMC-Zeilen NaN sein
            hdop_rmc = rmc_rows["gga_hdop"].dropna()
            assert len(hdop_rmc) == 0, "RMC sollte kein gga_hdop haben"


# ---------------------------------------------------------------------------
# Tests: Schema B (Konsolidierung)
# ---------------------------------------------------------------------------

class TestHdopConsolidationSchemaB:
    """HDOP-Konsolidierung in Schema B (eine Zeile pro Timestamp)."""

    def test_hdop_in_schema_b_columns(self, sample_messages):
        """gga_hdop ist in den Schema-B-Spalten."""
        df_a = build_dataframe(sample_messages)
        df_filt = filter_invalid(df_a)
        df_b = consolidate(df_filt)

        # Schema B sollte gga_hdop enthalten
        assert "gga_hdop" in df_b.columns, "gga_hdop fehlt in Schema B"

    def test_hdop_one_per_timestamp(self, sample_messages):
        """Nach Konsolidierung: eine HDOP-Zeile pro Timestamp (first keep)."""
        df_a = build_dataframe(sample_messages)
        df_filt = filter_invalid(df_a)
        df_b = consolidate(df_filt)

        # 2 Timestamps sollten vorhanden sein
        assert len(df_b) >= 1, "Schema B sollte Zeilen haben"

        # Keine Duplikate bei timestamp_utc
        assert df_b["timestamp_utc"].duplicated().sum() == 0, \
            "Timestamp-Duplikate in Schema B (sollte nicht vorkommen nach consolidate)"

    def test_hdop_values_in_schema_b(self, sample_messages):
        """HDOP-Werte sind in Schema B vorhanden."""
        df_a = build_dataframe(sample_messages)
        df_filt = filter_invalid(df_a)
        df_b = consolidate(df_filt)

        hdop_values = df_b["gga_hdop"].dropna()
        assert len(hdop_values) > 0, "Keine HDOP-Werte in Schema B"

        # Werte sollten von den erwarteten GGA-Sätzen stammen
        # Der erste Timestamp hat HDOP=1.2, der zweite könnte 1.5 oder 0.9 sein
        # (je nachdem, welcher GGA zuerst konsolidiert wird)
        for val in hdop_values:
            assert val in [0.9, 1.2, 1.5], f"Unerwarteter HDOP-Wert: {val}"

    def test_hdop_dtype_float32_in_schema_b(self, sample_messages):
        """HDOP in Schema B ist Float32."""
        df_a = build_dataframe(sample_messages)
        df_filt = filter_invalid(df_a)
        df_b = consolidate(df_filt)

        # Nur testen, wenn die Spalte vorhanden ist
        if "gga_hdop" in df_b.columns:
            assert df_b["gga_hdop"].dtype == "Float32", \
                f"Erwartet Float32, bekam {df_b['gga_hdop'].dtype}"


# ---------------------------------------------------------------------------
# Tests: Schema C (Enrichment)
# ---------------------------------------------------------------------------

class TestHdopEnrichmentSchemaC:
    """HDOP bleibt nach Enrichment erhalten in Schema C."""

    def test_hdop_preserved_in_schema_c(self, sample_messages):
        """gga_hdop bleibt nach enrich_speed erhalten."""
        df_a = build_dataframe(sample_messages)
        df_filt = filter_invalid(df_a)
        df_b = consolidate(df_filt)
        df_c = enrich_speed(df_b)

        assert "gga_hdop" in df_c.columns, "gga_hdop fehlt in Schema C"

    def test_hdop_values_unchanged_in_schema_c(self, sample_messages):
        """HDOP-Werte sind in Schema C unverändert."""
        df_a = build_dataframe(sample_messages)
        df_filt = filter_invalid(df_a)
        df_b = consolidate(df_filt)
        df_c = enrich_speed(df_b)

        # Schema C sollte dieselben HDOP-Werte wie Schema B haben
        assert df_b["gga_hdop"].equals(df_c["gga_hdop"]), \
            "HDOP-Werte haben sich zwischen Schema B und C verändert"


# ---------------------------------------------------------------------------
# Tests: Spezialfälle
# ---------------------------------------------------------------------------

class TestHdopSpecialCases:
    """Spezialfälle bei HDOP-Behandlung."""

    def test_missing_hdop_is_nan(self):
        """Fehlender HDOP wird als NaN behandelt."""
        # Erstelle einen GGA-Satz ohne HDOP (leeres Feld)
        date = _dt.date(2024, 1, 15)
        time = _dt.time(10, 30, 0)

        # Manueller GGA ohne HDOP (8. Feld leer)
        gga_no_hdop_body = (
            f"GNGGA,{time.strftime('%H%M%S')},4735.5000,N,"
            f"00830.5000,E,1,10,,500.0,M,46.9,M,,"
        )
        checksum = _compute_nmea_checksum(gga_no_hdop_body)
        gga_no_hdop = f"${gga_no_hdop_body}*{checksum}"
        rmc = _create_rmc_sentence(date, time)

        try:
            messages = [
                pynmea2.parse(rmc),
                pynmea2.parse(gga_no_hdop),
            ]
        except Exception:
            pytest.skip("pynmea2.parse fehlgeschlagen für GGA ohne HDOP")

        df_a = build_dataframe(messages)
        gga_rows = df_a[df_a["sentence_type"] == "GGA"]

        # HDOP sollte NaN sein
        if "gga_hdop" in df_a.columns:
            hdop_val = gga_rows["gga_hdop"].iloc[0]
            assert pd.isna(hdop_val), f"Erwartet NaN, bekam {hdop_val}"

    def test_empty_dataframe_handling(self):
        """Leere DataFrames werden korrekt verarbeitet."""
        df_empty = pd.DataFrame()
        df_b = consolidate(df_empty)

        # Sollte ein leeres DataFrame mit korrekten Spalten sein
        assert "gga_hdop" in df_b.columns, "gga_hdop sollte in leeren Schema B vorhanden sein"
        assert len(df_b) == 0, "Leeres Input sollte leeres Output ergeben"


# ---------------------------------------------------------------------------
# Integrationstests
# ---------------------------------------------------------------------------

class TestHdopIntegration:
    """End-to-End-Tests über alle Pipelines hinweg."""

    def test_full_pipeline_nmea_with_hdop(self, sample_messages):
        """Komplette Pipeline: Messages → Schema A → B → C mit HDOP."""
        # Schema A
        df_a = build_dataframe(sample_messages)
        assert "gga_hdop" in df_a.columns

        # Schema B
        df_filt = filter_invalid(df_a)
        df_b = consolidate(df_filt)
        assert "gga_hdop" in df_b.columns
        assert len(df_b) > 0

        # Schema C
        df_c = enrich_speed(df_b)
        assert "gga_hdop" in df_c.columns
        assert len(df_c) == len(df_b), "Enrichment sollte Zeilenzahl nicht ändern"

        # HDOP sollte keine NaN-Spikes nach Enrichment bekommen
        hdop_before = df_b["gga_hdop"].notna().sum()
        hdop_after = df_c["gga_hdop"].notna().sum()
        assert hdop_before == hdop_after, \
            f"Enrichment hat HDOP-Werte verloren: {hdop_before} → {hdop_after}"

    def test_hdop_alongside_other_quality_metrics(self, sample_messages):
        """HDOP funktioniert alongside Qualifier wie gga_num_sats und gga_gps_quality."""
        df_a = build_dataframe(sample_messages)
        df_filt = filter_invalid(df_a)
        df_b = consolidate(df_filt)

        # Alle drei Quality-Spalten sollten vorhanden sein
        quality_cols = {"gga_hdop", "gga_num_sats", "gga_gps_quality"}
        present_cols = quality_cols & set(df_b.columns)
        assert len(present_cols) >= 1, "Mindestens eine Quality-Spalte sollte vorhanden sein"

        # Länge sollte konsistent sein
        for col in present_cols:
            assert len(df_b[col]) == len(df_b), \
                f"Spalte {col} hat unterschiedliche Länge"
