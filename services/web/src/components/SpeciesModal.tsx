import { useEffect, useState } from "preact/hooks";
import { captureUrl, getSpecies } from "@/lib/api";
import type { SpeciesInfo } from "@/lib/types";

export interface SpeciesTarget {
  species: string;
  image?: string; // a specific captured thumbnail (timeline instance)
  ts?: string;
  conf?: number;
}

export function SpeciesModal({
  target,
  onClose,
}: {
  target: SpeciesTarget;
  onClose: () => void;
}) {
  const [info, setInfo] = useState<SpeciesInfo | null>(null);

  useEffect(() => {
    setInfo(null);
    getSpecies(target.species).then(setInfo).catch(() => setInfo(null));
  }, [target.species]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [onClose]);

  const hero = target.image
    ? captureUrl(target.image)
    : info?.thumb || "";
  const subtitle = target.ts
    ? new Date(target.ts).toLocaleString() +
      (target.conf ? ` · ${Math.round(target.conf * 100)}%` : "")
    : info
      ? `Seen ${info.today} today · ${info.total} total`
      : "";

  return (
    <div
      onClick={(e) => e.target === e.currentTarget && onClose()}
      class="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4"
    >
      <div class="safe-b max-h-[88vh] w-full overflow-y-auto rounded-t-2xl bg-surface shadow-pop sm:max-w-md sm:rounded-card">
        {hero && (
          <img
            src={hero}
            alt={target.species}
            class="h-52 w-full object-cover sm:rounded-t-card"
          />
        )}
        <div class="p-5">
          <div class="flex items-start justify-between gap-3">
            <div>
              <h2 class="text-xl font-semibold">{target.species}</h2>
              {subtitle && (
                <p class="mt-0.5 text-sm font-medium text-brand-600">
                  {subtitle}
                </p>
              )}
            </div>
            <button
              onClick={onClose}
              class="rounded-full px-2 text-2xl leading-none text-ink-muted hover:text-ink"
              aria-label="Close"
            >
              ×
            </button>
          </div>

          <p class="mt-3 text-sm leading-relaxed text-ink">
            {info ? info.extract || "No description found." : "Loading…"}
          </p>

          {info && (
            <div class="mt-4 flex flex-wrap gap-2">
              {info.aab_url && (
                <a
                  href={info.aab_url}
                  target="_blank"
                  rel="noopener"
                  class="rounded-lg bg-brand-500 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-600"
                >
                  Field guide →
                </a>
              )}
              {info.url && (
                <a
                  href={info.url}
                  target="_blank"
                  rel="noopener"
                  class="rounded-lg border border-line px-4 py-2 text-sm font-semibold text-ink hover:bg-surface-2"
                >
                  Wikipedia →
                </a>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
