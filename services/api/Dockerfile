FROM python:3.11-slim

# ffmpeg decodes the live stream; libgl/glib satisfy OpenCV's runtime deps.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only torch FIRST — the default PyPI torch wheel drags in ~2 GB of CUDA
# libraries that are useless on this CPU-only NUC. This keeps the image small
# and the build fast. ultralytics then finds torch already satisfied.
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bake in the detector weights (downloads if not already in the build context)
# so the first run needs no network and starts instantly.
RUN python -c "from ultralytics import YOLO; YOLO('yolov8s.pt')"

# Persistent state (db, photos, prefs) lives here — mounted as a volume.
ENV DATA_DIR=/app/data \
    INFER_THREADS=3 \
    DETECT_INTERVAL=0.5 \
    YOLO_IMGSZ=960
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
