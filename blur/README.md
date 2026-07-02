# blur/

**Privacy anonymization — the first stage, upstream of everything.** Before any frame is extracted,
detected, georeferenced, or written to the database, the raw drone video is run through this service to
**blur people (whole body) and redact vehicle license plates**. Nothing downstream ever sees
un-anonymized footage.

**Status:** Phase 0.5 — **implemented**. People are found with Ultralytics YOLO (COCO, `person`) and
blurred whole; license plates are found with a fine-tuned YOLOv11 plate model
(`morsetechlab/yolov11-license-plate-detection`, AGPL-3.0) and blurred tight. Each region is pixelated
(`--method blur` for Gaussian), and the video is re-encoded to **H.264 with ffmpeg** at the same fps so
frame↔telemetry sync holds. Audio is dropped; the `.SRT` is copied unchanged.

**`--vehicles`** picks vehicle handling: `plates` (default, plate-only), `whole` (blur the entire
vehicle — the safe fallback for high-altitude footage where plates are too small to detect), or `none`.
Other knobs: `--conf` (default 0.15) and `--imgsz` (default 960 — raise to 1280 for smaller/distant
objects). **Caveat:** at true drone-mapping altitude plates are only a few pixels and are often missed,
so use `--vehicles whole` when vehicle anonymity must be guaranteed.

Weights (`yolov8n.pt` + `license-plate-finetune-v1n.pt`) live in `blur/models/` (git-ignored) —
pre-baked into the Docker image, and auto-downloaded there on first local run.

## The flow

```
data/incoming/ (or SD card): raw video + .SRT
        │  blur/ (this service — watches data/incoming/)
        ▼
 YOLO detect people + license plates → blur boxes → re-encode H.264 (preserve fps) → copy .SRT sidecar
        │  verify output, then optionally wipe the SD source
        ▼
 data/anonymized/<flight>.mp4 (+ .SRT)   ← the only video the rest of the system ever sees
        │  filesystem handoff → pipeline/ ingest.py
```

The `.SRT` telemetry is copied **unchanged** and frame rate/count are preserved, so frame↔telemetry
sync still holds when `pipeline/ingest.py` later consumes the anonymized copy.

## Integration — a deliberate exception to the PostGIS-only rule

Every other service integrates **only through PostGIS**. Blur runs *before* the database is involved,
so it integrates via the **filesystem**: raw video in → clean video in `data/anonymized/`. It never
touches PostGIS and shares no code with the pipeline. It is the sole reader of raw footage.

## Run

As part of the stack (recommended) — the service watches `data/incoming/`:

```bash
docker compose up -d blur          # or `docker compose up -d` for the whole stack
cp flight.mp4 flight.SRT ../data/incoming/    # → data/anonymized/flight.mp4 (+ .SRT)
docker compose logs -f blur
```

One-off, or locally without Docker (heavy deps: ultralytics, opencv-python, numpy):

```bash
python -m venv .venv && .venv\Scripts\activate    # Windows; or: source .venv/bin/activate
pip install -r requirements.txt
python blur.py <video> [<srt>] [--output-dir ../data/anonymized] [--delete-source]
python blur.py --watch ../data/incoming           # run the watcher directly
```

`--delete-source` wipes the original **only after** the blurred output is written and verified
(verify-then-delete). Omit it to leave the source untouched.
