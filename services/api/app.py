#!/usr/bin/env python3
"""
Live "X-Ray" web app (prototype) with tracking, species voting, and visit logging.

Pipeline (all tuned to stay light on a low-power CPU):
  stream -> YOLO track (yolov8s + ByteTrack) -> crop -> species (iNat MobileNet)
         -> vote species per tracked bird -> log each visit to SQLite
         -> serve: live MJPEG + boxes, "on screen now" panel, and a /timeline gallery.

Why tracking matters: each bird gets a stable ID, so we (1) steady the boxes,
(2) vote the species across many frames (fixes single-frame mistakes), and
(3) count discrete visits -> the basis for "3rd goldfinch today" + notifications.

Run:
    .venv-ml/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Open http://localhost:8000  (live)  and  http://localhost:8000/timeline  (history)

Config via env: STREAM_URL, DETECT_INTERVAL, EMIT_FPS, STREAM_MAX_W, YOLO_MODEL,
YOLO_IMGSZ, YOLO_CONF, SPECIES_CONF, TRACK_EXPIRE_SEC.
"""

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from ultralytics import YOLO

import notify
from classifier import BirdClassifier
from region import load_allowlist

# Stop inference from grabbing every CPU core — the #1 cause of stream lag, and
# essential on a low-power host. Must be set before/around torch use.
INFER_THREADS = int(os.environ.get("INFER_THREADS", "3"))
os.environ.setdefault("OMP_NUM_THREADS", str(INFER_THREADS))
cv2.setNumThreads(INFER_THREADS)
try:
    import torch
    torch.set_num_threads(INFER_THREADS)
except Exception:
    pass

_HERE = Path(__file__).parent
STREAM_URL = os.environ.get("STREAM_URL", "https://www.youtube.com/watch?v=y9t1g8Ike6g")
# Wall-clock throttles (NOT frame counts) so bursty buffered reads can't saturate CPU:
DETECT_INTERVAL = float(os.environ.get("DETECT_INTERVAL", "0.3"))  # secs between detector runs (~3/s)
EMIT_FPS = float(os.environ.get("EMIT_FPS", "20"))                 # steady playout frame rate
STREAM_MAX_W = int(os.environ.get("STREAM_MAX_W", "960"))          # display/buffer width
BUFFER_SECONDS = float(os.environ.get("BUFFER_SECONDS", "2.5"))    # jitter buffer depth (live HLS is bursty)
YOLO_MODEL = os.environ.get("YOLO_MODEL", "yolov8s.pt")
YOLO_IMGSZ = int(os.environ.get("YOLO_IMGSZ", "960"))   # 960>640 finds more small/distant birds
CONF = float(os.environ.get("YOLO_CONF", "0.15"))       # lower = better recall (verified no false+)
SPECIES_CONF = float(os.environ.get("SPECIES_CONF", "0.30"))
# Live species classifier: bioclip (accurate, ~200ms/crop) or inat (fast, ~15ms).
CLASSIFIER = os.environ.get("CLASSIFIER", "bioclip")
CLASSIFY_INTERVAL = float(os.environ.get("CLASSIFY_INTERVAL", "1.0"))    # min secs between classifications per track
CLASSIFY_LOCK_CONF = float(os.environ.get("CLASSIFY_LOCK_CONF", "0.9"))  # stop re-classifying once a track reaches this conf
# Carry a locked label to a bird re-detected at the same spot (survives ByteTrack ID churn).
LABEL_MEMORY_SEC = float(os.environ.get("LABEL_MEMORY_SEC", "8"))
LABEL_IOU = float(os.environ.get("LABEL_IOU", "0.55"))
DEDUP_IOU = float(os.environ.get("DEDUP_IOU", "0.6"))  # collapse two ids on one bird into one box
TRACK_EXPIRE_SEC = float(os.environ.get("TRACK_EXPIRE_SEC", "10"))
# Motion gating: skip the expensive YOLO pass when the scene is idle (feeder empty
# and still). Wakes instantly on motion or while a bird is being tracked.
MOTION_GATING = os.environ.get("MOTION_GATING", "1").lower() not in ("0", "false", "no", "")
MOTION_MIN_AREA = int(os.environ.get("MOTION_MIN_AREA", "150"))  # largest moving blob (px, in 320x180) = motion
MOTION_IDLE_SEC = float(os.environ.get("MOTION_IDLE_SEC", "3"))  # keep detecting this long after last motion
IDLE_POLL = float(os.environ.get("IDLE_POLL", "0.12"))          # motion-check cadence while idle
URL_REFRESH_SEC = 1200.0                                        # re-resolve URL proactively (~20 min)
STALL_SEC = float(os.environ.get("STALL_SEC", "20"))           # kill+restart ffmpeg if no frame for this long

# All writable state lives under DATA_DIR (mount this as a Docker volume to persist).
DATA_DIR = Path(os.environ.get("DATA_DIR", _HERE))
DATA_DIR.mkdir(parents=True, exist_ok=True)
CAPTURES = DATA_DIR / "captures"
CAPTURES.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "birdwatch.db"
_db_lock = threading.Lock()
# Auto-delete captured thumbnails older than this many days, unless "kept".
RETENTION_DAYS = float(os.environ.get("RETENTION_DAYS", "2"))


# ---------------------------------------------------------------- database
def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS visits(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        species TEXT, species_conf REAL,
        start_ts TEXT, end_ts TEXT, seconds REAL, frames INTEGER, image TEXT,
        kept INTEGER DEFAULT 0)""")
    # migrate older DBs that predate the `kept` column
    cols = {r[1] for r in con.execute("PRAGMA table_info(visits)").fetchall()}
    if "kept" not in cols:
        con.execute("ALTER TABLE visits ADD COLUMN kept INTEGER DEFAULT 0")
    con.commit()
    con.close()


def insert_visit(species, conf, start_ts, end_ts, seconds, frames, image):
    with _db_lock:
        con = sqlite3.connect(DB_PATH)
        con.execute("INSERT INTO visits(species,species_conf,start_ts,end_ts,seconds,frames,image)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (species, conf, start_ts, end_ts, seconds, frames, image))
        con.commit()
        con.close()


def query(sql, args=()):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(sql, args).fetchall()
    con.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- preferences
PREFS_PATH = DATA_DIR / "prefs.json"
DEFAULT_PREFS = {
    "mode": "instant",       # instant | digest | off
    "species": [],           # allowlist of common names; [] = notify for any species
    "min_conf": 0.5,         # only notify above this species confidence
    "quiet_start": 22,       # quiet hours start (24h) — no instant alerts
    "quiet_end": 7,          # quiet hours end
    "cooldown_min": 30,      # per-species cooldown, avoids spam from one visitor
    "digest_hour": 20,       # hour to send the daily digest (digest mode)
}
_last_notified = {}          # species -> timestamp (in-memory cooldown)
_notify_lock = threading.Lock()


def load_prefs():
    p = dict(DEFAULT_PREFS)
    try:
        p.update(json.loads(PREFS_PATH.read_text()))
    except Exception:
        pass
    return p


def save_prefs(data):
    p = load_prefs()
    for k in DEFAULT_PREFS:
        if k in data:
            p[k] = data[k]
    PREFS_PATH.write_text(json.dumps(p, indent=2))
    return p


def _in_quiet_hours(p, now):
    h = datetime.fromtimestamp(now).hour
    s, e = p["quiet_start"], p["quiet_end"]
    if s == e:
        return False
    return (s <= h < e) if s < e else (h >= s or h < e)


def maybe_notify(species, conf, image, now):
    """Apply the preference rules and send a push if they pass. One shot per bird."""
    p = load_prefs()
    if p["mode"] != "instant" or species == "Bird" or conf < p["min_conf"]:
        return False
    if p["species"] and species not in p["species"]:
        return False
    if _in_quiet_hours(p, now):
        return False
    with _notify_lock:
        if now - _last_notified.get(species, 0) < p["cooldown_min"] * 60:
            return False
        _last_notified[species] = now
    img = str(CAPTURES / image) if image else None
    notify.send(f"{species} at the feeder",
                f"Spotted at {datetime.now():%I:%M %p} - {int(conf * 100)}% sure",
                image_path=img, tags="bird", priority=4)
    return True


def digest_worker():
    """In digest mode, send one daily summary at the chosen hour."""
    sent_on = None
    while state.running:
        p = load_prefs()
        now = datetime.now()
        if p["mode"] == "digest" and now.hour == p["digest_hour"] and sent_on != now.date():
            today = now.strftime("%Y-%m-%d")
            rows = query("SELECT species, COUNT(*) n FROM visits WHERE start_ts LIKE ?"
                         " GROUP BY species ORDER BY n DESC", (today + "%",))
            if rows:
                total = sum(r["n"] for r in rows)
                lines = ", ".join(f"{r['n']}x {r['species']}" for r in rows[:12])
                notify.send(f"Today's birds: {total} visits", lines, tags="bird")
            sent_on = now.date()
        time.sleep(60)


def cleanup_worker():
    """Delete captured thumbnails older than RETENTION_DAYS, unless the visit is
    marked kept. The visit row stays (for history/counts); only the image file is
    removed and its reference cleared, so disk usage stays bounded."""
    import datetime as _dt
    while state.running:
        cutoff = (datetime.now() - _dt.timedelta(days=RETENTION_DAYS)).isoformat()
        rows = query("SELECT id, image FROM visits "
                     "WHERE image != '' AND kept = 0 AND start_ts < ?", (cutoff,))
        for r in rows:
            try:
                (CAPTURES / r["image"]).unlink(missing_ok=True)
            except Exception:
                pass
            with _db_lock:
                con = sqlite3.connect(DB_PATH)
                con.execute("UPDATE visits SET image = '' WHERE id = ?", (r["id"],))
                con.commit()
                con.close()
        if rows:
            print(f"[cleanup] removed {len(rows)} thumbnail(s) older than {RETENTION_DAYS}d")
        time.sleep(3600)  # hourly


# ---------------------------------------------------------------- stream source
def resolve_stream_url(source: str) -> str:
    if source.startswith("rtsp://") or source.endswith(".m3u8") or Path(source).exists():
        return source
    out = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "-f",
         f"bestvideo[height<={FRAME_H}]/232/230/best", "-g", source],
        capture_output=True, text=True, check=True,
    )
    urls = [ln for ln in out.stdout.splitlines() if ln.strip()]
    if not urls:
        raise RuntimeError("yt-dlp returned no stream URL (is it live?).")
    return urls[-1]


# ---------------------------------------------------------------- shared state
class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.latest_frame = None          # newest full-res frame (live edge)
        self.detect_frame = None          # the frame currently being displayed (detector uses this)
        self.frames = deque(maxlen=max(2, int(30 * BUFFER_SECONDS)))  # full-res jitter buffer
        self.jpeg: bytes | None = None     # newest annotated JPEG for streaming
        self.last_frame_ts = 0.0           # wall-clock of the last decoded frame (watchdog)
        self.proc = None                   # current ffmpeg process (so the watchdog can kill it)
        self.detections: list[dict] = []
        self.fps = 0.0
        self.detect_ms = 0.0       # YOLO detect+track time
        self.classify_ms = 0.0     # species classification time
        self.motion_area = 0       # foreground pixels from the motion gate
        self.idle = False          # true when the motion gate is skipping detection
        self.running = True


state = State()


# ---------------------------------------------------------------- worker thread
def finalize_track(tid, t):
    """A tracked bird has left -> record the visit if it was a real one."""
    if not t.get("species") or t["frames"] < 2:
        return  # never confidently identified, or too brief -> skip noise
    species = t["species"]
    conf = round(t["best"], 2)
    seconds = round(t["last"] - t["first"], 1)
    insert_visit(species, conf,
                 datetime.fromtimestamp(t["first"]).isoformat(timespec="seconds"),
                 datetime.fromtimestamp(t["last"]).isoformat(timespec="seconds"),
                 seconds, t["frames"], t["image"] or "")


# Processing resolution. 1080 is the sweet spot (≈4× the pixels on a bird vs 720,
# still cheap); a close 4K feeder cam gives large, sharp crops even downscaled to this.
# Bump to 1440/2160 to trade CPU for detail. Detection resizes internally, so this
# mainly buys sharper classifier crops.
PROCESS_HEIGHT = int(os.environ.get("PROCESS_HEIGHT", "1080"))
FRAME_H = PROCESS_HEIGHT
FRAME_W = (FRAME_H * 16 // 9 + 1) // 2 * 2  # 16:9, even width for bgr24


def _start_ffmpeg():
    """Decode the live stream with ffmpeg (robust at live HLS, unlike OpenCV) and
    emit a steady, real-time BGR frame stream at EMIT_FPS. ffmpeg paces itself to
    the live source, so we get smooth frames without bursts/stalls."""
    url = resolve_stream_url(STREAM_URL)
    # No -r: let ffmpeg pace to the live source's native rate (~30 fps real-time).
    # scale=fixed so the raw frame size is known for np.reshape.
    # reconnect + rw_timeout: recover from transient network stalls / exit if I/O hangs.
    cmd = ["ffmpeg", "-loglevel", "error",
           "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
           "-rw_timeout", "15000000",
           "-i", url, "-an", "-sn",
           "-vf", f"scale={FRAME_W}:{FRAME_H}",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            bufsize=FRAME_W * FRAME_H * 3 * 4)


DISPLAY_H = int(FRAME_H * STREAM_MAX_W / FRAME_W)
BOX_SCALE = STREAM_MAX_W / FRAME_W


def reader():
    """Fill the jitter buffer from ffmpeg as fast as frames arrive. Live HLS is
    bursty (a segment's frames land at once, then a pause), so we just capture
    everything; the emitter handles smooth playback."""
    proc = _start_ffmpeg()
    state.proc = proc
    state.last_frame_ts = time.time()
    started = time.time()
    nbytes = FRAME_W * FRAME_H * 3

    while state.running:
        raw = proc.stdout.read(nbytes)
        if len(raw) < nbytes or (time.time() - started > URL_REFRESH_SEC):
            print("[reader] restarting ffmpeg...")
            try:
                proc.kill()
            except Exception:
                pass
            time.sleep(2)
            try:
                proc = _start_ffmpeg(); state.proc = proc; started = time.time()
                state.last_frame_ts = time.time()
            except Exception as e:
                print("[reader] ffmpeg restart failed:", e); time.sleep(3)
            continue

        frame = np.frombuffer(raw, np.uint8).reshape(FRAME_H, FRAME_W, 3)
        with state.lock:
            state.latest_frame = frame          # live edge (for the watchdog / reference)
            state.frames.append(frame)          # full-res jitter buffer
            state.last_frame_ts = time.time()

    proc.kill()


def watchdog():
    """If no frame has arrived for STALL_SEC (ffmpeg hung on an expired URL / dead
    socket), kill it so the reader's blocked read returns and it restarts with a
    freshly resolved URL. Without this a stalled stream freezes forever."""
    while state.running:
        time.sleep(5)
        ts = state.last_frame_ts
        if ts and time.time() - ts > STALL_SEC and state.proc is not None:
            print(f"[watchdog] no frames for {STALL_SEC}s — killing ffmpeg to force restart")
            try:
                state.proc.kill()
            except Exception:
                pass
            state.last_frame_ts = time.time()   # give the restart a grace period


def emitter():
    """Play the buffer out at a steady EMIT_FPS, drawing the detector's latest
    boxes. The jitter buffer absorbs the stream's burst/stall delivery, so the
    video stays smooth. Underflow (long stall) just holds the last frame."""
    etimes = deque(maxlen=30)
    last_emit = 0.0
    last_disp = None
    next_t = time.time()

    while state.running:
        next_t += 1.0 / EMIT_FPS
        nap = next_t - time.time()
        if nap > 0:
            time.sleep(nap)
        else:
            next_t = time.time()             # fell behind; resync

        with state.lock:
            full = state.frames.popleft() if state.frames else last_disp
        if full is None:
            continue
        last_disp = full
        # The detector runs on exactly the frame we're about to show, so the client
        # overlay is WYSIWYG — boxes match the visible video, not the live edge.
        with state.lock:
            state.detect_frame = full

        # Serve a CLEAN downscaled frame — the web client draws boxes/labels itself
        # as a canvas overlay (toggleable), from the normalized /detections data.
        disp = cv2.resize(full, (STREAM_MAX_W, DISPLAY_H))
        now = time.time()
        if last_emit:
            etimes.append(now - last_emit)
        last_emit = now
        fps = len(etimes) / sum(etimes) if etimes else 0.0

        ok, buf = cv2.imencode(".jpg", disp, [cv2.IMWRITE_JPEG_QUALITY, 78])
        if ok:
            with state.lock:
                state.jpeg = buf.tobytes()
                state.fps = round(fps, 1)


def make_classifier():
    """The live species classifier. BioCLIP is restricted to the local species (so it's
    a fine-grained 'which of these' decision); iNat uses the geographic prior."""
    allow = load_allowlist()
    if CLASSIFIER == "bioclip":
        from bioclip_classifier import BioCLIPClassifier
        return BioCLIPClassifier(sorted(allow))
    clf = BirdClassifier()
    clf.set_allow(allow)
    return clf


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def detector():
    """AI thread: run tracking + species classification on the latest frame as
    fast as the hardware allows (paced by DETECT_INTERVAL), updating the boxes
    the reader draws and logging visits. Slow inference => boxes just refresh
    less often; the video never stutters."""
    model = YOLO(YOLO_MODEL)
    bird_id = next(i for i, n in model.names.items() if n == "bird")
    clf = make_classifier()
    print(f"[detector] {YOLO_MODEL} + {CLASSIFIER} classifier + ByteTrack + visit logging")
    tracks = {}
    label_memory = []  # [{box, species, best, ts}] — locked labels kept by location, to survive ID churn
    bg = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=32, detectShadows=False)
    motion_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    last_motion = 0.0

    while state.running:
        cycle_start = time.time()
        with state.lock:
            lf = state.detect_frame          # the frame currently on screen (WYSIWYG)
        if lf is None:
            time.sleep(0.05); continue
        frame = lf.copy()
        now = time.time()

        # Motion check (keeps the bg model fresh). Gate on the LARGEST coherent blob,
        # not total pixels — a bird is one object; wind-blown foliage and the burned-in
        # timestamp overlay are diffuse speckle we mask/filter out.
        fg = bg.apply(cv2.resize(frame, (320, 180)))
        fg[:34, :110] = 0  # mask the top-left weather/clock overlay (changes every second)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, motion_kernel)
        cnts, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        motion_area = int(max((cv2.contourArea(c) for c in cnts), default=0))
        if motion_area > MOTION_MIN_AREA:
            last_motion = now

        # Idle: gating on, nothing tracked, no recent motion -> skip the expensive
        # YOLO pass and poll cheaply. Wakes instantly on motion or a lingering track.
        if MOTION_GATING and not tracks and (now - last_motion) > MOTION_IDLE_SEC:
            with state.lock:
                state.detections = []
                state.detect_ms = 0.0
                state.classify_ms = 0.0
                state.motion_area = motion_area
                state.idle = True
            time.sleep(IDLE_POLL)
            continue

        td = time.perf_counter()
        res = model.track(frame, imgsz=YOLO_IMGSZ, classes=[bird_id], conf=CONF,
                          persist=True, tracker="bytetrack.yaml", verbose=False)[0]
        yolo_ms = (time.perf_counter() - td) * 1000
        clf_ms = 0.0
        dets = []

        # De-dup: ByteTrack sometimes assigns two ids to one bird (overlapping YOLO
        # boxes). Keep, per cluster, the already-labeled / higher-confidence detection
        # and drop the rest, so one bird draws exactly one box.
        raw = []
        for b in res.boxes:
            if b.id is None:
                continue
            tid = int(b.id[0])
            box = list(map(int, b.xyxy[0]))
            conf = float(b.conf[0]) if b.conf is not None else 0.0
            raw.append((tid, box, conf))
        raw.sort(key=lambda r: ((tracks.get(r[0]) or {}).get("best", 0.0), r[2]), reverse=True)
        kept = []
        for tid, box, conf in raw:
            if any(_iou(box, k[1]) > DEDUP_IOU for k in kept):
                continue
            kept.append((tid, box, conf))

        for tid, box, conf in kept:
            x1, y1, x2, y2 = box

            t = tracks.get(tid)
            if t is None:
                t = tracks[tid] = {"first": now, "last": now, "frames": 0,
                                   "best": 0.0, "species": None, "image": None,
                                   "notified": False, "last_clf": 0.0}
            t["last"] = now
            t["frames"] += 1
            t["box"] = box

            # A bird re-detected at the same spot (new ByteTrack id) inherits the locked
            # label instead of re-classifying from scratch — keeps stationary birds stable.
            if not t["species"]:
                for m in label_memory:
                    if now - m["ts"] < LABEL_MEMORY_SEC and _iou(box, m["box"]) > LABEL_IOU:
                        t["species"], t["best"] = m["species"], m["best"]
                        break

            # Classify only until the track LOCKS a confident species (>=CLASSIFY_LOCK_CONF),
            # throttled per track — so the heavier BioCLIP model runs a few times per new
            # bird, then stops. Sticky label: keep the highest-confidence species seen.
            if t["best"] < CLASSIFY_LOCK_CONF and now - t["last_clf"] >= CLASSIFY_INTERVAL:
                t["last_clf"] = now
                pad = 8
                crop = frame[max(0, y1 - pad):y2 + pad, max(0, x1 - pad):x2 + pad]
                _tc = time.perf_counter()
                preds = clf.classify(crop, topk=1)
                clf_ms += (time.perf_counter() - _tc) * 1000
                sp, sc = (preds[0][0], preds[0][2]) if preds else ("Bird", 0.0)
                if sc >= SPECIES_CONF and sc > t["best"]:
                    t["best"] = sc
                    t["species"] = sp
                    if crop.size:  # keep the best-looking thumbnail for this visit
                        fn = f"{datetime.now():%Y%m%d_%H%M%S}_{sp.replace(' ', '')}_{tid}.jpg"
                        cv2.imwrite(str(CAPTURES / fn), crop)
                        t["image"] = fn

            voted = t["species"] or "Bird"
            vconf = round(t["best"], 2)
            dets.append({"id": tid, "box": [x1, y1, x2, y2],
                         "species": voted, "species_conf": vconf})

            # notify once per bird, after 2+ confident frames (per the prefs rules)
            if not t["notified"] and t["frames"] >= 2 and vconf > 0:
                if maybe_notify(voted, vconf, t["image"], now):
                    t["notified"] = True

        for tid in [k for k, v in tracks.items() if now - v["last"] > TRACK_EXPIRE_SEC]:
            finalize_track(tid, tracks.pop(tid))

        # Refresh location-keyed label memory: every labeled track keeps its entry fresh,
        # and a bird that just left lingers as an orphan (until LABEL_MEMORY_SEC) so a bird
        # re-appearing at that spot can inherit the label.
        new_mem = [{"box": t["box"], "species": t["species"], "best": t["best"], "ts": now}
                   for t in tracks.values() if t.get("species") and "box" in t]
        for m in label_memory:
            if now - m["ts"] < LABEL_MEMORY_SEC and not any(_iou(m["box"], n["box"]) > LABEL_IOU for n in new_mem):
                new_mem.append(m)
        label_memory = new_mem

        with state.lock:
            state.detections = dets
            state.detect_ms = round(yolo_ms, 1)
            state.classify_ms = round(clf_ms, 1)
            state.motion_area = motion_area
            state.idle = False

        dt = time.time() - cycle_start          # pace so we don't peg the CPU
        if dt < DETECT_INTERVAL:
            time.sleep(DETECT_INTERVAL - dt)


# ---------------------------------------------------------------- web app
app = FastAPI(title="Perch API")
app.mount("/captures", StaticFiles(directory=str(CAPTURES)), name="captures")

# Eval review crops (iNat-vs-BioCLIP disagreements from eval/compare.py)
REVIEW_DIR = DATA_DIR / "review"
REVIEW_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/review-imgs", StaticFiles(directory=str(REVIEW_DIR)), name="review-imgs")
_VERDICTS = DATA_DIR / "review_verdicts.json"


@app.on_event("startup")
def _start():
    init_db()
    threading.Thread(target=reader, daemon=True).start()
    threading.Thread(target=watchdog, daemon=True).start()
    threading.Thread(target=emitter, daemon=True).start()
    threading.Thread(target=detector, daemon=True).start()
    threading.Thread(target=digest_worker, daemon=True).start()
    threading.Thread(target=cleanup_worker, daemon=True).start()


@app.on_event("shutdown")
def _stop():
    state.running = False


def mjpeg():
    boundary = b"--frame"
    while True:
        with state.lock:
            jpg = state.jpeg
        if jpg:
            yield boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
        time.sleep(0.04)


@app.get("/stream")
def stream():
    return StreamingResponse(mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/detections")
def detections():
    with state.lock:
        raw = state.detections
        fps, dms = round(state.fps, 1), round(state.detect_ms, 1)
        clf_ms, motion, idle = state.classify_ms, state.motion_area, state.idle
    # Normalize boxes to 0..1 so the web client can scale them to any video size.
    dets = [{"id": d["id"],
             "box": [round(d["box"][0] / FRAME_W, 4), round(d["box"][1] / FRAME_H, 4),
                     round(d["box"][2] / FRAME_W, 4), round(d["box"][3] / FRAME_H, 4)],
             "species": d["species"], "species_conf": d["species_conf"]}
            for d in raw]
    return JSONResponse({"detections": dets, "fps": fps, "detect_ms": dms,
                         "classify_ms": clf_ms, "motion_area": motion, "idle": idle})


@app.get("/summary")
def summary():
    """Today's visit tally per species."""
    today = datetime.now().strftime("%Y-%m-%d")
    rows = query("SELECT species, COUNT(*) n FROM visits WHERE start_ts LIKE ?"
                 " GROUP BY species ORDER BY n DESC", (today + "%",))
    return {"today": today, "species": rows}


@app.get("/visits")
def visits(limit: int = 50):
    return {"visits": query("SELECT * FROM visits ORDER BY id DESC LIMIT ?", (limit,))}


@app.post("/visits/{visit_id}/keep")
async def keep_visit(visit_id: int, req: Request):
    """Mark a visit's photo to keep (exempt from retention cleanup), or unkeep it."""
    try:
        kept = 1 if (await req.json()).get("kept", True) else 0
    except Exception:
        kept = 1
    with _db_lock:
        con = sqlite3.connect(DB_PATH)
        con.execute("UPDATE visits SET kept = ? WHERE id = ?", (kept, visit_id))
        con.commit()
        con.close()
    return {"id": visit_id, "kept": kept}


# --- species info (visit stats + a field-guide link) --------------------------
@app.get("/species/{name}")
def species(name: str):
    today = datetime.now().strftime("%Y-%m-%d")
    total = query("SELECT COUNT(*) n FROM visits WHERE species=?", (name,))[0]["n"]
    tod = query("SELECT COUNT(*) n FROM visits WHERE species=? AND start_ts LIKE ?",
                (name, today + "%"))[0]["n"]
    last = query("SELECT start_ts FROM visits WHERE species=? ORDER BY id DESC LIMIT 1", (name,))
    # All About Birds (Cornell, free) — opened in a new tab (the site blocks embedding).
    slug = name.replace("'", "").replace(" ", "_")
    aab_url = f"https://www.allaboutbirds.org/guide/{slug}"
    return {"name": name, "total": total, "today": tod, "aab_url": aab_url,
            "last": last[0]["start_ts"] if last else None}


@app.get("/prefs")
def get_prefs():
    return load_prefs()


@app.post("/prefs")
async def set_prefs(req: Request):
    return save_prefs(await req.json())


@app.post("/notify-test")
def notify_test():
    ok = notify.send("Bird Watch test", "Your notifications are working!",
                     tags="tada", priority=4)
    return {"sent": ok, "configured": bool(notify.NTFY_TOPIC),
            "topic": notify.NTFY_TOPIC, "server": notify.NTFY_SERVER}


@app.get("/notify-status")
def notify_status():
    return {"configured": bool(notify.NTFY_TOPIC),
            "topic": notify.NTFY_TOPIC, "server": notify.NTFY_SERVER}


# --- eval adjudication dashboard (iNat vs BioCLIP) ---------------------------
@app.get("/eval/items")
def eval_items():
    try:
        manifest = json.loads((REVIEW_DIR / "manifest.json").read_text())
    except Exception:
        manifest = []
    try:
        verdicts = json.loads(_VERDICTS.read_text())
    except Exception:
        verdicts = {}
    return {"items": manifest, "verdicts": verdicts}


@app.post("/eval/verdict")
async def eval_verdict(req: Request):
    d = await req.json()
    try:
        verdicts = json.loads(_VERDICTS.read_text())
    except Exception:
        verdicts = {}
    verdicts[d["file"]] = d["winner"]
    _VERDICTS.write_text(json.dumps(verdicts))
    v = list(verdicts.values())
    return {"inat": v.count("inat"), "bioclip": v.count("bioclip"),
            "neither": v.count("neither"), "total": len(v)}


@app.get("/eval", response_class=HTMLResponse)
def eval_dashboard():
    return EVAL_HTML


EVAL_HTML = """
<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Perch — iNat vs BioCLIP</title>
<style>
  :root{color-scheme:light}
  body{margin:0;background:#f6f7f9;color:#1a1f26;font-family:system-ui,sans-serif;
       display:flex;flex-direction:column;align-items:center;min-height:100vh}
  header{width:100%;text-align:center;padding:14px;font-weight:600;border-bottom:1px solid #e4e8ec;background:#fff}
  #tally{margin:12px;font-variant-numeric:tabular-nums;color:#667085}
  #crop{width:min(90vw,460px);height:min(90vw,460px);object-fit:contain;background:#000;border-radius:14px}
  .btns{display:flex;flex-direction:column;gap:10px;width:min(90vw,460px);margin-top:14px}
  button{padding:14px;border-radius:12px;border:1px solid #e4e8ec;background:#fff;font-size:16px;font-weight:600;cursor:pointer}
  button.inat{border-color:#2f6fed;color:#2f6fed} button.bio{border-color:#1f9d57;color:#1f9d57}
  button:hover{filter:brightness(0.97)}
  #progress{margin:10px;color:#98a2b3;font-size:13px}
  kbd{background:#eef1f4;border-radius:4px;padding:1px 5px;font-size:12px}
</style></head><body>
<header>Which is right?  <kbd>1</kbd> iNat · <kbd>2</kbd> BioCLIP · <kbd>3</kbd> neither · <kbd>←</kbd><kbd>→</kbd></header>
<div id="tally">loading…</div>
<img id="crop" alt="crop">
<div class="btns">
  <button class="inat" id="binat"></button>
  <button class="bio" id="bbio"></button>
  <button id="bneither">Neither / unsure</button>
</div>
<div id="progress"></div>
<script>
let items=[], verdicts={}, i=0;
const $=id=>document.getElementById(id);
async function load(){
  const d=await (await fetch('/api/eval/items')).json();
  items=d.items||[]; verdicts=d.verdicts||{};
  i=items.findIndex(x=>!(x.file in verdicts)); if(i<0)i=0;
  render();
}
function tallyCounts(){const v=Object.values(verdicts);
  return {inat:v.filter(x=>x=='inat').length,bioclip:v.filter(x=>x=='bioclip').length,
          neither:v.filter(x=>x=='neither').length,total:v.length};}
function render(){
  if(!items.length){$('tally').textContent='No disagreements yet — run eval/compare.py.';
    $('crop').style.display='none';return;}
  const it=items[i];
  $('crop').src='/api/review-imgs/'+encodeURIComponent(it.file);
  $('binat').textContent='iNat: '+it.inat+'  ('+Math.round(it.inat_conf*100)+'%)';
  $('bbio').textContent='BioCLIP: '+it.bioclip+'  ('+Math.round(it.bioclip_conf*100)+'%)';
  const t=tallyCounts();
  $('tally').innerHTML='iNat <b>'+t.inat+'</b> · BioCLIP <b>'+t.bioclip+'</b> · neither '+t.neither+' · judged '+t.total+'/'+items.length;
  $('progress').textContent='#'+(i+1)+' of '+items.length+(it.file in verdicts?'  ✓ '+verdicts[it.file]:'');
}
async function vote(w){
  const it=items[i]; verdicts[it.file]=w;
  fetch('/api/eval/verdict',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({file:it.file,winner:w})});
  if(i<items.length-1)i++; render();
}
$('binat').onclick=()=>vote('inat'); $('bbio').onclick=()=>vote('bioclip'); $('bneither').onclick=()=>vote('neither');
addEventListener('keydown',e=>{
  if(e.key=='1')vote('inat'); else if(e.key=='2')vote('bioclip'); else if(e.key=='3')vote('neither');
  else if(e.key=='ArrowRight'&&i<items.length-1){i++;render();}
  else if(e.key=='ArrowLeft'&&i>0){i--;render();}
});
load();
</script></body></html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return LIVE_HTML


@app.get("/timeline", response_class=HTMLResponse)
def timeline():
    return TIMELINE_HTML


@app.get("/settings", response_class=HTMLResponse)
def settings():
    return SETTINGS_HTML


# ---------------------------------------------------------------- templates
_STYLE = """
  :root{color-scheme:dark}
  body{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.5 system-ui,sans-serif}
  header{padding:14px 20px;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:12px}
  header h1{font-size:17px;margin:0;font-weight:600}
  a{color:#58a6ff;text-decoration:none} a:hover{text-decoration:underline}
  .live{background:#da3633;color:#fff;font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;letter-spacing:.5px}
  .dot{width:8px;height:8px;border-radius:50%;background:#3fb950;display:inline-block;margin-right:6px}
"""

_MODAL_CSS = """
  .modal{display:none;position:fixed;inset:0;background:rgba(1,4,9,.72);z-index:50;align-items:center;justify-content:center;padding:16px}
  .modal.show{display:flex}
  .sheet{background:#161b22;border:1px solid #30363d;border-radius:14px;max-width:460px;width:100%;padding:20px;position:relative;max-height:86vh;overflow:auto}
  .sheet .x{position:absolute;top:8px;right:12px;background:none;border:none;color:#8b949e;font-size:22px;cursor:pointer}
  .m_img{width:100%;max-height:240px;object-fit:cover;border-radius:10px;margin-bottom:12px}
  .sheet h2{margin:0 0 6px;font-size:20px}
  .m_counts{color:#3fb950;font-weight:600;margin-bottom:10px;font-size:14px}
  .m_extract{color:#c9d1d9;font-size:14px;line-height:1.6;margin:0 0 12px}
  .m_links{display:flex;gap:8px;flex-wrap:wrap}
  .lbtn{display:inline-block;background:#238636;color:#fff !important;padding:8px 14px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none}
  .lbtn.sec{background:#21262d;color:#e6edf3 !important;border:1px solid #30363d}
  .clickable{cursor:pointer} .clickable:hover{border-color:#3fb950}
"""

_MODAL_HTML = """
<div id="modal" class="modal" onclick="if(event.target.id==='modal')closeSp()">
  <div class="sheet">
    <button class="x" onclick="closeSp()">&times;</button>
    <img id="m_img" class="m_img" style="display:none" alt="">
    <h2 id="m_name"></h2>
    <div id="m_counts" class="m_counts"></div>
    <p id="m_extract" class="m_extract"></p>
    <div class="m_links">
      <a id="m_aab" class="lbtn" target="_blank" rel="noopener" style="display:none">Field guide (All About Birds) &rarr;</a>
      <a id="m_link" class="lbtn sec" target="_blank" rel="noopener" style="display:none">Wikipedia &rarr;</a>
    </div>
  </div>
</div>
"""

_MODAL_JS = """
function setSpeciesLinks(d){
  const aab=document.getElementById('m_aab'), link=document.getElementById('m_link');
  if(d.aab_url){aab.href=d.aab_url; aab.style.display='inline-block';} else aab.style.display='none';
  if(d.url){link.href=d.url; link.style.display='inline-block';} else link.style.display='none';
}
async function openSpecies(name){
  if(!name || name==='Bird') return;
  document.getElementById('modal').classList.add('show');
  document.getElementById('m_name').textContent=name;
  document.getElementById('m_extract').textContent='Loading…';
  document.getElementById('m_counts').textContent='';
  const img=document.getElementById('m_img'); img.style.display='none';
  document.getElementById('m_aab').style.display='none'; document.getElementById('m_link').style.display='none';
  try{
    const d=await (await fetch('/species/'+encodeURIComponent(name))).json();
    document.getElementById('m_extract').textContent=d.extract||'No description found.';
    document.getElementById('m_counts').textContent='Seen '+d.today+' today · '+d.total+' total';
    setSpeciesLinks(d);
    if(d.thumb){img.src=d.thumb; img.style.display='block';}
  }catch(e){document.getElementById('m_extract').textContent='Could not load info.';}
}
function closeSp(){document.getElementById('modal').classList.remove('show');}
"""

LIVE_HTML = f"""
<!doctype html><html><head><meta charset="utf-8"><title>Bird Watch — X-Ray</title><style>{_STYLE}
  .wrap{{display:flex;gap:16px;padding:16px;flex-wrap:wrap}}
  .video{{flex:2;min-width:480px}} .video img{{width:100%;border-radius:10px;display:block;background:#000}}
  .panel{{flex:1;min-width:260px}}
  .panel h2{{font-size:13px;text-transform:uppercase;letter-spacing:.6px;color:#8b949e;margin:18px 0 10px}}
  .card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:12px 14px;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center}}
  .card .name{{font-weight:600}} .card .conf{{font-variant-numeric:tabular-nums;color:#3fb950;font-weight:600}}
  .empty{{color:#6e7681;font-style:italic}}
  .stats{{font-size:12px;color:#8b949e;margin-top:8px;font-variant-numeric:tabular-nums}}
  {_MODAL_CSS}
</style></head><body>
<header><span class="live">● LIVE</span><h1>Bird Watch — X-Ray</h1>
  <span style="color:#8b949e;font-size:13px">Gettysburg, PA feeder cam</span>
  <span style="margin-left:auto"><a href="/timeline">Timeline</a> · <a href="/settings">Settings →</a></span></header>
<div class="wrap">
  <div class="video"><img src="/stream" alt="live"></div>
  <div class="panel">
    <h2>On screen now</h2><div id="list"><div class="empty">watching…</div></div>
    <h2>Seen today</h2><div id="today"><div class="empty">—</div></div>
    <div class="stats" id="stats"></div>
  </div>
</div>
{_MODAL_HTML}
<script>
{_MODAL_JS}
async function tick(){{
  try{{
    const d = await (await fetch('/detections')).json();
    const list=document.getElementById('list');
    list.innerHTML = d.detections.length
      ? d.detections.map(x=>{{const sc=x.species_conf?Math.round(x.species_conf*100)+'%':'';
          return `<div class="card clickable" onclick="openSpecies('${{x.species}}')"><span class="name"><span class="dot"></span>${{x.species}} <span style="color:#6e7681">#${{x.id}}</span></span><span class="conf">${{sc}}</span></div>`;}}).join('')
      : '<div class="empty">no birds right now…</div>';
    const s = await (await fetch('/summary')).json();
    document.getElementById('today').innerHTML = s.species.length
      ? s.species.map(r=>`<div class="card clickable" onclick="openSpecies('${{r.species}}')"><span class="name">${{r.species}}</span><span class="conf">${{r.n}}</span></div>`).join('')
      : '<div class="empty">no visits logged yet…</div>';
    document.getElementById('stats').innerHTML = `stream: ${{d.fps}} fps · detector: ${{d.detect_ms}} ms/run`;
  }}catch(e){{}}
}}
setInterval(tick, 800); tick();
</script></body></html>
"""

TIMELINE_HTML = ("""
<!doctype html><html><head><meta charset="utf-8"><title>Bird Watch — Timeline</title><style>__STYLE__
  .box{max-width:760px;margin:0 auto;padding:16px}
  .group{background:#161b22;border:1px solid #21262d;border-radius:10px;margin-bottom:10px;overflow:hidden}
  .ghead{display:flex;align-items:center;gap:12px;padding:10px 14px;cursor:pointer;user-select:none}
  .ghead img{width:46px;height:46px;object-fit:cover;border-radius:8px;background:#000}
  .ghead .gname{font-weight:600;flex:1}
  .ghead .gcount{color:#3fb950;font-weight:600;background:#12261a;border:1px solid #21402c;border-radius:12px;padding:1px 10px;font-size:13px}
  .ghead .arrow{color:#8b949e;transition:transform .15s;font-size:11px}
  .group.open .arrow{transform:rotate(90deg)}
  .ginstances{display:none;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px;padding:0 14px 14px}
  .group.open .ginstances{display:grid}
  .inst{cursor:pointer;border:1px solid #21262d;border-radius:8px;overflow:hidden;background:#0d1117}
  .inst:hover{border-color:#3fb950}
  .inst img{width:100%;height:88px;object-fit:cover;display:block;background:#000}
  .inst .it{font-size:11px;color:#8b949e;padding:5px 7px}
  .empty{color:#6e7681;font-style:italic;padding:24px}
  __MODAL_CSS__
</style></head><body>
<header><h1>Bird Watch — Timeline</h1>
  <span style="color:#8b949e;font-size:13px">grouped by species — tap to expand</span>
  <span style="margin-left:auto"><a href="/">← Live</a></span></header>
<div class="box"><div id="groups"></div></div>
__MODAL_HTML__
<script>
__MODAL_JS__
const openGroups = new Set();
function openInstance(image, species, ts, conf){
  document.getElementById('modal').classList.add('show');
  document.getElementById('m_name').textContent=species;
  const img=document.getElementById('m_img');
  if(image){ img.src='/captures/'+image; img.style.display='block'; } else { img.style.display='none'; }
  const c = conf ? ' · '+Math.round(conf*100)+'%' : '';
  document.getElementById('m_counts').textContent = new Date(ts).toLocaleString()+c;
  document.getElementById('m_extract').textContent='Loading…';
  document.getElementById('m_aab').style.display='none'; document.getElementById('m_link').style.display='none';
  fetch('/species/'+encodeURIComponent(species)).then(r=>r.json()).then(d=>{
    document.getElementById('m_extract').textContent=d.extract||'No description found.';
    setSpeciesLinks(d);
  }).catch(()=>{document.getElementById('m_extract').textContent='Could not load info.';});
}
async function load(){
  const d=await (await fetch('/visits?limit=500')).json();
  const g=document.getElementById('groups');
  if(!d.visits.length){ g.innerHTML='<div class="empty">No visits logged yet. Leave the live view running — birds appear here as they come and go.</div>'; return; }
  const by={};
  d.visits.forEach(v=>{ (by[v.species]=by[v.species]||[]).push(v); });
  const species=Object.keys(by).sort((a,b)=> by[b][0].id - by[a][0].id);  // most recently seen first
  g.innerHTML = species.map(sp=>{
    const items=by[sp];
    const rep=items.find(x=>x.image)||items[0];
    const thumb=rep.image?'/captures/'+rep.image:'';
    const open=openGroups.has(sp)?' open':'';
    const insts=items.map(v=>{
      const t=new Date(v.start_ts).toLocaleString();
      const im=v.image?'/captures/'+v.image:'';
      return '<div class="inst" data-image="'+(v.image||'')+'" data-sp="'+sp+'" data-ts="'+v.start_ts+'" data-conf="'+(v.species_conf||0)+'">'+
             (im?'<img src="'+im+'">':'')+'<div class="it">'+t+'</div></div>';
    }).join('');
    return '<div class="group'+open+'"><div class="ghead" data-sp="'+sp+'">'+
           (thumb?'<img src="'+thumb+'">':'<div style="width:46px;height:46px"></div>')+
           '<span class="gname">'+sp+'</span><span class="gcount">'+items.length+'</span>'+
           '<span class="arrow">▶</span></div><div class="ginstances">'+insts+'</div></div>';
  }).join('');
}
// event delegation (robust to species names with apostrophes, e.g. "Cooper's Hawk")
document.getElementById('groups').addEventListener('click', e=>{
  const inst=e.target.closest('.inst');
  if(inst){ openInstance(inst.dataset.image, inst.dataset.sp, inst.dataset.ts, parseFloat(inst.dataset.conf)); return; }
  const head=e.target.closest('.ghead');
  if(head){ const sp=head.dataset.sp, grp=head.parentNode; grp.classList.toggle('open');
    grp.classList.contains('open')?openGroups.add(sp):openGroups.delete(sp); }
});
load(); setInterval(load, 5000);
</script></body></html>
""").replace("__STYLE__", _STYLE).replace("__MODAL_CSS__", _MODAL_CSS).replace("__MODAL_HTML__", _MODAL_HTML).replace("__MODAL_JS__", _MODAL_JS)

SETTINGS_HTML = """
<!doctype html><html><head><meta charset="utf-8"><title>Bird Watch — Settings</title><style>__STYLE__
  .box{max-width:560px;margin:16px auto;padding:0 16px}
  .row{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 16px;margin-bottom:12px}
  .row label{display:block;font-weight:600;margin-bottom:6px}
  .row .hint{color:#8b949e;font-size:12px;margin-top:6px}
  input,select{width:100%;box-sizing:border-box;background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:8px;padding:9px;font-size:14px}
  input[type=range]{padding:0}
  .two{display:flex;gap:12px} .two>div{flex:1}
  button{background:#238636;color:#fff;border:none;border-radius:8px;padding:11px 18px;font-weight:600;cursor:pointer;font-size:15px}
  button.sec{background:#21262d;color:#e6edf3;border:1px solid #30363d}
  .status{padding:10px 14px;border-radius:8px;margin-bottom:12px;font-size:13px;line-height:1.5}
  .ok{background:#12261a;color:#3fb950;border:1px solid #21402c}
  .warn{background:#2b2412;color:#d29922;border:1px solid #493f16}
  code{background:#0d1117;border:1px solid #30363d;border-radius:4px;padding:1px 5px;font-size:12px}
  .chips span{display:inline-block;background:#21262d;border:1px solid #30363d;border-radius:14px;padding:3px 10px;margin:4px 4px 0 0;font-size:12px;cursor:pointer}
</style></head><body>
<header><h1>Bird Watch — Settings</h1><span style="margin-left:auto"><a href="/">← Live</a></span></header>
<div class="box">
  <div id="ntfy" class="status"></div>
  <div class="row"><label>Notifications</label>
    <select id="mode">
      <option value="instant">Instant — alert as birds arrive</option>
      <option value="digest">Daily digest — one summary per day</option>
      <option value="off">Off</option>
    </select></div>
  <div class="row"><label>Which birds?</label>
    <input id="species" placeholder="e.g. Northern Cardinal, Ruby-throated Hummingbird">
    <div class="hint">Comma-separated. Leave blank to be notified about <b>any</b> bird. Tap a recent one to add:</div>
    <div class="chips" id="chips"></div></div>
  <div class="row"><label>Only notify above confidence: <span id="mcv"></span></label>
    <input type="range" id="min_conf" min="0" max="1" step="0.05"></div>
  <div class="row"><label>Quiet hours (no instant alerts)</label>
    <div class="two"><div><div class="hint">From (hour)</div><input type="number" id="quiet_start" min="0" max="23"></div>
      <div><div class="hint">Until (hour)</div><input type="number" id="quiet_end" min="0" max="23"></div></div></div>
  <div class="row"><label>Per-bird cooldown (minutes)</label>
    <input type="number" id="cooldown_min" min="0" max="1440">
    <div class="hint">Avoids repeat alerts from the same visitor.</div></div>
  <div class="row"><label>Daily digest time (hour, 0–23)</label>
    <input type="number" id="digest_hour" min="0" max="23"></div>
  <div style="display:flex;gap:10px;margin-bottom:30px;align-items:center">
    <button onclick="savePrefs()">Save</button>
    <button class="sec" onclick="testNotify()">Send test</button>
    <span id="saved" style="color:#3fb950"></span>
  </div>
</div>
<script>
const $=id=>document.getElementById(id);
async function loadStatus(){
  const r=await (await fetch('/notify-status')).json();
  const st=$('ntfy');
  if(r.configured){ st.className='status ok'; st.innerHTML='Connected to ntfy topic <b>'+r.topic+'</b> — alerts go to your phone.'; }
  else { st.className='status warn'; st.innerHTML='<b>No phone connected yet</b> (dry-run). To get alerts: install the <b>ntfy</b> app, subscribe to a topic like <code>annes-birds-x7q</code>, then restart the server with <code>NTFY_TOPIC=annes-birds-x7q</code>.'; }
}
async function loadPrefs(){
  const p=await (await fetch('/prefs')).json();
  $('mode').value=p.mode; $('species').value=(p.species||[]).join(', ');
  $('min_conf').value=p.min_conf; $('mcv').textContent=Math.round(p.min_conf*100)+'%';
  $('quiet_start').value=p.quiet_start; $('quiet_end').value=p.quiet_end;
  $('cooldown_min').value=p.cooldown_min; $('digest_hour').value=p.digest_hour;
  const s=await (await fetch('/summary')).json();
  $('chips').innerHTML=(s.species||[]).map(r=>'<span onclick="addSp(\\''+r.species+'\\')">'+r.species+'</span>').join('');
}
$('min_conf').addEventListener('input',()=>$('mcv').textContent=Math.round($('min_conf').value*100)+'%');
function addSp(n){const cur=$('species').value.split(',').map(x=>x.trim()).filter(Boolean); if(!cur.includes(n))cur.push(n); $('species').value=cur.join(', ');}
async function savePrefs(){
  const body={mode:$('mode').value,
    species:$('species').value.split(',').map(x=>x.trim()).filter(Boolean),
    min_conf:parseFloat($('min_conf').value), quiet_start:+$('quiet_start').value, quiet_end:+$('quiet_end').value,
    cooldown_min:+$('cooldown_min').value, digest_hour:+$('digest_hour').value};
  await fetch('/prefs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  $('saved').textContent='Saved ✓'; setTimeout(()=>$('saved').textContent='',2000);
}
async function testNotify(){
  const r=await (await fetch('/notify-test',{method:'POST'})).json();
  const st=$('ntfy');
  if(r.configured){ st.className='status ok'; st.innerHTML='Test sent to <b>'+r.topic+'</b> — check your phone.'; }
  else { st.className='status warn'; st.innerHTML='Dry-run: no phone connected. See the server console for the message. Set <code>NTFY_TOPIC</code> to send for real.'; }
}
loadStatus(); loadPrefs();
</script></body></html>
""".replace("__STYLE__", _STYLE)
