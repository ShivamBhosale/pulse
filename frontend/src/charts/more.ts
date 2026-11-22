// Phase 2 chart builders: trends with bands, stacks, heatmaps, calendar, scatter, workouts.
// Same conventions as options.ts: thin marks, one y-axis, recessive grid, legend only for ≥2
// series, values in ink tokens, a tooltip on every chart.
import type { EChartsCoreOption } from "echarts/core";
import type { Correlation, ExerciseDetail, Heatmap, MetricSeries, TagEffect, WeekdayProfile } from "../api/client";
import { fmtDay, fmtNum, fmtTime } from "../lib/format";
import type { Granularity } from "../lib/range";
import type { Palette } from "../lib/theme";
import { type Units, durationInterval, fmtAxis, fmtMetric } from "../lib/units";
import { MONO, ZONE_LABEL, axisCommon, base, row } from "./options";

export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function bucketLabel(iso: string, g: Granularity): string {
  if (g === "month") return fmtDay(iso, { month: "short", year: "2-digit" });
  return fmtDay(iso, { day: "numeric", month: "short" });
}

function tipHeader(iso: string, g: Granularity, p: Palette): string {
  const t =
    g === "month"
      ? fmtDay(iso, { month: "long", year: "numeric" })
      : g === "week"
        ? `Week of ${fmtDay(iso, { day: "numeric", month: "short", year: "numeric" })}`
        : fmtDay(iso, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  return `<div style="color:${p.muted};margin-bottom:4px">${t}</div>`;
}

export interface Band {
  date: string;
  lo: number;
  hi: number;
  mid?: number;
}

export interface TrendOpts {
  kind: "line" | "bar";
  units: Units;
  goal?: number | null;
  goalLabel?: string;
  band?: Band[] | null;
  bandLabel?: string;
  /** colour bars by sign around 0 with the diverging pair */
  diverging?: boolean;
  color?: string;
  /** dates to mark with a thin vertical line (e.g. days with a chosen tag) */
  markers?: string[];
  markerLabel?: string;
  /** extra tooltip line per date (tags · note) */
  annotations?: Record<string, string>;
}

/** One metric over time; optional baseline/range band, goal line or diverging bars. */
export function trendOption(s: MetricSeries, o: TrendOpts, p: Palette): EChartsCoreOption {
  const g = s.granularity as Granularity;
  const dates = s.points.map((pt) => pt.date);
  const bandBy = new Map((o.band ?? []).map((b) => [b.date, b]));
  const color = o.color ?? p.accent;
  const fmt = (v: number | null | undefined) => fmtMetric(v, s.unit, o.units, s.metric);
  const values = s.points.map((pt) => pt.value);
  const series: object[] = [];
  if (o.band?.length) {
    series.push(
      {
        name: "band-lo",
        type: "line",
        data: dates.map((d) => bandBy.get(d)?.lo ?? null),
        stack: "band",
        symbol: "none",
        lineStyle: { opacity: 0 },
        silent: true,
        tooltip: { show: false },
      },
      {
        name: o.bandLabel ?? "Usual range",
        type: "line",
        data: dates.map((d) => {
          const b = bandBy.get(d);
          return b ? b.hi - b.lo : null;
        }),
        stack: "band",
        symbol: "none",
        lineStyle: { opacity: 0 },
        areaStyle: { color: p.accentSoft, opacity: 1 },
        silent: true,
      },
    );
  }
  const markerLines = g === "day" ? (o.markers ?? []).filter((d) => dates.includes(d)).map((d) => ({ xAxis: d })) : [];
  const markerStyle = {
    silent: true,
    symbol: "none",
    lineStyle: { color: p.accent, type: "dotted" as const, width: 1, opacity: 0.8 },
    label: { show: false },
  };
  series.push({
    name: s.label,
    type: o.kind,
    data: values.map((v) =>
      o.diverging && v != null
        ? { value: v, itemStyle: { color: v >= 0 ? p.div.warm : p.div.cool, borderRadius: v >= 0 ? [3, 3, 0, 0] : [0, 0, 3, 3] } }
        : v,
    ),
    showSymbol: o.kind === "line" && dates.length <= 31,
    symbolSize: 5,
    connectNulls: false,
    barMaxWidth: 14,
    lineStyle: { color, width: 2 },
    itemStyle: { color, borderRadius: o.kind === "bar" ? [3, 3, 0, 0] : undefined },
    markLine:
      o.goal != null
        ? {
            silent: true,
            symbol: "none",
            lineStyle: { color: p.ink2, type: "dashed", width: 1 },
            label: { formatter: o.goalLabel ?? `Goal ${fmt(o.goal)}`, color: p.muted, fontSize: 10, position: "insideEndTop" },
            data: [{ yAxis: o.goal }],
          }
        : o.diverging
          ? { silent: true, symbol: "none", lineStyle: { color: p.axis, width: 1 }, label: { show: false }, data: [{ yAxis: 0 }] }
          : markerLines.length
            ? { ...markerStyle, data: markerLines }
            : undefined,
  });
  const durMax = Math.max(0, ...values.map((v) => v ?? 0), ...(o.band ?? []).map((b) => b.hi));
  const durInt = durationInterval(s.metric, durMax);
  const zeroBased = o.kind === "bar" || s.unit === "min" || s.unit === "count" || s.unit === "kcal" || s.unit === "km";
  return {
    ...base(p),
    grid: { left: 46, right: 14, top: 16, bottom: 26 },
    xAxis: {
      type: "category",
      data: dates,
      ...axisCommon(p),
      splitLine: { show: false },
      axisLabel: { ...axisCommon(p).axisLabel, formatter: (v: string) => bucketLabel(v, g), hideOverlap: true },
    },
    yAxis: {
      type: "value",
      scale: !zeroBased,
      min: zeroBased && !o.diverging ? 0 : undefined,
      interval: durInt,
      max: durInt ? Math.ceil(durMax / durInt) * durInt : undefined,
      ...axisCommon(p),
      axisLine: { show: false },
      splitNumber: 4,
      axisLabel: { ...axisCommon(p).axisLabel, formatter: (v: number) => fmtAxis(v, s.unit, o.units, s.metric) },
    },
    tooltip: {
      ...(base(p).tooltip as object),
      trigger: "axis",
      axisPointer: o.kind === "bar" ? { type: "shadow", shadowStyle: { color: p.accentSoft } } : { type: "line", lineStyle: { color: p.axis } },
      formatter: (params: { dataIndex: number }[]) => {
        const i = params[0]?.dataIndex ?? 0;
        const d = dates[i];
        if (!d) return "";
        const b = bandBy.get(d);
        return (
          tipHeader(d, g, p) +
          row(color, s.label, fmt(values[i])) +
          (b ? `<div style="color:${p.muted};font-size:11px;margin-top:2px">${o.bandLabel ?? "usual"} ${fmt(b.lo)} – ${fmt(b.hi)}</div>` : "") +
          (o.annotations?.[d] ? `<div style="color:${p.ink2};font-size:11px;margin-top:4px;max-width:240px;white-space:normal">${escapeHtml(o.annotations[d])}</div>` : "")
        );
      },
    },
    series,
  };
}

export interface StackPart {
  series: MetricSeries;
  label: string;
  color: string;
}

/** Stacked bars of parts of a whole (time in zones, calories, AZM by zone). */
export function stackOption(parts: StackPart[], units: Units, p: Palette, goal?: number | null, goalLabel?: string): EChartsCoreOption {
  const first = parts[0]?.series;
  if (!first) return {};
  const g = first.granularity as Granularity;
  const dates = [...new Set(parts.flatMap((x) => x.series.points.map((pt) => pt.date)))].sort();
  const lookup = parts.map((x) => new Map(x.series.points.map((pt) => [pt.date, pt.value])));
  const fmt = (v: number | null | undefined) => fmtMetric(v, first.unit, units, first.metric);
  return {
    ...base(p),
    grid: { left: 46, right: 14, top: 30, bottom: 26 },
    legend: {
      top: 0,
      left: 0,
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: p.ink2, fontSize: 11 },
      data: parts.map((x) => x.label),
    },
    xAxis: {
      type: "category",
      data: dates,
      ...axisCommon(p),
      splitLine: { show: false },
      axisLabel: { ...axisCommon(p).axisLabel, formatter: (v: string) => bucketLabel(v, g), hideOverlap: true },
    },
    yAxis: {
      type: "value",
      min: 0,
      ...axisCommon(p),
      axisLine: { show: false },
      splitNumber: 4,
      axisLabel: { ...axisCommon(p).axisLabel, formatter: (v: number) => fmtAxis(v, first.unit, units, first.metric) },
    },
    tooltip: {
      ...(base(p).tooltip as object),
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: p.accentSoft } },
      formatter: (x: { seriesName: string; value: number | null; color: string; dataIndex: number }[]) => {
        const d = dates[x[0]?.dataIndex ?? 0] ?? "";
        const total = x.reduce((a, s) => a + (s.value ?? 0), 0);
        return (
          tipHeader(d, g, p) +
          [...x].reverse().map((s) => row(s.color, s.seriesName, fmt(s.value))).join("") +
          `<div style="border-top:1px solid ${p.line};margin-top:4px;padding-top:4px">${row("transparent", "Total", fmt(total))}</div>`
        );
      },
    },
    series: parts.map((x, i) => ({
      name: x.label,
      type: "bar",
      stack: "parts",
      barMaxWidth: 14,
      data: dates.map((d) => lookup[i]?.get(d) ?? null),
      // surface gap between stacked segments (dataviz spacer rule)
      itemStyle: { color: x.color, borderColor: p.surface, borderWidth: 1 },
      markLine:
        i === parts.length - 1 && goal != null
          ? {
              silent: true,
              symbol: "none",
              lineStyle: { color: p.ink2, type: "dashed", width: 1 },
              label: { formatter: goalLabel ?? `Goal ${fmt(goal)}`, color: p.muted, fontSize: 10, position: "insideEndTop" },
              data: [{ yAxis: goal }],
            }
          : undefined,
    })),
  };
}

/** Steps by hour of day × weekday: one-hue sequential ramp. */
export function heatmapOption(h: Heatmap, p: Palette): EChartsCoreOption {
  const data: [number, number, number | null][] = [];
  h.values.forEach((rowVals, w) => rowVals.forEach((v, hour) => data.push([hour, w, v])));
  const max = Math.max(1, ...data.map((d) => d[2] ?? 0));
  return {
    ...base(p),
    grid: { left: 40, right: 14, top: 8, bottom: 52 },
    xAxis: {
      type: "category",
      data: Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0")),
      ...axisCommon(p),
      axisLine: { show: false },
      splitLine: { show: false },
      axisLabel: { ...axisCommon(p).axisLabel, interval: 2 },
    },
    yAxis: {
      type: "category",
      data: WEEKDAYS,
      inverse: true,
      ...axisCommon(p),
      axisLine: { show: false },
      splitLine: { show: false },
      axisLabel: { color: p.ink2, fontSize: 11 },
    },
    visualMap: {
      min: 0,
      max,
      calculable: false,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      itemHeight: 140,
      itemWidth: 10,
      text: [`${fmtNum(max)} steps/h`, "0"],
      textStyle: { color: p.muted, fontSize: 10, fontFamily: MONO },
      inRange: { color: p.seq },
    },
    tooltip: {
      ...(base(p).tooltip as object),
      trigger: "item",
      formatter: (x: { data: [number, number, number | null] }) => {
        const [hour, w, v] = x.data;
        return (
          `<div style="color:${p.muted};margin-bottom:4px">${WEEKDAYS[w]} ${String(hour).padStart(2, "0")}:00–${String(hour + 1).padStart(2, "0")}:00</div>` +
          row(p.accent, "Average steps", fmtNum(v)) +
          `<div style="color:${p.muted};font-size:11px;margin-top:2px">over ${h.days[w] ?? 0} ${WEEKDAYS[w]}s</div>`
        );
      },
    },
    series: [
      {
        type: "heatmap",
        data,
        itemStyle: { borderColor: p.surface, borderWidth: 2, borderRadius: 3 },
        emphasis: { itemStyle: { borderColor: p.ink, borderWidth: 1 } },
      },
    ],
  };
}

/** Year in pixels: one square per day; sequential, or diverging around 0. */
export function calendarOption(s: MetricSeries, year: number, units: Units, p: Palette, diverging: boolean, compact: boolean): EChartsCoreOption {
  const data = s.points.filter((pt) => pt.value != null).map((pt) => [pt.date, pt.value as number]);
  const vals = data.map((d) => d[1] as number);
  const absMax = Math.max(0.01, ...vals.map(Math.abs));
  const fmt = (v: number) => fmtMetric(v, s.unit, units, s.metric);
  const cell = compact ? 9 : 14;
  return {
    ...base(p),
    visualMap: {
      min: diverging ? -absMax : Math.min(...vals),
      max: diverging ? absMax : Math.max(...vals),
      orient: "horizontal",
      left: 0,
      bottom: 0,
      itemHeight: 120,
      itemWidth: 10,
      calculable: false,
      text: diverging ? [fmt(absMax), fmt(-absMax)] : [fmt(Math.max(...vals)), fmt(Math.min(...vals))],
      textStyle: { color: p.muted, fontSize: 10, fontFamily: MONO },
      inRange: { color: diverging ? [p.div.cool, p.div.mid, p.div.warm] : p.seq.slice(1) },
    },
    calendar: {
      range: String(year),
      top: 22,
      left: 30,
      right: 6,
      cellSize: [compact ? "auto" : cell, cell],
      orient: "horizontal",
      splitLine: { show: false },
      // empty days are outlines, so "no data" never looks like a value
      itemStyle: { color: p.surface, borderColor: p.line, borderWidth: 1 },
      yearLabel: { show: false },
      dayLabel: { firstDay: 1, nameMap: ["S", "M", "T", "W", "T", "F", "S"], color: p.muted, fontSize: 9 },
      monthLabel: { color: p.muted, fontSize: 10 },
    },
    tooltip: {
      ...(base(p).tooltip as object),
      trigger: "item",
      formatter: (x: { data: [string, number] }) =>
        `<div style="color:${p.muted};margin-bottom:4px">${fmtDay(x.data[0], { weekday: "short", day: "numeric", month: "short", year: "numeric" })}</div>` +
        row(p.accent, s.label, fmt(x.data[1])),
    },
    series: [{ type: "heatmap", coordinateSystem: "calendar", data, itemStyle: { borderColor: p.surface, borderWidth: 1.5 } }],
  };
}

/** Scatter of two metrics (one dot per day) with a least-squares line. */
export function scatterOption(c: Correlation, a: { label: string; unit: string }, b: { label: string; unit: string }, units: Units, p: Palette): EChartsCoreOption {
  const pts = c.points.map((pt) => [pt.x, pt.y, pt.date]);
  const n = pts.length;
  const mx = c.points.reduce((s, pt) => s + pt.x, 0) / (n || 1);
  const my = c.points.reduce((s, pt) => s + pt.y, 0) / (n || 1);
  const sxx = c.points.reduce((s, pt) => s + (pt.x - mx) ** 2, 0);
  const slope = sxx ? c.points.reduce((s, pt) => s + (pt.x - mx) * (pt.y - my), 0) / sxx : 0;
  const xs = c.points.map((pt) => pt.x);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  return {
    ...base(p),
    grid: { left: 50, right: 16, top: 14, bottom: 40 },
    xAxis: {
      type: "value",
      scale: true,
      interval: durationInterval(c.a, Math.max(0, ...xs)),
      name: a.label,
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { color: p.ink2, fontSize: 11 },
      ...axisCommon(p),
      axisLabel: { ...axisCommon(p).axisLabel, formatter: (v: number) => fmtAxis(v, a.unit, units, c.a) },
    },
    yAxis: {
      type: "value",
      scale: true,
      interval: durationInterval(c.b, Math.max(0, ...c.points.map((pt) => pt.y))),
      ...axisCommon(p),
      axisLine: { show: false },
      axisLabel: { ...axisCommon(p).axisLabel, formatter: (v: number) => fmtAxis(v, b.unit, units, c.b) },
    },
    tooltip: {
      ...(base(p).tooltip as object),
      trigger: "item",
      formatter: (x: { data: [number, number, string] }) =>
        `<div style="color:${p.muted};margin-bottom:4px">${fmtDay(x.data[2])}</div>` +
        row(p.accent, a.label, fmtMetric(x.data[0], a.unit, units, c.a)) +
        row(p.accent, b.label, fmtMetric(x.data[1], b.unit, units, c.b)),
    },
    series: [
      {
        type: "scatter",
        data: pts,
        symbolSize: 8,
        itemStyle: { color: p.accent, opacity: 0.75, borderColor: p.surface, borderWidth: 1 },
      },
      ...(n >= 3 && Number.isFinite(x0)
        ? [
            {
              type: "line",
              silent: true,
              symbol: "none",
              tooltip: { show: false },
              data: [
                [x0, my + slope * (x0 - mx)],
                [x1, my + slope * (x1 - mx)],
              ],
              lineStyle: { color: p.ink2, type: "dashed", width: 1 },
            },
          ]
        : []),
    ],
  };
}

export function weekdayOption(w: WeekdayProfile, units: Units, p: Palette): EChartsCoreOption {
  const fmt = (v: number | null | undefined) => fmtMetric(v, w.unit, units, w.metric);
  const vals = w.days.map((d) => d.avg);
  const zeroBased = ["min", "count", "kcal", "km"].includes(w.unit);
  return {
    ...base(p),
    grid: { left: 46, right: 14, top: 14, bottom: 26 },
    xAxis: { type: "category", data: WEEKDAYS, ...axisCommon(p), splitLine: { show: false } },
    yAxis: {
      type: "value",
      scale: !zeroBased,
      min: zeroBased ? 0 : undefined,
      ...axisCommon(p),
      axisLine: { show: false },
      splitNumber: 4,
      axisLabel: { ...axisCommon(p).axisLabel, formatter: (v: number) => fmtAxis(v, w.unit, units, w.metric) },
    },
    tooltip: {
      ...(base(p).tooltip as object),
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: p.accentSoft } },
      formatter: (x: { dataIndex: number }[]) => {
        const d = w.days[x[0]?.dataIndex ?? 0];
        return d
          ? `<div style="color:${p.muted};margin-bottom:4px">${WEEKDAYS[d.weekday]} · ${d.n} days</div>` + row(p.accent, `Average ${w.label.toLowerCase()}`, fmt(d.avg))
          : "";
      },
    },
    series: [{ type: "bar", data: vals, barMaxWidth: 28, itemStyle: { color: p.accent, borderRadius: [4, 4, 0, 0] } }],
  };
}

/** Heart rate through one workout with the day's zone bands. */
export function workoutHrOption(d: ExerciseDetail, p: Palette): EChartsCoreOption {
  const data = d.points.map((pt) => [new Date(pt.t).getTime(), pt.avg]);
  const bpms = d.points.map((pt) => pt.avg);
  const yMin = Math.max(40, Math.floor((Math.min(...bpms, 90) - 10) / 10) * 10);
  const yMax = Math.ceil((Math.max(...bpms, 120) + 10) / 10) * 10;
  const zoneAreas = d.zones
    .filter((z) => z.max_bpm > yMin && z.min_bpm < yMax)
    .map((z) => [
      {
        yAxis: Math.max(z.min_bpm, yMin),
        itemStyle: { color: p.hrz[z.zone as keyof Palette["hrz"]] ?? p.accentSoft, opacity: 0.16 },
        label: { show: true, position: "insideRight", formatter: ZONE_LABEL[z.zone] ?? z.zone, color: p.muted, fontSize: 10 },
      },
      { yAxis: Math.min(z.max_bpm, yMax) },
    ]);
  return {
    ...base(p),
    grid: { left: 36, right: 12, top: 12, bottom: 26 },
    xAxis: {
      type: "time",
      min: new Date(d.exercise.start).getTime(),
      max: new Date(d.exercise.end).getTime(),
      ...axisCommon(p),
      splitLine: { show: false },
      axisLabel: {
        ...axisCommon(p).axisLabel,
        formatter: (v: number) => new Date(v).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false }),
        hideOverlap: true,
      },
    },
    yAxis: { type: "value", min: yMin, max: yMax, ...axisCommon(p), axisLine: { show: false }, splitNumber: 4 },
    tooltip: {
      ...(base(p).tooltip as object),
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: p.axis } },
      formatter: (x: { data: [number, number] }[]) => {
        const pt = x[0]?.data;
        return pt ? `<div style="color:${p.muted};margin-bottom:4px">${fmtTime(new Date(pt[0]).toISOString())}</div>` + row(p.accent, "Heart rate", `${fmtNum(pt[1])} bpm`) : "";
      },
    },
    series: [
      {
        type: "line",
        data,
        showSymbol: false,
        lineStyle: { color: p.accent, width: 2 },
        itemStyle: { color: p.accent },
        markArea: { silent: true, data: zoneAreas },
      },
    ],
  };
}


function escapeHtml(t: string): string {
  return t.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c);
}

/** Tagged vs untagged days as two rows of dots, with each group's median as a bar. */
export function stripOption(e: TagEffect, units: Units, p: Palette): EChartsCoreOption {
  const fmt = (v: number | null | undefined) => fmtMetric(v, e.unit, units, e.metric);
  // Deterministic jitter from the date so dots don't stack.
  const jitter = (iso: string) => {
    let h = 0;
    for (const c of iso) h = (h * 31 + c.charCodeAt(0)) % 997;
    return (h / 997 - 0.5) * 0.5;
  };
  const rows = ["Without tag", `With ${e.tag_label}`];
  const pts = (list: { date: string; value: number | null }[], row: number) =>
    list.filter((x) => x.value != null).map((x) => [x.value as number, row + jitter(x.date), x.date]);
  const medians = [
    e.median_untagged != null ? [e.median_untagged, 0] : null,
    e.median_tagged != null ? [e.median_tagged, 1] : null,
  ].filter(Boolean);
  return {
    ...base(p),
    grid: { left: 96, right: 16, top: 8, bottom: 28 },
    xAxis: {
      type: "value",
      scale: true,
      ...axisCommon(p),
      axisLabel: { ...axisCommon(p).axisLabel, formatter: (v: number) => fmtAxis(v, e.unit, units, e.metric) },
    },
    yAxis: {
      type: "value",
      min: -0.6,
      max: 1.6,
      interval: 1,
      ...axisCommon(p),
      axisLine: { show: false },
      splitLine: { show: false },
      axisLabel: { color: p.ink2, fontSize: 11, formatter: (v: number) => rows[Math.round(v)] ?? "" },
    },
    tooltip: {
      ...(base(p).tooltip as object),
      trigger: "item",
      formatter: (x: { seriesName: string; data: [number, number, string?] }) =>
        x.seriesName === "Median"
          ? row(p.ink, `Median, ${rows[Math.round(x.data[1])]?.toLowerCase()}`, fmt(x.data[0]))
          : `<div style="color:${p.muted};margin-bottom:4px">${x.data[2] ? fmtDay(x.data[2]) : ""}</div>` + row(x.seriesName === "Tagged" ? p.accent : p.neutral, e.metric_label, fmt(x.data[0])),
    },
    series: [
      { name: "Untagged", type: "scatter", data: pts(e.untagged, 0), symbolSize: 6, itemStyle: { color: p.neutral, opacity: 0.7 } },
      { name: "Tagged", type: "scatter", data: pts(e.tagged, 1), symbolSize: 9, itemStyle: { color: p.accent, borderColor: p.surface, borderWidth: 1 } },
      { name: "Median", type: "scatter", data: medians, symbol: "rect", symbolSize: [3, 34], itemStyle: { color: p.ink }, z: 5 },
    ],
  };
}
