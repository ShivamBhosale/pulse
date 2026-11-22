import type { EChartsCoreOption, EChartsType } from "echarts/core";
import { useEffect, useRef, useState } from "react";

type Echarts = typeof import("echarts/core");
let loader: Promise<Echarts> | null = null;
const loadEcharts = () => (loader ??= import("../charts/echarts").then((m) => m.default));

interface Props {
  option: EChartsCoreOption;
  height: number;
  label: string;
}

/** Canvas chart with lazy-loaded ECharts, resize handling and an accessible label. */
export function EChart({ option, height, label }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<EChartsType | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let disposed = false;
    let ro: ResizeObserver | undefined;
    void loadEcharts().then((ec) => {
      if (disposed || !el.current) return;
      chart.current = ec.init(el.current, undefined, { renderer: "canvas" });
      ro = new ResizeObserver(() => chart.current?.resize());
      ro.observe(el.current);
      setReady(true);
    });
    return () => {
      disposed = true;
      ro?.disconnect();
      chart.current?.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    if (ready) chart.current?.setOption(option, { notMerge: true });
  }, [option, ready]);

  return (
    <div role="img" aria-label={label} style={{ height }} className="relative w-full">
      <div ref={el} className="absolute inset-0" />
      {!ready && <div className="absolute inset-0 animate-pulse rounded-lg bg-surface-2/60" />}
    </div>
  );
}
