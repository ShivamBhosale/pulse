import type { components } from "./schema";

type Schemas = components["schemas"];
export type Today = Schemas["Today"];
export type Tile = Schemas["Tile"];
export type Status = Schemas["Status"];
export type IntradayHeartRate = Schemas["IntradayHeartRate"];
export type StepsCurve = Schemas["StepsCurve"];
export type SleepNight = Schemas["SleepNight"];
export type SleepSession = Schemas["SleepSessionOut"];
export type SleepTrend = Schemas["SleepTrend"];
export type SleepTrendNight = Schemas["SleepTrendNight"];
export type SessionState = Schemas["SessionState"];

export class Locked extends Error {
  constructor() {
    super("passcode required");
  }
}

export const LOCKED_EVENT = "pulse:locked";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) },
  });
  if (res.status === 401 && !path.endsWith("/session")) {
    window.dispatchEvent(new Event(LOCKED_EVENT));
    throw new Locked();
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const qs = (params: Record<string, string | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const api = {
  today: () => request<Today>("/api/v1/today"),
  status: () => request<Status>("/api/v1/status"),
  sleep: (date?: string) => request<SleepNight>(`/api/v1/sleep${qs({ date })}`),
  sleepTrend: (from: string, to: string) => request<SleepTrend>(`/api/v1/sleep/trend${qs({ from, to })}`),
  sync: () => request<{ status: string }>("/api/v1/sync", { method: "POST" }),
  session: () => request<SessionState>("/api/v1/session"),
  unlock: async (passcode: string): Promise<"ok" | "wrong" | "limited"> => {
    const res = await fetch("/api/v1/session", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passcode }),
    });
    if (res.status === 204) return "ok";
    return res.status === 429 ? "limited" : "wrong";
  },
};
