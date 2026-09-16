import { useEffect, useRef } from "preact/hooks";
import { getDetections, streamUrl } from "@/lib/api";
import { usePoll } from "@/lib/hooks";
import type { Detection } from "@/lib/types";

interface Props {
  showBoxes: boolean;
  showStats: boolean;
  onPickSpecies: (name: string) => void;
}

const BOX = "#1f9d57";

export function VideoStage({ showBoxes, showStats, onPickSpecies }: Props) {
  const data = usePoll(getDetections, 500);
  const detections = data?.detections ?? [];

  const imgRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const detsRef = useRef<Detection[]>([]);
  detsRef.current = detections;

  // Draw the client-side overlay, kept sized to the rendered video.
  useEffect(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;

    const draw = () => {
      const w = img.clientWidth;
      const h = img.clientHeight;
      if (!w || !h) return;
      if (canvas.width !== w) canvas.width = w;
      if (canvas.height !== h) canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, w, h);
      if (!showBoxes) return;

      for (const d of detsRef.current) {
        const [x1, y1, x2, y2] = d.box;
        const bx = x1 * w;
        const by = y1 * h;
        const bw = (x2 - x1) * w;
        const bh = (y2 - y1) * h;
        ctx.lineWidth = 2;
        ctx.strokeStyle = BOX;
        ctx.strokeRect(bx, by, bw, bh);

        const label = d.species_conf ? `${d.species} ${Math.round(d.species_conf * 100)}%` : d.species;
        ctx.font = "600 13px system-ui, sans-serif";
        const tw = ctx.measureText(label).width;
        const ly = Math.max(0, by - 20);
        ctx.fillStyle = BOX;
        ctx.fillRect(bx, ly, tw + 12, 20);
        ctx.fillStyle = "#fff";
        ctx.fillText(label, bx + 6, ly + 14);
      }
    };

    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(img);
    return () => ro.disconnect();
    // redraw whenever the toggle flips or fresh detections arrive (via `data`)
  }, [showBoxes, data]);

  // Keep the MJPEG stream alive across tab-backgrounding / phone-sleep / blips.
  // The browser suspends the <img> connection when hidden and never re-opens it,
  // leaving a black frame until a manual refresh. So: reconnect (cache-busted) when
  // the page becomes visible, drop the connection while hidden, and retry on error.
  useEffect(() => {
    const img = imgRef.current;
    if (!img) return;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      img.src = `${streamUrl}${streamUrl.includes("?") ? "&" : "?"}t=${Date.now()}`;
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") connect();
      else img.removeAttribute("src"); // free the connection while backgrounded
    };
    const onError = () => {
      if (document.visibilityState !== "visible") return;
      clearTimeout(retry);
      retry = setTimeout(connect, 2000);
    };
    img.addEventListener("error", onError);
    document.addEventListener("visibilitychange", onVisibility);
    addEventListener("pageshow", onVisibility); // iOS/PWA bfcache restore
    return () => {
      clearTimeout(retry);
      img.removeEventListener("error", onError);
      document.removeEventListener("visibilitychange", onVisibility);
      removeEventListener("pageshow", onVisibility);
    };
  }, []);

  const onClick = (e: MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas || !showBoxes) return;
    const rect = canvas.getBoundingClientRect();
    const px = (e.clientX - rect.left) / rect.width;
    const py = (e.clientY - rect.top) / rect.height;
    for (const d of detsRef.current) {
      const [x1, y1, x2, y2] = d.box;
      if (px >= x1 && px <= x2 && py >= y1 && py <= y2) {
        onPickSpecies(d.species);
        return;
      }
    }
  };

  const n = detections.length;

  return (
    <div class="relative aspect-video w-full overflow-hidden rounded-card bg-black shadow-card">
      <img ref={imgRef} src={streamUrl} alt="Live feeder" class="h-full w-full object-cover" />
      <canvas
        ref={canvasRef}
        onClick={onClick}
        class="absolute inset-0 h-full w-full"
        style={{ cursor: showBoxes ? "pointer" : "default" }}
      />
      {showStats && data && (
        <div class="absolute left-3 top-3 flex items-center gap-2 rounded-lg bg-black/55 px-2.5 py-1 text-xs font-medium tabular-nums text-white backdrop-blur">
          <span class={`inline-block h-1.5 w-1.5 rounded-full ${data.idle ? "bg-ink-subtle" : "bg-live"}`} />
          {data.idle ? "idle" : `${n} bird${n === 1 ? "" : "s"}`} · {data.fps} fps ·{" "}
          {data.idle ? "gated" : `${data.detect_ms}+${data.classify_ms} ms`}
        </div>
      )}
    </div>
  );
}
