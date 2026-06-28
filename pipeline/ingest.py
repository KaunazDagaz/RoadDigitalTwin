from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from telemetry import TelemetryPoint, gps_coverage, nearest_point, parse_srt

@dataclass
class FrameMatch:
    frame_path: Path
    t_ms: int
    telemetry: TelemetryPoint | None

def _require(tool: str) -> str:
    path = shutil.which(tool)
    if path is None:
        sys.exit(f"error: '{tool}' not found on PATH. Install ffmpeg (includes {tool}).")
    return path

def probe_duration_ms(video: Path) -> int:
    _require("ffprobe")
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return int(float(out) * 1000)

def extract_frames(video: Path, frames_dir: Path, fps: float) -> list[Path]:
    _require("ffmpeg")
    frames_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(frames_dir / "frame_%06d.jpg")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(video), "-vf", f"fps={fps}", pattern],
        check=True,
    )
    return sorted(frames_dir.glob("frame_*.jpg"))

def sync_frames_to_telemetry(
    frames: list[Path], telemetry: list[TelemetryPoint], fps: float
) -> list[FrameMatch]:
    interval_ms = 1000.0 / fps
    matches: list[FrameMatch] = []
    for i, frame in enumerate(frames, start=1):
        t_ms = int((i - 0.5) * interval_ms)
        matches.append(FrameMatch(frame, t_ms, nearest_point(telemetry, t_ms)))
    return matches

def print_table(matches: list[FrameMatch]) -> None:
    print(f"{'frame':<18}{'t(ms)':>8}  {'lat':>12}  {'lon':>12}  {'rel_alt':>8}")
    print("-" * 64)
    for m in matches:
        tp = m.telemetry
        lat = f"{tp.lat:.6f}" if tp and tp.lat is not None else "-"
        lon = f"{tp.lon:.6f}" if tp and tp.lon is not None else "-"
        alt = f"{tp.rel_alt:.1f}" if tp and tp.rel_alt is not None else "-"
        print(f"{m.frame_path.name:<18}{m.t_ms:>8}  {lat:>12}  {lon:>12}  {alt:>8}")

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ingest a drone flight: extract + sync frames.")
    ap.add_argument("video", type=Path, help="path to drone video (e.g. .mp4)")
    ap.add_argument("srt", type=Path, help="path to telemetry .SRT alongside the video")
    ap.add_argument("--fps", type=float, default=1.0, help="frames per second to extract")
    ap.add_argument("--frames-dir", type=Path, default=Path("../data/frames"),
                    help="output directory for extracted frames")
    args = ap.parse_args(argv)

    if not args.video.exists():
        sys.exit(f"error: video not found: {args.video}")
    if not args.srt.exists():
        sys.exit(f"error: SRT not found: {args.srt}")

    telemetry = parse_srt(args.srt)
    coverage = gps_coverage(telemetry)
    print(f"Parsed {len(telemetry)} telemetry points; GPS coverage = {coverage:.0%}\n")

    frames = extract_frames(args.video, args.frames_dir, args.fps)
    matches = sync_frames_to_telemetry(frames, telemetry, args.fps)
    print_table(matches)

    print(f"\nExtracted {len(frames)} frames, synced to telemetry (GPS coverage {coverage:.0%}).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
