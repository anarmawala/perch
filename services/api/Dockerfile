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
# Longer HTTP timeout for slow/flaky package mirrors.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=180 \
    PATH="/app/.venv/bin:$PATH"

# Dependencies first — this layer is cached and only rebuilds when deps change.
# A persistent uv cache mount keeps already-downloaded wheels across builds, so a
# retry after a flaky-network failure resumes instead of re-fetching everything.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen

COPY . .

# Bake in the detector weights and export to OpenVINO (Intel CPU runtime, 2-3x
# faster than torch on the NUC). Export at the inference size so shapes match —
# 1920 so small/distant feeder birds survive the letterbox (must match YOLO_IMGSZ).
# Produces /app/yolov8s_openvino_model/, which the detector prefers at runtime.
RUN python -c "from ultralytics import YOLO; YOLO('yolov8s.pt').export(format='openvino', imgsz=1920)"

# Persistent state (db, photos, prefs) lives here — mounted as a volume.
ENV DATA_DIR=/app/data \
    INFER_THREADS=3 \
    DETECT_INTERVAL=0.5 \
    YOLO_IMGSZ=960
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
