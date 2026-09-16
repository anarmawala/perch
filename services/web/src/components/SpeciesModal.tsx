import { useEffect, useState } from "preact/hooks";
import { captureUrl, getSpecies, keepVisit } from "@/lib/api";
import type { SpeciesInfo } from "@/lib/types";

export interface SpeciesTarget {
  species: string;
  image?: string; // a specific captured thumbnail (timeline instance)
  ts?: string;
  conf?: number;
  id?: number; // visit id (timeline instance) — enables "keep"
  kept?: number;
}

export function SpeciesModal({ target, onClose }: { target: SpeciesTarget; onClose: () => void }) {
  const [info, setInfo] = useState<SpeciesInfo | null>(null);
  const [kept, setKept] = useState(!!target.kept);
  const [zoom, setZoom] = useState(false);

  const toggleKeep = async () => {
    if (target.id == null) return;
    const next = !kept;
    setKept(next);
    try {
      await keepVisit(target.id, next);
    } catch {
      setKept(!next); // revert on failure
    }
  };

  useEffect(() => {
    setInfo(null);
    getSpecies(target.species)
      .then(setInfo)
      .catch(() => setInfo(null));
  }, [target.species]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (zoom) setZoom(false);
      else onClose();
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [onClose, zoom]);

  const captured = target.image ? captureUrl(target.image) : "";
  const subtitle = target.ts
    ? new Date(target.ts).toLocaleString() + (target.conf ? ` · ${Math.round(target.conf * 100)}%` : "")
    : info
      ? `Seen ${info.today} today · ${info.total} total`
      : "";

  return (
    <div
      onClick={(e) => e.target === e.currentTarget && onClose()}
      class="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4"
    >
      <div class="safe-b max-h-[90vh] w-full overflow-y-auto rounded-t-2xl bg-surface shadow-pop sm:max-w-lg sm:rounded-card">
        {/* The captured shot of this bird — shown whole (never cropped); tap to zoom. */}
        {captured && (
          <button
            onClick={() => setZoom(true)}
            class="flex w-full justify-center bg-ink/90 sm:rounded-t-card"
            aria-label="View full size"
          >
            <img src={captured} alt={target.species} class="max-h-[60vh] w-full object-contain" />
          </button>
        )}

        <div class="p-5">
          <div class="flex items-start justify-between gap-3">
            <div>
              <h2 class="text-xl font-semibold">{target.species}</h2>
              {subtitle && <p class="mt-0.5 text-sm font-medium text-brand-600">{subtitle}</p>}
            </div>
            <button
              onClick={onClose}
              class="rounded-full px-2 text-2xl leading-none text-ink-muted hover:text-ink"
              aria-label="Close"
            >
              ×
            </button>
          </div>

          {target.id != null && (
            <button
              onClick={toggleKeep}
              class={`mt-4 flex w-full items-center justify-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold ${
                kept ? "border-brand-500 bg-brand-50 text-brand-700" : "border-line text-ink hover:bg-surface-2"
              }`}
            >
              {kept ? "★ Kept — won't be deleted" : "☆ Keep this photo"}
            </button>
          )}

          {info?.aab_url && (
            <a
              href={info.aab_url}
              target="_blank"
              rel="noopener"
              class="mt-3 inline-block text-sm font-semibold text-brand-600 hover:text-brand-700"
            >
              Field guide →
            </a>
          )}
        </div>
      </div>

      {/* Full-size view of the captured photo. */}
      {zoom && captured && (
        <div
          onClick={() => setZoom(false)}
          class="fixed inset-0 z-[60] flex items-center justify-center bg-black/90 p-4"
        >
          <img src={captured} alt={target.species} class="max-h-[95vh] max-w-full object-contain" />
        </div>
      )}
    </div>
  );
}
