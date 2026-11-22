import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { Journal, TagInfo } from "../api/client";
import { useJournal, useSaveJournal, useTags } from "../api/hooks";
import { addDays, fmtDay } from "../lib/format";

const NOTE_MAX = 2000;
const AUTOSAVE_MS = 800;

function JournalEditor({ date, initial, tags }: { date: string; initial: Journal; tags: TagInfo[] }) {
  const save = useSaveJournal(date);
  const [selected, setSelected] = useState<string[]>(initial.tags);
  const [note, setNote] = useState(initial.note);
  const [dirty, setDirty] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  // Latest values for the debounced save (updated in handlers, never during render).
  const latest = useRef({ selected: initial.tags, note: initial.note });

  const flush = () => {
    window.clearTimeout(timer.current);
    timer.current = undefined;
    save.mutate({ tags: latest.current.selected, note: latest.current.note }, { onSettled: () => setDirty(false) });
  };
  // Save a pending note edit if the card unmounts (day switch, navigation).
  useEffect(
    () => () => {
      if (timer.current !== undefined) {
        window.clearTimeout(timer.current);
        save.mutate({ tags: latest.current.selected, note: latest.current.note });
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const toggle = (key: string) => {
    const next = selected.includes(key) ? selected.filter((k) => k !== key) : [...selected, key];
    setSelected(next);
    latest.current = { selected: next, note: latest.current.note };
    flush();
  };
  const onNote = (v: string) => {
    setNote(v);
    latest.current = { selected: latest.current.selected, note: v };
    setDirty(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(flush, AUTOSAVE_MS);
  };

  // Active tags, plus archived ones already on this day (so history stays visible).
  const shown = tags.filter((t) => !t.archived || selected.includes(t.key));
  const evening = shown.filter((t) => t.kind === "evening");
  const day = shown.filter((t) => t.kind === "day");
  const state = save.isError ? "error" : dirty || save.isPending ? "saving" : save.isSuccess ? "saved" : "idle";

  const chip = (t: TagInfo) => {
    const on = selected.includes(t.key);
    return (
      <button
        key={t.key}
        type="button"
        aria-pressed={on}
        onClick={() => toggle(t.key)}
        className={`min-h-9 rounded-full border px-3 py-1.5 text-sm transition-colors ${
          on ? "border-accent bg-accent-soft text-accent-ink" : "border-line text-ink-2 hover:border-axis hover:text-ink"
        } ${t.archived ? "opacity-60" : ""}`}
      >
        {on && <span aria-hidden>✓ </span>}
        {t.label}
      </button>
    );
  };

  return (
    <div className="flex flex-col gap-3">
      {evening.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs text-muted">Evening (compared with the following night)</div>
          <div className="flex flex-wrap gap-2">{evening.map(chip)}</div>
        </div>
      )}
      {day.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs text-muted">Day</div>
          <div className="flex flex-wrap gap-2">{day.map(chip)}</div>
        </div>
      )}
      <label className="flex flex-col gap-1">
        <span className="sr-only">Note for {date}</span>
        <textarea
          value={note}
          maxLength={NOTE_MAX}
          rows={2}
          onChange={(e) => onNote(e.target.value)}
          onBlur={() => timer.current !== undefined && flush()}
          placeholder="Note (optional): how you felt, what was different…"
          className="w-full resize-y rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted"
        />
      </label>
      <div className="flex items-center justify-between text-xs text-muted" aria-live="polite">
        <span>
          {state === "error" ? (
            <span className="text-ink-2">
              <span className="text-serious" aria-hidden>▲ </span>
              Not saved: {save.error instanceof Error ? save.error.message : "error"}
            </span>
          ) : state === "saving" ? (
            "Saving…"
          ) : state === "saved" ? (
            <span>
              <span className="text-good-ink" aria-hidden>✓ </span>Saved
            </span>
          ) : (
            "Changes save automatically"
          )}
        </span>
        <span className="num">{note.length > NOTE_MAX - 200 ? `${note.length}/${NOTE_MAX}` : ""}</span>
      </div>
    </div>
  );
}

/** Tag a day and jot a note. Evening tags usually get logged the next morning, so
 *  Yesterday is one tap away. */
export function JournalCard({ today, index = 1 }: { today: string; index?: number }) {
  const [date, setDate] = useState(today);
  const yesterday = addDays(today, -1);
  const j = useJournal(date);
  const tags = useTags();
  const tab = (d: string, label: string) => (
    <button
      type="button"
      role="tab"
      aria-selected={date === d}
      onClick={() => setDate(d)}
      className={`rounded-md px-2.5 py-1 text-xs ${date === d ? "bg-surface-2 text-ink" : "text-muted hover:text-ink"}`}
    >
      {label}
    </button>
  );
  return (
    <section className="card reveal p-4" style={{ ["--i" as string]: index }} aria-label="Journal">
      <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-medium text-ink">Journal</h2>
          <div className="text-xs text-muted">
            {date === today ? "Today" : date === yesterday ? "Yesterday" : fmtDay(date)} ·{" "}
            <Link to="/trends#tags" className="underline decoration-dotted underline-offset-2 hover:text-ink">
              see what your tags change
            </Link>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <div role="tablist" className="inline-flex rounded-lg border border-line p-0.5">
            {tab(yesterday, "Yesterday")}
            {tab(today, "Today")}
          </div>
          <input
            type="date"
            value={date}
            max={today}
            onChange={(e) => e.target.value && setDate(e.target.value)}
            className="num rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink"
            aria-label="Journal day"
          />
        </div>
      </header>
      {!j.data || !tags.data ? (
        <div className="h-28 animate-pulse rounded-lg bg-surface-2/60" />
      ) : (
        <JournalEditor key={date} date={date} initial={j.data} tags={tags.data} />
      )}
    </section>
  );
}
