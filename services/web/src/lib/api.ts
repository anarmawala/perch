import type {
  DetectionsResponse,
  NotifyStatus,
  Prefs,
  SpeciesInfo,
  SummaryRow,
  Visit,
} from "./types";

// Everything is same-origin under /api (vite proxy in dev, nginx in prod).
const BASE = "/api";

export const streamUrl = `${BASE}/stream`;
export const captureUrl = (file: string) => `${BASE}/captures/${file}`;

async function get<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json() as Promise<T>;
}

export const getDetections = () => get<DetectionsResponse>("/detections");
export const getSummary = () =>
  get<{ today: string; species: SummaryRow[] }>("/summary");
export const getVisits = (limit = 500) =>
  get<{ visits: Visit[] }>(`/visits?limit=${limit}`);
export const getSpecies = (name: string) =>
  get<SpeciesInfo>(`/species/${encodeURIComponent(name)}`);
export const getPrefs = () => get<Prefs>("/prefs");
export const getNotifyStatus = () => get<NotifyStatus>("/notify-status");

export async function savePrefs(p: Partial<Prefs>): Promise<Prefs> {
  const r = await fetch(`${BASE}/prefs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(p),
  });
  if (!r.ok) throw new Error(`prefs -> ${r.status}`);
  return r.json();
}

export async function sendTestNotification(): Promise<{
  sent: boolean;
  configured: boolean;
}> {
  const r = await fetch(`${BASE}/notify-test`, { method: "POST" });
  return r.json();
}
