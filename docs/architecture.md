# Architecture

Full project plan: [`Roadmap.md`](Roadmap.md).

## Components

```
drone video + .SRT telemetry
        │
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

- **pipeline/** — Python batch job, run per flight. Ingests a video + telemetry, detects defects,
  georeferences them, deduplicates within the flight, matches to the persistent twin, and writes to
  PostGIS. The only writer.
- **PostGIS** — the shared store: `flights`, `defects`, `observations` tables plus image crops on disk.
- **api/** — ASP.NET Core read-only API (EF Core + Npgsql + NetTopologySuite) serving defects, flights,
  heatmap, and reports over HTTP/JSON.
- **web/** — Leaflet dashboard: map, severity heatmap, flight/time selector, before/after crops, trends.

## Integration

The pipeline and the API communicate only through PostGIS (plus the shared image-crop folder). The
pipeline writes; the API reads. They make no direct calls to each other.

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
