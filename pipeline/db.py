from __future__ import annotations
import os

def get_connection(database_url: str | None = None):
    database_url = database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set (see .env.example).")
    raise NotImplementedError("Open a psycopg connection to PostGIS.")


def insert_flight(conn, flown_at, drone_model, video_path, telemetry_path,
                  coverage_geom_wkt, camera_params: dict) -> int:
    raise NotImplementedError("INSERT INTO flights ... RETURNING id.")


def insert_observation(conn, defect_id: int, flight_id: int, geo, image_crop_path: str) -> int:
    raise NotImplementedError("INSERT INTO observations ... RETURNING id.")
