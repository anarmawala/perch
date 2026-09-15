# Deploying Bird Watch on the Intel NUC

## Recommended: Docker (nothing to install on the NUC but Docker)

The NUC only needs Docker + the Docker Compose plugin — no Python, ffmpeg, or
anything else on the host.

```bash
# 1. Get the code onto the NUC (from your Mac):
rsync -av --exclude .venv-ml --exclude data --exclude '*.jpg' \
      ~/projects/bird_watch/prototype/  <user>@<nuc-ip>:~/bird_watch/prototype/

# 2. On the NUC:
ssh <user>@<nuc-ip>
cd ~/bird_watch/prototype
cp .env.example .env
nano .env                      # set NTFY_TOPIC, EBIRD_REGION, PUBLIC_URL, etc.

# 3. Build + run (first build pulls ~1–2 GB, a few minutes):
docker compose up -d --build
docker compose logs -f         # watch it start

# open http://<nuc-ip>:8000
```

- **Persistence:** photos, the database, and preferences live in `./data` on the
  host (mounted into the container), so `docker compose up --build` never loses them.
- **Update:** `git pull` (or re-rsync), then `docker compose up -d --build`.
- **Stop / start:** `docker compose down` / `docker compose up -d`.
- **Restart on boot** is automatic (`restart: unless-stopped`).
- **Config** is all env vars in `.env` — change and `docker compose up -d` to apply.
- **Faster Intel inference:** run the OpenVINO export once inside the container
  (`docker compose exec birdwatch python deploy/export_openvino.py`) and set
  `YOLO_MODEL=yolov8s_openvino_model` in `.env`.

The rest of this file is the **manual (non-Docker) install**, if you ever want it.

---

## Manual install (no Docker)

## 1. Get the code onto the NUC

```bash
# from your Mac (whole prototype folder incl. the models/ dir):
rsync -av --exclude .venv-ml --exclude captures --exclude '*.jpg' \
      ~/projects/bird_watch/prototype/  <user>@<nuc-ip>:~/bird_watch/prototype/
```
(or `git clone` if you push this repo somewhere.)

## 2. Install

```bash
ssh <user>@<nuc-ip>
cd ~/bird_watch/prototype
bash deploy/setup.sh          # installs ffmpeg + venv + deps, fetches weights
```

## 3. First run (verify it works)

```bash
.venv-ml/bin/uvicorn app:app --host 0.0.0.0 --port 8000
```
Open `http://<nuc-ip>:8000` from your laptop/phone on the same network. You should
see the live X-Ray view. Ctrl-C when satisfied.

## 4. Faster inference on Intel (optional but recommended)

```bash
.venv-ml/bin/python deploy/export_openvino.py
# then run with:  YOLO_MODEL=yolov8s_openvino_model ...
```

## 5. Benchmark & tune

The NUC is weaker than a laptop, so set the pacing knobs to taste. Watch the
`detect_ms` and `fps` on the live page (or `/detections`) and adjust env vars:

| Env | Meaning | If the NUC struggles |
|-----|---------|----------------------|
| `DETECT_INTERVAL` | seconds between detector runs | raise (0.5 → 1.0) |
| `YOLO_IMGSZ` | detector input size | lower (960 → 640) |
| `INFER_THREADS` | cores inference may use | match NUC core count −1 |
| `EMIT_FPS` | video frame rate | lower (20 → 12) if needed |

Video stays smooth regardless (jitter buffer + separate threads); these only
affect how often boxes refresh and CPU load.

## 6. Run it always-on (systemd)

```bash
sudo cp deploy/birdwatch.service /etc/systemd/system/birdwatch.service
sudo nano /etc/systemd/system/birdwatch.service   # set User, paths, NTFY_TOPIC, region
sudo systemctl daemon-reload
sudo systemctl enable --now birdwatch
journalctl -u birdwatch -f                         # watch logs
```

## 7. Notifications & preferences

- Set `NTFY_TOPIC` (see ../README.md) and subscribe on the phone.
- Set `PUBLIC_URL=http://<nuc-ip>:8000/timeline` so tapping a push opens the timeline.
- Configure species/quiet-hours/digest at `http://<nuc-ip>:8000/settings`.
- Add `EBIRD_API_KEY` + `EBIRD_REGION` (e.g. your county `US-PA-XXX`) for a
  location-accurate species prior.

## 8. When the real camera arrives

Only `STREAM_URL` changes — point it at the camera's RTSP URL:
```
STREAM_URL=rtsp://user:pass@<cam-ip>:554/h264Preview_01_main
```
Everything downstream is identical.
