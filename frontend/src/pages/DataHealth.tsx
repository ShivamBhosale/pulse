import { useState } from "react";
import type { CellState, Coverage, DataFreshness, SignalCoverage } from "../api/client";
import { useCoverage, useDayHealth, useFreshness, useResync } from "../api/hooks";
import { Card, ErrorNote, RangeTabs } from "../components/ui";
import { addDays, fmtAgo, fmtDay, fmtDuration, fmtNum, fmtTime, isoDate } from "../lib/format";

const RANGES = ["30D", "90D", "1Y"] as const;
type R = (typeof RANGES)[number];
const DAYS: Record<R, number> = { "30D": 30, "90D": 90, "1Y": 365 };

const STATE_TEXT: Record<CellState, string> = {
  ok: "Has data",
  low: "Band mostly off (under half the day)",
  missing: "Missing",
  untracked: "Not tracked yet",
  today: "Today (in progress)",
};
const FRESH = {
  fresh: { icon: "●", color: "var(--good)", word: "fresh" },
  behind: { icon: "▲", color: "var(--warning)", word: "a bit behind" },
  stale: { icon: "▲", color: "var(--serious)", word: "stale" },
  none: { icon: "○", color: "var(--ink-muted)", word: "no data" },
} as const;

function fmtLag(min: number | null | undefined): string {
  if (min == null) return "–";
  if (min < 60) return `${Math.round(min)} min`;
  if (min < 48 * 60) return `${fmtNum(min / 60, min < 600 ? 1 : 0)} h`;
  return `${Math.round(min / 1440)} days`;
}

function FreshnessCard({ f }: { f: DataFreshness }) {
  const b = f.band;
  const t = FRESH[b.status];
  const errors = f.streams.filter((s) => s.last_error);
  return (
    <section className="card reveal grid gap-4 p-4 md:grid-cols-[1.2fr_2fr]" style={{ ["--i" as string]: 1 }} aria-label="Freshness">
      <div>
        <div className="eyebrow mb-1">Band → Google → Pulse</div>
        <div className="flex items-baseline gap-2">
          <span aria-hidden style={{ color: t.color }}>{t.icon}</span>
          <span className="text-lg font-medium text-ink">
            {b.latest_at ? `Band data up to ${fmtTime(b.latest_at)}` : "No band data yet"}
          </span>
        </div>
        <div className="num mt-0.5 text-sm text-ink-2">
          {b.latest_at ? `${fmtLag(b.lag_min)} ago · ${t.word}` : ""}
        </div>
        {(b.status === "behind" || b.status === "stale") && (
          <p className="mt-2 text-xs text-ink-2">Open the Fitbit app on your phone so the band syncs to Google. Pulse picks it up within 15 minutes.</p>
        )}
        <div className="num mt-2 text-xs text-muted">
          Pulse synced {fmtAgo(f.last_sync)}
          {f.next_run && ` · next ${fmtTime(f.next_run)}`}
          {f.job && <span className="text-accent-ink"> · {f.job} running…</span>}
        </div>
        {errors.length > 0 && (
          <p className="mt-2 text-xs text-ink-2">
            <span className="text-serious" aria-hidden>▲ </span>
            {errors.length} stream{errors.length === 1 ? "" : "s"} failed last time: {errors.map((e) => e.stream).join(", ")}
          </p>
        )}
      </div>
      <ul className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
        {f.signals
          .filter((s) => s.key !== "wear")
          .map((s) => {
            const st = FRESH[s.status];
            return (
              <li key={s.key} className="min-w-0">
                <div className="truncate text-xs text-muted">{s.label}</div>
                <div className="num truncate text-ink-2">
                  <span aria-hidden style={{ color: st.color }}>{st.icon} </span>
                  {s.latest_at ? `${fmtTime(s.latest_at)} · ${fmtLag(s.lag_min)} ago` : s.latest_date ? fmtDay(s.latest_date, { day: "numeric", month: "short" }) : "–"}
                  <span className="sr-only"> ({st.word})</span>
                </div>
              </li>
            );
          })}
      </ul>
    </section>
  );
}

const CELL = 12;
const GAP = 2;
const LABEL_W = 0;

/** One row per signal, one column per day. Shape + fill + outline carry the state, not colour alone. */
function CoverageGrid({ c, selected, onSelect }: { c: Coverage; selected: string | null; onSelect: (d: string) => void }) {
  const n = c.days.length;
  const w = n * (CELL + GAP);
  const h = c.signals.length * (CELL + 6);
  const compact = n > 120;
  return (
    <div className="grid grid-cols-[132px_minmax(0,1fr)] gap-x-2">
      <div>
        {c.signals.map((s) => (
          <div key={s.key} className="flex h-[18px] items-center truncate text-xs text-ink-2">
            {s.label}
          </div>
        ))}
      </div>
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${w + LABEL_W} ${h}`}
          width={compact ? "100%" : w}
          height={h}
          preserveAspectRatio="none"
          role="grid"
          aria-label="Data coverage per signal and day"
          className="block min-w-full"
        >
          {c.signals.map((s, row) =>
            s.cells.map((state, i) => {
              const d = c.days[i]!;
              const x = i * (CELL + GAP);
              const y = row * (CELL + 6) + 3;
              const v = s.values[i];
              const title = `${s.label} · ${fmtDay(d)} · ${STATE_TEXT[state]}${v != null ? ` · worn ${Math.round(v * 100)}%` : ""}`;
              const common = { x, y, width: CELL, height: CELL, rx: 2 };
              const isSel = selected === d;
              let el;
              if (state === "ok" || state === "low") {
                const opacity = s.key === "wear" && v != null ? 0.25 + 0.75 * v : 0.85;
                el = <rect {...common} fill="var(--accent)" fillOpacity={opacity} />;
              } else if (state === "missing") {
                el = <rect {...common} x={x + 0.5} y={y + 0.5} width={CELL - 1} height={CELL - 1} fill="none" stroke="var(--warning)" strokeWidth={1} />;
              } else if (state === "today") {
                el = <rect {...common} x={x + 0.5} y={y + 0.5} width={CELL - 1} height={CELL - 1} fill="none" stroke="var(--ink-muted)" strokeDasharray="2 2" />;
              } else {
                el = <rect {...common} fill="var(--surface-2)" fillOpacity={0.5} />;
              }
              return (
                <g key={`${s.key}-${d}`} onClick={() => onSelect(d)} style={{ cursor: "pointer" }}>
                  <title>{title}</title>
                  {/* hit area larger than the mark, covering the gaps around it */}
                  <rect x={x - GAP / 2} y={y - 3} width={CELL + GAP} height={CELL + 6} fill="transparent" />
                  {el}
                  {isSel && <rect x={x - 1} y={y - 1} width={CELL + 2} height={CELL + 2} rx={3} fill="none" stroke="var(--ink)" strokeWidth={1.5} />}
                </g>
              );
            }),
          )}
        </svg>
        <div className="num mt-1 flex justify-between text-[10px] text-muted">
          <span>{fmtDay(c.days[0]!, { day: "numeric", month: "short", year: "2-digit" })}</span>
          <span>{fmtDay(c.days[n - 1]!, { day: "numeric", month: "short" })}</span>
        </div>
      </div>
    </div>
  );
}

function Legend() {
  const sw = (el: React.ReactNode, label: string) => (
    <span className="inline-flex items-center gap-1.5">
      <svg width={12} height={12} aria-hidden>
        {el}
      </svg>
      {label}
    </span>
  );
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
      {sw(<rect width={12} height={12} rx={2} fill="var(--accent)" fillOpacity={0.85} />, "Has data (wear: darker = longer worn)")}
      {sw(<rect x={0.5} y={0.5} width={11} height={11} rx={2} fill="none" stroke="var(--warning)" />, "Missing")}
      {sw(<rect width={12} height={12} rx={2} fill="var(--surface-2)" fillOpacity={0.5} />, "Not tracked yet")}
      {sw(<rect x={0.5} y={0.5} width={11} height={11} rx={2} fill="none" stroke="var(--ink-muted)" strokeDasharray="2 2" />, "Today")}
    </div>
  );
}

function ResyncButton({ since, until, streams, label = "Re-sync" }: { since: string; until: string; streams: string[]; label?: string }) {
  const { resync, mutation, running } = useResync();
  const done = mutation.isSuccess && !running;
  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        disabled={running}
        onClick={() => resync({ since, until, streams })}
        className="rounded-lg border border-line px-2.5 py-1 text-xs text-ink-2 transition-colors hover:text-ink disabled:opacity-50"
      >
        {mutation.isPending ? "Starting…" : label}
      </button>
      {mutation.isError && (
        <span className="text-xs text-ink-2">
          <span className="text-serious" aria-hidden>▲ </span>
          {mutation.error instanceof Error ? mutation.error.message : "failed"}
        </span>
      )}
      {done && (
        <span className="text-xs text-ink-2">
          <span className="text-good-ink" aria-hidden>✓ </span>Done
        </span>
      )}
    </span>
  );
}

function DayPanel({ date, signals }: { date: string; signals: SignalCoverage[] }) {
  const q = useDayHealth(date);
  const d = q.data;
  const missing = signals.filter((s) => d?.signals[s.key] === "missing" || d?.signals[s.key] === "low");
  const streams = [...new Set((missing.length ? missing : signals).map((s) => s.stream))];
  const dayStart = new Date(`${date}T00:00:00`).getTime();
  const span = (d?.day_minutes ?? 1440) * 60000;
  return (
    <Card index={3} title={fmtDay(date, { weekday: "long", day: "numeric", month: "long", year: "numeric" })} subtitle="Click another square to change day">
      {q.error ? (
        <ErrorNote error={q.error} />
      ) : !d ? (
        <div className="h-24 animate-pulse rounded-lg bg-surface-2/60" />
      ) : (
        <div className="flex flex-col gap-3 text-sm">
          <div>
            <div className="mb-1 flex justify-between text-xs text-ink-2">
              <span>
                Band worn {d.wear_fraction != null ? `${Math.round(d.wear_fraction * 100)}%` : "–"} ({fmtDuration(d.wear_minutes)} of heart-rate data)
              </span>
              <span className="num text-muted">{d.step_slots} step slots</span>
            </div>
            <div className="relative h-3 overflow-hidden rounded-full bg-accent/70" aria-label="Wear timeline: gaps are breaks of an hour or more">
              {d.wear_gaps.map((g) => (
                <span
                  key={g.start}
                  className="absolute inset-y-0 bg-surface-2"
                  style={{ left: `${((new Date(g.start).getTime() - dayStart) / span) * 100}%`, width: `${(g.minutes * 60000 * 100) / span}%` }}
                />
              ))}
            </div>
            <div className="num mt-0.5 flex justify-between text-[10px] text-muted">
              <span>00</span>
              <span>06</span>
              <span>12</span>
              <span>18</span>
              <span>24</span>
            </div>
            {d.wear_gaps.length > 0 ? (
              <ul className="num mt-1 text-xs text-ink-2">
                {d.wear_gaps.map((g) => (
                  <li key={g.start}>
                    No heart rate {fmtTime(g.start)}–{fmtTime(g.end)} ({fmtDuration(g.minutes)})
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-xs text-muted">No breaks of an hour or more.</p>
            )}
          </div>
          <ul className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
            {signals.map((s) => {
              const st = d.signals[s.key] ?? "untracked";
              return (
                <li key={s.key} className="text-xs">
                  <span className="text-muted">{s.label}</span>
                  <div className="text-ink-2">
                    <span aria-hidden className={st === "missing" ? "text-warning" : st === "ok" ? "text-good-ink" : "text-muted"}>
                      {st === "missing" ? "▲ " : st === "ok" ? "● " : "○ "}
                    </span>
                    {STATE_TEXT[st]}
                  </div>
                </li>
              );
            })}
          </ul>
          <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
            <ResyncButton since={date} until={date} streams={streams} label={missing.length ? "Re-sync missing data for this day" : "Re-sync this day"} />
            <span className="text-xs text-muted">Streams: {streams.join(", ")}</span>
          </div>
        </div>
      )}
    </Card>
  );
}

function GapsCard({ c }: { c: Coverage }) {
  const rows = c.signals.flatMap((s) => s.gaps.map((g) => ({ s, g }))).sort((a, b) => (a.g.end < b.g.end ? 1 : -1));
  return (
    <Card index={4} title="Missing days" subtitle="Newest first. A re-sync fills a gap if Google has the data; if not, the band probably wasn't worn or didn't record.">
      {rows.length === 0 ? (
        <p className="text-sm text-ink-2">
          <span className="text-good-ink" aria-hidden>● </span>No missing days in this range.
        </p>
      ) : (
        <ul className="max-h-[360px] divide-y divide-line overflow-y-auto">
          {rows.slice(0, 80).map(({ s, g }) => (
            <li key={`${s.key}-${g.start}`} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <span className="min-w-0">
                <span className="text-ink">{s.label}</span>
                <span className="num text-ink-2">
                  {" "}
                  · {g.days} day{g.days === 1 ? "" : "s"} · {fmtDay(g.start, { day: "numeric", month: "short" })}
                  {g.days > 1 && `–${fmtDay(g.end, { day: "numeric", month: "short" })}`}
                </span>
              </span>
              <ResyncButton since={g.start} until={g.end} streams={[s.stream]} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function StreamsCard({ f }: { f: DataFreshness }) {
  const today = isoDate(new Date());
  return (
    <Card index={5} title="Sync streams" subtitle="Each run re-fetches the last 3 days. Re-sync a stream to fetch its last 7 days again.">
      <div className="overflow-x-auto">
        <table className="num w-full text-sm">
          <thead>
            <tr className="eyebrow text-left">
              <th className="pb-2 font-medium">Stream</th>
              <th className="pb-2 font-medium">Last success</th>
              <th className="pb-2 font-medium">Status</th>
              <th className="pb-2" />
            </tr>
          </thead>
          <tbody>
            {f.streams.map((s) => (
              <tr key={s.stream} className="border-t border-line align-top">
                <td className="py-2 pr-3 text-ink">{s.stream}</td>
                <td className="py-2 pr-3 text-ink-2">{fmtAgo(s.last_success)}</td>
                <td className="py-2 pr-3 text-xs text-ink-2">
                  {s.last_error ? (
                    <span>
                      <span className="text-serious" aria-hidden>▲ </span>
                      {s.last_error}
                    </span>
                  ) : (
                    <span>
                      <span className="text-good-ink" aria-hidden>● </span>ok
                    </span>
                  )}
                </td>
                <td className="py-2 text-right">
                  <ResyncButton since={addDays(today, -6)} until={today} streams={[s.stream]} label="Re-sync 7 days" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function DataHealthPage() {
  const [range, setRange] = useState<R>("90D");
  const [selected, setSelected] = useState<string | null>(null);
  const to = isoDate(new Date());
  const from = addDays(to, -(DAYS[range] - 1));
  const fresh = useFreshness();
  const cov = useCoverage(from, to);
  const summary = cov.data?.signals.reduce(
    (a, s) => ({ present: a.present + s.present_days, expected: a.expected + s.expected_days }),
    { present: 0, expected: 0 },
  );
  return (
    <div className="flex flex-col gap-4">
      <div className="reveal flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Data health</h1>
        <RangeTabs value={range} options={RANGES} onChange={setRange} />
      </div>
      {fresh.error ? <ErrorNote error={fresh.error} /> : fresh.data ? <FreshnessCard f={fresh.data} /> : <div className="card h-28 animate-pulse" />}
      <Card
        index={2}
        title="Coverage"
        subtitle={
          summary && summary.expected
            ? `${fmtNum((summary.present / summary.expected) * 100, 1)}% of expected days have data · squares before a signal's first day aren't counted`
            : "Which days have data, per signal"
        }
      >
        {cov.error ? (
          <ErrorNote error={cov.error} />
        ) : !cov.data ? (
          <div className="h-40 animate-pulse rounded-lg bg-surface-2/60" />
        ) : (
          <div className="flex flex-col gap-3">
            <CoverageGrid c={cov.data} selected={selected} onSelect={setSelected} />
            <Legend />
          </div>
        )}
      </Card>
      {selected && cov.data && <DayPanel key={selected} date={selected} signals={cov.data.signals} />}
      <div className="grid gap-4 lg:grid-cols-2">
        {cov.data && <GapsCard c={cov.data} />}
        {fresh.data && <StreamsCard f={fresh.data} />}
      </div>
    </div>
  );
}
