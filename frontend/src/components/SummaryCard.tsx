import { useState } from "react";
import { Link } from "react-router-dom";
import type { Summary } from "../api/client";
import { useSummary } from "../api/hooks";
import { addDays, fmtDay } from "../lib/format";

const TONE = {
  good: { icon: "●", color: "var(--good)", label: "Good" },
  attention: { icon: "▲", color: "var(--warning)", label: "Worth a look" },
  neutral: { icon: "·", color: "var(--ink-muted)", label: "Note" },
} as const;

/** Where a sentence's chart lives. */
function linkFor(metrics: string[], date: string): string | null {
  const m = metrics[0] ?? "";
  if (m.startsWith("sleep") || m === "bedtime_min") return `/sleep?date=${date}`;
  if (["resting_hr", "hrv_rmssd", "spo2_avg", "skin_temp_delta"].includes(m)) return "/heart";
  if (["steps", "azm", "load_ratio"].includes(m)) return "/activity";
  if (m === "readiness") return null;
  return "/records";
}

/** Rule-based daily summary (templates, no AI), with ← → through earlier days. */
export function SummaryCard({ today, initial }: { today: string; initial: Summary }) {
  const [date, setDate] = useState(today);
  const q = useSummary(date, date !== today);
  const s = date === today ? initial : q.data;
  return (
    <section className="card reveal relative overflow-hidden p-4" style={{ ["--i" as string]: 0 }} aria-label="Daily summary">
      <div aria-hidden className="pointer-events-none absolute inset-y-0 left-0 w-[3px] bg-accent" />
      <header className="mb-2 flex items-center justify-between gap-3">
        <div className="eyebrow">{date === today ? "Today so far" : fmtDay(date, { weekday: "long", day: "numeric", month: "short" })}</div>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => setDate(addDays(date, -1))} className="rounded-md border border-line px-2 py-0.5 text-xs text-ink-2 hover:text-ink" aria-label="Previous day's summary">
            ←
          </button>
          <button
            type="button"
            onClick={() => setDate(addDays(date, 1))}
            disabled={date >= today}
            className="rounded-md border border-line px-2 py-0.5 text-xs text-ink-2 hover:text-ink disabled:opacity-40"
            aria-label="Next day's summary"
          >
            →
          </button>
        </div>
      </header>
      {!s ? (
        <div className="h-24 animate-pulse rounded-lg bg-surface-2/60" />
      ) : (
        <>
          <h2 className="text-lg font-medium leading-snug tracking-tight text-ink">{s.headline}</h2>
          {s.sentences.length > 0 ? (
            <ul className="mt-2 space-y-1.5">
              {s.sentences.map((x) => {
                const tone = TONE[x.tone];
                const to = linkFor(x.metrics, s.date);
                const body = (
                  <>
                    <span aria-hidden className="mt-[3px] w-3 shrink-0 text-center text-[11px] leading-4" style={{ color: tone.color }}>
                      {tone.icon}
                    </span>
                    <span className="sr-only">{tone.label}: </span>
                    <span className="text-sm leading-snug text-ink-2">{x.text}</span>
                  </>
                );
                return (
                  <li key={x.text}>
                    {to ? (
                      <Link to={to} className="-mx-1 flex gap-2 rounded-md px-1 py-0.5 transition-colors hover:bg-surface-2">
                        {body}
                      </Link>
                    ) : (
                      <div className="flex gap-2 px-0 py-0.5">{body}</div>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="mt-1 text-sm text-muted">Nothing stands out yet.</p>
          )}
          <p className="mt-3 text-[11px] text-muted">Written by fixed rules from your own data and baselines. Not medical advice.</p>
        </>
      )}
    </section>
  );
}
