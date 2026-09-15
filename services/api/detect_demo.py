#!/usr/bin/env python3
"""
Prove the core capability: draw boxes on birds.

Runs a YOLO detector on an image, keeps only the 'bird' class, draws boxes +
confidence, and saves an annotated copy. This is the exact detection step that
will feed the live X-Ray overlay — here we just run it on one still to see it work.

Usage:
    python detect_demo.py test_frame.jpg
    python detect_demo.py test_frame.jpg --model yolov8s.pt --conf 0.25
"""

import argparse
from pathlib import Path

import cv2
from ultralytics import YOLO


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", help="Path to an image to run detection on")
    ap.add_argument("--model", default="yolov8s.pt", help="YOLO weights (auto-downloads)")
    ap.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    ap.add_argument("--out", default=None, help="Output path (default: <image>_boxed.jpg)")
    args = ap.parse_args()

    model = YOLO(args.model)
    # COCO 'bird' is one class; restrict detection to it.
    bird_id = next(i for i, n in model.names.items() if n == "bird")

    results = model(args.image, conf=args.conf, classes=[bird_id], verbose=False)[0]

    img = cv2.imread(args.image)
    n = 0
    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        conf = float(box.conf[0])
        n += 1
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 220, 0), 3)
        label = f"bird {conf:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(img, (x1, y1 - th - 8), (x1 + tw + 4, y1), (0, 220, 0), -1)
        cv2.putText(img, label, (x1 + 2, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

    out = args.out or str(Path(args.image).with_name(Path(args.image).stem + "_boxed.jpg"))
    cv2.imwrite(out, img)
    print(f"Found {n} bird(s). Annotated image -> {out}")


if __name__ == "__main__":
    main()
