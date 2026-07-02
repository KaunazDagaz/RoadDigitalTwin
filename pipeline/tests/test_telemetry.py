from pathlib import Path

import pytest

from telemetry import (
    gps_coverage,
    nearest_point,
    parse_srt,
    parse_srt_text,
)

FIXTURES = Path(__file__).parent / "fixtures"

def test_parses_dji_mini_bracket_style():
    points = parse_srt(FIXTURES / "sample_dji_mini.srt")
    assert len(points) == 4

    p0 = points[0]
    assert p0.index == 1
    assert p0.start_ms == 0
    assert p0.lat == pytest.approx(50.450100)
    assert p0.lon == pytest.approx(30.523400)
    assert p0.rel_alt == pytest.approx(12.300)
    assert p0.abs_alt == pytest.approx(191.600)
    assert p0.extras.get("iso") == "100"
    assert p0.timestamp is not None and p0.timestamp.year == 2024


def test_risk1_every_block_has_gps():
    points = parse_srt(FIXTURES / "sample_dji_mini.srt")
    assert all(p.has_gps for p in points)
    assert gps_coverage(points) == 1.0

def test_parses_legacy_gps_paren_style():
    points = parse_srt(FIXTURES / "sample_dji_go_legacy.srt")
    assert len(points) == 2
    assert points[0].lat == pytest.approx(50.450100)
    assert points[0].lon == pytest.approx(30.523400)
    assert points[0].rel_alt == pytest.approx(12.30)
    assert gps_coverage(points) == 1.0

def test_timecode_to_ms_and_ordering():
    points = parse_srt(FIXTURES / "sample_dji_mini.srt")
    assert [p.start_ms for p in points] == [0, 33, 66, 1000]

def test_nearest_point_matches_closest_frame():
    points = parse_srt(FIXTURES / "sample_dji_mini.srt")
    assert nearest_point(points, 900).index == 4
    assert nearest_point(points, 40).index == 2

def test_nearest_point_empty():
    assert nearest_point([], 100) is None
    assert gps_coverage([]) == 0.0

def test_block_without_gps_yields_none_coords():
    text = "1\n00:00:00,000 --> 00:00:01,000\n[iso : 100] no position here\n"
    points = parse_srt_text(text)
    assert len(points) == 1
    assert not points[0].has_gps
    assert gps_coverage(points) == 0.0

def test_crlf_and_bom_tolerated():
    text = "1\r\n00:00:00,000 --> 00:00:01,000\r\n[latitude: 1.5] [longitude: 2.5]\r\n"
    points = parse_srt_text(text)
    assert len(points) == 1
    assert points[0].lat == pytest.approx(1.5)
    assert points[0].lon == pytest.approx(2.5)
