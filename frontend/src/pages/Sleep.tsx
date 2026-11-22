import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useSleep, useSleepTrend } from "../api/hooks";
import type { SleepSession } from "../api/client";
import {
  STAGE_LABEL,
  STAGES,
  consistencyOption,
  durationOption,
  hypnogramOption,
  stagesStackOption,
  type Stage,
} from "../charts/options";
import { EChart } from "../components/EChart";
import { Card, Empty, ErrorNote, RangeTabs, Stat } from "../components/ui";
import { addDays, fmtClock, fmtDay, fmtDuration, fmtNum, fmtTime, isoDate } from "../lib/format";
import { usePalette } from "../lib/theme";

const RANGES = ["14D", "30D", "90D"] as const;
type Range = (typeof RANGES)[number];
const RANGE_DAYS: Record<Range, number> = { "14D": 14, "30D": 30, "90D": 90 };

function StageTable({ s }: { s: SleepSession }) {
  const mins: Record<Stage, number | null | undefined> = {
    DEEP: s.deep_min,
    LIGHT: s.light_min,
    REM: s.rem_min,
    AWAKE: s.awake_min,
  };
  const total = STAGES.reduce((acc, k) => acc + (mins[k] ?? 0), 0);
  if (!total) return null;
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">Minutes and share per sleep stage</caption>
      <thead>
        <tr className="eyebrow text-left">
          <th className="pb-2 font-medium">Stage</th>
          <th className="pb-2 text-right font-medium">Time</th>
          <th className="pb-2 text-right font-medium">Share</th>
          <th className="w-2/5 pb-2" aria-hidden />
        </tr>
      </thead>
      <tbody>
        {[...STAGES].reverse().map((k) => {
          const m = mins[k] ?? 0;
          const pct = (m / total) * 100;
          return (
            <tr key={k} className="border-t border-line">
              <td className="py-2">
                <span className="mr-2 inline-block h-2.5 w-2.5 rounded-sm align-middle" style={{ background: `var(--stage-${k.toLowerCase()})` }} />
                {STAGE_LABEL[k]}
              </td>
              <td className="num py-2 text-right">{fmtDuration(m)}</td>
              <td className="num py-2 text-right text-ink-2">{fmtNum(pct)}%</td>
              <td className="py-2 pl-3">
                <div className="h-1.5 rounded-full bg-surface-2">
                  <div className="h-full rounded-full" style={{ width: `${pct}%`, background: `var(--stage-${k.toLowerCase()})` }} />
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function SleepPage() {
  const [params, setParams] = useSearchParams();
  const date = params.get("date") ?? undefined;
  const night = useSleep(date);
  const [range, setRange] = useState<Range>("30D");
  const to = isoDate(new Date());
  const from = addDays(to, -(RANGE_DAYS[range] - 1));
  const trend = useSleepTrend(from, to);
  const p = usePalette();

  const n = night.data;
  const s = n?.session;
  const hypno = useMemo(() => (s && s.stages.length ? hypnogramOption(s, p) : null), [s, p]);
  const nights = useMemo(() => trend.data?.nights ?? [], [trend.data]);
  const goal = trend.data?.goal_min ?? n?.goal_min ?? 480;
  const dur = useMemo(() => (nights.length ? durationOption(nights, goal, p) : null), [nights, goal, p]);
  const stack = useMemo(() => (nights.length ? stagesStackOption(nights, p) : null), [nights, p]);
  const timing = useMemo(() => (nights.length ? consistencyOption(nights, p) : null), [nights, p]);

  const go = (d: string | null | undefined) => d && setParams({ date: d });

  if (night.error) return <ErrorNote error={night.error} />;

  return (
    <div className="flex flex-col gap-4">
      <div className="reveal flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Sleep</h1>
        <div className="flex items-center gap-1">
          <button type="button" className="rounded-lg border border-line px-2.5 py-1.5 text-sm text-ink-2 disabled:opacity-40" disabled={!n?.prev_date} onClick={() => go(n?.prev_date)} aria-label="Previous night">
            ←
          </button>
          <input
            type="date"
            className="num rounded-lg border border-line bg-surface px-2 py-1 text-sm text-ink"
            value={n?.date ?? ""}
            max={to}
            onChange={(e) => go(e.target.value)}
            aria-label="Night (wake-up date)"
          />
          <button type="button" className="rounded-lg border border-line px-2.5 py-1.5 text-sm text-ink-2 disabled:opacity-40" disabled={!n?.next_date} onClick={() => go(n?.next_date)} aria-label="Next night">
            →
          </button>
        </div>
      </div>

      {night.isPending ? (
        <div className="card h-64 animate-pulse" />
      ) : !s ? (
        <div className="card p-4">
          <Empty>No sleep recorded for the night ending {n ? fmtDay(n.date) : ""}.</Empty>
        </div>
      ) : (
        <>
          <section className="card reveal grid grid-cols-2 gap-4 p-4 sm:grid-cols-4" style={{ ["--i" as string]: 1 }}>
            <Stat label="Asleep" value={fmtDuration(s.minutes_asleep)} hint={`goal ${fmtDuration(n.goal_min)}`} />
            <Stat label="In bed" value={fmtDuration(s.minutes_in_bed)} hint={`${fmtTime(s.start)} → ${fmtTime(s.end)}`} />
            <Stat label="Efficiency" value={fmtNum(s.efficiency, 0)} unit="%" hint={`${fmtDuration(s.minutes_to_fall_asleep)} to fall asleep`} />
            <Stat label="Sleeping HR" value={n.sleeping_hr ? fmtNum(n.sleeping_hr.avg) : "–"} unit="bpm" hint={n.sleeping_hr ? `lowest ${n.sleeping_hr.min}` : undefined} />
            <Stat label="HRV" value={fmtNum(n.hrv_rmssd, 1)} unit="ms" />
            <Stat label="Resting HR" value={fmtNum(n.resting_hr)} unit="bpm" />
            <Stat label="SpO₂" value={n.spo2 ? fmtNum(n.spo2.avg, 1) : "–"} unit="%" hint={n.spo2 ? `${fmtNum(n.spo2.low, 0)}–${fmtNum(n.spo2.high, 0)}%` : undefined} />
            <Stat
              label="Skin temp"
              value={n.skin_temp_delta != null ? `${n.skin_temp_delta >= 0 ? "+" : "−"}${fmtNum(Math.abs(n.skin_temp_delta), 1)}` : "–"}
              unit="°C"
              hint="vs. your baseline"
            />
          </section>
          <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
            <Card index={2} title="Stages" subtitle={`${fmtDay(n.date, { weekday: "long", day: "numeric", month: "short" })}${n.naps.length ? ` · +${n.naps.length} nap` : ""}`}>
              {hypno ? <EChart option={hypno} height={200} label="Hypnogram of sleep stages through the night" /> : <Empty>No stage data for this night</Empty>}
            </Card>
            <Card index={3} title="Time per stage">
              <StageTable s={s} />
            </Card>
          </div>
        </>
      )}

      <div className="reveal mt-2 flex items-center justify-between" style={{ ["--i" as string]: 4 }}>
        <h2 className="text-lg font-semibold tracking-tight">Trends</h2>
        <RangeTabs value={range} options={RANGES} onChange={setRange} />
      </div>
      {trend.error ? (
        <ErrorNote error={trend.error} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card index={5} title="Time asleep vs goal (incl. naps)" subtitle={trend.data?.avg_asleep_min != null ? <span className="num">avg {fmtDuration(trend.data.avg_asleep_min)}</span> : undefined}>
            {dur ? <EChart option={dur} height={220} label="Time asleep per night compared with goal" /> : <Empty>No nights in range</Empty>}
          </Card>
          <Card index={6} title="Stages per night">
            {stack ? <EChart option={stack} height={220} label="Stacked sleep stages per night" /> : <Empty>No nights in range</Empty>}
          </Card>
          <Card
            index={7}
            title="Bedtime and wake consistency"
            subtitle={
              trend.data ? (
                <span className="num">
                  last {trend.data.consistency.nights} nights: bedtime ±{fmtNum(trend.data.consistency.bedtime_sd_min)} min, wake ±
                  {fmtNum(trend.data.consistency.waketime_sd_min)} min (SD)
                </span>
              ) : undefined
            }
          >
            {timing ? <EChart option={timing} height={240} label="Bedtime to wake-up span per night" /> : <Empty>No nights in range</Empty>}
            {nights.length > 0 && (
              <div className="num mt-2 text-xs text-muted">
                typical {fmtClock(median(nights.map((x) => x.bedtime_min)))} → {fmtClock(median(nights.map((x) => x.waketime_min)))}
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}

function median(xs: (number | null | undefined)[]): number | null {
  const v = xs.filter((x): x is number => x != null).sort((a, b) => a - b);
  if (!v.length) return null;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m]! : (v[m - 1]! + v[m]!) / 2;
}
