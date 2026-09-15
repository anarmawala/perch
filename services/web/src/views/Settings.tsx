import { useEffect, useState } from "preact/hooks";
import { getNotifyStatus, getPrefs, getSummary, savePrefs, sendTestNotification } from "@/lib/api";
import type { NotifyStatus, Prefs } from "@/lib/types";

export function Settings() {
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [status, setStatus] = useState<NotifyStatus | null>(null);
  const [seen, setSeen] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getPrefs()
      .then(setPrefs)
      .catch(() => {});
    getNotifyStatus()
      .then(setStatus)
      .catch(() => {});
    getSummary()
      .then((s) => setSeen(s.species.map((r) => r.species)))
      .catch(() => {});
  }, []);

  if (!prefs) return <p class="p-8 text-center text-ink-subtle">Loading…</p>;

  const set = <K extends keyof Prefs>(k: K, v: Prefs[K]) => setPrefs({ ...prefs, [k]: v });

  const speciesText = prefs.species.join(", ");
  const setSpeciesText = (t: string) =>
    set(
      "species",
      t
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean),
    );
  const addSpecies = (name: string) => {
    if (!prefs.species.includes(name)) set("species", [...prefs.species, name]);
  };

  const onSave = async () => {
    const p = await savePrefs(prefs);
    setPrefs(p);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div class="mx-auto max-w-xl space-y-4 p-4">
      <div
        class={`rounded-card border px-4 py-3 text-sm ${
          status?.configured
            ? "border-brand-100 bg-brand-50 text-brand-700"
            : "border-amber-200 bg-amber-50 text-amber-700"
        }`}
      >
        {status?.configured ? (
          <>
            Connected to ntfy topic <b>{status.topic}</b> — alerts go to your phone.
          </>
        ) : (
          <>
            <b>No phone connected yet.</b> Install the <b>ntfy</b> app, subscribe to a topic, and set{" "}
            <code>NTFY_TOPIC</code> on the server.
          </>
        )}
      </div>

      <Card label="Notifications">
        <select
          value={prefs.mode}
          onChange={(e) => set("mode", (e.target as HTMLSelectElement).value as Prefs["mode"])}
          class="w-full rounded-lg border border-line bg-surface px-3 py-2"
        >
          <option value="instant">Instant — alert as birds arrive</option>
          <option value="digest">Daily digest — one summary per day</option>
          <option value="off">Off</option>
        </select>
      </Card>

      <Card label="Which birds?" hint="Comma-separated. Blank = any bird.">
        <input
          value={speciesText}
          onInput={(e) => setSpeciesText((e.target as HTMLInputElement).value)}
          placeholder="e.g. Northern Cardinal, Ruby-throated Hummingbird"
          class="w-full rounded-lg border border-line bg-surface px-3 py-2"
        />
        {seen.length > 0 && (
          <div class="mt-2 flex flex-wrap gap-1.5">
            {seen.map((s) => (
              <button
                key={s}
                onClick={() => addSpecies(s)}
                class="rounded-full border border-line bg-surface-2 px-2.5 py-1 text-xs hover:border-brand-500"
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </Card>

      <Card label={`Only notify above ${Math.round(prefs.min_conf * 100)}% confidence`}>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={prefs.min_conf}
          onInput={(e) => set("min_conf", parseFloat((e.target as HTMLInputElement).value))}
          class="w-full"
        />
      </Card>

      <div class="grid grid-cols-2 gap-4">
        <Card label="Quiet from (hour)">
          <NumberInput value={prefs.quiet_start} min={0} max={23} onChange={(v) => set("quiet_start", v)} />
        </Card>
        <Card label="Quiet until (hour)">
          <NumberInput value={prefs.quiet_end} min={0} max={23} onChange={(v) => set("quiet_end", v)} />
        </Card>
      </div>

      <Card label="Per-bird cooldown (minutes)" hint="Avoids repeat alerts from the same visitor.">
        <NumberInput value={prefs.cooldown_min} min={0} max={1440} onChange={(v) => set("cooldown_min", v)} />
      </Card>

      <div class="flex items-center gap-3 pb-8">
        <button
          onClick={onSave}
          class="rounded-lg bg-brand-500 px-5 py-2.5 font-semibold text-white hover:bg-brand-600"
        >
          Save
        </button>
        <button
          onClick={() => sendTestNotification()}
          class="rounded-lg border border-line px-5 py-2.5 font-semibold text-ink hover:bg-surface-2"
        >
          Send test
        </button>
        {saved && <span class="font-medium text-brand-600">Saved ✓</span>}
      </div>
    </div>
  );
}

function Card({ label, hint, children }: { label: string; hint?: string; children: preact.ComponentChildren }) {
  return (
    <div class="rounded-card border border-line bg-surface p-4 shadow-card">
      <label class="mb-2 block font-semibold">{label}</label>
      {children}
      {hint && <p class="mt-2 text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}

function NumberInput({
  value,
  min,
  max,
  onChange,
}: {
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
}) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      onInput={(e) => onChange(Number((e.target as HTMLInputElement).value))}
      class="w-full rounded-lg border border-line bg-surface px-3 py-2"
    />
  );
}
