from __future__ import annotations
from dataclasses import dataclass
from detect import Detection
from telemetry import TelemetryPoint

@dataclass
class GeoDetection:
    lat: float
    lon: float
    severity_m2: float
    defect_class: str
    confidence: float

def ground_sample_distance(rel_alt_m: float, hfov_deg: float, image_width_px: int) -> float:
    raise NotImplementedError("W = 2*H*tan(HFOV/2); return W / image_width_px.")

def course_over_ground(prev: TelemetryPoint, curr: TelemetryPoint) -> float:
    raise NotImplementedError("Bearing from prev→curr lat/lon.")

def project_detection(
    det: Detection,
    telemetry: TelemetryPoint,
    heading_deg: float,
    hfov_deg: float,
    image_size_px: tuple[int, int],
) -> GeoDetection:
    raise NotImplementedError("Pixel offset → metric → rotate → pyproj add.")
