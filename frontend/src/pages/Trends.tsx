import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { MetricInfo } from "../api/client";
import { useAvailable, useCorrelate, useJournalRange, useMetric, useTags, useWeekday } from "../api/hooks";
import { TagEffectCard, TagOverviewCard, type Lag } from "../components/TagEffects";
import { calendarOption, scatterOption, weekdayOption } from "../charts/more";
import { EChart } from "../components/EChart";
import { MetricCard } from "../components/MetricCard";
import { RangeBar } from "../components/RangeBar";
import { Card, Empty, ErrorNote } from "../components/ui";
import { fmtNum } from "../lib/format";
import { spanFor, useRange, type Span } from "../lib/range";
import { usePalette } from "../lib/theme";
import { useUnits } from "../lib/units";

const GROUPS: Record<string, string> = { activity: "Activity", heart: "Heart", sleep: "Sleep", derived: "Derived" };
const DIVERGING = new Set(["skin_temp_delta"]);
const BAR_KEYS = /^(steps|distance_km|azm|calories_|hr_zone_|strain)/;

function MetricSelect({ label, value, onChange, metrics }: { label: string; value: string; onChange: (k: string) => void; metrics: MetricInfo[] }) {
  const groups = Object.keys(GROUPS).map((g) => [g, metrics.filter((m) => m.group === g)] as const);
  return (
    <label className="flex min-w-0 items-center gap-2 text-xs text-muted">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} className="min-w-0 max-w-[220px] rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink">
        {groups.map(([g, ms]) =>
          ms.length ? (
            <optgroup key={g} label={GROUPS[g]}>
              {ms.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </optgroup>
          ) : null,
        )}
      </select>
    </label>
  );
}

function CorrelationCard({ a, b, span, index }: { a: MetricInfo; b: MetricInfo; span: Span; index: number }) {
  const q = useCorrelate(a.key, b.key, span.from, span.to);
  const p = usePalette();
  const units = useUnits();
  const option = useMemo(() => (q.data && q.data.n >= 3 ? scatterOption(q.data, a, b, units, p) : null), [q.data, a, b, units, p]);
  const sub =
    a.key === b.key
      ? "Pick two different metrics"
      : q.data
        ? `r = ${q.data.r == null ? "–" : fmtNum(q.data.r, 2)} · ${q.data.strength} · ${q.data.n} days with both`
        : undefined;
  return (
    <Card index={index} title={`${b.label} vs ${a.label}`} subtitle={<span className="num">{sub}</span>}>
      {q.error ? <ErrorNote error={q.error} /> : option ? <EChart option={option} height={260} label={`Scatter of ${b.label} against ${a.label}, one dot per day`} /> : <Empty>{a.key === b.key ? "Same metric on both sides" : "Not enough days with both metrics"}</Empty>}
      <p className="mt-2 text-xs text-muted">Correlation over daily values in the selected range. It shows association, not cause.</p>
    </Card>
  );
}

function WeekdayCard({ m, span, index }: { m: MetricInfo; span: Span; index: number }) {
  const q = useWeekday(m.key, span.from, span.to);
  const p = usePalette();
  const units = useUnits();
  const option = useMemo(() => (q.data ? weekdayOption(q.data, units, p) : null), [q.data, units, p]);
  return (
    <Card index={index} title={`${m.label} by day of week`} subtitle="Average per weekday in the selected range">
      {q.error ? <ErrorNote error={q.error} /> : option ? <EChart option={option} height={220} label={`Average ${m.label} for each weekday`} /> : <div className="h-[220px] animate-pulse rounded-lg bg-surface-2/60" />}
    </Card>
  );
}

function YearCard({ m, index }: { m: MetricInfo; index: number }) {
  const first = Number(m.first.slice(0, 4));
  const last = Number(m.last.slice(0, 4));
  const [year, setYear] = useState(last);
  const y = Math.min(Math.max(year, first), last);
  const q = useMetric(m.key, `${y}-01-01`, `${y}-12-31`, "day");
  const p = usePalette();
  const units = useUnits();
  const compact = typeof window !== "undefined" && window.innerWidth < 760;
  const option = useMemo(() => (q.data ? calendarOption(q.data, y, units, p, DIVERGING.has(m.key), compact) : null), [q.data, y, units, p, m.key, compact]);
  const years = Array.from({ length: last - first + 1 }, (_, i) => last - i);
  return (
    <Card
      index={index}
      title={`Year in pixels · ${m.label}`}
      subtitle={DIVERGING.has(m.key) ? "Blue below, orange above your baseline · outlined squares have no data" : "Stronger colour = higher · outlined squares have no data"}
      actions={
        years.length > 1 && (
          <select value={y} onChange={(e) => setYear(Number(e.target.value))} className="num rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink" aria-label="Year">
            {years.map((yy) => (
              <option key={yy}>{yy}</option>
            ))}
          </select>
        )
      }
    >
      <div className="overflow-x-auto">
        <div style={{ minWidth: compact ? 0 : 780 }}>{option ? <EChart option={option} height={compact ? 120 : 160} label={`Calendar of daily ${m.label} for ${y}`} /> : <div className="h-[160px] animate-pulse rounded-lg bg-surface-2/60" />}</div>
      </div>
    </Card>
  );
}

/** Lazy page + async data means the browser's own #tags jump happens too early. */
function scrollIfLinked(el: HTMLElement | null) {
  if (el && window.location.hash === "#tags") requestAnimationFrame(() => el.scrollIntoView({ block: "start" }));
}

function TagSection({ metrics, span, tag, setTag, index }: { metrics: MetricInfo[]; span: Span; tag: string; setTag: (k: string) => void; index: number }) {
  const [params, setParams] = useSearchParams();
  const tags = useTags();
  const active = (tags.data ?? []).filter((t) => !t.archived);
  const metricKey = params.get("tm") ?? "hrv_rmssd";
  const m = metrics.find((x) => x.key === metricKey) ?? metrics[0];
  const [lag, setLag] = useState<Lag>("auto");
  const t = active.find((x) => x.key === tag) ?? active[0];
  if (!m || !t) return null;
  const setMetric = (k: string) =>
    setParams(
      (prev) => {
        const n = new URLSearchParams(prev);
        n.set("tm", k);
        return n;
      },
      { replace: true },
    );
  return (
    <section id="tags" ref={scrollIfLinked} className="flex scroll-mt-4 flex-col gap-4">
      <div className="reveal flex flex-wrap items-end justify-between gap-3" style={{ ["--i" as string]: index }}>
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Tags</h2>
          <p className="text-xs text-muted">Do days you tagged differ from the rest? Tag days on Today → Journal.</p>
        </div>
      </div>
      <div className="card reveal flex flex-wrap items-center gap-3 p-3" style={{ ["--i" as string]: index }}>
        <label className="flex items-center gap-2 text-xs text-muted">
          Tag
          <select value={t.key} onChange={(e) => setTag(e.target.value)} className="rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink">
            {active.map((x) => (
              <option key={x.key} value={x.key}>
                {x.label} ({x.uses})
              </option>
            ))}
          </select>
        </label>
        <MetricSelect label="Metric" value={m.key} onChange={setMetric} metrics={metrics} />
        <div role="radiogroup" aria-label="Which day to compare" className="inline-flex rounded-lg border border-line p-0.5">
          {(
            [
              ["auto", "Auto"],
              ["0", "Same day"],
              ["1", "Next day"],
            ] as const
          ).map(([v, label]) => (
            <button key={v} type="button" role="radio" aria-checked={lag === v} onClick={() => setLag(v)} className={`rounded-md px-2.5 py-1 text-xs ${lag === v ? "bg-surface-2 text-ink" : "text-muted hover:text-ink"}`}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <TagEffectCard tag={t} metric={m} span={span} lag={lag} index={index + 1} />
        <TagOverviewCard metric={m} span={span} selected={t.key} onSelect={setTag} index={index + 2} />
      </div>
    </section>
  );
}

export function TrendsPage() {
  const [range, setRange] = useRange("90D");
  const [params, setParams] = useSearchParams();
  const avail = useAvailable();
  const metrics = avail.all;
  const tagKey = params.get("tag") ?? "alcohol";
  const setTag = (k: string) =>
    setParams(
      (prev) => {
        const n = new URLSearchParams(prev);
        n.set("tag", k);
        return n;
      },
      { replace: true },
    );
  const [showTag, setShowTag] = useState(false);
  const a = params.get("a") ?? "hrv_rmssd";
  const b = params.get("b") ?? "sleep_main_min";
  const ma = avail.info(a) ?? metrics[0];
  const mb = avail.info(b) ?? metrics[1] ?? metrics[0];
  const set = (k: "a" | "b", v: string) =>
    setParams(
      (prev) => {
        const n = new URLSearchParams(prev);
        n.set(k, v);
        return n;
      },
      { replace: true },
    );
  const tags = useTags();
  const labels = useMemo(() => new Map((tags.data ?? []).map((t) => [t.key, t.label])), [tags.data]);
  const tagLabel = labels.get(tagKey) ?? tagKey;
  const spanForJournal = ma && mb ? spanFor(range, ma.first > mb.first ? ma.first : mb.first) : null;
  const journalQ = useJournalRange(spanForJournal?.from ?? "", spanForJournal?.to ?? "", Boolean(spanForJournal));
  const { markers, annotations } = useMemo(() => {
    const ann: Record<string, string> = {};
    const mk: string[] = [];
    for (const d of journalQ.data?.days ?? []) {
      const parts = d.tags.map((k) => labels.get(k) ?? k).join(", ");
      const note = d.note.split("\n")[0]?.slice(0, 80) ?? "";
      ann[d.date] = [parts && `Tags: ${parts}`, note && `“${note}”`].filter(Boolean).join(" · ");
      if (showTag && d.tags.includes(tagKey)) mk.push(d.date);
    }
    return { markers: mk, annotations: ann };
  }, [journalQ.data, labels, showTag, tagKey]);
  if (!avail.ready) return <div className="card h-64 animate-pulse" />;
  if (!ma || !mb) return <Empty>No data yet</Empty>;
  const firstOfBoth = ma.first > mb.first ? ma.first : mb.first;
  const span = spanFor(range, firstOfBoth);
  const tagSpan = spanFor(range === "7D" || range === "30D" ? "1Y" : range, firstOfBoth);
  return (
    <div className="flex flex-col gap-4">
      <RangeBar title="Trends & explore" range={range} onChange={setRange} />
      <div className="card reveal flex flex-wrap items-center gap-3 p-3">
        <MetricSelect label="Metric A" value={ma.key} onChange={(v) => set("a", v)} metrics={metrics} />
        <MetricSelect label="Metric B" value={mb.key} onChange={(v) => set("b", v)} metrics={metrics} />
        <label className="flex items-center gap-2 text-xs text-muted">
          <input type="checkbox" checked={showTag} onChange={(e) => setShowTag(e.target.checked)} className="accent-[var(--accent)]" />
          Mark “{tagLabel}” days
        </label>
        <span className="text-xs text-muted">Shared time axis · separate scales, never a dual axis</span>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <MetricCard index={1} metric={ma.key} title={ma.label} span={span} markers={markers} markerLabel={tagLabel} annotations={annotations} kind={BAR_KEYS.test(ma.key) || DIVERGING.has(ma.key) ? "bar" : "line"} diverging={DIVERGING.has(ma.key)} height={180} />
        <MetricCard index={2} metric={mb.key} title={mb.label} span={span} markers={markers} markerLabel={tagLabel} annotations={annotations} kind={BAR_KEYS.test(mb.key) || DIVERGING.has(mb.key) ? "bar" : "line"} diverging={DIVERGING.has(mb.key)} height={180} />
        <CorrelationCard a={ma} b={mb} span={spanFor(range === "7D" ? "30D" : range, firstOfBoth)} index={3} />
        <WeekdayCard m={ma} span={span} index={4} />
      </div>
      <YearCard key={ma.key} m={ma} index={5} />
      <TagSection metrics={metrics} span={tagSpan} tag={tagKey} setTag={setTag} index={6} />
    </div>
  );
}
