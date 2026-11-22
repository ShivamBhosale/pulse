import { useMemo, type ReactNode } from "react";
import { useMetric, useSeries } from "../api/hooks";
import { type Band, type StackPart, stackOption, trendOption } from "../charts/more";
import type { Span } from "../lib/range";
import { usePalette } from "../lib/theme";
import { fmtMetric, useUnits } from "../lib/units";
import { EChart } from "./EChart";
import { Card, Empty, ErrorNote } from "./ui";

interface Props {
  metric: string;
  title: string;
  span: Span;
  kind?: "line" | "bar";
  /** rolling 28-day median/IQR band (day granularity only) */
  baseline?: boolean;
  goal?: number | null;
  goalLabel?: string;
  diverging?: boolean;
  subtitle?: ReactNode;
  index?: number;
  height?: number;
  /** override the granularity (e.g. weekly AZM always by week) */
  granularity?: Span["granularity"];
}

/** A single metric over the page's range, with the period average as the headline. */
export function MetricCard({ metric, title, span, kind = "line", baseline, goal, goalLabel, diverging, subtitle, index = 0, height = 220, granularity }: Props) {
  const g = granularity ?? span.granularity;
  const wantBand = Boolean(baseline) && g === "day";
  const q = useMetric(metric, span.from, span.to, g, wantBand);
  const p = usePalette();
  const units = useUnits();
  const band: Band[] | null = useMemo(
    () => q.data?.band?.map((b) => ({ date: b.date, lo: b.q1, hi: b.q3, mid: b.median })) ?? null,
    [q.data],
  );
  const option = useMemo(
    () => (q.data ? trendOption(q.data, { kind, units, goal, goalLabel, band, bandLabel: "usual range (28-day IQR)", diverging }, p) : null),
    [q.data, kind, units, goal, goalLabel, band, diverging, p],
  );
  const s = q.data;
  const headline = s?.summary.avg != null ? (
    <span className="num">
      {g === "day" ? "avg" : `avg per ${g}`} {fmtMetric(s.summary.avg, s.unit, units, s.metric)}
      {s.summary.count > 1 && (
        <span className="text-muted">
          {" "}
          · range {fmtMetric(s.summary.min, s.unit, units, s.metric, false)}–{fmtMetric(s.summary.max, s.unit, units, s.metric)}
        </span>
      )}
    </span>
  ) : null;
  return (
    <Card index={index} title={title} subtitle={subtitle ?? headline}>
      {q.error ? (
        <ErrorNote error={q.error} />
      ) : !s ? (
        <div className="animate-pulse rounded-lg bg-surface-2/60" style={{ height }} />
      ) : s.summary.count === 0 ? (
        <Empty>No data in this range</Empty>
      ) : (
        option && <EChart option={option} height={height} label={`${title} over the selected range`} />
      )}
    </Card>
  );
}

interface StackProps {
  title: string;
  span: Span;
  parts: { metric: string; label: string; color: string }[];
  goal?: number | null;
  goalLabel?: string;
  subtitle?: ReactNode;
  index?: number;
  height?: number;
  granularity?: Span["granularity"];
}

/** Stacked bars for parts of one whole, fetched in one request. */
export function StackCard({ title, span, parts, goal, goalLabel, subtitle, index = 0, height = 220, granularity }: StackProps) {
  const g = granularity ?? span.granularity;
  const q = useSeries(
    parts.map((x) => x.metric),
    span.from,
    span.to,
    g,
  );
  const p = usePalette();
  const units = useUnits();
  const option = useMemo(() => {
    if (!q.data) return null;
    const stack: StackPart[] = q.data.series.map((s, i) => ({ series: s, label: parts[i]?.label ?? s.label, color: parts[i]?.color ?? p.accent }));
    return stackOption(stack, units, p, goal, goalLabel);
  }, [q.data, parts, p, units, goal, goalLabel]);
  const empty = q.data && q.data.series.every((s) => s.summary.count === 0);
  return (
    <Card index={index} title={title} subtitle={subtitle}>
      {q.error ? (
        <ErrorNote error={q.error} />
      ) : !q.data ? (
        <div className="animate-pulse rounded-lg bg-surface-2/60" style={{ height }} />
      ) : empty ? (
        <Empty>No data in this range</Empty>
      ) : (
        option && <EChart option={option} height={height} label={`${title}, stacked by part`} />
      )}
    </Card>
  );
}
