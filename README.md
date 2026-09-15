# 🐦 Perch

A backyard wildlife camera. Point it at a bird feeder (or any live stream) and
Perch watches for visitors, identifies the species, logs each visit with a photo,
and can push a notification to your phone. The web app is video-first with a
toggleable "X-Ray" overlay, and installs to your home screen as a PWA.

## Architecture

Two services, one origin:

```
          ┌─────────────┐         ┌──────────────────────────┐
 stream ─▶│  services/  │  /api   │        services/web       │─▶ browser / PWA
          │    api      │◀────────│  Preact + Vite (nginx),   │
          │  (FastAPI)  │  proxy  │  reverse-proxies /api     │
          └─────────────┘         └──────────────────────────┘
```

- **`services/api`** — FastAPI: ffmpeg stream ingest, YOLOv8s detection, ByteTrack,
  iNaturalist species classification (+ optional eBird region prior), visit logging
  (SQLite), ntfy notifications. Serves a clean MJPEG + normalized detection JSON.
- **`services/web`** — Preact + TypeScript + Vite + Tailwind. Clean, mobile-first UI
  with a client-side canvas overlay, grouped timeline, and settings. Installable PWA.

Everything runs in Docker — no Python, Node, or ffmpeg needed on the host.

## Deploy (production)

```bash
git clone https://github.com/anarmawala/perch.git && cd perch
cp services/api/.env.example services/api/.env   # edit: NTFY_TOPIC, PUBLIC_URL, etc.
docker compose up -d --build
```
Open **http://localhost:8000**. Persistent data (database, photos) lives in `./data`.

## Develop (hot reload, also in Docker)

```bash
npm install        # once, for git hooks
npm run dev         # web http://localhost:5173 (HMR), api http://localhost:8000 (--reload)
```
Both services bind-mount your source, so edits reload live. No local toolchain required.

## Configuration

All via environment variables in `services/api/.env` (see `.env.example`): `STREAM_URL`
(YouTube live or an `rtsp://` camera), `NTFY_TOPIC` (phone notifications), `EBIRD_*`
(species accuracy), and performance knobs (`DETECT_INTERVAL`, `YOLO_IMGSZ`, `INFER_THREADS`).

## Tooling

ESLint + Prettier in `services/web`; a Husky pre-commit hook runs lint-staged on
staged web files. Captured photos auto-expire after `RETENTION_DAYS` (default 2)
unless you tap "Keep".
