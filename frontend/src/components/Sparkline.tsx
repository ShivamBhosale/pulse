interface Point {
  date: string;
  value?: number | null;
}

/** 14-day sparkline as inline SVG (no chart library: tiles must paint instantly). */
export function Sparkline({ points, band }: { points: Point[]; band?: { q1: number; q3: number } | null }) {
  const w = 120;
  const h = 32;
  const vals = points.map((p) => p.value ?? null);
  const nums = vals.filter((v): v is number => v != null);
  const cls = "h-8 w-[84px] shrink-0 overflow-visible sm:w-[120px]";
  if (nums.length < 2) return <svg className={cls} aria-hidden />;
  let lo = Math.min(...nums, band?.q1 ?? Infinity);
  let hi = Math.max(...nums, band?.q3 ?? -Infinity);
  if (hi === lo) {
    hi += 1;
    lo -= 1;
  }
  const x = (i: number) => (i / (vals.length - 1)) * (w - 4) + 2;
  const y = (v: number) => h - 3 - ((v - lo) / (hi - lo)) * (h - 6);
  let d = "";
  let pen = false;
  vals.forEach((v, i) => {
    if (v == null) {
      pen = false;
      return;
    }
    d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    pen = true;
  });
  const lastIdx = vals.findLastIndex((v) => v != null);
  const last = vals[lastIdx];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} aria-hidden className={cls}>
      {band && (
        <rect x={0} width={w} y={y(band.q3)} height={Math.max(1, y(band.q1) - y(band.q3))} fill="var(--accent-soft)" rx={2} />
      )}
      <path d={d} fill="none" stroke="var(--ink-muted)" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      {last != null && <circle cx={x(lastIdx)} cy={y(last)} r={3} fill="var(--accent)" stroke="var(--surface)" strokeWidth={2} />}
    </svg>
  );
}
