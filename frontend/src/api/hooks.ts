import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api } from "./client";

export const useToday = () =>
  useQuery({ queryKey: ["today"], queryFn: api.today, refetchInterval: 5 * 60_000 });

export const useStatus = (fast = false) =>
  useQuery({ queryKey: ["status"], queryFn: api.status, refetchInterval: fast ? 2_000 : 60_000 });

export const useSleep = (date?: string) =>
  useQuery({ queryKey: ["sleep", date ?? "latest"], queryFn: () => api.sleep(date) });

export const useSleepTrend = (from: string, to: string) =>
  useQuery({ queryKey: ["sleep-trend", from, to], queryFn: () => api.sleepTrend(from, to) });

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
