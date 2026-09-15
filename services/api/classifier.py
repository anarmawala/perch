#!/usr/bin/env python3
"""
Lightweight bird species classifier (iNaturalist MobileNetV2, TFLite, ~3.5 MB).

Runs on a cropped bird box and returns the top species guesses. CPU-friendly —
this is the "not stupidly heavy" model that turns a YOLO 'bird' box into an
actual species name for the X-Ray panel.
"""

import re
from pathlib import Path

import cv2
import numpy as np
from ai_edge_litert.interpreter import Interpreter

_HERE = Path(__file__).parent
DEFAULT_MODEL = _HERE / "models" / "inat_bird.tflite"
DEFAULT_LABELS = _HERE / "models" / "inat_bird_labels.txt"


def common_name(label: str) -> str:
    """'Haemorhous mexicanus (House Finch)' -> 'House Finch'."""
    m = re.search(r"\(([^)]+)\)", label)
    return m.group(1) if m else label


# Species not in the local region list are multiplied by this (soft prior, so a
# very confident off-list detection can still win — it just needs more evidence).
PRIOR_PENALTY = 0.05


def _square_pad(img):
    """Pad a crop to a square with replicated edge pixels (no stretching)."""
    h, w = img.shape[:2]
    if h == w:
        return img
    s = max(h, w)
    top, left = (s - h) // 2, (s - w) // 2
    return cv2.copyMakeBorder(img, top, s - h - top, left, s - w - left, cv2.BORDER_REPLICATE)


class BirdClassifier:
    def __init__(self, model_path=DEFAULT_MODEL, labels_path=DEFAULT_LABELS):
        self.interp = Interpreter(model_path=str(model_path))
        self.interp.allocate_tensors()
        self.inp = self.interp.get_input_details()[0]
        self.out = self.interp.get_output_details()[0]
        _, self.h, self.w, _ = self.inp["shape"]
        with open(labels_path) as f:
            self.labels = [ln.strip() for ln in f if ln.strip()]
        self.common = [common_name(l) for l in self.labels]
        self.prior = None  # optional per-label multiplier from a region allowlist

    def set_allow(self, allow):
        """Apply a geographic prior: downweight labels whose common name isn't in
        `allow` (a set of common names). Pass None to disable."""
        if not allow:
            self.prior = None
            return
        self.prior = np.array([1.0 if c in allow else PRIOR_PENALTY
                               for c in self.common], dtype=np.float32)
        n = int(sum(1 for c in self.common if c in allow))
        print(f"[classifier] region prior active: {n}/{len(self.common)} species boosted")

    def classify(self, bgr_crop, topk=3):
        """Return [(common_name, full_label, score), ...] best-first."""
        if bgr_crop.size == 0:
            return []
        # Square-pad (replicate edges) so the bird isn't stretched to a square, then
        # resize with cubic interpolation — preserves shape/proportions the model relies on.
        crop = _square_pad(bgr_crop)
        img = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.w, self.h), interpolation=cv2.INTER_CUBIC)
        x = img.astype(self.inp["dtype"])
        if self.inp["dtype"] == np.float32:
            x = x / 127.5 - 1.0
        x = np.expand_dims(x, 0)
        self.interp.set_tensor(self.inp["index"], x)
        self.interp.invoke()
        out = self.interp.get_tensor(self.out["index"])[0].astype(np.float32)
        scale, zp = self.out["quantization"]
        if scale:  # dequantize the uint8 output to real probabilities
            out = (out - zp) * scale
        if self.prior is not None:  # apply the geographic prior
            out = out * self.prior
        idx = out.argsort()[-topk:][::-1]
        return [(self.common[i], self.labels[i], float(out[i])) for i in idx]


if __name__ == "__main__":
    import sys
    from ultralytics import YOLO

    from region import load_allowlist

    image = sys.argv[1] if len(sys.argv) > 1 else "test_frame.jpg"
    frame = cv2.imread(image)
    yolo = YOLO("yolov8s.pt")
    bird_id = next(i for i, n in yolo.names.items() if n == "bird")
    clf = BirdClassifier()
    if "--prior" in sys.argv:
        clf.set_allow(load_allowlist())

    res = yolo(frame, imgsz=640, classes=[bird_id], conf=0.2, verbose=False)[0]
    print(f"{image}: {len(res.boxes)} bird box(es)\n")
    for i, b in enumerate(res.boxes, 1):
        x1, y1, x2, y2 = map(int, b.xyxy[0])
        # pad the crop a little so the whole bird is in view
        pad = 8
        crop = frame[max(0, y1 - pad):y2 + pad, max(0, x1 - pad):x2 + pad]
        preds = clf.classify(crop, topk=3)
        det = f"box{i} (yolo conf {float(b.conf[0]):.2f}):"
        print(det)
        for name, full, score in preds:
            print(f"    {score:5.2f}  {name}")
        print()
