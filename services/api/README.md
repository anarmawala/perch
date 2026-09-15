# Prototype — Phase 0: motion capture from a live stream

Prove we can reliably capture wildlife from a **real** video source, using a live
YouTube bird-feeder stream so we need zero hardware to start.

## The whole point: the camera is a drop-in swap

`grab_frames.py` gets its pixels from **one** function, `resolve_stream_url()`.
It already passes `rtsp://` URLs straight through. So going from prototype →
real camera is literally changing the `--url` value:

```bash
# Prototype today — YouTube live feeder cam:
python grab_frames.py --url "https://www.youtube.com/watch?v=<live_id>"

# Later — your Reolink, nothing else changes:
python grab_frames.py --url "rtsp://user:pass@192.168.1.42:554/h264Preview_01_main"
```

Everything downstream (motion detection, and soon detection + species ID) is
identical for both. That's the design.

## Setup

```bash
cd prototype
uv venv --python 3.10 .venv-ml          # ML stack needs Python 3.10–3.12, not 3.14
uv pip install --python .venv-ml -r requirements.txt
```

## Run — live X-Ray web app (the main thing)

```bash
.venv-ml/bin/uvicorn app:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** (live) and **/timeline** (logged visits with photos).

Requires **ffmpeg** installed (system dep) — it decodes the live stream; OpenCV's
HLS reader stalls. Tuning knobs are env vars (see top of `app.py`):
`STREAM_URL`, `DETECT_INTERVAL` (secs between detections; raise to lighten CPU),
`EMIT_FPS`, `BUFFER_SECONDS` (jitter buffer depth), `INFER_THREADS`, `YOLO_MODEL`,
`YOLO_IMGSZ`, `YOLO_CONF`, `SPECIES_CONF`.

### How it stays smooth (3 threads)
- **reader** — ffmpeg → a jitter buffer, capturing the stream's bursty frames.
- **emitter** — plays the buffer out at a steady `EMIT_FPS` (video never stutters).
- **detector** — YOLO+ByteTrack+species on the latest frame at its own pace; if
  inference is slow the boxes just refresh less often, the video is unaffected.

## Run — headless motion capture (Phase 0)

```bash
.venv-ml/bin/python grab_frames.py --url "<youtube_live_url>" --out captures
```

Motion stills land in `captures/` as `YYYYMMDD_HHMMSS_area<n>.jpg`.

Useful flags:
- `--min-area 800` — how much must change to count as motion. Raise it if leaves/light trigger saves; lower it if you miss small birds.
- `--cooldown 3.0` — seconds between saves, so a 10-second visit becomes one shot, not 200.
- `--show` — live preview window (needs a display).

## Finding a stream

Search YouTube for **"live bird feeder cam"** — Cornell Lab's *Sapsucker Woods*
and *Panama Fruit Feeder* cams are reliable 24/7 options. Grab the watch URL of a
currently-**live** video.

> Note: pulling frames is against YouTube's ToS — fine for private prototyping,
> just don't redistribute the footage.

## Where this is going: the live "X-Ray" web app

The prototype's centerpiece is a **Prime Video X-Ray, but for the feeder** — watch the
live stream in a browser, real-time boxes track each bird, click one for a species info
card (photo, facts, confidence, "seen N× today").

Architecture (video and detections travel separately so boxes stay interactive):

```
  live stream ─▶ FastAPI backend ─▶ detect birds (YOLO) ─▶ classify species
                     │
                     ├─ video  ────────────▶ browser <video>
                     └─ WebSocket JSON ─────▶ browser <canvas> overlay + X-Ray panel
                        [{box, species, conf, id}, ...]
```

Build order (each step shows up on screen):
1. ✅ Stream the live feeder into a web page.
2. ✅ YOLO (yolov8s) draws real-time boxes on every bird.
3. ✅ Species ID — iNat MobileNetV2 classifier names each bird in the panel.
4. ✅ Object tracking (ByteTrack) — stable per-bird IDs + cross-frame species voting.
5. ✅ Geographic range prior (`region.py`) — downweights species that don't occur
      locally (eBird if you set EBIRD_API_KEY, else eastern-US fallback). Fixes
      Lesser→American Goldfinch.
6. ✅ Visit logging → SQLite, /timeline gallery, "seen today" tally.
7. ✅ Click a bird (panel or timeline) → species card with Wikipedia photo + facts
      + visit counts (`/species/{name}`).
8. ✅ Notifications + preferences — push to phone (with photo) when chosen species
      appear; `/settings` page for species allowlist, min confidence, quiet hours,
      per-bird cooldown, and instant-vs-daily-digest.
9. ⬜ Deploy to the NUC — **Dockerized** (`Dockerfile` + `docker-compose.yml`; only
      Docker needed on the NUC). Persistent state in `./data`. See `deploy/README.md`.
      Then OpenVINO export + benchmark.

## Notifications setup (ntfy — free, no account)

1. Install the **ntfy** app (iOS/Android), or open https://ntfy.sh in a browser.
2. Subscribe to an unguessable topic name, e.g. `annes-birds-x7q`.
3. Start the server with that topic:
   ```bash
   NTFY_TOPIC=annes-birds-x7q .venv-ml/bin/uvicorn app:app --host 0.0.0.0 --port 8000
   ```
4. Open **/settings** to choose which birds to be alerted about, quiet hours, etc.,
   and hit "Send test". Without `NTFY_TOPIC` it runs in dry-run (prints to console).

Optional: `PUBLIC_URL=http://<nuc-ip>:8000/timeline` makes tapping a push open the
timeline. Self-host ntfy and set `NTFY_SERVER=` to keep everything on your network.

Detection recall: default `YOLO_IMGSZ=960`, `YOLO_CONF=0.15` (verified to catch
more small/distant birds than 640/0.25 with no false positives). Bump imgsz higher
or raise DETECT_INTERVAL to trade accuracy vs CPU — tune per machine.

Default stream: `https://www.youtube.com/watch?v=y9t1g8Ike6g` (Gettysburg, PA — proven,
good multi-bird view). Any live "bird feeder cam" URL works as a drop-in.

> Note: heavy ML deps (torch/ultralytics/opencv) want a supported Python (3.11–3.12) —
> best run on the NUC. `grab_frames.py` above stays lightweight and runs anywhere.

