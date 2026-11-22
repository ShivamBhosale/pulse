// ECharts option builders. Pure functions of (data, palette) so theme switches just rebuild.
// Conventions (dataviz method): thin marks, recessive grid, one axis, legend only for ≥2 series,
// text in ink tokens (never series colours), tooltip on every chart.
import type { EChartsCoreOption } from "echarts/core";
import type { IntradayHeartRate, SleepSession, SleepTrendNight, StepsCurve } from "../api/client";
import { fmtClock, fmtDay, fmtDuration, fmtNum, fmtTime } from "../lib/format";
import type { Palette } from "../lib/theme";

export const FONT = "IBM Plex Sans, system-ui, sans-serif";
export const MONO = "IBM Plex Mono, ui-monospace, monospace";

export function base(p: Palette): EChartsCoreOption {
  return {
    animationDuration: 500,
    textStyle: { fontFamily: FONT, color: p.ink2, fontSize: 11 },
    tooltip: {
      backgroundColor: p.surface,
      borderColor: p.line,
      borderWidth: 1,
      padding: [8, 10],
      textStyle: { color: p.ink, fontFamily: FONT, fontSize: 12 },
      extraCssText: "border-radius:10px;box-shadow:0 8px 24px rgb(0 0 0 / .25);",
    },
  };
}

export const axisCommon = (p: Palette) => ({
  axisLine: { lineStyle: { color: p.axis } },
  axisTick: { show: false },
  axisLabel: { color: p.muted, fontFamily: MONO, fontSize: 10 },
  splitLine: { lineStyle: { color: p.grid, width: 1 } },
});

export const row = (swatch: string, label: string, value: string) =>
  `<div style="display:flex;gap:8px;align-items:center;justify-content:space-between;min-width:150px">` +
  `<span style="display:inline-flex;gap:6px;align-items:center">` +
  `<span style="width:8px;height:8px;border-radius:2px;background:${swatch}"></span>${label}</span>` +
  `<b style="font-family:${MONO};font-weight:500">${value}</b></div>`;

export const ZONE_LABEL: Record<string, string> = { below: "Below zones", light: "Light", moderate: "Fat burn", vigorous: "Cardio", peak: "Peak" };

// ---- intraday heart rate ------------------------------------------------------------------

export function heartRateOption(hr: IntradayHeartRate, p: Palette): EChartsCoreOption {
  const dayStart = new Date(`${hr.date}T00:00:00`).getTime();
  const dayEnd = dayStart + 24 * 3600 * 1000;
  const data = hr.points.map((pt) => [new Date(pt.t).getTime(), pt.avg, pt.min, pt.max]);
  const bpms = hr.points.map((pt) => pt.avg);
  const yMin = Math.max(30, Math.floor((Math.min(...bpms, 60) - 8) / 10) * 10);
  const yMax = Math.ceil((Math.max(...bpms, 100) + 10) / 10) * 10;
  // Zone bands (skip "light": it starts at ~30 bpm and would tint the whole plot).
  const zones = hr.zones.filter((z) => z.zone !== "light" && z.min_bpm < yMax);
  const zoneAreas = zones.map((z, i) => [
    {
      yAxis: z.min_bpm,
      itemStyle: { color: p.zones[Math.min(i, 2)] },
      label: { show: true, position: "insideRight", formatter: ZONE_LABEL[z.zone] ?? z.zone, color: p.muted, fontSize: 10 },
    },
    { yAxis: Math.min(z.max_bpm, yMax) },
  ]);
  const periodAreas = hr.periods.map((pd) => [
    {
      xAxis: Math.max(new Date(pd.start).getTime(), dayStart),
      itemStyle: { color: pd.kind === "sleep" ? p.bandSleep : p.bandWorkout },
      label: {
        show: true,
        position: "insideTop",
        formatter: pd.label,
        color: p.ink2,
        fontSize: 10,
        distance: 4,
      },
    },
    { xAxis: Math.min(new Date(pd.end).getTime(), dayEnd) },
  ]);
  const zoneOf = (bpm: number) => [...hr.zones].reverse().find((z) => bpm >= z.min_bpm)?.zone;
  return {
    ...base(p),
    grid: { left: 36, right: 12, top: 18, bottom: 26 },
    xAxis: {
      type: "time",
      min: dayStart,
      max: dayEnd,
      ...axisCommon(p),
      splitLine: { show: false },
      axisLabel: {
        ...axisCommon(p).axisLabel,
        formatter: (v: number) => new Date(v).toLocaleTimeString(undefined, { hour: "2-digit", hour12: false }),
      },
      splitNumber: 6,
    },
    yAxis: { type: "value", min: yMin, max: yMax, ...axisCommon(p), axisLine: { show: false }, splitNumber: 4 },
    tooltip: {
      ...(base(p).tooltip as object),
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: p.axis } },
      formatter: (params: { data: number[] }[]) => {
        const d = params[0]?.data;
        if (!d) return "";
        const [t, avg, lo, hi] = d as [number, number, number, number];
        const z = zoneOf(avg);
        return (
          `<div style="color:${p.muted};margin-bottom:4px">${fmtTime(new Date(t).toISOString())}${z ? ` · ${ZONE_LABEL[z] ?? z} zone` : ""}</div>` +
          row(p.accent, "Heart rate", `${fmtNum(avg)} bpm`) +
          `<div style="color:${p.muted};font-size:11px;margin-top:2px">range ${lo}–${hi}</div>`
        );
      },
    },
    series: [
      {
        type: "line",
        name: "Heart rate",
        data,
        showSymbol: false,
        sampling: "lttb",
        lineStyle: { color: p.accent, width: 1.5 },
        itemStyle: { color: p.accent },
        connectNulls: false,
        markArea: { silent: true, data: [...zoneAreas, ...periodAreas] },
        markLine:
          hr.resting_hr != null
            ? {
                silent: true,
                symbol: "none",
                lineStyle: { color: p.muted, type: "dashed", width: 1 },
                label: { formatter: `Resting ${fmtNum(hr.resting_hr)}`, color: p.muted, fontSize: 10, position: "insideEndTop" },
                data: [{ yAxis: hr.resting_hr }],
              }
            : undefined,
      },
    ],
  };
}

// ---- steps accumulation --------------------------------------------------------------------

export function stepsCurveOption(curve: StepsCurve, goal: number, p: Palette): EChartsCoreOption {
  const slots = curve.median.length || curve.today.length;
  const labels = Array.from({ length: slots }, (_, i) => fmtClock(i * curve.slot_minutes));
  const lastToday = curve.today.findLastIndex((v) => v != null);
  return {
    ...base(p),
    grid: { left: 44, right: 64, top: 30, bottom: 26 },
    legend: {
      top: 0,
      left: 0,
      itemWidth: 14,
      itemHeight: 2,
      textStyle: { color: p.ink2, fontSize: 11 },
      data: ["Today", "Usual day"],
    },
    xAxis: {
      type: "category",
      data: labels,
      boundaryGap: false,
      ...axisCommon(p),
      splitLine: { show: false },
      axisLabel: { ...axisCommon(p).axisLabel, interval: (i: number) => i % 12 === 0 },
    },
    yAxis: {
      type: "value",
      ...axisCommon(p),
      axisLine: { show: false },
      splitNumber: 4,
      axisLabel: { ...axisCommon(p).axisLabel, formatter: (v: number) => (v >= 1000 ? `${v / 1000}k` : `${v}`) },
    },
    tooltip: {
      ...(base(p).tooltip as object),
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: p.axis } },
      formatter: (params: { seriesName: string; value: number | null; dataIndex: number; color: string }[]) => {
        const i = params[0]?.dataIndex ?? 0;
        return (
          `<div style="color:${p.muted};margin-bottom:4px">by ${labels[i]}</div>` +
          params.filter((x) => x.value != null).map((x) => row(x.color, x.seriesName, fmtNum(x.value))).join("")
        );
      },
    },
    series: [
      {
        name: "Usual day",
        type: "line",
        data: curve.median,
        showSymbol: false,
        lineStyle: { color: p.muted, width: 1.5, type: "dashed" },
        itemStyle: { color: p.muted },
        endLabel: { show: curve.median.length > 0, formatter: "usual", color: p.muted, fontSize: 10 },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: p.axis, width: 1 },
          label: { formatter: `Goal ${fmtNum(goal)}`, color: p.muted, fontSize: 10, position: "insideStartTop" },
          data: [{ yAxis: goal }],
        },
      },
      {
        name: "Today",
        type: "line",
        data: curve.today,
        showSymbol: false,
        lineStyle: { color: p.accent, width: 2 },
        itemStyle: { color: p.accent },
        areaStyle: { color: p.accentSoft },
        endLabel: {
          show: lastToday >= 0,
          formatter: (x: { value: number }) => fmtNum(x.value),
          color: p.ink,
          fontFamily: MONO,
          fontSize: 11,
        },
      },
    ],
  };
}

// ---- sleep ---------------------------------------------------------------------------------

export const STAGES = ["DEEP", "LIGHT", "REM", "AWAKE"] as const;
export type Stage = (typeof STAGES)[number];
export const STAGE_LABEL: Record<Stage, string> = { DEEP: "Deep", LIGHT: "Light", REM: "REM", AWAKE: "Awake" };

export function hypnogramOption(s: SleepSession, p: Palette): EChartsCoreOption {
  // Rows top→bottom: Awake, REM, Light, Deep (depth reads downward).
  const rows: Stage[] = ["DEEP", "LIGHT", "REM", "AWAKE"];
  const data = s.stages
    .filter((st): st is typeof st & { stage: Stage } => (rows as readonly string[]).includes(st.stage))
    .map((st) => ({
      value: [rows.indexOf(st.stage), new Date(st.start).getTime(), new Date(st.end).getTime()],
      itemStyle: { color: p.stage[st.stage] },
      stage: st.stage,
    }));
  return {
    ...base(p),
    grid: { left: 52, right: 12, top: 8, bottom: 26 },
    xAxis: {
      type: "time",
      min: new Date(s.start).getTime(),
      max: new Date(s.end).getTime(),
      ...axisCommon(p),
      splitLine: { show: false },
      axisLabel: {
        ...axisCommon(p).axisLabel,
        formatter: (v: number) => new Date(v).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false }),
      },
    },
    yAxis: {
      type: "category",
      data: rows.map((r) => STAGE_LABEL[r]),
      ...axisCommon(p),
      axisLine: { show: false },
      splitLine: { show: true, lineStyle: { color: p.grid } },
      axisLabel: { color: p.ink2, fontSize: 11, fontFamily: FONT },
    },
    tooltip: {
      ...(base(p).tooltip as object),
      trigger: "item",
      formatter: (x: { data: { value: number[]; stage: Stage } }) => {
        const [, a, b] = x.data.value as [number, number, number];
        return (
          row(p.stage[x.data.stage], STAGE_LABEL[x.data.stage], fmtDuration((b - a) / 60000)) +
          `<div style="color:${p.muted};font-size:11px;margin-top:2px">${fmtTime(new Date(a).toISOString())}–${fmtTime(new Date(b).toISOString())}</div>`
        );
      },
    },
    series: [
      {
        type: "custom",
        data,
        encode: { x: [1, 2], y: 0 },
        renderItem: (
          _params: unknown,
          api: {
            value: (i: number) => number;
            coord: (v: [number, number]) => [number, number];
            size: (v: [number, number]) => [number, number];
            style: () => object;
          },
        ) => {
          const rowIdx = api.value(0);
          const start = api.coord([api.value(1), rowIdx]);
          const end = api.coord([api.value(2), rowIdx]);
          const h = api.size([0, 1])[1] * 0.62;
          return {
            type: "rect",
            shape: { x: start[0], y: start[1] - h / 2, width: Math.max(1, end[0] - start[0]), height: h, r: 2 },
            style: api.style(),
          };
        },
      },
    ],
  };
}

const dayLabels = (nights: SleepTrendNight[]) => nights.map((n) => fmtDay(n.date, { day: "numeric", month: "short" }));

export function durationOption(nights: SleepTrendNight[], goalMin: number, p: Palette): EChartsCoreOption {
  return {
    ...base(p),
    grid: { left: 40, right: 12, top: 14, bottom: 26 },
    xAxis: { type: "category", data: dayLabels(nights), ...axisCommon(p), splitLine: { show: false } },
    yAxis: {
      type: "value",
      ...axisCommon(p),
      axisLine: { show: false },
      min: 0,
      interval: 120,
      axisLabel: { ...axisCommon(p).axisLabel, formatter: (v: number) => `${Math.round(v / 60)}h` },
    },
    tooltip: {
      ...(base(p).tooltip as object),
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: p.accentSoft } },
      formatter: (x: { dataIndex: number }[]) => {
        const n = nights[x[0]?.dataIndex ?? 0];
        if (!n) return "";
        const diff = (n.asleep_min ?? 0) - goalMin;
        return (
          `<div style="color:${p.muted};margin-bottom:4px">${fmtDay(n.date)}</div>` +
          row(p.accent, "Asleep", fmtDuration(n.asleep_min)) +
          `<div style="color:${p.muted};font-size:11px;margin-top:2px">${diff >= 0 ? "+" : "−"}${fmtDuration(Math.abs(diff))} vs goal</div>`
        );
      },
    },
    series: [
      {
        type: "bar",
        data: nights.map((n) => n.asleep_min),
        barMaxWidth: 14,
        itemStyle: { color: p.accent, borderRadius: [4, 4, 0, 0] },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: p.ink2, type: "dashed", width: 1 },
          label: { formatter: `Goal ${fmtDuration(goalMin)}`, color: p.muted, fontSize: 10, position: "insideEndTop" },
          data: [{ yAxis: goalMin }],
        },
      },
    ],
  };
}

export function stagesStackOption(nights: SleepTrendNight[], p: Palette): EChartsCoreOption {
  const field: Record<Stage, keyof SleepTrendNight> = {
    DEEP: "deep_min",
    LIGHT: "light_min",
    REM: "rem_min",
    AWAKE: "awake_min",
  };
  return {
    ...base(p),
    grid: { left: 40, right: 12, top: 30, bottom: 26 },
    legend: {
      top: 0,
      left: 0,
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: p.ink2, fontSize: 11 },
      data: STAGES.map((s) => STAGE_LABEL[s]),
    },
    xAxis: { type: "category", data: dayLabels(nights), ...axisCommon(p), splitLine: { show: false } },
    yAxis: {
      type: "value",
      ...axisCommon(p),
      axisLine: { show: false },
      min: 0,
      interval: 120,
      axisLabel: { ...axisCommon(p).axisLabel, formatter: (v: number) => `${Math.round(v / 60)}h` },
    },
    tooltip: {
      ...(base(p).tooltip as object),
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: p.accentSoft } },
      formatter: (x: { seriesName: string; value: number | null; color: string; dataIndex: number }[]) => {
        const n = nights[x[0]?.dataIndex ?? 0];
        return (
          `<div style="color:${p.muted};margin-bottom:4px">${n ? fmtDay(n.date) : ""}</div>` +
          [...x].reverse().map((s) => row(s.color, s.seriesName, fmtDuration(s.value))).join("")
        );
      },
    },
    series: STAGES.map((s) => ({
      name: STAGE_LABEL[s],
      type: "bar",
      stack: "stages",
      barMaxWidth: 14,
      data: nights.map((n) => n[field[s]] as number | null),
      // 1px surface border between stacked segments (dataviz spacer rule).
      itemStyle: { color: p.stage[s], borderColor: p.surface, borderWidth: 1 },
    })),
  };
}

export function consistencyOption(nights: SleepTrendNight[], p: Palette): EChartsCoreOption {
  const data = nights
    .map((n, i) => (n.bedtime_min != null && n.waketime_min != null ? [i, n.bedtime_min, n.waketime_min] : null))
    .filter((x): x is number[] => x != null);
  // Align to 2-hour ticks so labels are evenly spaced.
  const lo = Math.floor((Math.min(...data.map((d) => d[1] ?? 0), -120) - 30) / 120) * 120;
  const hi = Math.ceil((Math.max(...data.map((d) => d[2] ?? 0), 420) + 30) / 120) * 120;
  return {
    ...base(p),
    grid: { left: 44, right: 12, top: 10, bottom: 26 },
    xAxis: { type: "category", data: dayLabels(nights), ...axisCommon(p), splitLine: { show: false } },
    yAxis: {
      type: "value",
      inverse: true, // evening at the top, morning below: reads like a night
      min: lo,
      max: hi,
      interval: 120,
      ...axisCommon(p),
      axisLine: { show: false },
      axisLabel: { ...axisCommon(p).axisLabel, formatter: (v: number) => fmtClock(v) },
    },
    tooltip: {
      ...(base(p).tooltip as object),
      trigger: "item",
      formatter: (x: { data: number[] }) => {
        const [i, bed, wake] = x.data as [number, number, number];
        const n = nights[i];
        return (
          `<div style="color:${p.muted};margin-bottom:4px">${n ? fmtDay(n.date) : ""}</div>` +
          row(p.accent, "Bedtime", fmtClock(bed)) +
          row(p.accent, "Wake", fmtClock(wake))
        );
      },
    },
    series: [
      {
        type: "custom",
        data,
        encode: { x: 0, y: [1, 2] },
        renderItem: (
          _params: unknown,
          api: {
            value: (i: number) => number;
            coord: (v: [number, number]) => [number, number];
            size: (v: [number, number]) => [number, number];
          },
        ) => {
          const a = api.coord([api.value(0), api.value(1)]);
          const b = api.coord([api.value(0), api.value(2)]);
          const w = Math.min(12, api.size([1, 0])[0] * 0.55);
          return {
            type: "group",
            children: [
              {
                type: "rect",
                shape: { x: a[0] - w / 2, y: a[1], width: w, height: b[1] - a[1], r: 4 },
                style: { fill: p.accentSoft, stroke: p.accent, lineWidth: 1 },
              },
            ],
          };
        },
      },
    ],
  };
}
