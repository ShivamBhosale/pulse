import { useState } from "react";
import type { ReadinessComponent, Tile } from "../api/client";
import { fmtDuration, fmtNum } from "../lib/format";

const LABEL: Record<ReadinessComponent["key"], string> = { hrv: "HRV", rhr: "Resting HR", sleep: "Sleep", strain: "Strain" };

function valueText(c: ReadinessComponent): string {
  if (c.value == null) return "no data";
  if (c.key === "sleep") return `${fmtDuration(c.value)} of ${fmtDuration(c.reference)}`;
  const unit = c.key === "hrv" ? "ms" : c.key === "rhr" ? "bpm" : "min";
  const dec = c.key === "hrv" ? 1 : 0;
  return `${fmtNum(c.value, dec)} ${unit}${c.reference != null ? ` · usual ${fmtNum(c.reference, dec)}` : ""}`;
}

/** The four readiness parts as small bars, plus the formula behind an info button. */
export function ReadinessBreakdown({ tile }: { tile: Tile }) {
  const [open, setOpen] = useState(false);
  const comps = tile.components ?? [];
  return (
    <div className="relative">
      <ul className="grid grid-cols-2 gap-x-3 gap-y-1.5">
        {comps.map((c) => (
          <li key={c.key} className="min-w-0" title={`${LABEL[c.key]}: ${valueText(c)}${c.weight ? ` · weight ${Math.round(c.weight * 100)}%` : ""}`}>
            <div className="flex items-baseline justify-between text-[11px] text-ink-2">
              <span>{LABEL[c.key]}</span>
              <span className="num text-muted">{c.score == null ? "–" : fmtNum(c.score)}</span>
            </div>
            <div className="mt-0.5 h-[3px] rounded-full bg-surface-2">
              {c.score != null && <div className="h-full rounded-full bg-accent" style={{ width: `${c.score}%`, opacity: c.weight ? 1 : 0.35 }} />}
            </div>
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="mt-2 text-[11px] text-muted underline decoration-dotted underline-offset-2 hover:text-ink"
      >
        ⓘ How it's calculated
      </button>
      {open && (
        <div role="note" className="card absolute bottom-7 left-0 z-20 w-[min(320px,80vw)] p-3 text-xs leading-relaxed text-ink-2 shadow-xl">
          <p>{tile.formula}</p>
          <ul className="num mt-2 space-y-0.5 text-muted">
            {comps.map((c) => (
              <li key={c.key}>
                {LABEL[c.key]}: {c.score == null ? "missing" : `${fmtNum(c.score)} × ${Math.round(c.weight * 100)}%`} — {valueText(c)}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-muted">Change the weights in Settings.</p>
        </div>
      )}
    </div>
  );
}
