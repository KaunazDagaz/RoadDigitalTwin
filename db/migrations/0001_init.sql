CREATE EXTENSION IF NOT EXISTS postgis;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'defect_status') THEN
        CREATE TYPE defect_status AS ENUM (
            'NEW', 'GROWING', 'STABLE', 'SHRINKING', 'REPAIRED'
        );
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS flights (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    flown_at        TIMESTAMPTZ      NOT NULL,
    drone_model     TEXT,
    video_path      TEXT,
    telemetry_path  TEXT,
    coverage_geom   geometry(Polygon, 4326),
    camera_params   JSONB,
    created_at      TIMESTAMPTZ      NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS defects (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    geom                geometry(Point, 4326)   NOT NULL,
    defect_class        TEXT                    NOT NULL,
    status              defect_status           NOT NULL DEFAULT 'NEW',
    current_severity_m2 DOUBLE PRECISION,
    first_seen_flight   BIGINT REFERENCES flights(id),
    last_seen_flight    BIGINT REFERENCES flights(id),
    created_at          TIMESTAMPTZ             NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ             NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS observations (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    defect_id       BIGINT          NOT NULL REFERENCES defects(id) ON DELETE CASCADE,
    flight_id       BIGINT          NOT NULL REFERENCES flights(id) ON DELETE CASCADE,
    geom            geometry(Point, 4326)   NOT NULL,
    defect_class    TEXT            NOT NULL,
    confidence      REAL,
    severity_m2     DOUBLE PRECISION,
    bbox            JSONB,
    image_crop_path TEXT,
    observed_at     TIMESTAMPTZ     NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_flights_coverage_geom  ON flights      USING GIST (coverage_geom);
CREATE INDEX IF NOT EXISTS idx_defects_geom           ON defects      USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_observations_geom      ON observations USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_observations_defect_id ON observations (defect_id);
CREATE INDEX IF NOT EXISTS idx_observations_flight_id ON observations (flight_id);
CREATE INDEX IF NOT EXISTS idx_defects_status         ON defects (status);
CREATE INDEX IF NOT EXISTS idx_defects_class          ON defects (defect_class);
