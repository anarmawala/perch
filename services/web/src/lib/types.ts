// Box coords are normalized (0..1) relative to the source frame, so the client
// can scale them to whatever size the video is rendered at.
export interface Detection {
  id: number;
  box: [number, number, number, number]; // [x1, y1, x2, y2] in 0..1
  species: string;
  species_conf: number;
}

export interface DetectionsResponse {
  detections: Detection[];
  fps: number;
  detect_ms: number;
}

export interface SummaryRow {
  species: string;
  n: number;
}

export interface Visit {
  id: number;
  species: string;
  species_conf: number;
  start_ts: string;
  end_ts: string;
  seconds: number;
  frames: number;
  image: string;
  kept: number;
}

export interface SpeciesInfo {
  name: string;
  total: number;
  today: number;
  last: string | null;
  aab_url: string;
  extract: string;
  thumb: string;
  url: string;
}

export interface Prefs {
  mode: "instant" | "digest" | "off";
  species: string[];
  min_conf: number;
  quiet_start: number;
  quiet_end: number;
  cooldown_min: number;
  digest_hour: number;
}

export interface NotifyStatus {
  configured: boolean;
  topic: string;
  server: string;
}
