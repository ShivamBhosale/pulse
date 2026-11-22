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
export type MetricSeries = Schemas["MetricSeries"];
export type MultiSeries = Schemas["MultiSeries"];
export type MetricInfo = Schemas["MetricInfo"];
export type WeekdayProfile = Schemas["WeekdayProfile"];
export type Correlation = Schemas["Correlation"];
export type Heatmap = Schemas["Heatmap"];
export type ExerciseList = Schemas["ExerciseList"];
export type Exercise = Schemas["ExerciseOut"];
export type ExerciseDetail = Schemas["ExerciseDetail"];
export type Records = Schemas["Records"];
export type Settings = Schemas["SettingsOut"];
export type SettingsIn = Schemas["SettingsIn"];
export type ReadinessComponent = Schemas["ReadinessComponent"];
export type Granularity = Schemas["MetricSeries"]["granularity"];

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

const qs = (params: Record<string, string | string[] | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else if (v) p.set(k, v);
  }
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const api = {
  today: () => request<Today>("/api/v1/today"),
  status: () => request<Status>("/api/v1/status"),
  sleep: (date?: string) => request<SleepNight>(`/api/v1/sleep${qs({ date })}`),
  sleepTrend: (from: string, to: string) => request<SleepTrend>(`/api/v1/sleep/trend${qs({ from, to })}`),
  sync: () => request<{ status: string }>("/api/v1/sync", { method: "POST" }),
  metric: (metric: string, from: string, to: string, granularity: Granularity, band = false) =>
    request<MetricSeries>(
      `/api/v1/metrics/${metric}${qs({ from, to, granularity, band: band ? "true" : undefined })}`,
    ),
  series: (metrics: string[], from: string, to: string, granularity: Granularity) =>
    request<MultiSeries>(`/api/v1/series${qs({ metrics, from, to, granularity })}`),
  weekday: (metric: string, from: string, to: string) =>
    request<WeekdayProfile>(`/api/v1/metrics/${metric}/weekday${qs({ from, to })}`),
  correlate: (a: string, b: string, from: string, to: string) =>
    request<Correlation>(`/api/v1/explore/correlate${qs({ a, b, from, to })}`),
  heatmap: (from: string, to: string) => request<Heatmap>(`/api/v1/activity/heatmap${qs({ from, to })}`),
  intradayHr: (date: string) => request<IntradayHeartRate>(`/api/v1/intraday/heart-rate${qs({ date })}`),
  exercises: (from: string, to: string) => request<ExerciseList>(`/api/v1/exercises${qs({ from, to })}`),
  exercise: (id: string) => request<ExerciseDetail>(`/api/v1/exercises/${id.split("/").map(encodeURIComponent).join("/")}`),
  records: () => request<Records>("/api/v1/records"),
  settings: () => request<Settings>("/api/v1/settings"),
  updateSettings: (body: SettingsIn) =>
    request<Settings>("/api/v1/settings", { method: "PUT", body: JSON.stringify(body) }),
  changePasscode: (current: string | null, next: string | null) =>
    request<void>("/api/v1/settings/passcode", {
      method: "PUT",
      body: JSON.stringify({ current, new: next }),
    }),
  backfill: (since: string | null) =>
    request<{ job: string }>("/api/v1/backfill", { method: "POST", body: JSON.stringify({ since }) }),
  resync: (since: string, streams: string[] | null) =>
    request<{ job: string }>("/api/v1/resync", { method: "POST", body: JSON.stringify({ since, streams }) }),
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
