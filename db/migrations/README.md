# db/migrations/

SQL migrations — the single source of truth for the PostGIS schema. Applied by
[`../migrate.py`](../migrate.py), which records each file in a `schema_migrations` table so
it runs exactly once.

## Apply

```bash
# from repo root, pipeline venv active (psycopg required)
python db/migrate.py
python db/migrate.py --status
```

## Adding a migration

1. Create the next file with a zero-padded numeric prefix: `0002_short_description.sql`,
   `0003_...`. Files apply in filename order.
2. Write forward-only DDL/DML (e.g. `ALTER TABLE ... ADD COLUMN ...`). Prefer idempotent
   statements (`IF NOT EXISTS`) so a retry after a partial failure is safe.
3. **Never edit a migration that has already been applied** anywhere — add a new one instead.
   Editing an applied file won't re-run and will drift environments apart.
4. If the change affects the writer, update `pipeline/db.py` (and later the .NET API's
   entities) in the **same** change.
5. Run `python db/migrate.py`.

Each file runs in its own transaction: on success it's recorded; on failure it's rolled back
and the run aborts. Avoid statements that can't run inside a transaction (e.g.
`CREATE INDEX CONCURRENTLY`); use a plain `CREATE INDEX` here.
