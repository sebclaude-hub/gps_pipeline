"""Tests fuer merge_tracks (processing/merge.py) und write_gpx
(export/gpx_export.py), inklusive GPX-<hdop>-Roundtrip.

Synthetische Fixtures mit klar fiktiven Koordinaten (Aequator-Naehe),
analog zu den Traxel-Tests (merge.test.ts / gpx.test.ts).
"""

import pandas as pd
import pytest
from geopy.distance import geodesic

from gps_pipeline.export.gpx_export import write_gpx
from gps_pipeline.parsing.gpx import parse_gpx_file
from gps_pipeline.processing.merge import merge_tracks


def _make_track(points):
    """Schema-B-DataFrame aus (ts_s, lon, speed_kmh, hdop)-Tupeln (lat=0)."""
    rows = [
        {
            "timestamp_utc": pd.Timestamp("2024-01-01", tz="UTC")
            + pd.Timedelta(seconds=ts_s),
            "directional_latitude": 0.0,
            "directional_longitude": lon,
            "altitude_corrected": 100.0,
            "speed_kmh": speed,
            "speed_knots": speed / 1.852 if speed is not None else None,
            "gga_hdop": hdop,
        }
        for ts_s, lon, speed, hdop in points
    ]
    return pd.DataFrame(rows)


def _track_a():
    """0-20 s, endet bei lon 0.002."""
    return _make_track([
        (0, 0.0, 40.0, 1.1),
        (10, 0.001, 40.0, 1.2),
        (20, 0.002, 40.0, 1.3),
    ])


def _track_b(start_s=120):
    """Startet (default) 100 s nach Ende von A, bei lon 0.003."""
    return _make_track([
        (start_s, 0.003, 40.0, None),
        (start_s + 10, 0.004, 40.0, None),
    ])


def _expected_bridge_s():
    """Brueckenzeit ueber die Naht A-Ende -> B-Start bei 40 km/h."""
    d = geodesic((0.0, 0.002), (0.0, 0.003)).meters
    return d / (40.0 / 3.6)


def _ts_seconds(df):
    ts = pd.to_datetime(df["timestamp_utc"], utc=True)
    epoch = pd.Timestamp("2024-01-01", tz="UTC")
    return [(t - epoch).total_seconds() for t in ts]


class TestMergeGap:
    def test_disjunkt_bleibt_unveraendert(self):
        res = merge_tracks(_track_a(), _track_b(), mode="gap")
        assert res.effective_mode == "gap"
        assert res.shift_s == 0.0
        assert len(res.df) == 5
        assert _ts_seconds(res.df) == [0, 10, 20, 120, 130]

    def test_spalten_ueberleben(self):
        res = merge_tracks(_track_a(), _track_b(), mode="gap")
        assert res.df["gga_hdop"].iloc[1] == 1.2
        assert pd.isna(res.df["gga_hdop"].iloc[3])
        assert res.df["speed_kmh"].iloc[4] == 40.0

    def test_eingaben_unveraendert(self):
        a, b = _track_a(), _track_b()
        merge_tracks(a, b, mode="gap")
        assert _ts_seconds(a) == [0, 10, 20]
        assert _ts_seconds(b) == [120, 130]


class TestMergeBridge:
    def test_zweiter_track_vorgezogen(self):
        res = merge_tracks(_track_a(), _track_b(), mode="bridge")
        assert res.effective_mode == "bridge"
        new_start = 20 + _expected_bridge_s()
        got = _ts_seconds(res.df)
        assert got[3] == pytest.approx(new_start, abs=0.01)
        # Punktabstaende innerhalb des zweiten Tracks bleiben erhalten.
        assert got[4] - got[3] == pytest.approx(10.0, abs=0.001)
        # Verschiebung positiv (nach vorne), Pause 100s - Bruecke ~10s.
        assert res.shift_s == pytest.approx(120 - new_start, abs=0.1)

    def test_ueberlappung_erzwingt_bridge(self):
        res = merge_tracks(_track_a(), _track_b(start_s=10), mode="gap")
        assert res.effective_mode == "bridge"
        got = _ts_seconds(res.df)
        # Zweiter Track beginnt hinter dem Ende des ersten -> streng monoton.
        assert got == sorted(got)
        assert got[3] == pytest.approx(20 + _expected_bridge_s(), abs=0.01)
        # Nach HINTEN geschoben -> negative Verschiebung.
        assert res.shift_s < 0

    def test_unbekannter_modus(self):
        with pytest.raises(ValueError):
            merge_tracks(_track_a(), _track_b(), mode="trim")


class TestMergeLeereTracks:
    def test_leerer_zweiter_track(self):
        res = merge_tracks(_track_a(), _track_a().iloc[0:0], mode="gap")
        assert len(res.segments) == 1
        assert len(res.df) == 3


class TestWriteGpxRoundtrip:
    def test_roundtrip_mit_hdop_und_speed(self, tmp_path):
        res = merge_tracks(_track_a(), _track_b(), mode="gap")
        out = tmp_path / "merged.gpx"
        write_gpx(res.segments, out, name="a+b")
        df = parse_gpx_file(str(out))
        assert len(df) == 5
        assert df["directional_longitude"].iloc[4] == pytest.approx(0.004)
        assert df["altitude_corrected"].iloc[0] == pytest.approx(100.0)
        assert df["speed_kmh"].iloc[0] == pytest.approx(40.0, abs=0.01)
        assert df["gga_hdop"].iloc[1] == pytest.approx(1.2)
        assert pd.isna(df["gga_hdop"].iloc[3])
        ts = pd.to_datetime(df["timestamp_utc"], utc=True)
        assert ts.iloc[3] == pd.Timestamp("2024-01-01T00:02:00Z")

    def test_segmente_und_name_escaping(self, tmp_path):
        res = merge_tracks(_track_a(), _track_b(), mode="gap")
        out = tmp_path / "merged.gpx"
        write_gpx(res.segments, out, name='a<b>&"c"')
        xml = out.read_text(encoding="utf-8")
        assert xml.count("<trkseg>") == 2
        assert "a&lt;b&gt;&amp;" in xml

    def test_optionale_felder_weggelassen(self, tmp_path):
        df = _make_track([(0, 0.0, None, None)])
        df["altitude_corrected"] = None
        out = tmp_path / "min.gpx"
        write_gpx(df, out)
        xml = out.read_text(encoding="utf-8")
        assert "<ele>" not in xml
        assert "<speed>" not in xml
        assert "<hdop>" not in xml
        back = parse_gpx_file(str(out))
        assert len(back) == 1
        assert pd.isna(back["altitude_corrected"].iloc[0])


class TestGpxHdopParsing:
    def test_parse_hdop_element(self, tmp_path):
        gpx = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="0.0" lon="0.0"><time>2024-01-01T00:00:00Z</time><hdop>1.4</hdop></trkpt>
    <trkpt lat="0.0" lon="0.001"><time>2024-01-01T00:00:10Z</time></trkpt>
  </trkseg></trk>
</gpx>"""
        p = tmp_path / "hdop.gpx"
        p.write_text(gpx, encoding="utf-8")
        df = parse_gpx_file(str(p))
        assert "gga_hdop" in df.columns
        assert df["gga_hdop"].iloc[0] == pytest.approx(1.4)
        assert pd.isna(df["gga_hdop"].iloc[1])
