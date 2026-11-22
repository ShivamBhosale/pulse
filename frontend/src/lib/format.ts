const nf0 = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

export function fmtNum(v: number | null | undefined, decimals = 0): string {
  if (v == null || Number.isNaN(v)) return "–";
  return decimals === 0
    ? nf0.format(v)
    : new Intl.NumberFormat(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(v);
}

export function fmtDuration(min: number | null | undefined): string {
  if (min == null) return "–";
  const m = Math.round(min);
  const h = Math.floor(m / 60);
  return h > 0 ? `${h}h ${String(m % 60).padStart(2, "0")}m` : `${m}m`;
}

/** Minutes from local midnight (negative = evening before) → "22:50". */
export function fmtClock(min: number | null | undefined): string {
  if (min == null) return "–";
  const m = ((Math.round(min) % 1440) + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function fmtDay(isoDate: string, opts: Intl.DateTimeFormatOptions = { weekday: "short", day: "numeric", month: "short" }): string {
  return new Date(`${isoDate}T12:00:00`).toLocaleDateString(undefined, opts);
}

export function fmtAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "never";
  const s = Math.max(0, (now - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export function signed(v: number, decimals = 0): string {
  const s = fmtNum(Math.abs(v), decimals);
  return v > 0 ? `+${s}` : v < 0 ? `−${s}` : s;
}

export function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + n);
  return isoDate(d);
}

/** "Strength training" from STRENGTH_TRAINING unless the workout has its own name. */
export function exerciseName(e: { name?: string | null; exercise_type: string }): string {
  return e.name ?? e.exercise_type.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
}
