import type { ReactNode } from "react";
import { RANGES, type Range } from "../lib/range";
import { RangeTabs } from "./ui";

/** Page title + the one range switcher that drives every chart on the page. */
export function RangeBar({ title, range, onChange, children }: { title: string; range: Range; onChange: (r: Range) => void; children?: ReactNode }) {
  return (
    <div className="reveal flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <div className="flex flex-wrap items-center gap-2">
        {children}
        <RangeTabs value={range} options={RANGES} onChange={onChange} />
      </div>
    </div>
  );
}
