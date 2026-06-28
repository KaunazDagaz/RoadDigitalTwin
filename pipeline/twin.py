from __future__ import annotations
from georef import GeoDetection

STATUSES = ("NEW", "GROWING", "STABLE", "SHRINKING", "REPAIRED")

def match_observation(conn, flight_id: int, obs: GeoDetection, radius_m: float = 4.0) -> int:
    raise NotImplementedError("ST_DWithin nearest match or INSERT new defect.")

def recompute_status(conn, defect_id: int) -> str:
    raise NotImplementedError("Derive GROWING/STABLE/SHRINKING from severity trend.")

def mark_repaired_outside_coverage(conn, flight_id: int) -> int:
    raise NotImplementedError("Defects within coverage_geom lacking a this-flight obs.")
