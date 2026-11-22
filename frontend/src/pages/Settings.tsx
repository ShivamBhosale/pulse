import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { api, type Settings } from "../api/client";
import { useSettings, useStatus, useTagMutations, useTags, useUpdateSettings } from "../api/hooks";
import type { TagInfo } from "../api/client";
import { Card, ErrorNote } from "../components/ui";
import { addDays, fmtAgo, fmtDuration, fmtNum, isoDate } from "../lib/format";
import { useTheme } from "../lib/theme";

const input = "num w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm text-ink";
const textInput = "w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm text-ink";
const btn = "rounded-lg border border-line px-3 py-1.5 text-sm text-ink-2 transition-colors hover:text-ink disabled:opacity-50";
const primary = "rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-[var(--page)] disabled:opacity-50";

function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-ink-2">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </label>
  );
}

function Result({ m }: { m: { isError: boolean; isSuccess: boolean; error: unknown } }) {
  if (m.isError) return <span role="alert" className="text-xs text-ink-2"><span className="text-serious" aria-hidden>▲ </span>{m.error instanceof Error ? m.error.message : "Failed"}</span>;
  if (m.isSuccess) return <span className="text-xs text-ink-2"><span className="text-good-ink" aria-hidden>✓ </span>Saved</span>;
  return null;
}

function GoalsCard({ s }: { s: Settings }) {
  const save = useUpdateSettings();
  const [sleepH, setSleepH] = useState(s.goals.sleep_min / 60);
  const [steps, setSteps] = useState(s.goals.steps);
  const [azm, setAzm] = useState(s.goals.azm_weekly);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate({ goals: { sleep_min: Math.round(sleepH * 60), steps, azm_weekly: azm } });
  };
  return (
    <Card index={1} title="Goals" subtitle="Used for tiles, streaks, sleep debt and readiness">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-3">
        <Field label="Sleep (hours)" hint={fmtDuration(sleepH * 60)}>
          <input className={input} type="number" min={3} max={12} step={0.25} value={sleepH} onChange={(e) => setSleepH(Number(e.target.value))} />
        </Field>
        <Field label="Steps per day">
          <input className={input} type="number" min={1000} max={50000} step={500} value={steps} onChange={(e) => setSteps(Number(e.target.value))} />
        </Field>
        <Field label="Active zone minutes per week">
          <input className={input} type="number" min={10} max={1500} step={10} value={azm} onChange={(e) => setAzm(Number(e.target.value))} />
        </Field>
        <div className="flex items-center gap-3 sm:col-span-3">
          <button className={primary} disabled={save.isPending}>Save goals</button>
          <Result m={save} />
        </div>
      </form>
    </Card>
  );
}

function DisplayCard({ s }: { s: Settings }) {
  const save = useUpdateSettings();
  const { theme, toggle } = useTheme();
  return (
    <Card index={2} title="Display">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Units" hint={s.units === "metric" ? "km, °C" : "miles, °F"}>
          <div role="radiogroup" className="inline-flex w-fit rounded-lg border border-line p-0.5">
            {(["metric", "imperial"] as const).map((u) => (
              <button key={u} type="button" role="radio" aria-checked={s.units === u} onClick={() => save.mutate({ units: u })} className={`rounded-md px-3 py-1 text-sm ${s.units === u ? "bg-surface-2 text-ink" : "text-muted hover:text-ink"}`}>
                {u === "metric" ? "Metric" : "Imperial"}
              </button>
            ))}
          </div>
        </Field>
        <Field label="Theme" hint="Saved on this device">
          <div role="radiogroup" className="inline-flex w-fit rounded-lg border border-line p-0.5">
            {(["dark", "light"] as const).map((t) => (
              <button key={t} type="button" role="radio" aria-checked={theme === t} onClick={() => theme !== t && toggle()} className={`rounded-md px-3 py-1 text-sm capitalize ${theme === t ? "bg-surface-2 text-ink" : "text-muted hover:text-ink"}`}>
                {t}
              </button>
            ))}
          </div>
        </Field>
      </div>
    </Card>
  );
}

const WEIGHT_LABEL = { hrv: "HRV vs baseline", rhr: "Resting HR vs baseline", sleep: "Sleep vs goal", strain: "Yesterday's strain" } as const;
type WeightKey = keyof typeof WEIGHT_LABEL;

function WeightsCard({ s }: { s: Settings }) {
  const save = useUpdateSettings();
  const [w, setW] = useState(s.readiness_weights);
  const total = Object.values(w).reduce((a, b) => a + b, 0);
  const defaults = { hrv: 35, rhr: 25, sleep: 25, strain: 15 };
  return (
    <Card index={3} title="Readiness weights" subtitle="A personal heuristic, not a medical measure. Weights are relative; missing parts are left out.">
      <div className="flex flex-col gap-3">
        {(Object.keys(WEIGHT_LABEL) as WeightKey[]).map((k) => (
          <label key={k} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 sm:grid-cols-[180px_1fr_auto]">
            <span className="text-sm text-ink-2">{WEIGHT_LABEL[k]}</span>
            <input type="range" min={0} max={100} step={5} value={w[k]} onChange={(e) => setW({ ...w, [k]: Number(e.target.value) })} className="col-span-2 accent-[var(--accent)] sm:col-span-1" aria-label={`${WEIGHT_LABEL[k]} weight`} />
            <span className="num row-start-1 text-right text-sm text-ink sm:row-auto">{total ? fmtNum((w[k] / total) * 100) : 0}%</span>
          </label>
        ))}
        <details className="text-xs text-muted">
          <summary className="cursor-pointer">Formula</summary>
          <p className="mt-1 leading-relaxed">{s.readiness_formula}</p>
        </details>
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={primary} disabled={save.isPending || total <= 0} onClick={() => save.mutate({ readiness_weights: w })}>
            Save and recompute
          </button>
          <button type="button" className={btn} onClick={() => setW(defaults)}>
            Reset to 35 / 25 / 25 / 15
          </button>
          <Result m={save} />
        </div>
      </div>
    </Card>
  );
}

function PasscodeCard({ s }: { s: Settings }) {
  const qc = useQueryClient();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const m = useMutation({
    mutationFn: (clear: boolean) => api.changePasscode(s.passcode_set ? current : null, clear ? null : next),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      void qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });
  const valid = /^\d{4,6}$/.test(next);
  return (
    <Card index={4} title="Passcode" subtitle={s.passcode_set ? "On · changing it signs out every other device" : "Off · anyone on your tailnet can open Pulse"}>
      <form
        className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) m.mutate(false);
        }}
      >
        {s.passcode_set && (
          <Field label="Current passcode">
            <input className={input} type="password" inputMode="numeric" autoComplete="current-password" maxLength={6} value={current} onChange={(e) => setCurrent(e.target.value.replace(/\D/g, ""))} />
          </Field>
        )}
        <Field label={s.passcode_set ? "New passcode" : "Passcode (4–6 digits)"}>
          <input className={input} type="password" inputMode="numeric" autoComplete="new-password" maxLength={6} value={next} onChange={(e) => setNext(e.target.value.replace(/\D/g, ""))} />
        </Field>
        <div className="flex items-end gap-2">
          <button className={primary} disabled={!valid || m.isPending}>{s.passcode_set ? "Change" : "Turn on"}</button>
          {s.passcode_set && (
            <button type="button" className={btn} disabled={current.length < 4 || m.isPending} onClick={() => m.mutate(true)}>
              Turn off
            </button>
          )}
        </div>
      </form>
      <div className="mt-2">
        <Result m={m} />
      </div>
    </Card>
  );
}

function ConnectionCard() {
  const status = useStatus(true);
  const qc = useQueryClient();
  const st = status.data;
  const [since, setSince] = useState(addDays(isoDate(new Date()), -30));
  const [stream, setStream] = useState("");
  const [backfillSince, setBackfillSince] = useState("");
  const after = { onSuccess: () => void qc.invalidateQueries({ queryKey: ["status"] }) };
  const sync = useMutation({ mutationFn: api.sync, ...after });
  const backfill = useMutation({ mutationFn: () => api.backfill(backfillSince || null), ...after });
  const resync = useMutation({ mutationFn: () => api.resync(since, stream ? [stream] : null), ...after });
  if (!st) return <Card index={5} title="Google connection"><div className="h-24 animate-pulse rounded-lg bg-surface-2/60" /></Card>;
  const busy = st.syncing;
  return (
    <Card index={5} title="Google connection & sync">
      <div className="flex flex-col gap-4 text-sm">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden className={st.auth.ok ? "text-good-ink" : "text-serious"}>{st.auth.ok ? "●" : "▲"}</span>
            {st.auth.ok ? "Connected" : "Needs reconnecting"}
          </span>
          <span className="num text-ink-2">Last sync {fmtAgo(st.last_sync)}</span>
          {st.next_run && <span className="num text-muted">next {new Date(st.next_run).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false })}</span>}
          {busy && <span className="num text-accent-ink"><span className="syncing-dot" aria-hidden>●</span> {st.job ?? "sync"} running…</span>}
        </div>
        {!st.auth.ok && (
          <p className="text-ink-2">
            {st.auth.error}. Reconnecting needs the browser sign-in on the server: run{" "}
            <code className="num rounded bg-surface-2 px-1">docker compose run --rm -p 127.0.0.1:8765:8765 pulse auth</code> with an SSH tunnel to port 8765.
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={btn} disabled={busy} onClick={() => sync.mutate()}>Sync now</button>
          <Result m={sync} />
        </div>
        <div className="grid gap-3 border-t border-line pt-3 sm:grid-cols-[1fr_1fr_auto]">
          <Field label="Re-sync from" hint="Re-fetches this range and replaces what's stored">
            <input className={input} type="date" value={since} max={isoDate(new Date())} onChange={(e) => setSince(e.target.value)} />
          </Field>
          <Field label="Stream">
            <select className={input} value={stream} onChange={(e) => setStream(e.target.value)}>
              <option value="">All streams</option>
              {st.stream_names.map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </Field>
          <div className="flex items-end">
            <button type="button" className={btn} disabled={busy || !since} onClick={() => resync.mutate()}>Re-sync</button>
          </div>
          <Result m={resync} />
        </div>
        <div className="grid gap-3 border-t border-line pt-3 sm:grid-cols-[1fr_auto]">
          <Field label="Backfill history since" hint={st.backfill.floor ? `Backfilled to ${st.backfill.floor}${st.backfill.cursor && st.backfill.cursor > st.backfill.floor ? ` · resuming at ${st.backfill.cursor}` : ""}. Leave empty to discover the earliest data.` : "Leave empty to discover the earliest data."}>
            <input className={input} type="date" value={backfillSince} max={isoDate(new Date())} onChange={(e) => setBackfillSince(e.target.value)} />
          </Field>
          <div className="flex items-end">
            <button type="button" className={btn} disabled={busy} onClick={() => backfill.mutate()}>Backfill</button>
          </div>
          <Result m={backfill} />
        </div>
        <details className="text-xs text-muted">
          <summary className="cursor-pointer">Streams</summary>
          <table className="num mt-2 w-full">
            <tbody>
              {st.streams.map((x) => (
                <tr key={x.stream} className="border-t border-line">
                  <td className="py-1 pr-2 text-ink-2">{x.stream}</td>
                  <td className="py-1 pr-2">{fmtAgo(x.last_success)}</td>
                  <td className="py-1">{x.last_error ? <span><span className="text-serious" aria-hidden>▲ </span>{x.last_error}</span> : "ok"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </div>
    </Card>
  );
}

function TagRow({ t }: { t: TagInfo }) {
  const { update } = useTagMutations();
  const [label, setLabel] = useState(t.label);
  const changed = label.trim() !== t.label && label.trim().length > 0;
  return (
    <li className={`grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 py-2 sm:grid-cols-[minmax(0,1fr)_auto_auto_auto] ${t.archived ? "opacity-60" : ""}`}>
      <form
        className="flex min-w-0 items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (changed) update.mutate({ key: t.key, patch: { label: label.trim() } });
        }}
      >
        <input className={`${textInput} min-w-0`} value={label} maxLength={40} onChange={(e) => setLabel(e.target.value)} aria-label={`Rename ${t.label}`} />
        {changed && <button className={btn}>Rename</button>}
      </form>
      <span className="num text-right text-xs text-muted">
        {t.uses} day{t.uses === 1 ? "" : "s"}
      </span>
      <select
        className="rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink"
        value={t.kind}
        onChange={(e) => update.mutate({ key: t.key, patch: { kind: e.target.value as TagInfo["kind"] } })}
        aria-label={`When ${t.label} applies`}
      >
        <option value="evening">Evening → next night</option>
        <option value="day">Day</option>
      </select>
      <button type="button" className={btn} onClick={() => update.mutate({ key: t.key, patch: { archived: !t.archived } })}>
        {t.archived ? "Restore" : "Archive"}
      </button>
    </li>
  );
}

function TagsCard() {
  const tags = useTags();
  const { create } = useTagMutations();
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState<TagInfo["kind"]>("day");
  const [showArchived, setShowArchived] = useState(false);
  const list = (tags.data ?? []).filter((t) => showArchived || !t.archived);
  const archivedCount = (tags.data ?? []).filter((t) => t.archived).length;
  return (
    <Card index={7} title="Tags" subtitle="Evening tags are compared with the night that follows. Archiving hides a tag but keeps its history.">
      <form
        className="mb-3 grid gap-2 sm:grid-cols-[1fr_auto_auto]"
        onSubmit={(e) => {
          e.preventDefault();
          if (label.trim()) create.mutate({ label: label.trim(), kind }, { onSuccess: () => setLabel("") });
        }}
      >
        <input className={textInput} placeholder="New tag, e.g. Sauna" value={label} maxLength={40} onChange={(e) => setLabel(e.target.value)} aria-label="New tag name" />
        <select className={input} value={kind} onChange={(e) => setKind(e.target.value as TagInfo["kind"])} aria-label="New tag kind">
          <option value="day">Day</option>
          <option value="evening">Evening → next night</option>
        </select>
        <button className={primary} disabled={!label.trim() || create.isPending}>Add tag</button>
      </form>
      <Result m={create} />
      {!tags.data ? (
        <div className="h-24 animate-pulse rounded-lg bg-surface-2/60" />
      ) : (
        <ul className="divide-y divide-line">
          {list.map((t) => (
            <TagRow key={`${t.key}-${t.label}`} t={t} />
          ))}
        </ul>
      )}
      {archivedCount > 0 && (
        <button type="button" className="mt-2 text-xs text-muted underline decoration-dotted underline-offset-2 hover:text-ink" onClick={() => setShowArchived((x) => !x)}>
          {showArchived ? "Hide archived" : `Show ${archivedCount} archived`}
        </button>
      )}
    </Card>
  );
}

function fmtBytes(n: number): string {
  return n >= 1e9 ? `${fmtNum(n / 1e9, 1)} GB` : `${fmtNum(n / 1e6, 1)} MB`;
}

function BackupCard() {
  const status = useStatus(true);
  const qc = useQueryClient();
  const run = useMutation({ mutationFn: api.backup, onSuccess: () => void qc.invalidateQueries({ queryKey: ["status"] }) });
  const b = status.data?.backup;
  if (!b) return <Card index={6} title="Backups"><div className="h-20 animate-pulse rounded-lg bg-surface-2/60" /></Card>;
  const failedLast = b.last_error && (!b.last_at || (b.last_error_at && b.last_error_at > b.last_at));
  return (
    <Card index={6} title="Backups" subtitle={b.enabled ? `Nightly at ${b.schedule} · keeps 7 daily, 4 weekly, 6 monthly` : "Nightly backups are off (PULSE_BACKUP_ENABLED=false)"}>
      <div className="flex flex-col gap-3 text-sm">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden className={failedLast ? "text-serious" : b.last_at ? "text-good-ink" : "text-muted"}>{failedLast ? "▲" : b.last_at ? "●" : "○"}</span>
            {failedLast ? "Last backup failed" : b.last_at ? `Last backup ${fmtAgo(b.last_at)}` : "No backup yet"}
          </span>
          {b.count > 0 && (
            <span className="num text-ink-2">
              {b.count} file{b.count === 1 ? "" : "s"} · {fmtBytes(b.total_bytes)}
            </span>
          )}
          {b.next_run && <span className="num text-muted">next {new Date(b.next_run).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false })}</span>}
        </div>
        {failedLast && <p className="text-xs text-ink-2">{b.last_error}</p>}
        {b.latest_file && <p className="num text-xs text-muted">Latest: data/backups/{b.latest_file}{b.latest_size_bytes ? ` (${fmtBytes(b.latest_size_bytes)})` : ""}</p>}
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={btn} disabled={b.running || run.isPending} onClick={() => run.mutate()}>
            {b.running ? "Backing up…" : "Back up now"}
          </button>
          <Result m={run} />
        </div>
        <details className="text-xs text-muted">
          <summary className="cursor-pointer">How to restore</summary>
          <ol className="mt-2 list-decimal space-y-1 pl-4 leading-relaxed">
            <li>
              Stop Pulse: <code className="num rounded bg-surface-2 px-1">docker compose stop</code>
            </li>
            <li>
              Restore: <code className="num rounded bg-surface-2 px-1">docker compose run --rm pulse restore /data/backups/&lt;file&gt;</code>
            </li>
            <li>
              Start again: <code className="num rounded bg-surface-2 px-1">docker compose up -d</code>
            </li>
          </ol>
          <p className="mt-1">The current database is kept next to it as a <code>.pre-restore</code> copy. Backups contain all your health data: keep copies somewhere private.</p>
        </details>
      </div>
    </Card>
  );
}

export function SettingsPage() {
  const q = useSettings();
  if (q.error) return <ErrorNote error={q.error} />;
  if (!q.data) return <div className="card h-64 animate-pulse" />;
  return (
    <div className="flex flex-col gap-4">
      <h1 className="reveal text-2xl font-semibold tracking-tight">Settings</h1>
      <div className="grid gap-4 lg:grid-cols-2">
        <GoalsCard key={JSON.stringify(q.data.goals)} s={q.data} />
        <DisplayCard s={q.data} />
        <WeightsCard key={JSON.stringify(q.data.readiness_weights)} s={q.data} />
        <PasscodeCard s={q.data} />
      </div>
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <ConnectionCard />
        <BackupCard />
      </div>
      <TagsCard />
    </div>
  );
}
