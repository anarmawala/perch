import { useState } from "preact/hooks";
import { VideoStage } from "@/components/VideoStage";
import { XRayPanel } from "@/components/XRayPanel";

export function Live({
  openSpecies,
}: {
  openSpecies: (name: string) => void;
}) {
  const [boxes, setBoxes] = useState(true);
  const [stats, setStats] = useState(true);
  const [panel, setPanel] = useState(false);

  return (
    <div class="flex h-full flex-col p-3 sm:p-4">
      {/* Video is the hero — fills available space, centered, capped to fit height */}
      <div class="flex min-h-0 flex-1 items-center justify-center">
        <div class="w-full max-w-[calc((100vh-11rem)*16/9)]">
          <VideoStage
            showBoxes={boxes}
            showStats={stats}
            onPickSpecies={openSpecies}
          />
        </div>
      </div>

      {/* Controls */}
      <div class="mt-3 flex items-center justify-center gap-2">
        <Toggle active={boxes} onClick={() => setBoxes(!boxes)}>
          X-Ray
        </Toggle>
        <Toggle active={stats} onClick={() => setStats(!stats)}>
          Stats
        </Toggle>
        <button
          onClick={() => setPanel(true)}
          class="rounded-full bg-brand-500 px-5 py-2 text-sm font-semibold text-white shadow-card hover:bg-brand-600"
        >
          Who's here
        </button>
      </div>

      <XRayPanel
        open={panel}
        onClose={() => setPanel(false)}
        onPickSpecies={(n) => {
          setPanel(false);
          openSpecies(n);
        }}
      />
    </div>
  );
}

function Toggle({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: preact.ComponentChildren;
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      class={`rounded-full px-5 py-2 text-sm font-semibold shadow-card transition-colors ${
        active ? "bg-ink text-white" : "bg-surface text-ink-muted hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}
