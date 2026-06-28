from __future__ import annotations
from georef import GeoDetection

def deduplicate(
    detections: list[GeoDetection], eps_m: float = 2.0, min_samples: int = 2
) -> list[GeoDetection]:
    raise NotImplementedError(
        "Project to a local metric CRS, DBSCAN(eps_m), collapse each cluster."
    )
