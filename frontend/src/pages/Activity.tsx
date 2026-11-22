import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { Exercise } from "../api/client";
import { useAvailable, useExercises, useHeatmap, useSettings } from "../api/hooks";
import { heatmapOption } from "../charts/more";
import { EChart } from "../components/EChart";
import { MetricCard, StackCard } from "../components/MetricCard";
import { RangeBar } from "../components/RangeBar";
import { Card, Empty, ErrorNote } from "../components/ui";
import { exerciseName, fmtDay, fmtDuration, fmtNum, fmtTime } from "../lib/format";
import { spanFor, useRange, type Span } from "../lib/range";
import { usePalette } from "../lib/theme";
import { fmtMetric, useUnits } from "../lib/units";


function HeatmapCard({ span, index }: { span: Span; index: number }) {
  const q = useHeatmap(span.from, span.to);
  const p = usePalette();
  const option = useMemo(() => (q.data ? heatmapOption(q.data, p) : null), [q.data, p]);
  const total = q.data?.days.reduce((a, b) => a + b, 0) ?? 0;
  return (
    <Card index={index} title="When you move" subtitle={`Average steps per hour, by weekday · ${total} days`}>
      {q.error ? <ErrorNote error={q.error} /> : !q.data ? <div className="h-[260px] animate-pulse rounded-lg bg-surface-2/60" /> : total === 0 ? <Empty>No intraday steps in this range</Empty> : option && <EChart option={option} height={260} label="Heatmap of average steps by hour of day and weekday" />}
    </Card>
  );
}

function WorkoutRow({ e }: { e: Exercise }) {
  const units = useUnits();
  return (
    <li>
      <Link to={`/activity/workout?id=${encodeURIComponent(e.id)}`} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-0.5 rounded-lg px-2 py-2 transition-colors hover:bg-surface-2 sm:grid-cols-[minmax(0,1.4fr)_repeat(4,minmax(0,1fr))]">
        <div className="min-w-0">
          <div className="truncate text-sm text-ink">{exerciseName(e)}</div>
          <div className="num text-xs text-muted">
            {fmtDay(e.date)} · {fmtTime(e.start)}
          </div>
        </div>
        <div className="num text-right text-sm text-ink sm:text-left">{fmtDuration(e.duration_min)}</div>
        <div className="num hidden text-sm text-ink-2 sm:block">{e.distance_km ? fmtMetric(e.distance_km, "km", units, "distance_km") : "–"}</div>
        <div className="num hidden text-sm text-ink-2 sm:block">{e.avg_hr ? `${fmtNum(e.avg_hr)} bpm` : "–"}</div>
        <div className="num hidden text-sm text-ink-2 sm:block">{e.kcal ? `${fmtNum(e.kcal)} kcal` : "–"}</div>
      </Link>
    </li>
  );
}

function WorkoutsCard({ span, index }: { span: Span; index: number }) {
  const q = useExercises(span.from, span.to);
  const [showWalks, setShowWalks] = useState(false);
  const all = q.data?.exercises ?? [];
  const walks = all.filter((e) => e.exercise_type === "WALKING");
  const shown = showWalks ? all : all.filter((e) => e.exercise_type !== "WALKING");
  const walkMin = walks.reduce((a, e) => a + e.duration_min, 0);
  return (
    <Card
      index={index}
      title="Workouts"
      subtitle={`${all.length - walks.length} workouts · ${walks.length} walks (${fmtDuration(walkMin)})`}
      actions={
        walks.length > 0 && (
          <button type="button" aria-pressed={showWalks} onClick={() => setShowWalks((s) => !s)} className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${showWalks ? "border-accent text-accent-ink" : "border-line text-muted hover:text-ink"}`}>
            {showWalks ? "Hide walks" : "Show walks"}
          </button>
        )
      }
    >
      {q.error ? (
        <ErrorNote error={q.error} />
      ) : !q.data ? (
        <div className="h-40 animate-pulse rounded-lg bg-surface-2/60" />
      ) : shown.length === 0 ? (
        <Empty>{walks.length ? "Only walks in this range. Show them above." : "No workouts in this range"}</Empty>
      ) : (
        <>
          <div className="eyebrow hidden grid-cols-[minmax(0,1.4fr)_repeat(4,minmax(0,1fr))] gap-x-3 px-2 pb-1 sm:grid">
            <span>Workout</span>
            <span>Duration</span>
            <span>Distance</span>
            <span>Avg HR</span>
            <span>Calories</span>
          </div>
          <ul className="max-h-[420px] divide-y divide-line overflow-y-auto">
            {shown.slice(0, 200).map((e) => (
              <WorkoutRow key={e.id} e={e} />
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

export function ActivityPage() {
  const [range, setRange] = useRange("30D");
  const avail = useAvailable();
  const settings = useSettings();
  const goals = settings.data?.goals;
  const span = spanFor(range, avail.info("steps")?.first);
  const p = usePalette();
  const perBucket = (daily: number | undefined) => (daily == null ? null : span.granularity === "day" ? daily : span.granularity === "week" ? daily * 7 : null);
  const azmWeekSpan = spanFor(range === "7D" || range === "30D" ? "90D" : range, avail.info("azm")?.first);
  let i = 0;
  return (
    <div className="flex flex-col gap-4">
      <RangeBar title="Activity" range={range} onChange={setRange} />
      <div className="grid gap-4 lg:grid-cols-2">
        {avail.has("steps") && (
          <MetricCard index={i++} metric="steps" title="Steps" span={span} kind="bar" goal={perBucket(goals?.steps)} goalLabel={span.granularity === "week" ? "Goal × 7" : undefined} />
        )}
        {avail.has("distance_km") && <MetricCard index={i++} metric="distance_km" title="Distance" span={span} kind="bar" />}
        {avail.has("azm") && (
          <MetricCard
            index={i++}
            metric="azm"
            title="Active zone minutes per week"
            subtitle={`Weekly target ${goals?.azm_weekly ?? 150} min · always by week`}
            span={azmWeekSpan}
            granularity="week"
            kind="bar"
            goal={goals?.azm_weekly ?? 150}
            goalLabel={`Target ${goals?.azm_weekly ?? 150}`}
          />
        )}
        {avail.has("azm_fat_burn") && (
          <StackCard
            index={i++}
            title="Active zone minutes by zone"
            subtitle="Cardio and peak minutes count double"
            span={span}
            parts={[
              { metric: "azm_fat_burn", label: "Fat burn", color: p.hrz.moderate },
              { metric: "azm_cardio", label: "Cardio", color: p.hrz.vigorous },
              { metric: "azm_peak", label: "Peak", color: p.hrz.peak },
            ].filter((x) => avail.has(x.metric))}
          />
        )}
        {avail.has("calories_active") && avail.has("calories_bmr") && (
          <StackCard
            index={i++}
            title="Calories burned"
            subtitle="Active vs resting (resting = total − active; the band reports no BMR)"
            span={span}
            parts={[
              { metric: "calories_bmr", label: "Resting (est.)", color: p.cal.rest },
              { metric: "calories_active", label: "Active", color: p.cal.active },
            ]}
          />
        )}
        {avail.has("sedentary_min") && <MetricCard index={i++} metric="sedentary_min" title="Sedentary time" span={span} />}
        {avail.has("sedentary_longest_min") && <MetricCard index={i++} metric="sedentary_longest_min" title="Longest sedentary stretch" span={span} kind="bar" />}
      </div>
      {avail.has("steps") && <HeatmapCard span={span.range === "7D" ? spanFor("30D") : span} index={i++} />}
      <WorkoutsCard span={span} index={i} />
    </div>
  );
}
