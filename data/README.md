# data/

Working directory for drone footage and pipeline outputs. **Nothing here is committed**
except this README (see `.gitignore`).

Put a sample flight here

```
data/
  sample.mp4     # drone video
  sample.SRT     # its telemetry sidecar
  frames/        # ffmpeg output
  crops/         # defect image crops
```

Then from `pipeline/`:

```bash
python ingest.py ../data/sample.mp4 ../data/sample.SRT
```

This prints a per-frame `(t, lat, lon, rel_alt)` table
