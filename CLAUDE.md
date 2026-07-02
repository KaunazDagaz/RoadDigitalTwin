# CLAUDE.md

Guidance for AI agents working in this repo. Keep it current as the project evolves.

## What this is

**Road Digital Twin** — an automated pipeline that turns drone video of roads into a geo-referenced,
time-aware **Digital Twin** of road-surface defects (potholes, cracks). Each physical defect has a
persistent identity; every flight adds a timestamped *observation*; the system computes whether a
defect is **NEW / GROWING / STABLE / SHRINKING / REPAIRED**, and surfaces it on a map + heatmap with
before/after imagery.

Before any of that, raw video is **anonymized first** — people are blurred and vehicle license plates
redacted (see `blur/`) so nothing downstream ever processes un-anonymized footage.

It's a greenfield diploma project. Full plan: [`docs/Roadmap.md`](docs/Roadmap.md). Key decisions and
their rationale: [`docs/architecture.md`](docs/architecture.md).

## Architecture — the rule that matters most

**DB-centric: three decoupled services that integrate ONLY through PostGIS** — plus an upstream `blur/`
service that runs first and hands off via the **filesystem** (the one deliberate exception, since it
runs before the DB). The Python pipeline and the .NET API never call each other — no HTTP, no shared
code, no imports across the boundary.

```
raw drone video + .SRT telemetry
        │
        ▼
 blur/ (Python)  — blur people + license plates (YOLO) → clean video + copied .SRT   ⟵ runs first
        │ clean video on disk (filesystem handoff — never the DB)
        ▼
 pipeline/ (Python)  — frame extract → YOLO detect → georeference → dedup → match to twin → WRITE DB
        │ writes
        ▼
 PostGIS  — flights / defects / observations  (+ image crops on disk)
        │ reads
        ▼
 api/ (.NET)  — READ-ONLY API (/defects /flights /heatmap …)
        │ HTTP/JSON
        ▼
 web/ (Leaflet)  — map + heatmap + before/after + trends
```

The SQL files in `db/migrations/` are the **single source of truth** for the shared data model, applied
by `db/migrate.py`. The pipeline is the sole
**writer**; the API is a read-only **consumer** whose EF Core entities mirror these tables.

## Repo map

| Path | What | Status |
|---|---|---|
| `blur/` | Python privacy blur (people + license plates), own container, **runs first** | `blur.py` implemented (Phase 0.5) |
| `pipeline/` | Python processing (batch, per-flight — not a hosted service) | `telemetry.py`, `ingest.py` real; rest stubbed |
| `api/` | .NET read API (EF Core + Npgsql + NetTopologySuite) | placeholder README (Phase 4) |
| `web/` | Leaflet dashboard (static site) | shell `index.html` only (Phase 5) |
| `db/` | `migrations/*.sql` (schema source of truth) + `migrate.py` runner | done |
| `docs/` | `Roadmap.md` (plan), `architecture.md` (decisions) | — |
| `data/` | drone footage / incoming / anonymized / frames / crops | **git-ignored** (only `data/README.md` tracked) |
| `docker-compose.yml` | local PostGIS + `blur` (watches `data/incoming`); api/web added later | done |

## Phase status

**Phases 0 (scaffold) and 0.5 (privacy blur) are done.** Real, working code: `pipeline/telemetry.py`
(SRT parser + frame sync, tested), `pipeline/ingest.py` (ffmpeg extract + sync), and `blur/blur.py`
(YOLO person-blur + license-plate blur → clean video, tested helpers). The rest of `pipeline/` —
`detect.py`, `georef.py`, `dedup.py`, `twin.py`, `db.py` — is an intentional **stub** that raises
`NotImplementedError` with the phase it belongs to.

**Do not implement later-phase logic unless asked.** Phases: **0.5 privacy blur (done)**, 1 detection
(YOLO), 2 georeferencing + dedup, 3 DB write + twin matching, 4 .NET API, 5 Leaflet dashboard,
6 reporting/eval. See the Roadmap.

## Development rules

- **Monorepo with service folders — not submodules.** Folders give per-service isolation; keep
  cross-service changes atomic in one commit. Don't reach for submodules.
- **Respect the service boundary.** Pipeline writes, API reads. Never make them call each other or
  share code; the database is the contract. `blur/` is upstream of both and integrates via the
  **filesystem** (clean video on disk), never the DB — the sole, documented exception to the
  PostGIS-only rule (it runs before the DB is involved).
- **Dependency hygiene.** Lightweight modules (`telemetry.py`, `ingest.py`) are **stdlib-only** on
  purpose so they stay importable/testable without the heavy stack. Heavy geo/ML deps
  (`pyproj`, `shapely`, `geopandas`, `opencv-python`, `ultralytics`, `scikit-learn`) belong only in
  the modules that actually need them. Add new deps to `pipeline/requirements.txt`. The `blur/` service
  has its **own** `blur/requirements.txt` (heavy subset: `ultralytics`, `opencv-python`, `numpy`) — add
  blur deps there, not to the pipeline's.
- **Geometry conventions** (mirror `db/migrations/`): all geometry is **SRID 4326** (WGS84 lon/lat);
  every geometry column gets a **GiST** index. Note coordinate order: PostGIS/GeoJSON is lon/lat,
  but the DJI `GPS(lon,lat,sats)` SRT field is already handled in `telemetry.py` — don't re-swap.
- **Free / open-source only.** Every tool/library/host must have a free tier or OSS license (project
  constraint). No paid services.
- **Risk checks are manual.** Data-quality verification on real footage (GPS present/sane, altitude,
  frame↔telemetry alignment) is a pre-production step done by hand — do **not** bake it into code as a
  pass/fail gate. `gps_coverage()` is informational only.
- **Never commit drone footage.** `data/` is git-ignored except its README.

## Common commands

```bash
# Python pipeline env (from pipeline/)
python -m venv .venv && .venv\Scripts\activate     # Windows; or: source .venv/bin/activate
pip install -r requirements.txt

# Tests — run from pipeline/. conftest.py puts the modules on sys.path.
pytest

# Local PostGIS — comes up empty; schema is applied by migrations.
docker compose up -d postgis
python db/migrate.py          # apply pending migrations (run from repo root); --status to inspect
docker compose down           # stop, KEEP data
docker compose down -v        # ⚠ DESTROYS all data (drops the volume) — dev reset only; re-run migrate.py after

# Anonymize a flight FIRST — the blur service watches data/incoming/ and writes data/anonymized/
docker compose up -d blur                          # runs with the stack; drop videos into data/incoming/
cp sample.mp4 sample.SRT data/incoming/            # → data/anonymized/sample.mp4 (+ .SRT)
# one-off instead of the watcher:  docker compose run --rm blur /data/incoming/sample.mp4

# Ingest the ANONYMIZED copy (when footage is available; from pipeline/)
python ingest.py ../data/anonymized/sample.mp4 ../data/anonymized/sample.SRT
```

## Conventions for agents

- **No comments, no docstrings.** The codebase is deliberately comment- and docstring-free — it reads
  as self-documenting code (clear names + type hints). Do **not** add `#` comments, `--` SQL comments,
  or docstrings; if something needs explaining, put it in the docs (`docs/`, a README), not inline.
- **Match the surrounding style** — read the neighboring module before adding code; mirror its naming
  and `from __future__ import annotations` + type-hint usage.
- **Schema changes are paired changes.** Add a new `db/migrations/NNNN_*.sql` (never edit an applied
  migration) and update the dependent pipeline writer (`db.py`) and, later, the API's EF entities in
  the same change. Apply with `python db/migrate.py`.
- **Tests** live in `pipeline/tests/` with fixtures under `pipeline/tests/fixtures/`. Add a test when
  you add behavior; keep them stdlib + pytest only.
- **Commit only when the user asks.** The repo is on `main` with no commits yet. If asked to commit,
  prefer a feature branch first. Don't commit, push, or amend unprompted.
- **Environment:** Windows + PowerShell (a Bash tool is also available). Mind LF↔CRLF; if it becomes
  noisy, propose a `.gitattributes` rather than silently reformatting files.
