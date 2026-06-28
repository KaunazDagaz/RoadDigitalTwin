from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Detection:
    defect_class: str
    confidence: float
    bbox: tuple[float, float, float, float]


def load_model(weights_path: str | Path):
    raise NotImplementedError("Load Ultralytics YOLO weights here.")


def detect_frame(model, frame_path: str | Path, conf: float = 0.25) -> list[Detection]:
    raise NotImplementedError("Run model inference and map results to Detection.")
