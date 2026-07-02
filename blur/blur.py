from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PERSON_CLASSES = ("person",)
VEHICLE_CLASSES = ("car", "truck", "bus", "motorcycle", "bicycle")
VIDEO_SUFFIXES = (".mp4", ".mov", ".avi", ".mkv")
BLUR_MARGIN = 0.08
PLATE_MARGIN = 0.25
PIXELATE_BLOCKS = 12
MODELS_DIR = Path(__file__).resolve().parent / "models"
DEFAULT_WEIGHTS = MODELS_DIR / "yolov8n.pt"
PLATE_REPO = "morsetechlab/yolov11-license-plate-detection"
PLATE_FILE = "license-plate-finetune-v1n.pt"
PLATE_WEIGHTS = MODELS_DIR / PLATE_FILE

@dataclass
class BlurRegion:
    frame_idx: int
    bbox: tuple[float, float, float, float]
    cls: str
    confidence: float

def _target_class_ids(names: dict[int, str], classes) -> set[int]:
    wanted = set(classes)
    return {i for i, name in names.items() if name in wanted}

def _expand_and_clamp(
    bbox: tuple[float, float, float, float], w: int, h: int, margin: float = BLUR_MARGIN
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    dx = (x2 - x1) * margin
    dy = (y2 - y1) * margin
    x1 = max(0, int(x1 - dx))
    y1 = max(0, int(y1 - dy))
    x2 = min(w, int(x2 + dx))
    y2 = min(h, int(y2 + dy))
    return x1, y1, x2, y2

def _redact(frame, box: tuple[int, int, int, int], method: str = "pixelate") -> None:
    import cv2

    x1, y1, x2, y2 = box
    if x2 <= x1 or y2 <= y1:
        return
    roi = frame[y1:y2, x1:x2]
    if method == "blur":
        k = max(3, (min(roi.shape[:2]) // 2) | 1)
        frame[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (k, k), 0)
    else:
        blocks = min(PIXELATE_BLOCKS, x2 - x1, y2 - y1)
        small = cv2.resize(roi, (blocks, blocks), interpolation=cv2.INTER_LINEAR)
        frame[y1:y2, x1:x2] = cv2.resize(
            small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST
        )

def load_model(weights_path: str | Path = DEFAULT_WEIGHTS):
    from ultralytics import YOLO

    return YOLO(str(weights_path))

def _ensure_plate_weights() -> Path:
    if not PLATE_WEIGHTS.exists():
        from huggingface_hub import hf_hub_download

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        hf_hub_download(PLATE_REPO, PLATE_FILE, local_dir=str(MODELS_DIR))
    return PLATE_WEIGHTS

def build_detectors(vehicles: str = "plates", weights: str | Path = DEFAULT_WEIGHTS):
    coco = load_model(weights)
    if vehicles == "whole":
        return [(coco, frozenset(PERSON_CLASSES) | frozenset(VEHICLE_CLASSES), BLUR_MARGIN)]
    detectors = [(coco, frozenset(PERSON_CLASSES), BLUR_MARGIN)]
    if vehicles == "plates":
        detectors.append((load_model(_ensure_plate_weights()), None, PLATE_MARGIN))
    return detectors

def detect_regions(
    model, frame, classes, conf: float = 0.15, frame_idx: int = 0, imgsz: int = 960
) -> list[BlurRegion]:
    targets = None if classes is None else _target_class_ids(model.names, classes)
    result = model.predict(frame, conf=conf, imgsz=imgsz, verbose=False)[0]
    regions: list[BlurRegion] = []
    for b in result.boxes:
        cls_id = int(b.cls)
        if targets is not None and cls_id not in targets:
            continue
        x1, y1, x2, y2 = (float(v) for v in b.xyxy[0].tolist())
        regions.append(BlurRegion(frame_idx, (x1, y1, x2, y2), model.names[cls_id], float(b.conf)))
    return regions

def blur_video(
    input_video: Path, output_video: Path, detectors,
    conf: float = 0.15, method: str = "pixelate", imgsz: int = 960,
) -> int:
    import cv2

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg not found on PATH (needed to encode the blurred video).")

    cap = cv2.VideoCapture(str(input_video))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {input_video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    proc: subprocess.Popen | None = None
    w = h = 0
    frames = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if proc is None:
                h, w = frame.shape[:2]
                proc = subprocess.Popen(
                    [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                     "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                     "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                     "-pix_fmt", "yuv420p", str(output_video)],
                    stdin=subprocess.PIPE,
                )
            for model, classes, margin in detectors:
                for region in detect_regions(model, frame, classes, conf, frames, imgsz):
                    _redact(frame, _expand_and_clamp(region.bbox, w, h, margin), method)
            proc.stdin.write(frame.tobytes())
            frames += 1
    finally:
        cap.release()
        rc = 0
        if proc is not None:
            proc.stdin.close()
            rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg encoding failed (exit {rc}) for {output_video}")
    return frames

def anonymize_flight(
    input_video: Path, output_dir: Path, srt: Path | None = None, delete_source: bool = False,
    conf: float = 0.15, method: str = "pixelate", weights: str | Path = DEFAULT_WEIGHTS,
    imgsz: int = 960, vehicles: str = "plates",
) -> Path:
    import cv2

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / input_video.name

    detectors = build_detectors(vehicles, weights)
    frames_written = blur_video(input_video, out, detectors, conf, method, imgsz)

    if srt is None:
        candidate = input_video.with_suffix(".SRT")
        srt = candidate if candidate.exists() else None
    if srt is not None:
        shutil.copy2(srt, output_dir / srt.name)

    check = cv2.VideoCapture(str(out))
    out_frames = int(check.get(cv2.CAP_PROP_FRAME_COUNT)) if check.isOpened() else 0
    check.release()
    if not (out.exists() and out.stat().st_size > 0 and frames_written > 0 and out_frames > 0):
        raise RuntimeError(f"blur output failed verification: {out}")

    if delete_source:
        input_video.unlink()
        if srt is not None and srt.exists():
            srt.unlink()
    return out

def watch_incoming(
    indir: Path, output_dir: Path, conf: float = 0.15, delete_source: bool = False,
    method: str = "pixelate", weights: str | Path = DEFAULT_WEIGHTS, imgsz: int = 960,
    vehicles: str = "plates", poll_s: float = 5.0,
) -> None:
    indir.mkdir(parents=True, exist_ok=True)
    print(f"watching {indir} for videos (poll {poll_s:.0f}s)", flush=True)
    seen: set[Path] = set()
    while True:
        for video in sorted(indir.iterdir()):
            if video in seen or video.suffix.lower() not in VIDEO_SUFFIXES:
                continue
            seen.add(video)
            srt = video.with_suffix(".SRT")
            print(f"found {video.name} -> anonymizing", flush=True)
            try:
                out = anonymize_flight(
                    video, output_dir, srt if srt.exists() else None,
                    delete_source, conf, method, weights, imgsz, vehicles,
                )
                print(f"wrote {out}", flush=True)
            except Exception as e:
                print(f"error anonymizing {video.name}: {e}", flush=True)
        time.sleep(poll_s)

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Anonymize a drone flight: blur people + license plates before any processing."
    )
    ap.add_argument("video", type=Path, nargs="?",
                    help="path to raw drone video (one-off mode; e.g. on the SD card)")
    ap.add_argument("srt", type=Path, nargs="?",
                    help="path to telemetry .SRT alongside the video (copied unchanged)")
    ap.add_argument("--watch", type=Path,
                    help="watch this directory and anonymize any video dropped in (runs until stopped)")
    ap.add_argument("--output-dir", type=Path, default=Path("../data/anonymized"),
                    help="where to write the blurred video + copied .SRT")
    ap.add_argument("--conf", type=float, default=0.15, help="YOLO confidence threshold")
    ap.add_argument("--imgsz", type=int, default=960,
                    help="YOLO inference size; raise (e.g. 1280) to catch smaller/distant objects")
    ap.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS,
                    help="Ultralytics YOLO (COCO) weights for people/vehicles")
    ap.add_argument("--vehicles", choices=("plates", "whole", "none"), default="plates",
                    help="vehicle handling: blur license plates only, whole vehicles, or leave them")
    ap.add_argument("--method", choices=("pixelate", "blur"), default="pixelate",
                    help="how to redact each box (default: pixelate)")
    ap.add_argument("--delete-source", action="store_true",
                    help="delete the original video AFTER the blurred output is verified")
    args = ap.parse_args(argv)

    if args.watch is not None:
        if args.video is not None:
            sys.exit("error: pass either a video or --watch <dir>, not both")
        watch_incoming(args.watch, args.output_dir, args.conf, args.delete_source,
                       args.method, args.weights, args.imgsz, args.vehicles)
        return 0

    if args.video is None:
        sys.exit("error: provide a video path, or --watch <dir> to run as a service")
    if not args.video.exists():
        sys.exit(f"error: video not found: {args.video}")
    if args.srt is not None and not args.srt.exists():
        sys.exit(f"error: SRT not found: {args.srt}")

    out = anonymize_flight(args.video, args.output_dir, args.srt, args.delete_source,
                           args.conf, args.method, args.weights, args.imgsz, args.vehicles)
    print(f"Anonymized video written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
