import type { Route } from "@/lib/hooks";

const TABS: [Route, string][] = [
  ["live", "Live"],
  ["timeline", "Timeline"],
  ["settings", "Settings"],
];

export function TopBar({ route, navigate }: { route: Route; navigate: (r: Route) => void }) {
  return (
    <header class="safe-t sticky top-0 z-20 flex items-center gap-3 border-b border-line bg-surface/90 px-4 py-2.5 backdrop-blur">
      <span class="flex items-center gap-2 font-semibold tracking-tight">
        <span class="inline-block h-2 w-2 animate-pulse rounded-full bg-live" />
        Perch
      </span>
      <nav class="ml-auto flex gap-1 rounded-full bg-surface-2 p-1 text-sm font-medium">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            onClick={() => navigate(id)}
            class={`rounded-full px-3 py-1 transition-colors ${
              route === id ? "bg-surface text-ink shadow-card" : "text-ink-muted hover:text-ink"
            }`}
          >
            {label}
          </button>
        ))}
      </nav>
    </header>
  );
}
