# API service (.NET) — placeholder

ASP.NET Core read-only API over the shared PostGIS database. **Read-only consumer** —
it never writes; the Python pipeline is the sole writer. The two integrate only through
the database.

Planned endpoints: `GET /defects` (filter by class/status/zone/bbox), `GET /defects/{id}`
(observation history + before/after crops), `GET /heatmap`, `GET /flights`, `GET /reports`.
Plus Swagger, CORS, and static serving of image crops.
