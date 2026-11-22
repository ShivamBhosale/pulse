import type { Tile as TileData } from "../api/client";
import { fmtDuration, fmtNum, signed } from "../lib/format";
import { ReadinessBreakdown } from "./Readiness";
import { Sparkline } from "./Sparkline";

type Tone = { label: string; icon: string; color: string } | null;

/** Status colours carry meaning only, always with an icon and a word. */
function toneFor(t: TileData): Tone {
  if (t.status === "none" || t.delta == null) return null;
  if (t.status === "in_range") return { label: "Usual", icon: "●", color: "var(--good)" };
  const up = t.delta > 0;
  const favourable = t.better !== "none" && (t.better === "up") === up;
  const icon = up ? "▲" : "▼";
  if (favourable) return { label: up ? "Above usual" : "Below usual", icon, color: "var(--good)" };
  if (t.status === "mild") return { label: up ? "A bit high" : "A bit low", icon, color: "var(--warning)" };
  return { label: up ? "Well above usual" : "Well below usual", icon, color: "var(--serious)" };
}

function display(t: TileData): { value: string; unit: string } {
  if (t.value == null) return { value: "–", unit: "" };
  switch (t.key) {
    case "sleep_main_min":
      return { value: fmtDuration(t.value), unit: "" };
    case "hrv_rmssd":
      return { value: fmtNum(t.value, 1), unit: "ms" };
    case "resting_hr":
      return { value: fmtNum(t.value), unit: "bpm" };
    case "azm":
      return { value: fmtNum(t.value), unit: "min" };
    case "steps":
      return { value: fmtNum(t.value), unit: "" };
    case "readiness":
      return { value: fmtNum(t.value), unit: "/ 100" };
    default:
      return { value: fmtNum(t.value), unit: t.unit };
  }
}

function deltaText(t: TileData): string | null {
  if (t.delta == null || t.baseline == null) return null;
  if (t.key === "sleep_main_min") {
    const d = Math.round(t.delta);
    return `${d >= 0 ? "+" : "−"}${fmtDuration(Math.abs(d))} vs usual`;
  }
  return `${signed(t.delta, t.key === "hrv_rmssd" ? 1 : 0)} vs usual`;
}

export function Tile({ tile, index }: { tile: TileData; index: number }) {
  const tone = toneFor(tile);
  const { value, unit } = display(tile);
  const delta = deltaText(tile);
  const goalPct = tile.goal && tile.value != null && tile.key !== "azm" ? Math.min(1, tile.value / tile.goal) : null;
  return (
    <article className="card reveal flex min-h-[148px] min-w-0 flex-col gap-2 p-3.5 sm:p-4" style={{ ["--i" as string]: index }}>
      <header className="flex items-start justify-between gap-2">
        <h3 className="eyebrow">{tile.label}</h3>
        {tone && (
          <span className="inline-flex items-center gap-1 whitespace-nowrap text-[11px] font-medium text-ink-2">
            <span aria-hidden style={{ color: tone.color }}>
              {tone.icon}
            </span>
            {tone.label}
          </span>
        )}
      </header>
      <div className="flex items-baseline gap-1.5">
        <span className={`num text-[26px] font-medium leading-none sm:text-[30px] ${tile.value == null ? "text-muted" : "text-ink"}`}>{value}</span>
        {unit && <span className="text-sm text-muted">{unit}</span>}
      </div>
      <div className="mt-auto flex items-end justify-between gap-3">
        <div className="min-w-0 text-xs leading-snug text-ink-2">
          {delta && <div className="num">{delta}</div>}
          {tile.note && <div className="truncate text-muted">{tile.note}</div>}
          {!delta && !tile.note && tile.key !== "readiness" && (
            <div className="text-muted">{tile.value == null ? "No data yet" : "Building baseline…"}</div>
          )}
        </div>
        <Sparkline points={tile.spark} band={tile.key === "steps" || tile.key === "azm" ? null : tile.baseline} />
      </div>
      {tile.key === "readiness" && tile.components && <ReadinessBreakdown tile={tile} />}
      {goalPct != null && (
        <div className="h-[3px] overflow-hidden rounded-full bg-surface-2" aria-label={`${Math.round(goalPct * 100)}% of goal`}>
          <div className="h-full rounded-full bg-accent" style={{ width: `${goalPct * 100}%` }} />
        </div>
      )}
    </article>
  );
}
