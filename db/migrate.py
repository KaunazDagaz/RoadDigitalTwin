#!/usr/bin/env python3
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

try:
    import psycopg
except ImportError:
    sys.exit("psycopg not installed — from pipeline/: pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_ENSURE_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())

def database_url() -> str:
    load_dotenv(ROOT / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set (see .env.example).")
    return url

def discover() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))

def applied_filenames(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Apply pending PostGIS migrations.")
    ap.add_argument("--status", action="store_true",
                    help="show applied/pending migrations without applying anything")
    args = ap.parse_args(argv)

    files = discover()
    if not files:
        print(f"No migrations found in {MIGRATIONS_DIR}.")
        return 0

    with psycopg.connect(database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(_ENSURE_TABLE)
        conn.commit()

        done = applied_filenames(conn)
        pending = [f for f in files if f.name not in done]

        if args.status:
            for f in files:
                mark = "x" if f.name in done else " "
                print(f"  [{mark}] {f.name}")
            print(f"{len(pending)} pending.")
            return 0

        if not pending:
            print("Up to date - no pending migrations.")
            return 0

        for f in pending:
            print(f"applying {f.name} ...", end=" ", flush=True)
            try:
                with conn.cursor() as cur:
                    cur.execute(f.read_text(encoding="utf-8"))
                    cur.execute(
                        "INSERT INTO schema_migrations (filename) VALUES (%s)", (f.name,)
                    )
                conn.commit()
                print("ok")
            except Exception as exc:
                conn.rollback()
                print("FAILED")
                sys.exit(f"migration {f.name} failed: {exc}")

        print(f"Applied {len(pending)} migration(s).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
