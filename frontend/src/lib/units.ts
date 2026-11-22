import { useSettings } from "../api/hooks";
import { fmtClock, fmtDuration, fmtNum } from "./format";

export type Units = "metric" | "imperial";

export const useUnits = (): Units => useSettings().data?.units ?? "metric";

const CLOCK = new Set(["bedtime_min", "waketime_min"]);
const DURATION = /^sleep_.*_min$|^sleep_min$|^sleep_debt_min$|_sd_min$|^sedentary.*min$/;

/** Display unit for a metric (after unit conversion). */
export function unitLabel(unit: string, units: Units, key = ""): string {
  if (CLOCK.has(key) || DURATION.test(key)) return "";
  if (units === "imperial" && unit === "km") return "mi";
  if (units === "imperial" && unit === "°C") return "°F";
  if (unit === "count" || unit === "steps") return "steps";
  if (unit === "score" || unit === "ratio") return "";
  return unit;
}

/** Convert a raw value into display units (numbers only, for chart axes). */
export function convert(v: number, unit: string, units: Units, key = ""): number {
  if (units !== "imperial") return v;
  if (unit === "km") return v * 0.621371;
  if (unit === "°C") return key.includes("delta") ? v * 1.8 : v * 1.8 + 32;
  return v;
}

const DECIMALS: Record<string, number> = { km: 2, "%": 1, ms: 1, "°C": 2, ratio: 2 };

/** Value + unit, formatted for this metric ("7h 05m", "23:40", "4.21 mi", "52 bpm"). */
export function fmtMetric(v: number | null | undefined, unit: string, units: Units, key = "", withUnit = true): string {
  if (v == null || Number.isNaN(v)) return "–";
  if (CLOCK.has(key)) return fmtClock(v);
  if (DURATION.test(key)) return fmtDuration(v);
  const dec = DECIMALS[unit] ?? 0;
  const value = convert(v, unit, units, key);
  const sign = key.includes("delta") && value > 0 ? "+" : "";
  const u = unitLabel(unit, units, key);
  return `${sign}${fmtNum(value, dec)}${withUnit && u ? ` ${u}` : ""}`;
}

/** Short axis label (no unit) in display units. */
export function fmtAxis(v: number, unit: string, units: Units, key = ""): string {
  if (CLOCK.has(key)) return fmtClock(v);
  if (DURATION.test(key)) {
    const h = v / 60;
    return Number.isInteger(h) ? `${h}h` : Math.abs(h) < 1 ? `${Math.round(v)}m` : `${fmtNum(h, 1)}h`;
  }
  const value = convert(v, unit, units, key);
  if (Math.abs(value) >= 10000) return `${fmtNum(value / 1000)}k`;
  const a = Math.abs(value);
  return fmtNum(value, Number.isInteger(value) || a >= 10 ? 0 : a < 1 ? 2 : 1);
}

/** Hour-aligned tick interval for duration metrics (so a sleep axis reads 0h, 2h, 4h…). */
export function durationInterval(key: string, max: number): number | undefined {
  if (!DURATION.test(key) || !Number.isFinite(max) || max <= 0) return undefined;
  const steps = [30, 60, 120, 180, 240, 360];
  return steps.find((s) => max / s <= 5) ?? 480;
}
