# Perch — API service

FastAPI backend that ingests a live video stream, detects and identifies birds,
logs visits, and sends notifications. It serves a clean MJPEG stream plus JSON
endpoints; the web app draws the overlay client-side.

## Pipeline

`ffmpeg` decode → **YOLOv8s** detection → **ByteTrack** tracking → **iNaturalist
MobileNet** species classification (with an optional **eBird** region prior) →
visit logging (SQLite) → **ntfy** notifications.

Three threads keep it smooth: a reader fills a jitter buffer, an emitter plays it
out at a steady frame rate, and the detector runs on the latest frame at its own
pace — so the video never stutters even when inference is slow.

## Key endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /stream` | clean MJPEG video |
| `GET /detections` | current boxes (normalized 0–1) + fps/latency |
| `GET /summary` · `GET /visits` | today's tally · visit history |
| `GET /species/{name}` | Wikipedia + All About Birds info + counts |
| `POST /visits/{id}/keep` | keep a photo (exempt from retention) |
| `GET/POST /prefs` · `POST /notify-test` | notification preferences |

## Run (local dev)

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
STREAM_URL=... NTFY_TOPIC=... .venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
```
For local dev you need **ffmpeg** installed (`brew install ffmpeg` /
`apt install ffmpeg`). The Docker image bundles ffmpeg, so the containerized
deploy needs nothing on the host. Config is via environment variables — see
`.env.example`.
