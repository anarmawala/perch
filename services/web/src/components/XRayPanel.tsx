import { getDetections, getSummary } from "@/lib/api";
import { usePoll } from "@/lib/hooks";

interface Props {
  open: boolean;
  onClose: () => void;
  onPickSpecies: (name: string) => void;
}

export function XRayPanel({ open, onClose, onPickSpecies }: Props) {
  const dets = usePoll(getDetections, open ? 800 : 60000);
  const summary = usePoll(getSummary, open ? 4000 : 60000);
  const onScreen = dets?.detections ?? [];
  const today = summary?.species ?? [];

  return (
    <>
      <div
        onClick={onClose}
        class={`fixed inset-0 z-30 bg-black/30 transition-opacity duration-200 ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />
      <aside
        class={`safe-b fixed z-40 flex flex-col overflow-hidden bg-surface shadow-pop transition-transform duration-300 ease-out
          inset-x-0 bottom-0 max-h-[78vh] rounded-t-2xl
          sm:inset-y-0 sm:left-auto sm:right-0 sm:max-h-none sm:w-[380px] sm:rounded-none
          ${open ? "translate-y-0 sm:translate-x-0" : "translate-y-full sm:translate-y-0 sm:translate-x-full"}`}
      >
        <header class="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 class="font-semibold">X-Ray</h2>
          <button
            onClick={onClose}
            class="rounded-full px-2 text-xl leading-none text-ink-muted hover:text-ink"
            aria-label="Close"
          >
            ×
          </button>
        </header>

        <div class="flex-1 overflow-y-auto px-5 py-4">
          <SectionLabel>On screen now</SectionLabel>
          {onScreen.length === 0 ? (
            <Empty>No birds right now…</Empty>
          ) : (
            <ul class="space-y-2">
              {onScreen.map((d) => (
                <li key={d.id}>
                  <Row
                    label={d.species}
                    right={d.species_conf ? `${Math.round(d.species_conf * 100)}%` : ""}
                    onClick={() => onPickSpecies(d.species)}
                  />
                </li>
              ))}
            </ul>
          )}

          <SectionLabel class="mt-6">Seen today</SectionLabel>
          {today.length === 0 ? (
            <Empty>No visits logged yet…</Empty>
          ) : (
            <ul class="space-y-2">
              {today.map((r) => (
                <li key={r.species}>
                  <Row label={r.species} right={`${r.n}`} onClick={() => onPickSpecies(r.species)} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </>
  );
}

function SectionLabel({ children, class: cls = "" }: { children: preact.ComponentChildren; class?: string }) {
  return <h3 class={`mb-2 text-xs font-semibold uppercase tracking-wide text-ink-subtle ${cls}`}>{children}</h3>;
}

function Row({ label, right, onClick }: { label: string; right: string; onClick: () => void }) {
  const known = label !== "Bird";
  return (
    <button
      onClick={known ? onClick : undefined}
      class={`flex w-full items-center justify-between rounded-xl border border-line bg-surface px-4 py-3 text-left ${
        known ? "hover:border-brand-500" : "cursor-default"
      }`}
    >
      <span class="flex items-center gap-2 font-medium">
        <span class="inline-block h-1.5 w-1.5 rounded-full bg-brand-500" />
        {label}
      </span>
      <span class="font-semibold tabular-nums text-brand-600">{right}</span>
    </button>
  );
}

function Empty({ children }: { children: preact.ComponentChildren }) {
  return <p class="text-sm italic text-ink-subtle">{children}</p>;
}
