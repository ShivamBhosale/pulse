import { useRecords } from "../api/hooks";
import { Card, ErrorNote } from "../components/ui";
import { fmtDay, fmtNum } from "../lib/format";
import { fmtMetric, useUnits } from "../lib/units";

function ago(iso: string): string {
  const days = Math.round((Date.now() - new Date(`${iso}T12:00:00`).getTime()) / 864e5);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 60) return `${days} days ago`;
  if (days < 730) return `${Math.round(days / 30)} months ago`;
  return `${fmtNum(days / 365, 1)} years ago`;
}

export function RecordsPage() {
  const q = useRecords();
  const units = useUnits();
  if (q.error) return <ErrorNote error={q.error} />;
  if (!q.data) return <div className="card h-64 animate-pulse" />;
  const { bests, streaks } = q.data;
  return (
    <div className="flex flex-col gap-4">
      <h1 className="reveal text-2xl font-semibold tracking-tight">Records & streaks</h1>
      <Card index={1} title="Streaks" subtitle="Today and this week are in progress: they extend a streak but never break it">
        <ul className="grid gap-5 sm:grid-cols-3">
          {streaks.map((s) => {
            const max = Math.max(s.longest, s.current, 1);
            const unit = s.period === "day" ? "days" : "weeks";
            const goal = s.key === "sleep" ? fmtMetric(s.goal, "min", units, "sleep_main_min") : `${fmtNum(s.goal)} ${s.key === "steps" ? "steps" : "min"}`;
            return (
              <li key={s.key}>
                <div className="eyebrow">{s.label}</div>
                <div className="text-xs text-muted">
                  {goal} {s.period === "day" ? "a day" : "a week"}
                </div>
                <div className="mt-2 flex items-baseline gap-1.5">
                  <span className="num text-3xl font-medium">{s.current}</span>
                  <span className="text-sm text-muted">{unit} now</span>
                </div>
                <div className="mt-2 space-y-1.5" aria-hidden>
                  <div className="h-1.5 rounded-full bg-surface-2">
                    <div className="h-full rounded-full bg-accent" style={{ width: `${(s.current / max) * 100}%` }} />
                  </div>
                  <div className="h-1.5 rounded-full bg-surface-2">
                    <div className="h-full rounded-full bg-[var(--neutral-series)]" style={{ width: `${(s.longest / max) * 100}%` }} />
                  </div>
                </div>
                <div className="num mt-1.5 text-xs text-ink-2">
                  Longest {s.longest} {unit}
                  {s.longest_end && <span className="text-muted"> · ended {fmtDay(s.longest_end, { day: "numeric", month: "short", year: "numeric" })}</span>}
                </div>
              </li>
            );
          })}
        </ul>
      </Card>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {bests.map((b, i) => (
          <article key={b.key} className="card reveal flex flex-col gap-1 p-4" style={{ ["--i" as string]: i + 2 }}>
            <h3 className="eyebrow">{b.label}</h3>
            <div className="num text-[26px] font-medium leading-tight">{fmtMetric(b.value, b.unit, units, b.key === "longest_workout" ? "" : b.key)}</div>
            <div className="text-xs text-ink-2">
              {fmtDay(b.date, { weekday: "short", day: "numeric", month: "short", year: "numeric" })} <span className="text-muted">· {ago(b.date)}</span>
            </div>
            {b.note && <div className="text-xs text-muted">{b.note}</div>}
          </article>
        ))}
      </div>
    </div>
  );
}
