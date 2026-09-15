#!/usr/bin/env python3
"""
Export the YOLO detector to OpenVINO — Intel's inference runtime — for a big
speedup on the Intel NUC's CPU/iGPU. Run once on the NUC:

    .venv-ml/bin/python deploy/export_openvino.py

Then point the app at the exported model:

    YOLO_MODEL=yolov8s_openvino_model .venv-ml/bin/uvicorn app:app --host 0.0.0.0 --port 8000

(ultralytics loads the exported directory just like a .pt file.)
"""
from ultralytics import YOLO

if __name__ == "__main__":
    m = YOLO("yolov8s.pt")
    path = m.export(format="openvino")   # -> yolov8s_openvino_model/
    print(f"\nExported to: {path}")
    print("Set  YOLO_MODEL=yolov8s_openvino_model  to use it.")
