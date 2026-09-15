FROM python:3.11-slim

# uv — fast, reproducible Python installs from the committed uv.lock.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# ffmpeg decodes the live stream; libgl/glib satisfy OpenCV's runtime deps.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Compile bytecode for faster cold starts; copy (don't hardlink) wheels into the layer.
# The lockfile pins CPU-only torch (see pyproject [tool.uv.sources]), so no CUDA bloat.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Dependencies first — this layer is cached and only rebuilds when deps change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache

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
