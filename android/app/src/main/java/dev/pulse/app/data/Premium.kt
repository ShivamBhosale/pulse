package dev.pulse.app.data

import dev.pulse.app.core.Derived
import dev.pulse.app.core.Summary
import dev.pulse.app.core.premium.BodySignals
import dev.pulse.app.core.premium.Fitness
import dev.pulse.app.core.premium.SleepNeed
import dev.pulse.app.core.premium.SleepNeeds
import dev.pulse.app.core.premium.SleepScore
import dev.pulse.app.core.premium.SleepScoring
import dev.pulse.app.core.premium.Stress
import dev.pulse.app.core.premium.StressScoring
import dev.pulse.app.core.premium.Training
import dev.pulse.app.db.DailyMetric
import dev.pulse.app.db.PulseDb
import java.time.LocalDate
import java.time.ZoneId

/** Premium-style features: DB → pure maths (core.premium) → rows, cards and summary sentences. */
object Premium {
    /** Daily metrics this module owns (written per synced window). */
    val DAILY_KEYS = listOf("sleep_score", "sleep_need_min", "stress_score")

    data class Day(
        val date: LocalDate,
        val sleepScore: SleepScore?,
        val need: SleepNeed,
        val bedtime: SleepNeeds.Bedtime?,
        val stress: Stress?,
        val signals: List<dev.pulse.app.core.premium.Signal>,
        val strainTarget: Int?,
        val loadRatio: Double?,
        val loadStatus: String?,
        val vo2: Double?,
        val vo2Band: String?,
    )

    private suspend fun series(
        db: PulseDb,
        metric: String,
        from: LocalDate,
        to: LocalDate,
    ) = db.metrics().series(metric, from.toEpochDay(), to.toEpochDay()).associate { LocalDate.ofEpochDay(it.day) to it.value }

    /** Everything premium for civil day [d] (night ending on d, the day itself so far). */
    suspend fun day(
        db: PulseDb,
        d: LocalDate,
        p: UserPrefs,
        zone: ZoneId,
        age: Int,
    ): Day {
        val lo = d.minusDays(Derived.BASELINE_DAYS + 2L)
        val goal = p.goals.sleepMin.toDouble()
        val sleepMain = series(db, "sleep_main_min", lo, d)
        val azm = series(db, "azm", lo, d)
        val rhr = series(db, "resting_hr", lo, d)
        val hrv = series(db, "hrv_rmssd", lo, d)
        val resp = series(db, "resp_rate", lo, d)
        val spo2 = series(db, "spo2_avg", lo, d)
        val skin = series(db, "skin_temp_delta", d, d)[d]

        // Need for the night ending on d is based on the debt up to the night before.
        val need =
            SleepNeeds.need(
                goal,
                Derived.sleepDebt(sleepMain, d.minusDays(1), goal),
                azm[d.minusDays(2)],
                Derived.baselineAt(azm, d.minusDays(2)),
            )
        val main = db.sleep().night(d.toEpochDay()).let { s -> s.firstOrNull { it.isMain } ?: s.maxByOrNull { it.asleepMin } }
        val score =
            main?.let { m ->
                val hr = db.intraday().hr(m.start, m.end)
                SleepScoring.score(
                    asleepMin = m.asleepMin.toDouble(),
                    needMin = need.needMin,
                    deepMin = m.deepMin?.toDouble(),
                    remMin = m.remMin?.toDouble(),
                    sleepingHrAvg = hr.takeIf { it.isNotEmpty() }?.map { it.avg }?.average(),
                    restingHr = rhr[d] ?: Derived.baselineAt(rhr, d)?.median,
                    awakeMin = m.awakeMin.toDouble(),
                    interruptions = m.interruptions,
                )
            }
        // Tonight's need and bedtime (for the night ending tomorrow).
        val tonight = SleepNeeds.need(goal, Derived.sleepDebt(sleepMain, d, goal), azm[d.minusDays(1)], Derived.baselineAt(azm, d.minusDays(1)))
        val recent = db.sleep().range(d.minusDays(14).toEpochDay(), d.toEpochDay()).filter { it.isMain }
        val bedtime =
            SleepNeeds.bedtime(
                recent.map { java.time.Duration.between(LocalDate.ofEpochDay(it.day).atStartOfDay(zone).toInstant(), java.time.Instant.ofEpochMilli(it.end)).toMinutes().toDouble() },
                recent.map { it.latencyMin.toDouble() },
                tonight.needMin,
            )

        // Stress: waking-hours HR vs resting while barely moving.
        val rest = rhr[d] ?: Derived.baselineAt(rhr, d)?.median
        val waking =
            rest?.let {
                val start = d.atStartOfDay(zone).plusHours(7).toInstant().toEpochMilli()
                val end = d.atStartOfDay(zone).plusHours(22).toInstant().toEpochMilli()
                val slots = db.intraday().steps(d.toEpochDay(), d.toEpochDay()).associate { s -> s.ts to s.steps }
                db.intraday().hr(start, end).map { m ->
                    val slot = m.ts - Math.floorMod(m.ts, 15 * 60_000L)
                    m.avg to (slots[slot] ?: 0.0)
                }
            }
        fun pair(
            s: Map<LocalDate, Double>,
        ) = s[d]?.let { v -> Derived.baselineAt(s, d)?.let { v to it } }
        val stress =
            StressScoring.score(
                hrv = pair(hrv),
                rhr = pair(rhr),
                asleepMin = sleepMain[d],
                needMin = need.needMin,
                resp = pair(resp),
                elevatedShare = waking?.let { StressScoring.elevatedStillShare(it, rest) },
            )
        val signals =
            BodySignals.unusual(
                BodySignals.In(rhr[d], Derived.baselineAt(rhr, d)),
                BodySignals.In(hrv[d], Derived.baselineAt(hrv, d)),
                BodySignals.In(resp[d], Derived.baselineAt(resp, d)),
                BodySignals.In(spo2[d], Derived.baselineAt(spo2, d)),
                skin,
            )
        val readiness = series(db, "readiness", lo, d)
        val chronic = Derived.trailing(azm, d.minusDays(1), 28, includeDay = true).filterNotNull().takeIf { it.size >= 14 }?.average()
        val ratio = series(db, "load_ratio", d, d)[d]
        val rhr7 = Derived.trailing(rhr, d, 7, includeDay = true).filterNotNull().takeIf { it.size >= 5 }?.average()
        val vo2 = rhr7?.let { Fitness.estimate(age, it) }
        return Day(
            date = d,
            sleepScore = score,
            need = tonight,
            bedtime = bedtime,
            stress = stress,
            signals = signals,
            strainTarget = Training.target(chronic, readiness[d], Derived.baselineAt(readiness, d)),
            loadRatio = ratio,
            loadStatus = Training.loadStatus(ratio),
            vo2 = vo2,
            vo2Band = vo2?.let { Fitness.band(it, age, p.profile.sex) },
        )
    }

    /** Rows to store for day [d] (keeps history chartable in Trends). */
    suspend fun rows(
        db: PulseDb,
        d: LocalDate,
        p: UserPrefs,
        zone: ZoneId,
        age: Int,
    ): List<DailyMetric> {
        val x = day(db, d, p, zone, age)
        val e = d.toEpochDay()
        return listOfNotNull(
            x.sleepScore?.let { DailyMetric(e, "sleep_score", it.total.toDouble(), "score") },
            DailyMetric(e, "sleep_need_min", x.need.needMin, "min"),
            x.stress?.let { DailyMetric(e, "stress_score", it.score.toDouble(), "score") },
        )
    }

    /** VO₂ max estimate for every day with ≥ 5 resting-HR values in its 7-day window. */
    fun vo2Rows(
        rhr: Map<LocalDate, Double>,
        age: Int,
    ): List<DailyMetric> =
        rhr.keys.mapNotNull { d ->
            val w = Derived.trailing(rhr, d, 7, includeDay = true).filterNotNull()
            if (w.size >= 5) DailyMetric(d.toEpochDay(), "vo2max", Fitness.estimate(age, w.average()), "ml/kg/min") else null
        }

    // ---- summary sentences ---------------------------------------------------------------

    suspend fun sentences(
        repo: LocalRepository,
        d: LocalDate,
        p: UserPrefs,
    ): List<Summary.Sentence> {
        val x = day(repo.db, d, p, ZoneId.systemDefault(), repo.prefs.age(p, d.year))
        val isToday = d == repo.today()
        val out = mutableListOf<Summary.Sentence>()
        x.sleepScore?.let {
            out +=
                Summary.Sentence(
                    "Sleep score ${it.total} (${it.label}).",
                    if (it.total >= 80) Summary.Tone.GOOD else if (it.total < 60) Summary.Tone.ATTENTION else Summary.Tone.NEUTRAL,
                    if (it.total < 60) 78 else 47,
                    listOf("sleep_score"),
                )
        }
        if (x.signals.size >= 3) {
            out +=
                Summary.Sentence(
                    "Several body signals are unusual ${if (isToday) "today" else "that day"} (${x.signals.joinToString(", ") { it.label.lowercase() }}). Consider taking it easy.",
                    Summary.Tone.ATTENTION,
                    88,
                    x.signals.map { it.key },
                )
        }
        x.stress?.takeIf { it.band == "High" }?.let {
            out += Summary.Sentence("Body stress is high (${it.score}).", Summary.Tone.ATTENTION, 62, listOf("stress_score"))
        }
        if (isToday) {
            x.bedtime?.let {
                out +=
                    Summary.Sentence(
                        "Tonight's sleep need is ${Summary.duration(x.need.needMin)}: aim to be asleep by ${Summary.clock(it.asleepBy)}.",
                        Summary.Tone.NEUTRAL,
                        57,
                        listOf("sleep_need_min"),
                    )
            }
            x.strainTarget?.let {
                out += Summary.Sentence("Today's active-minutes target: $it min.", Summary.Tone.NEUTRAL, 44, listOf("azm"))
            }
        }
        return out
    }
}
