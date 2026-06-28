# Road Digital Twin

AI-driven road infrastructure health monitor: turns drone video of roads into a geo-referenced,
time-aware **Digital Twin** of road-surface defects (potholes, cracks). Each physical defect has a
persistent identity; every flight adds a timestamped *observation*; the system computes whether each
defect is **new / growing / stable / shrinking / repaired**.

Full project plan: [`docs/Roadmap.md`](docs/Roadmap.md).

## Architecture

```
drone video + SRT telemetry
        │
        ▼
 (1) pipeline/   Python  — frame extract → YOLO detect → georeference → dedup → match to twin → write DB
        │ writes
        ▼
     PostGIS     flights / defects / observations  (+ image crops on disk)
        │ reads
        ▼
 (2) api/        .NET ASP.NET Core — read API (/defects /flights /heatmap …)
        │ HTTP/JSON
        ▼
 (3) web/        Leaflet dashboard — map + heatmap + before/after + trends
```

## Repo layout

| Path | What | Status |
|---|---|---|
| `pipeline/` | Python ML/geo processing (runs per-flight, batch — not a hosted service) |
| `api/` | .NET read API (EF Core + Npgsql + NetTopologySuite) |
| `web/` | Leaflet dashboard |
| `db/` | `migrations/*.sql` (schema source of truth) + `migrate.py` runner |
| `docs/` | Roadmap + architecture notes |
| `data/` | Sample footage / extracted frames / crops — **git-ignored** |
| `docker-compose.yml` | Local PostGIS (api/web added later) |

## Quick start

```bash
cp .env.example .env          # adjust credentials if you like

# 1. Python pipeline env
cd pipeline
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd ..

# 2. Bring up local PostGIS (empty) and apply the schema via migrations
docker compose up -d postgis
python db/migrate.py          # applies db/migrations/*.sql; --status to inspect
```

To evolve the schema later, add a new `db/migrations/NNNN_*.sql` and re-run `python db/migrate.py` —
it applies only the new file and **preserves data**. See [`db/migrations/`](db/migrations/README.md).

> **Full reset (⚠ destroys all data — dev only):** `docker compose down -v` drops the database volume.
> `docker compose down` (without `-v`) keeps your data. After a `-v` reset, re-run `python db/migrate.py`.

> **Port 5432 already in use?** If you have a local PostgreSQL running, host connections to `5432` hit
> *it*, not the container (you'll see `password authentication failed` / `no password supplied` from
> `migrate.py`). Set a free host port in `.env` — `POSTGRES_PORT=5433` and update `DATABASE_URL`'s port
> to match — then `docker compose up -d postgis` and migrate. The container's internal port is
> unchanged; only the host mapping moves.

## Telemetry

The DJI Mini records GPS + camera metadata in a sidecar `.SRT` alongside the video.
[`pipeline/telemetry.py`](pipeline/telemetry.py) parses that track (lat/lon/rel_alt per frame) and
[`pipeline/ingest.py`](pipeline/ingest.py) syncs each extracted frame to the nearest telemetry point —
the input georeferencing needs to project pixel detections to coordinates.

Data-quality checks on real footage (GPS present and sane, altitude reasonable, frame↔telemetry
alignment) are a **manual pre-production step**, not part of the scaffold.
