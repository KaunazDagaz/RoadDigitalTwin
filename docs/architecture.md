# Architecture

Full project plan: [`Roadmap.md`](Roadmap.md).

## Components

```
raw drone video + .SRT telemetry
        │
        ▼
 blur/ (Python)  — blur people + license plates (YOLO) → clean video + copied .SRT   ⟵ runs first
        │ clean video on disk (filesystem handoff — never the DB)
        ▼
 pipeline/ (Python)  — frame extract → YOLO detect → georeference → dedup → match to twin → write DB
        │ writes
        ▼
 PostGIS  — flights / defects / observations  (+ image crops on disk)
        │ reads
        ▼
 api/ (.NET)  — read-only API (/defects /flights /heatmap …)
        │ HTTP/JSON
        ▼
 web/ (Leaflet)  — map + heatmap + before/after + trends
```

- **blur/** — its own container, started with the stack (`docker compose up`). Watches
  `data/incoming/` and is the sole reader of **raw** footage: blurs whole people (Ultralytics YOLO,
  COCO) and redacts vehicle license plates (a fine-tuned YOLOv11 plate model), and writes a clean,
  anonymized video (plus the unchanged `.SRT`) to `data/anonymized/`. Runs *before* the pipeline;
  nothing downstream sees un-anonymized frames.
- **pipeline/** — Python batch job, run per flight. Ingests the **anonymized** video + telemetry,
  detects defects, georeferences them, deduplicates within the flight, matches to the persistent twin,
  and writes to PostGIS. The only writer.
- **PostGIS** — the shared store: `flights`, `defects`, `observations` tables plus image crops on disk.
- **api/** — ASP.NET Core read-only API (EF Core + Npgsql + NetTopologySuite) serving defects, flights,
  heatmap, and reports over HTTP/JSON.
- **web/** — Leaflet dashboard: map, severity heatmap, flight/time selector, before/after crops, trends.

## Integration

The pipeline and the API communicate only through PostGIS (plus the shared image-crop folder). The
pipeline writes; the API reads. They make no direct calls to each other.

**blur/ is the one deliberate exception.** It runs before the database exists in the flow, so it can't
integrate through PostGIS — it hands off via the **filesystem** (clean video in `data/anonymized/`,
`.SRT` copied unchanged). It shares no code with the pipeline and never touches the DB; the pipeline
simply ingests the file blur produced.

## Privacy blur

Drone footage inevitably captures identifiable people and vehicles. To avoid storing or processing raw
personal data (a privacy/GDPR concern, especially once cloud-hosted), the raw video is anonymized
**first**, before any frame is extracted, detected, or written.

- **People whole-blurred, vehicles plate-only.** People are blurred by their full COCO bounding box.
  Vehicles are left visible with only the **license plate** redacted (a fine-tuned YOLOv11 plate model,
  AGPL-3.0, reusing the Ultralytics stack). Because plates shrink to a few unreadable pixels at
  drone-mapping altitude and are then easily missed, `--vehicles whole` falls back to blurring the
  entire vehicle when anonymity must be guaranteed.
- **Verify-then-delete.** The blur CLI can wipe the original off the SD card, but only after the
  anonymized output is written and validated (`--delete-source`). Deletion is irreversible, so it is
  gated behind an explicit flag and never runs before verification.
- **Separate container.** Blur is its own service/image (peer to api/pipeline/web), keeping its heavy
  YOLO/OpenCV deps isolated and letting the "insert SD → blur → wipe" desktop UX wrap it later without
  entangling the pipeline.

## Data model

PostGIS, `geometry(Point/Polygon, 4326)`. Source of truth: [`../db/migrations/`](../db/migrations/).

- **flights** — one row per drone flight: when it flew, the surveyed area (`coverage_geom`), camera
  params, and source paths.
- **defects** — the persistent twin identity, one per physical defect: best location (`geom`), class,
  `status` (NEW | GROWING | STABLE | SHRINKING | REPAIRED), `current_severity_m2`, and first/last seen
  flight.
- **observations** — one row per (defect × flight) detection: location, class, confidence,
  `severity_m2`, bbox, image-crop path, and timestamp.

Geometry is SRID 4326 (WGS84 lon/lat); every geometry column has a GiST index. A defect is REPAIRED
when it lies inside a new flight's `coverage_geom` but receives no matching observation that flight.

## Telemetry

The DJI Mini records GPS + camera metadata in a sidecar `.SRT`. `pipeline/telemetry.py` parses it
(lat/lon/rel_alt per frame) and `pipeline/ingest.py` syncs each extracted frame to the nearest
telemetry point — the position input georeferencing uses to project detections to coordinates.
