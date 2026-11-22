import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useExercise } from "../api/hooks";
import { workoutHrOption } from "../charts/more";
import { ZONE_LABEL } from "../charts/options";
import { EChart } from "../components/EChart";
import { Card, Empty, ErrorNote, Stat } from "../components/ui";
import { exerciseName, fmtDay, fmtDuration, fmtNum, fmtTime } from "../lib/format";
import { usePalette, type Palette } from "../lib/theme";
import { fmtMetric, useUnits } from "../lib/units";

export function WorkoutPage() {
  const [params] = useSearchParams();
  const id = params.get("id");
  const q = useExercise(id);
  const p = usePalette();
  const units = useUnits();
  const option = useMemo(() => (q.data && q.data.points.length ? workoutHrOption(q.data, p) : null), [q.data, p]);
  if (q.error) return <ErrorNote error={q.error} />;
  if (!q.data) return <div className="card h-64 animate-pulse" />;
  const { exercise: e, time_in_zones: tiz } = q.data;
  const totalZ = tiz.reduce((a, z) => a + z.minutes, 0);
  return (
    <div className="flex flex-col gap-4">
      <div className="reveal">
        <Link to="/activity" className="text-xs text-muted hover:text-ink">
          ← Activity
        </Link>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">{exerciseName(e)}</h1>
        <div className="num text-sm text-muted">
          {fmtDay(e.date, { weekday: "long", day: "numeric", month: "long", year: "numeric" })} · {fmtTime(e.start)}–{fmtTime(e.end)} · {e.source.split("/").pop()}
        </div>
      </div>
      <div className="card reveal grid grid-cols-2 gap-4 p-4 sm:grid-cols-3 lg:grid-cols-6" style={{ ["--i" as string]: 1 }}>
        <Stat label="Duration" value={fmtDuration(e.duration_min)} />
        <Stat label="Active" value={e.active_min != null ? fmtDuration(e.active_min) : "–"} />
        <Stat label="Distance" value={e.distance_km ? fmtMetric(e.distance_km, "km", units, "distance_km", false) : "–"} unit={e.distance_km ? (units === "imperial" ? "mi" : "km") : undefined} />
        <Stat label="Avg HR" value={e.avg_hr ? fmtNum(e.avg_hr) : "–"} unit={e.avg_hr ? "bpm" : undefined} />
        <Stat label="Max HR" value={q.data.max_hr ?? "–"} unit={q.data.max_hr ? "bpm" : undefined} />
        <Stat label="Calories" value={e.kcal ? fmtNum(e.kcal) : "–"} unit={e.kcal ? "kcal" : undefined} />
      </div>
      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <Card index={2} title="Heart rate" subtitle="1-minute average with your zones">
          {option ? <EChart option={option} height={260} label="Heart rate during the workout with zone bands" /> : <Empty>No heart-rate data for this workout</Empty>}
        </Card>
        <Card index={3} title="Time in zones" subtitle={totalZ ? `${fmtDuration(totalZ)} with heart-rate data` : undefined}>
          {totalZ ? (
            <ul className="space-y-2.5">
              {[...tiz].reverse().map((z) => (
                <li key={z.zone}>
                  <div className="flex items-baseline justify-between text-sm">
                    <span className="flex items-center gap-2">
                      <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: p.hrz[z.zone as keyof Palette["hrz"]] }} />
                      {ZONE_LABEL[z.zone] ?? z.zone}
                    </span>
                    <span className="num text-ink-2">
                      {fmtDuration(z.minutes)} <span className="text-muted">· {fmtNum((z.minutes / totalZ) * 100)}%</span>
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-surface-2">
                    <div className="h-full rounded-full" style={{ width: `${(z.minutes / totalZ) * 100}%`, background: p.hrz[z.zone as keyof Palette["hrz"]] }} />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>No zone data</Empty>
          )}
        </Card>
      </div>
    </div>
  );
}
