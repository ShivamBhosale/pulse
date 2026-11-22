import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useAvailable, useIntradayHr, useSeries } from "../api/hooks";
import { type Band } from "../charts/more";
import { trendOption } from "../charts/more";
import { heartRateOption } from "../charts/options";
import { EChart } from "../components/EChart";
import { MetricCard, StackCard } from "../components/MetricCard";
import { RangeBar } from "../components/RangeBar";
import { Card, Empty, ErrorNote } from "../components/ui";
import { addDays, fmtDay, fmtNum, isoDate } from "../lib/format";
import { spanFor, useRange, type Span } from "../lib/range";
import { usePalette } from "../lib/theme";
import { useUnits } from "../lib/units";

export function DayStepper({ date, onChange, max }: { date: string; onChange: (d: string) => void; max: string }) {
  return (
    <div className="flex items-center gap-1">
      <button type="button" className="rounded-md border border-line px-2 py-1 text-xs text-ink-2 hover:text-ink" onClick={() => onChange(addDays(date, -1))} aria-label="Previous day">
        ←
      </button>
      <input
        type="date"
        value={date}
        max={max}
        onChange={(e) => e.target.value && onChange(e.target.value)}
        className="num rounded-md border border-line bg-surface px-2 py-0.5 text-xs text-ink"
        aria-label="Day"
      />
      <button
        type="button"
        className="rounded-md border border-line px-2 py-1 text-xs text-ink-2 hover:text-ink disabled:opacity-40"
        onClick={() => onChange(addDays(date, 1))}
        disabled={date >= max}
        aria-label="Next day"
      >
        →
      </button>
    </div>
  );
}

function IntradayCard({ index }: { index: number }) {
  const [params, setParams] = useSearchParams();
  const today = isoDate(new Date());
  const day = params.get("day") ?? today;
  const q = useIntradayHr(day);
  const p = usePalette();
  const option = useMemo(() => (q.data && q.data.points.length ? heartRateOption(q.data, p) : null), [q.data, p]);
  const setDay = (d: string) =>
    setParams(
      (prev) => {
        const n = new URLSearchParams(prev);
        n.set("day", d);
        return n;
      },
      { replace: true },
    );
  const pts = q.data?.points ?? [];
  const avg = pts.length ? pts.reduce((a, x) => a + x.avg, 0) / pts.length : null;
  return (
    <Card
      index={index}
      title={`Heart rate · ${fmtDay(day, { weekday: "short", day: "numeric", month: "short" })}`}
      subtitle={avg != null ? <span className="num">avg {fmtNum(avg)} bpm · max {fmtNum(Math.max(...pts.map((x) => x.max)))} bpm</span> : "No heart-rate data this day"}
      actions={<DayStepper date={day} onChange={setDay} max={today} />}
    >
      {q.error ? <ErrorNote error={q.error} /> : option ? <EChart option={option} height={250} label="Heart rate across the chosen day" /> : <Empty>No data</Empty>}
    </Card>
  );
}

function Spo2Card({ span, index }: { span: Span; index: number }) {
  const q = useSeries(["spo2_avg", "spo2_low", "spo2_high"], span.from, span.to, span.granularity);
  const p = usePalette();
  const units = useUnits();
  const option = useMemo(() => {
    const [avg, lo, hi] = q.data?.series ?? [];
    if (!avg || !lo || !hi) return null;
    const hiBy = new Map(hi.points.map((x) => [x.date, x.value]));
    const band: Band[] = lo.points.flatMap((x) => {
      const h = hiBy.get(x.date);
      return x.value != null && h != null ? [{ date: x.date, lo: x.value, hi: h }] : [];
    });
    return trendOption(avg, { kind: "line", units, band, bandLabel: "night low–high" }, p);
  }, [q.data, p, units]);
  const avg = q.data?.series[0];
  return (
    <Card index={index} title="Blood oxygen (SpO₂)" subtitle={avg?.summary.avg != null ? <span className="num">avg {fmtNum(avg.summary.avg, 1)}% · band shows each night's low–high</span> : undefined}>
      {q.error ? <ErrorNote error={q.error} /> : !avg ? <div className="h-[220px] animate-pulse rounded-lg bg-surface-2/60" /> : avg.summary.count === 0 ? <Empty>No data in this range</Empty> : option && <EChart option={option} height={220} label="Average blood oxygen per night with low-high band" />}
    </Card>
  );
}

export function HeartPage() {
  const [range, setRange] = useRange("90D");
  const avail = useAvailable();
  const span = spanFor(range, avail.info("resting_hr")?.first);
  const p = usePalette();
  const zones = [
    { metric: "hr_zone_min_moderate", label: "Fat burn", color: p.hrz.moderate },
    { metric: "hr_zone_min_vigorous", label: "Cardio", color: p.hrz.vigorous },
    { metric: "hr_zone_min_peak", label: "Peak", color: p.hrz.peak },
  ].filter((z) => !avail.ready || avail.has(z.metric));
  let i = 0;
  return (
    <div className="flex flex-col gap-4">
      <RangeBar title="Heart & recovery" range={range} onChange={setRange} />
      <div className="grid gap-4 lg:grid-cols-2">
        {avail.has("resting_hr") && <MetricCard index={i++} metric="resting_hr" title="Resting heart rate" span={span} baseline />}
        {avail.has("hrv_rmssd") && <MetricCard index={i++} metric="hrv_rmssd" title="Heart rate variability (RMSSD)" span={span} baseline />}
      </div>
      <IntradayCard index={i++} />
      <div className="grid gap-4 lg:grid-cols-2">
        {zones.length > 0 && (
          <StackCard
            index={i++}
            title="Time in heart-rate zones"
            subtitle="Minutes above the light zone, from your Fitbit zones. Light (most of the day) is left out."
            span={span}
            parts={zones}
          />
        )}
        {avail.has("spo2_avg") && <Spo2Card span={span} index={i++} />}
        {avail.has("skin_temp_delta") && (
          <MetricCard
            index={i++}
            metric="skin_temp_delta"
            title="Skin temperature variation"
            subtitle="Nightly difference from your personal baseline"
            span={span}
            kind="bar"
            diverging
          />
        )}
        {avail.has("nonrem_hr") && <MetricCard index={i} metric="nonrem_hr" title="Sleeping heart rate (non-REM)" span={span} baseline />}
      </div>
    </div>
  );
}
