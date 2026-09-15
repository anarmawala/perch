import { useMemo, useState } from "preact/hooks";
import { captureUrl, getVisits } from "@/lib/api";
import { usePoll } from "@/lib/hooks";
import type { SpeciesTarget } from "@/components/SpeciesModal";
import type { Visit } from "@/lib/types";

export function Timeline({ openSpecies }: { openSpecies: (name: string, extra?: Partial<SpeciesTarget>) => void }) {
  const data = usePoll(() => getVisits(500), 5000);
  const [open, setOpen] = useState<Set<string>>(new Set());

  const groups = useMemo(() => {
    const by = new Map<string, Visit[]>();
    for (const v of data?.visits ?? []) {
      const arr = by.get(v.species) ?? [];
      arr.push(v);
      by.set(v.species, arr);
    }
    // most-recently-seen species first (visits come newest-id first)
    return [...by.entries()].sort((a, b) => b[1][0].id - a[1][0].id);
  }, [data]);

  const toggle = (sp: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(sp)) next.delete(sp);
      else next.add(sp);
      return next;
    });

  if (data && groups.length === 0) {
    return (
      <p class="p-8 text-center italic text-ink-subtle">
        No visits logged yet. Leave the live view running — birds appear here as they come and go.
      </p>
    );
  }

  return (
    <div class="mx-auto max-w-3xl space-y-3 p-4">
      {groups.map(([species, items]) => {
        const isOpen = open.has(species);
        const rep = items.find((v) => v.image) ?? items[0];
        return (
          <section key={species} class="overflow-hidden rounded-card border border-line bg-surface shadow-card">
            <button onClick={() => toggle(species)} class="flex w-full items-center gap-3 px-4 py-3 text-left">
              {rep.image ? (
                <img
                  src={captureUrl(rep.image)}
                  alt={species}
                  loading="lazy"
                  class="h-12 w-12 shrink-0 rounded-lg bg-surface-2 object-cover"
                />
              ) : (
                <div class="h-12 w-12 shrink-0 rounded-lg bg-surface-2" />
              )}
              <span class="flex-1 font-semibold">{species}</span>
              <span class="rounded-full bg-brand-50 px-2.5 py-0.5 text-sm font-semibold text-brand-700">
                {items.length}
              </span>
              <span class={`text-ink-subtle transition-transform ${isOpen ? "rotate-90" : ""}`}>▸</span>
            </button>

            {isOpen && (
              <div class="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-2.5 px-4 pb-4">
                {items.map((v) => (
                  <button
                    key={v.id}
                    onClick={() =>
                      openSpecies(species, {
                        image: v.image,
                        ts: v.start_ts,
                        conf: v.species_conf,
                        id: v.id,
                        kept: v.kept,
                      })
                    }
                    class="overflow-hidden rounded-lg border border-line bg-surface text-left hover:border-brand-500"
                  >
                    {v.image ? (
                      <img
                        src={captureUrl(v.image)}
                        alt={species}
                        loading="lazy"
                        class="h-20 w-full bg-surface-2 object-cover"
                      />
                    ) : (
                      <div class="h-20 w-full bg-surface-2" />
                    )}
                    <div class="px-2 py-1.5 text-[11px] text-ink-muted">
                      {new Date(v.start_ts).toLocaleString([], {
                        month: "short",
                        day: "numeric",
                        hour: "numeric",
                        minute: "2-digit",
                      })}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
