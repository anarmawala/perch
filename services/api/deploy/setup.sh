#!/usr/bin/env bash
# Bird Watch — one-shot setup for an Intel NUC (Ubuntu/Debian).
# Run from anywhere:  bash deploy/setup.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # the prototype/ dir
cd "$HERE"
echo "==> Bird Watch setup in $HERE"

echo "==> Installing system packages (ffmpeg, python venv)…"
sudo apt-get update -y
sudo apt-get install -y ffmpeg python3-venv python3-pip

echo "==> Creating virtualenv (.venv-ml)…"
python3 -m venv .venv-ml
.venv-ml/bin/pip install --upgrade pip wheel
.venv-ml/bin/pip install -r requirements.txt

echo "==> Pre-fetching detector weights…"
.venv-ml/bin/python -c "from ultralytics import YOLO; YOLO('yolov8s.pt')" || true

echo
echo "Done. Try it:"
echo "  .venv-ml/bin/uvicorn app:app --host 0.0.0.0 --port 8000"
echo "Then open http://<this-nuc-ip>:8000 from any device on the network."
echo
echo "For a faster Intel run, export OpenVINO once:"
echo "  .venv-ml/bin/python deploy/export_openvino.py   # then set YOLO_MODEL=yolov8s_openvino_model"
echo "To run it as an always-on service, see deploy/README.md."
