import { useMemo } from "react";
import type { MetricInfo, TagEffect, TagInfo } from "../api/client";
import { useTagEffect, useTagEffects } from "../api/hooks";
import { stripOption } from "../charts/more";
import type { Span } from "../lib/range";
import { usePalette } from "../lib/theme";
import { fmtMetric, useUnits, type Units } from "../lib/units";
import { EChart } from "./EChart";
import { Card, Empty, ErrorNote } from "./ui";

export type Lag = "auto" | "0" | "1";

const VERDICT_ICON: Record<TagEffect["verdict"], string> = { clear: "●", possible: "◐", none: "○", too_few: "·" };

function diffText(e: TagEffect, units: Units): string {
  if (e.diff == null) return "–";
  const sign = e.diff > 0 ? "+" : e.diff < 0 ? "−" : "";
  return `${sign}${fmtMetric(Math.abs(e.diff), e.unit, units, e.metric)}`;
}

function when(e: TagEffect): string {
  return e.lag === 1 ? "the night after" : "the same day";
}

/** One sentence that says what the comparison found, without overstating it. */
function effectSentence(e: TagEffect, units: Units): string {
  if (e.verdict === "too_few")
    return `${e.n_tagged} day${e.n_tagged === 1 ? "" : "s"} tagged ${e.tag_label} with ${e.metric_label.toLowerCase()} data so far. Tag at least 3 to compare.`;
  const size = e.diff_in_iqr != null ? ` (${Math.abs(e.diff_in_iqr).toFixed(1)}× your typical spread)` : "";
  return `${e.metric_label} ${when(e)} ${e.tag_label}: median ${fmtMetric(e.median_tagged, e.unit, units, e.metric)} vs ${fmtMetric(
    e.median_untagged,
    e.unit,
    units,
    e.metric,
  )} without, ${diffText(e, units)}${size}.`;
}

export function TagEffectCard({ tag, metric, span, lag, index }: { tag: TagInfo; metric: MetricInfo; span: Span; lag: Lag; index: number }) {
  const q = useTagEffect(tag.key, metric.key, span.from, span.to, lag);
  const p = usePalette();
  const units = useUnits();
  const option = useMemo(() => (q.data && q.data.n_tagged > 0 ? stripOption(q.data, units, p) : null), [q.data, units, p]);
  const e = q.data;
  return (
    <Card
      index={index}
      title={`${metric.label} with and without ${tag.label}`}
      subtitle={e ? `Compared ${when(e)} · ${e.n_tagged} tagged, ${e.n_untagged} other days${tag.key !== "sick" ? " (sick days left out)" : ""}` : undefined}
    >
      {q.error ? (
        <ErrorNote error={q.error} />
      ) : !e ? (
        <div className="h-40 animate-pulse rounded-lg bg-surface-2/60" />
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-ink-2">
            <span className="font-medium text-ink">
              <span aria-hidden className="mr-1 text-accent-ink">
                {VERDICT_ICON[e.verdict]}
              </span>
              {e.verdict_text}.
            </span>{" "}
            {effectSentence(e, units)}
          </p>
          {option ? <EChart option={option} height={170} label={`Strip plot of ${metric.label} on days with and without ${tag.label}`} /> : <Empty>No tagged days in this range yet</Empty>}
          <p className="text-xs text-muted">
            A permutation test checks whether a gap this big shows up by chance when the days are shuffled
            {e.p != null ? ` (p = ${e.p < 0.001 ? "<0.001" : e.p.toFixed(3)})` : ""}. It shows association, not cause.
          </p>
        </div>
      )}
    </Card>
  );
}

export function TagOverviewCard({ metric, span, selected, onSelect, index }: { metric: MetricInfo; span: Span; selected: string; onSelect: (k: string) => void; index: number }) {
  const q = useTagEffects(metric.key, span.from, span.to);
  const units = useUnits();
  const effects = q.data?.effects ?? [];
  const maxAbs = Math.max(1, ...effects.map((e) => Math.abs(e.diff_in_iqr ?? 0)));
  return (
    <Card index={index} title={`Every tag vs ${metric.label.toLowerCase()}`} subtitle="Bigger bars = bigger difference relative to your usual spread">
      {q.error ? (
        <ErrorNote error={q.error} />
      ) : !q.data ? (
        <div className="h-40 animate-pulse rounded-lg bg-surface-2/60" />
      ) : (
        <ul className="divide-y divide-line">
          {effects.map((e) => {
            const w = e.diff_in_iqr != null ? (Math.min(Math.abs(e.diff_in_iqr), maxAbs) / maxAbs) * 50 : 0;
            const neg = (e.diff ?? 0) < 0;
            return (
              <li key={e.tag}>
                <button
                  type="button"
                  onClick={() => onSelect(e.tag)}
                  aria-pressed={selected === e.tag}
                  className={`grid w-full grid-cols-[minmax(0,1fr)_88px_minmax(0,1fr)] items-center gap-3 rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-surface-2 ${selected === e.tag ? "bg-surface-2" : ""}`}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-ink">{e.tag_label}</span>
                    <span className="num text-xs text-muted">
                      {e.n_tagged} tagged · {e.lag === 1 ? "next night" : "same day"}
                    </span>
                  </span>
                  <span className="relative h-2 rounded-full bg-surface-2" aria-hidden>
                    <span className="absolute inset-y-0 left-1/2 w-px bg-axis" />
                    {w > 0 && (
                      <span
                        className="absolute inset-y-0 rounded-full"
                        style={{ background: neg ? "var(--div-cool)" : "var(--div-warm)", width: `${w}%`, [neg ? "right" : "left"]: "50%" }}
                      />
                    )}
                  </span>
                  <span className="min-w-0 text-right">
                    <span className="num block text-ink">{e.verdict === "too_few" ? "–" : diffText(e, units)}</span>
                    <span className="text-xs text-muted">
                      <span aria-hidden>{VERDICT_ICON[e.verdict]} </span>
                      {e.verdict_text}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
