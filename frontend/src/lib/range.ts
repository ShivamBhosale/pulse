import { useSearchParams } from "react-router-dom";
import { addDays, isoDate } from "./format";

export const RANGES = ["7D", "30D", "90D", "1Y", "All"] as const;
export type Range = (typeof RANGES)[number];
export type Granularity = "day" | "week" | "month";

const DAYS: Record<Exclude<Range, "All">, number> = { "7D": 7, "30D": 30, "90D": 90, "1Y": 365 };

export interface Span {
  from: string;
  to: string;
  granularity: Granularity;
  range: Range;
}

/** Date span for a range. "All" starts at the first day with data (falls back to 2 years). */
export function spanFor(range: Range, firstDate?: string | null, today = isoDate(new Date())): Span {
  if (range === "All") {
    const from = firstDate ?? addDays(today, -730);
    const days = (new Date(`${today}T12:00:00`).getTime() - new Date(`${from}T12:00:00`).getTime()) / 864e5;
    return { from, to: today, granularity: days > 1100 ? "month" : "week", range };
  }
  return {
    from: addDays(today, -(DAYS[range] - 1)),
    to: today,
    granularity: range === "1Y" ? "week" : "day",
    range,
  };
}

/** Range kept in the URL (?range=90D) so it survives reloads and can be shared. */
export function useRange(fallback: Range = "90D", key = "range"): [Range, (r: Range) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get(key);
  const value = (RANGES as readonly string[]).includes(raw ?? "") ? (raw as Range) : fallback;
  const set = (r: Range) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set(key, r);
        return next;
      },
      { replace: true },
    );
  return [value, set];
}
