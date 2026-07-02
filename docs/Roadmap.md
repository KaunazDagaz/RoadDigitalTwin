# Roadmap — AI-Driven Road Infrastructure Health Monitor & Digital Twin

## Context

This is a **greenfield diploma project**: an automated pipeline that turns drone video of roads into a
geo-referenced, time-aware inventory of road-surface defects (potholes, cracks). The headline contribution
is a **Digital Twin**: each physical defect has a persistent identity, every flight adds a timestamped
*observation* of it, and the system computes whether each defect is **new / growing / stable / shrinking /
repaired** — visualized for a municipality as a map + severity **heatmap**, with before/after imagery.

Decisions locked in with the user:
- **Stack:** Python for the ML/geo **processing pipeline**; **.NET (ASP.NET Core)** for the **read API**;
  JS/**Leaflet** dashboard. All three share one **PostGIS** database (Python writes, .NET reads/serves).
- **Timeline:** ~4–6 months (~20 weeks, phases overlap).
- **Centerpiece:** the temporal Digital Twin (persistent defects + observation history + progress), built on
  a reliable detection + georeferencing foundation.
- **Data:** Hybrid — prototype on a public aerial dataset, then fine-tune on own labeled drone frames.
- **Hardware:** **DJI Mini 4K**. Software must be **drone-agnostic** — it only consumes
  a video file + a telemetry track (GPS/altitude per timestamp). Everything must be **free / open-source**.

---

## Architecture (decoupled, DB-centric)

```
[Drone] --raw video.mp4 + SRT ------->   ┌──────────────────────────────┐
                                         │ (0) PRIVACY BLUR — own service │  blur people + plates FIRST
                                         │  raw video → YOLO(COCO) → clean│  (watches data/incoming/)
                                         └──────────────┬───────────────┘
                                                        │ clean video + copied .SRT (filesystem handoff)
                                         ┌──────────────▼───────────────┐
                                         │ (1) PYTHON PROCESSING PIPELINE │  run per flight (CLI/batch)
                                         │  ingest → frames+telemetry sync │
                                         │  → YOLO detect → georeference   │
                                         │  → intra-flight dedup           │
                                         │  → match to twin / write DB     │
                                         └──────────────┬───────────────┘
                                                        │ writes
                                            ┌───────────▼───────────┐
                                            │   PostGIS database     │  flights / defects / observations
                                            │   + image crops (disk) │
                                            └───────────┬───────────┘
                                                        │ reads
                                         ┌──────────────▼───────────────┐
                                         │ (2) .NET ASP.NET CORE READ API │  EF Core + Npgsql + NetTopologySuite
                                         │  /defects /flights /heatmap …  │
                                         └──────────────┬───────────────┘
                                                        │ HTTP/JSON
                                         ┌──────────────▼───────────────┐
                                         │ (3) LEAFLET DASHBOARD (JS)     │  map + heatmap + before/after + trends
                                         └────────────────────────────────┘
```

The Python pipeline and the .NET API never call each other — they integrate **only through PostGIS** (and a
shared image-crop folder). This keeps the two languages cleanly separated and each independently testable.

The **privacy-blur** service sits upstream of all of this: it is the sole reader of raw footage and hands the
pipeline a clean, anonymized video via the **filesystem** (never the DB) — a deliberate exception to the
PostGIS-only rule, since blur runs before the database is involved.

---

## Data model (the Digital Twin)

Three core tables (PostGIS, `geometry(Point/Polygon, 4326)`):

- **`flights`** — one row per drone flight: `id, flown_at, drone_model, video_path, telemetry_path,
  coverage_geom (Polygon — area actually surveyed), camera_params, created_at`.
- **`defects`** — the **persistent twin identity** (one per physical defect): `id, geom (Point, best
  location), defect_class, status (NEW|GROWING|STABLE|SHRINKING|REPAIRED), current_severity_m2,
  first_seen_flight, last_seen_flight, created_at, updated_at`.
- **`observations`** — one row per (defect × flight) detection: `id, defect_id FK, flight_id FK, geom (Point),
  defect_class, confidence, severity_m2, bbox, image_crop_path, observed_at`.

This directly satisfies your vision:
- "write defects in DB, municipality retrieves them" → `defects` + .NET API.
- "compare new flight to old" → matching step links new observations to existing `defects`.
- "see how it looked last time" → the previous `observations` row + its `image_crop_path` (before/after = last
  two observations).
- "digital twin showing progress / heatmap" → `status` + `current_severity_m2` + observation history →
  heatmap & per-defect trend chart.

GiST spatial indexes on all `geom`. "Repaired" is inferred when a `defect` lies inside a new flight's
`coverage_geom` but gets **no** matching observation that flight.

---

## Tech stack (all free / open-source)

| Concern | Choice | License / note |
|---|---|---|
| Privacy blur | **Ultralytics YOLO (COCO + plate) + OpenCV + ffmpeg** — blur people + license plates, H.264 out | OSS — own container, runs first |
| Frame extraction | **ffmpeg** | free |
| Telemetry parse | custom Python SRT parser (regex) | — |
| Detection model | **Ultralytics YOLOv8/v11** (n/s) | **AGPL-3.0** — free & OSS; fine for a thesis. (Permissive alt: MMDetection/Detectron2, Apache-2.0, harder.) |
| Training compute | **Google Colab / Kaggle** free GPU | free tier |
| Annotation | **CVAT** or **Label Studio** | OSS (fully open, unlike Roboflow's free tier) |
| Geo math | **pyproj, shapely, geopandas, OpenCV** | OSS |
| Dedup clustering | **scikit-learn DBSCAN** | OSS |
| Database | **PostgreSQL + PostGIS** | OSS — local Docker `postgis/postgis`; **Neon** free tier for cloud |
| API | **ASP.NET Core** + EF Core + **Npgsql** + **NetTopologySuite** | MIT, OSS |
| Frontend | **Leaflet** + **Leaflet.heat** + **Chart.js**, **OSM** tiles | BSD/MIT, free tiles |
| Reporting | **Python WeasyPrint/Jinja2** → PDF, or CSV | OSS |
| Image storage | local folder served statically (stretch: **MinIO**, OSS S3) | OSS |
| Orthomosaic (stretch) | **OpenDroneMap (ODM)** | OSS |

---

## Key technical designs

**Telemetry sync.** DJI Fly writes an `.SRT` subtitle track alongside the video with per-frame
`[latitude] [longitude] [rel_alt/abs_alt]` (+ iso/shutter/focal). Parse SRT → table of
`(timecode, lat, lon, rel_alt)`; extract frames with ffmpeg at a fixed interval; match each frame to the
nearest telemetry timestamp (interpolate if needed). **Heading** (for pixel rotation) is often *not* in the
Mini's SRT — derive it as course-over-ground from consecutive GPS fixes.

**Pixel → GPS georeferencing** (nadir gimbal −90°, flat-ground assumption):
- Ground sample distance from altitude + camera FOV: `W = 2·H·tan(HFOV/2)`, `mpp = W / image_width_px`
  (H = `rel_alt` ≈ AGL when takeoff is at road level). DJI Mini 4K ≈ 1/2.3" sensor, ~82° **diagonal** FOV,
  4K = 3840×2160 — derive H/V FOV from 16:9; **verify exact FOV per recording mode**.
- Pixel offset from image center × `mpp` → metric east/north offset → rotate by heading → add to drone
  lat/lon via pyproj (local UTM/azimuthal). Accuracy ≈ a few metres (GPS + altitude + non-perfect nadir).
- **Rigorous option:** one-time OpenCV camera calibration (intrinsics + distortion) instead of the FOV
  approximation — quantify the accuracy gain and report it in the thesis.
- **Severity** = `bbox_area_px × mpp²` → defect area in m² (the magnitude tracked over time).

**Intra-flight dedup.** A pothole appears in many consecutive frames → many detections at ~same GPS. Cluster
projected coordinates with **DBSCAN** (eps ≈ 1–3 m), collapse each cluster to one observation (centroid +
median/max severity). → one observation per physical defect per flight.

**Temporal matching (the twin).** For each new observation, PostGIS nearest-neighbor (`ST_DWithin`, ~3–5 m,
same class): match → append observation to existing `defect` and recompute `status`/severity trend from
history; no match → create new `defect` (status NEW). Coverage-without-detection → REPAIRED.

---

## Phased roadmap (~20 weeks; phases overlap)

### Phase 0 — De-risk & scaffold (Weeks 1–2)
- **#1 RISK FIRST:** obtain a **real DJI Mini 4K video + SRT** (borrow a drone, or find a public Mini 4K
  sample) and **confirm GPS lat/lon is present in the SRT**. If absent → fallback: shoot **photos** (EXIF GPS)
  or log a separate GPS track. *Do not build on an unverified assumption.*
- Monorepo scaffold: `/pipeline` (Python), `/api` (.NET), `/web` (JS), `/db` (migrations), `/docs`; git.
- Provision PostGIS (local Docker + Neon free tier); `CREATE EXTENSION postgis`.
- Validate ffmpeg frame extraction + first SRT parser → per-frame `(t, lat, lon, alt)` table.

### Phase 0.5 — Privacy blur (anonymization pre-processing) — done
- **Runs before everything.** Blur people and vehicle license plates in the raw video so nothing
  downstream ever sees un-anonymized footage (privacy/GDPR — matters especially once cloud-hosted).
- Own **separate container** (`blur/`), started with the stack — watches `data/incoming/` and writes
  `data/anonymized/`; integrates via the **filesystem**, not PostGIS.
- **Ultralytics YOLO** blurs whole people (COCO `person`) and redacts **license plates** (a fine-tuned
  YOLOv11 plate model); `--vehicles whole` falls back to whole-vehicle blur for high-altitude footage.
  Re-encode to **H.264 with ffmpeg** preserving fps; copy the `.SRT` sidecar unchanged so
  frame↔telemetry sync survives. Point `ingest.py` at the anonymized copy in `data/anonymized/`.
- **Verify-then-delete:** wipe the original off the SD card only after the blurred output is validated
  (`--delete-source`). The desktop "insert SD → blur → wipe" UX is a thin future driver over this CLI.

### Phase 1 — Detection model (Weeks 3–6, overlaps P2)
- Hybrid data: pull a public **aerial** pothole/road-damage set (Roboflow Universe) → train YOLOv8n/s on
  Colab/Kaggle → baseline mAP. (Note: most public sets like **RDD2022 are street-level dashcam**, not
  top-down — prefer aerial sets, then fine-tune on own frames.)
- Stand up CVAT/Label Studio; label a small set of **your own** drone frames; fine-tune. Export `.pt`
  (Python inference) + ONNX (portability).

### Phase 2 — Georeferencing pipeline (Weeks 5–8)
- Implement GSD/offset/heading/pyproj pixel→GPS + severity (m²). Intra-flight DBSCAN dedup.
- **Validate accuracy** at a test site (compare to hand-measured GPS) → report error bounds.

### Phase 3 — Database & twin logic (Weeks 7–11)
- PostGIS schema + migrations (flights/defects/observations + coverage). Pipeline writes observations;
  matching links to/creates defects, computes status + trend; REPAIRED via coverage. Save image crops.
- **End-to-end test: two flights over the same road → confirm progress is computed.**

### Phase 4 — .NET read API (Weeks 10–13)
- ASP.NET Core + EF Core + Npgsql + NetTopologySuite. Endpoints: `GET /defects` (filter by class/status/
  zone/bbox), `GET /defects/{id}` (history + before/after crops), `GET /heatmap`, `GET /flights`,
  `GET /reports`. Swagger + CORS. Serve image crops as static files.

### Phase 5 — Leaflet dashboard (Weeks 12–16)
- OSM map; defect markers colored by status; **severity heatmap** (Leaflet.heat); **flight/time selector**
  for the temporal view; detail panel with **before/after crops** + **trend chart** (Chart.js); filters;
  report download.

### Phase 6 — Reporting, evaluation, write-up (Weeks 15–20)
- Automated **prioritized repair report** (PDF/CSV) by severity/trend/zone.
- **System evaluation** (thesis numbers): detection mAP, georef accuracy (m), dedup correctness, temporal
  matching accuracy.
- `docker-compose` (postgis + api + web), README, demo video, thesis writing throughout.

**Stretch:** ODM orthomosaic basemap; weather/traffic data layers; auth/roles for municipality users
(multi-tenant); deploy to Azure/AWS free tier.

---

## Repo structure (files to create)

```
/blur (Python)       blur.py (YOLO people/vehicle blur), requirements.txt, Dockerfile, models/<weights>
/pipeline (Python)   requirements.txt, ingest.py (orchestrator), telemetry.py (SRT+sync),
                     detect.py (YOLO), georef.py (pixel→GPS/GSD), dedup.py (DBSCAN),
                     twin.py (match+trend+status), db.py (SQLAlchemy/psycopg), models/<weights>
/api (.NET)          Program.cs, appsettings.json, Data/AppDbContext.cs (UseNetTopologySuite),
                     Models/{Flight,Defect,Observation}.cs, Controllers/{Defects,Flights,Heatmap,Reports}
/web                 index.html, map.js (Leaflet + Leaflet.heat), charts.js (Chart.js)
/db                  schema.sql / migrations (PostGIS)
docker-compose.yml   postgis + blur + api + web   README.md
```

---

## Key risks & mitigations

1. **SRT GPS availability on Mini 4K** (highest) → verify in Phase 0; fallback to photo/EXIF or separate GPS log.
2. **Dataset domain mismatch** (street-level vs aerial) → hybrid + own labeling; prefer aerial sources.
3. **Georeferencing accuracy** → nadir + flat-ground assumption; validate against ground truth; document error.
4. **Heading missing from SRT** → derive course-over-ground from consecutive GPS fixes.
5. **"Repaired" detection** → requires per-flight `coverage_geom`; only conclude repaired inside surveyed area.
6. **Free training GPU** → Colab/Kaggle.
7. **Ultralytics AGPL-3.0** → fine for a diploma; note it (permissive alt exists if ever needed).

---

## Verification (end-to-end)

1. **Pipeline:** run `ingest.py` on two sample flights over the same road → assert `defects`, `observations`,
   and `coverage_geom` rows exist; the second flight links observations to existing defects and sets correct
   `status` (e.g. GROWING / REPAIRED); image crops written.
2. **API:** hit Swagger/curl — `/defects` returns geo-points with filters; `/defects/{id}` returns observation
   history + before/after crop URLs; `/heatmap` returns weighted points.
3. **Dashboard:** load the map → markers colored by status, heatmap toggles, time/flight selector switches the
   temporal view, detail panel shows before/after + trend, report downloads.
4. **Metrics:** record detection mAP, georef error (m), dedup precision/recall, temporal match accuracy.
```
