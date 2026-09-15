#!/usr/bin/env python3
"""
Push notifications via ntfy (https://ntfy.sh) — free, no account:
  1. Install the "ntfy" app (iOS/Android) or open ntfy.sh in a browser.
  2. Subscribe to a topic name of your choosing, e.g. "annes-birds-8f3a".
  3. export NTFY_TOPIC=annes-birds-8f3a   (pick something unguessable)
Optional: self-host ntfy and set NTFY_SERVER=https://your-server.

Without NTFY_TOPIC set, notifications are printed (dry-run) so the rest of the
system is fully testable before you wire up a phone.
"""

import os
import urllib.request
from pathlib import Path

NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
# Optional URL the notification opens when tapped (e.g. http://<server-ip>:8000/timeline)
CLICK_URL = os.environ.get("PUBLIC_URL", "")


def _hdr(s):
    """HTTP headers must be latin-1; drop anything that isn't (e.g. emoji)."""
    return str(s).encode("latin-1", "ignore").decode("latin-1")


def send(title, message, image_path=None, tags="bird", priority=None, click=None):
    """Send a push. Attaches image_path as a photo if given. Returns True on send.
    Put emoji in `tags` (ntfy renders them), not in title — headers are latin-1."""
    if not NTFY_TOPIC:
        extra = f"  [photo: {Path(image_path).name}]" if image_path else ""
        print(f"[notify:dry-run] {title} — {message}{extra}")
        return False

    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"
    headers = {"Title": _hdr(title), "Tags": _hdr(tags)}
    if priority:
        headers["Priority"] = str(priority)
    if click or CLICK_URL:
        headers["Click"] = click or CLICK_URL
    try:
        if image_path and Path(image_path).exists():
            headers["Message"] = _hdr(message)
            headers["Filename"] = _hdr(Path(image_path).name)
            req = urllib.request.Request(url, data=Path(image_path).read_bytes(),
                                         headers=headers, method="PUT")
        else:
            req = urllib.request.Request(url, data=message.encode("utf-8"),
                                         headers=headers, method="POST")
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print("[notify] send failed:", e)
        return False


if __name__ == "__main__":
    ok = send("Bird Watch test", "If you see this on your phone, notifications work!",
              tags="tada", priority=4)
    print("sent" if ok else "dry-run (set NTFY_TOPIC to actually send)")
