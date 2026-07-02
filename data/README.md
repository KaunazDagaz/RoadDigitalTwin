# data/

Working directory for drone footage and pipeline outputs. **Nothing here is committed**
except this README (see `.gitignore`).

Put a sample flight here

```
data/
  incoming/        # drop raw videos here → the blur service anonymizes them
  anonymized/      # blur output: people/vehicles blurred, .SRT copied unchanged
  frames/          # ffmpeg output
  crops/           # defect image crops
```

**Anonymize first.** With the stack running (`docker compose up -d`), the `blur` service watches
`data/incoming/` and writes a blurred copy to `data/anonymized/`. Just drop a flight in:

```bash
cp flight.mp4 flight.SRT data/incoming/     # → data/anonymized/flight.mp4 (+ .SRT)
```

One-off (no watcher): `docker compose run --rm blur /data/incoming/flight.mp4 /data/incoming/flight.SRT`.

Then from `pipeline/`, point ingest at the **anonymized** copy:

```bash
python ingest.py ../data/anonymized/flight.mp4 ../data/anonymized/flight.SRT
```

This prints a per-frame `(t, lat, lon, rel_alt)` table
