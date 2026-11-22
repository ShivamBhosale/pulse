import { useMemo } from "react";
import { useToday } from "../api/hooks";
import { heartRateOption, stepsCurveOption } from "../charts/options";
import { EChart } from "../components/EChart";
import { JournalCard } from "../components/JournalCard";
import { SummaryCard } from "../components/SummaryCard";
import { Tile } from "../components/Tile";
import { Card, Empty, ErrorNote } from "../components/ui";
import { fmtDay, fmtNum } from "../lib/format";
import { usePalette } from "../lib/theme";

function Skeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="card h-[148px] animate-pulse" />
      ))}
    </div>
  );
}

export function TodayPage() {
  const { data, error, isPending } = useToday();
  const p = usePalette();
  const hrOption = useMemo(() => (data ? heartRateOption(data.heart_rate, p) : null), [data, p]);
  const stepsOption = useMemo(() => (data ? stepsCurveOption(data.steps_curve, data.goals.steps, p) : null), [data, p]);

  if (error) return <ErrorNote error={error} />;
  if (isPending || !data) return <Skeleton />;

  const hrPts = data.heart_rate.points;
  const latest = hrPts[hrPts.length - 1];
  return (
    <div className="flex flex-col gap-4">
      <div className="reveal flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">{fmtDay(data.date, { weekday: "long", day: "numeric", month: "long" })}</h1>
      </div>
      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <SummaryCard key={data.date} today={data.date} initial={data.summary} />
        <JournalCard key={`j-${data.date}`} today={data.date} />
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        {data.tiles.map((t, i) => (
          <Tile key={t.key} tile={t} index={i} />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <Card
          index={6}
          title="Heart rate"
          subtitle={
            latest ? (
              <span className="num">
                latest {fmtNum(latest.avg)} bpm · zones shaded, sleep and workouts banded
              </span>
            ) : (
              "No heart-rate data yet today"
            )
          }
        >
          {hrOption && hrPts.length ? <EChart option={hrOption} height={260} label="Heart rate across today with heart-rate zones, sleep and workouts" /> : <Empty>No data yet</Empty>}
        </Card>
        <Card index={7} title="Steps through the day" subtitle="Cumulative, compared with your median day (28 days)">
          {stepsOption && data.steps_curve.median.length ? (
            <EChart option={stepsOption} height={260} label="Cumulative steps today against your usual day" />
          ) : (
            <Empty>Needs a few days of history</Empty>
          )}
        </Card>
      </div>
    </div>
  );
}
