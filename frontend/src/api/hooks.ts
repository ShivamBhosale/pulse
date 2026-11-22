import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api, type Granularity, type Journal, type SettingsIn, type TagInfo } from "./client";

export const useToday = () =>
  useQuery({ queryKey: ["today"], queryFn: api.today, refetchInterval: 5 * 60_000 });

export const useStatus = (fast = false) =>
  useQuery({ queryKey: ["status"], queryFn: api.status, refetchInterval: fast ? 2_000 : 60_000 });

export const useSleep = (date?: string) =>
  useQuery({ queryKey: ["sleep", date ?? "latest"], queryFn: () => api.sleep(date) });

export const useSleepTrend = (from: string, to: string) =>
  useQuery({ queryKey: ["sleep-trend", from, to], queryFn: () => api.sleepTrend(from, to) });

export const useMetric = (metric: string, from: string, to: string, granularity: Granularity, band = false, enabled = true) =>
  useQuery({
    queryKey: ["metric", metric, from, to, granularity, band],
    queryFn: () => api.metric(metric, from, to, granularity, band),
    enabled,
  });

export const useSeries = (metrics: string[], from: string, to: string, granularity: Granularity, enabled = true) =>
  useQuery({
    queryKey: ["series", metrics.join(","), from, to, granularity],
    queryFn: () => api.series(metrics, from, to, granularity),
    enabled: enabled && metrics.length > 0,
  });

export const useWeekday = (metric: string, from: string, to: string) =>
  useQuery({ queryKey: ["weekday", metric, from, to], queryFn: () => api.weekday(metric, from, to) });

export const useCorrelate = (a: string, b: string, from: string, to: string) =>
  useQuery({ queryKey: ["correlate", a, b, from, to], queryFn: () => api.correlate(a, b, from, to), enabled: a !== b });

export const useHeatmap = (from: string, to: string) =>
  useQuery({ queryKey: ["heatmap", from, to], queryFn: () => api.heatmap(from, to) });

export const useIntradayHr = (date: string) =>
  useQuery({ queryKey: ["intraday-hr", date], queryFn: () => api.intradayHr(date) });

export const useExercises = (from: string, to: string) =>
  useQuery({ queryKey: ["exercises", from, to], queryFn: () => api.exercises(from, to) });

export const useExercise = (id: string | null) =>
  useQuery({ queryKey: ["exercise", id], queryFn: () => api.exercise(id ?? ""), enabled: Boolean(id) });

export const useSummary = (date: string, enabled = true) =>
  useQuery({ queryKey: ["summary", date], queryFn: () => api.summary(date), enabled });

export const useTags = () => useQuery({ queryKey: ["tags"], queryFn: api.tags, staleTime: 5 * 60_000 });

export const useJournal = (date: string) =>
  useQuery({ queryKey: ["journal", date], queryFn: () => api.journal(date) });

export const useJournalRange = (from: string, to: string, enabled = true) =>
  useQuery({ queryKey: ["journal-range", from, to], queryFn: () => api.journalRange(from, to), enabled });

/** Save a day's tags + note optimistically; roll back if the server refuses. */
export function useSaveJournal(date: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (j: Pick<Journal, "tags" | "note">) => api.putJournal(date, j.tags, j.note),
    onMutate: async (j) => {
      await qc.cancelQueries({ queryKey: ["journal", date] });
      const prev = qc.getQueryData<Journal>(["journal", date]);
      qc.setQueryData<Journal>(["journal", date], { date, ...j });
      return { prev };
    },
    onError: (_e, _j, ctx) => ctx?.prev && qc.setQueryData(["journal", date], ctx.prev),
    onSuccess: (data) => {
      qc.setQueryData(["journal", date], data);
      for (const k of ["tags", "journal-range", "tag-effect", "tag-effects", "summary", "today"])
        void qc.invalidateQueries({ queryKey: [k] });
    },
  });
}

export function useTagMutations() {
  const qc = useQueryClient();
  const done = { onSuccess: () => void qc.invalidateQueries({ queryKey: ["tags"] }) };
  return {
    create: useMutation({ mutationFn: (t: { label: string; kind: TagInfo["kind"] }) => api.createTag(t.label, t.kind), ...done }),
    update: useMutation({
      mutationFn: (t: { key: string; patch: Partial<Pick<TagInfo, "label" | "kind" | "archived">> }) => api.updateTag(t.key, t.patch),
      ...done,
    }),
  };
}

export const useTagEffect = (tag: string, metric: string, from: string, to: string, lag: "auto" | "0" | "1", enabled = true) =>
  useQuery({
    queryKey: ["tag-effect", tag, metric, from, to, lag],
    queryFn: () => api.tagEffect(tag, metric, from, to, lag),
    enabled: enabled && Boolean(tag && metric),
  });

export const useTagEffects = (metric: string, from: string, to: string) =>
  useQuery({ queryKey: ["tag-effects", metric, from, to], queryFn: () => api.tagEffects(metric, from, to), enabled: Boolean(metric) });

export const useFreshness = () =>
  useQuery({ queryKey: ["data-health", "freshness"], queryFn: api.freshness, refetchInterval: 60_000 });

export const useCoverage = (from: string, to: string) =>
  useQuery({ queryKey: ["data-health", "coverage", from, to], queryFn: () => api.coverage(from, to) });

export const useDayHealth = (date: string | null) =>
  useQuery({ queryKey: ["data-health", "day", date], queryFn: () => api.dayHealth(date ?? ""), enabled: Boolean(date) });

/** Start a re-sync, then refresh data-health views (and everything else) when the job ends. */
export function useResync() {
  const qc = useQueryClient();
  const status = useStatus(true);
  const started = useRef(false);
  const m = useMutation({
    mutationFn: (r: { since: string; until?: string | null; streams?: string[] | null }) => api.resync(r.since, r.streams ?? null, r.until ?? null),
    onSuccess: () => {
      started.current = true;
      void qc.invalidateQueries({ queryKey: ["status"] });
    },
  });
  const running = m.isPending || Boolean(status.data?.syncing);
  useEffect(() => {
    if (started.current && status.data && !status.data.syncing) {
      started.current = false;
      void qc.invalidateQueries();
    }
  }, [status.data, qc]);
  return { resync: m.mutate, mutation: m, running, job: status.data?.job ?? null };
}

export const useRecords = () => useQuery({ queryKey: ["records"], queryFn: api.records });

export const useSettings = () => useQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 5 * 60_000 });

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SettingsIn) => api.updateSettings(body),
    onSuccess: (data) => {
      qc.setQueryData(["settings"], data);
      // Goals/weights change derived metrics: refresh every view.
      void qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "settings" });
    },
  });
}

/** Map of metric key → availability info (hide metrics with no data on this device). */
export function useAvailable() {
  const status = useStatus();
  const map = new Map((status.data?.metrics ?? []).map((m) => [m.key, m]));
  return { ready: Boolean(status.data), has: (k: string) => map.has(k), info: (k: string) => map.get(k), all: status.data?.metrics ?? [] };
}

/** Trigger a sync, poll /status until it finishes, then refresh every view. */
export function useRefresh() {
  const qc = useQueryClient();
  const status = useStatus(true);
  const started = useRef(false);
  const mutation = useMutation({
    mutationFn: api.sync,
    onSuccess: () => {
      started.current = true;
      void qc.invalidateQueries({ queryKey: ["status"] });
    },
  });
  const syncing = mutation.isPending || Boolean(status.data?.syncing);
  useEffect(() => {
    if (started.current && status.data && !status.data.syncing) {
      started.current = false;
      void qc.invalidateQueries();
    }
  }, [status.data, qc]);
  return { refresh: () => mutation.mutate(), syncing, status: status.data };
}
