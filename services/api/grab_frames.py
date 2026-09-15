#!/usr/bin/env python3
"""
Phase 0 prototype: pull frames from a live YouTube bird-feeder stream and save
a still whenever motion is detected. No AI yet — this just proves we can
reliably capture visitors from a real video source.

The video source is deliberately the ONLY thing that changes when we later swap
in a real RTSP camera: replace resolve_stream_url()/the source arg with the
camera's rtsp:// URL and everything downstream stays the same.

Usage:
    python grab_frames.py --url "https://www.youtube.com/watch?v=<live_id>"
    python grab_frames.py --url "<youtube_or_rtsp_url>" --out captures --min-area 800

Deps: see pyproject.toml  (yt-dlp, opencv-python, numpy) — `uv sync`
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2


def resolve_stream_url(source: str) -> str:
    """Turn a YouTube URL into a direct stream URL via yt-dlp.

    Passes rtsp://, http(s):// .m3u8, and local file paths straight through so
    the same script works for the eventual real camera.
    """
    if source.startswith("rtsp://") or source.endswith(".m3u8") or Path(source).exists():
        return source
    try:
        # -g prints the direct media URL; -f best picks a combined stream.
        out = subprocess.run(
            ["yt-dlp", "-f", "best", "-g", source],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        sys.exit("yt-dlp not found. Install deps:  uv sync")
    except subprocess.CalledProcessError as e:
        sys.exit(f"yt-dlp failed to resolve the stream:\n{e.stderr}")
    # Last non-empty line is the media URL.
    urls = [ln for ln in out.stdout.splitlines() if ln.strip()]
    if not urls:
        sys.exit("yt-dlp returned no stream URL (is the stream live?).")
    return urls[-1]


def open_capture(source: str) -> cv2.VideoCapture:
    stream_url = resolve_stream_url(source)
    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        sys.exit(f"Could not open video stream: {source}")
    return cap


def main() -> None:
    ap = argparse.ArgumentParser(description="Motion-triggered frame capture from a video stream.")
    ap.add_argument("--url", required=True, help="YouTube URL, rtsp:// URL, or local file")
    ap.add_argument("--out", default="captures", help="Directory to save motion frames")
    ap.add_argument("--min-area", type=int, default=800,
                    help="Min changed-pixel area (px) to count as motion. Raise to ignore small movement.")
    ap.add_argument("--cooldown", type=float, default=3.0,
                    help="Seconds to wait after a save before saving again (groups a burst into one visit).")
    ap.add_argument("--refresh", type=float, default=1800.0,
                    help="Seconds before re-resolving the stream URL (live URLs expire).")
    ap.add_argument("--show", action="store_true", help="Show a preview window (needs a display).")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cap = open_capture(args.url)
    opened_at = time.time()
    prev_gray = None
    last_save = 0.0
    saved = 0

    print(f"Watching {args.url}\nSaving motion frames to {out_dir.resolve()}\nCtrl-C to stop.\n")

    try:
        while True:
            ok, frame = cap.read()

            # Stream dropped or URL expired: reconnect (re-resolving if it's a YouTube URL).
            if not ok or (time.time() - opened_at > args.refresh):
                print("Reconnecting to stream...")
                cap.release()
                time.sleep(2)
                cap = open_capture(args.url)
                opened_at = time.time()
                prev_gray = None
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            if prev_gray is None:
                prev_gray = gray
                continue

            # Frame differencing → threshold → dilate → contour areas.
            delta = cv2.absdiff(prev_gray, gray)
            thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
            thresh = cv2.dilate(thresh, None, iterations=2)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            motion_area = sum(cv2.contourArea(c) for c in contours)
            prev_gray = gray

            now = time.time()
            if motion_area > args.min_area and (now - last_save) > args.cooldown:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = out_dir / f"{ts}_area{int(motion_area)}.jpg"
                cv2.imwrite(str(path), frame)
                saved += 1
                last_save = now
                print(f"[{ts}] motion (area={int(motion_area)}) -> {path.name}   (total: {saved})")

            if args.show:
                cv2.imshow("bird_watch prototype", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        print(f"\nStopped. Saved {saved} frames to {out_dir.resolve()}")
    finally:
        cap.release()
        if args.show:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
