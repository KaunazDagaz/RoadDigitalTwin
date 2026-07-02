from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_TIMECODE_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)

_LAT_RE = re.compile(r"latitude\s*[:\s]\s*(-?\d+\.\d+)", re.IGNORECASE)
_LON_RE = re.compile(r"longitude\s*[:\s]\s*(-?\d+\.\d+)", re.IGNORECASE)
_REL_ALT_RE = re.compile(r"rel_alt\s*[:\s]\s*(-?\d+\.?\d*)", re.IGNORECASE)
_ABS_ALT_RE = re.compile(r"abs_alt\s*[:\s]\s*(-?\d+\.?\d*)", re.IGNORECASE)

_GPS_PAREN_RE = re.compile(
    r"GPS\s*\(\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*,\s*(\d+)\s*\)", re.IGNORECASE
)
_BAROMETER_RE = re.compile(r"BAROMETER\s*[:\s]\s*(-?\d+\.?\d*)", re.IGNORECASE)

_TIMESTAMP_RE = re.compile(
    r"(\d{4})[-.](\d{2})[-.](\d{2})\s+(\d{2}):(\d{2}):(\d{2})(?:[.,](\d{1,6}))?"
)


@dataclass
class TelemetryPoint:
    index: int
    start_ms: int
    lat: float | None
    lon: float | None
    rel_alt: float | None = None
    abs_alt: float | None = None
    timestamp: datetime | None = None
    extras: dict = field(default_factory=dict)

    @property
    def has_gps(self) -> bool:
        return self.lat is not None and self.lon is not None

def _timecode_to_ms(h: str, m: str, s: str, ms: str) -> int:
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)

def _parse_timestamp(text: str) -> datetime | None:
    m = _TIMESTAMP_RE.search(text)
    if not m:
        return None
    yr, mo, dy, hh, mm, ss, frac = m.groups()
    micro = int((frac or "0").ljust(6, "0")[:6])
    try:
        return datetime(int(yr), int(mo), int(dy), int(hh), int(mm), int(ss), micro)
    except ValueError:
        return None

def _parse_block(block: str) -> TelemetryPoint | None:
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if not lines:
        return None

    index = 0
    if lines[0].isdigit():
        index = int(lines[0])
        lines = lines[1:]
    if not lines:
        return None

    tc = _TIMECODE_RE.search(lines[0])
    if not tc:
        return None
    start_ms = _timecode_to_ms(*tc.groups()[:4])

    payload = " ".join(lines[1:])

    lat = lon = rel_alt = abs_alt = None

    if (mlat := _LAT_RE.search(payload)) and (mlon := _LON_RE.search(payload)):
        lat, lon = float(mlat.group(1)), float(mlon.group(1))
    else:
        if gps := _GPS_PAREN_RE.search(payload):
            lon, lat = float(gps.group(1)), float(gps.group(2))

    if mra := _REL_ALT_RE.search(payload):
        rel_alt = float(mra.group(1))
    if maa := _ABS_ALT_RE.search(payload):
        abs_alt = float(maa.group(1))
    if rel_alt is None and (baro := _BAROMETER_RE.search(payload)):
        rel_alt = float(baro.group(1))

    extras: dict = {}
    for key in ("iso", "shutter", "fnum", "ev", "focal_len"):
        m = re.search(rf"{key}\s*[:\s]\s*([^\]\s]+)", payload, re.IGNORECASE)
        if m:
            extras[key] = m.group(1)

    return TelemetryPoint(
        index=index,
        start_ms=start_ms,
        lat=lat,
        lon=lon,
        rel_alt=rel_alt,
        abs_alt=abs_alt,
        timestamp=_parse_timestamp(payload),
        extras=extras,
    )

def parse_srt_text(text: str) -> list[TelemetryPoint]:
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text)
    points = [p for blk in blocks if (p := _parse_block(blk)) is not None]
    points.sort(key=lambda p: p.start_ms)
    return points

def parse_srt(path: str | Path, encoding: str = "utf-8") -> list[TelemetryPoint]:
    raw = Path(path).read_bytes()
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return parse_srt_text(text)

def nearest_point(points: list[TelemetryPoint], t_ms: int) -> TelemetryPoint | None:
    if not points:
        return None
    return min(points, key=lambda p: abs(p.start_ms - t_ms))

def gps_coverage(points: list[TelemetryPoint]) -> float:
    if not points:
        return 0.0
    return sum(1 for p in points if p.has_gps) / len(points)
