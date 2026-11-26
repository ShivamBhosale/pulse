package dev.pulse.app.data

import dev.pulse.api.models.BaselineOut
import dev.pulse.api.models.DayValue
import dev.pulse.api.models.HrPoint
import dev.pulse.api.models.IntradayHeartRate
import dev.pulse.api.models.Journal
import dev.pulse.api.models.Period
import dev.pulse.api.models.ReadinessComponent
import dev.pulse.api.models.SleepNight
import dev.pulse.api.models.SleepSessionOut
import dev.pulse.api.models.SleepStageOut
import dev.pulse.api.models.SleepingHeartRate
import dev.pulse.api.models.Spo2
import dev.pulse.api.models.StepsCurve
import dev.pulse.api.models.SummarySentence
import dev.pulse.api.models.TagOut
import dev.pulse.api.models.Tile
import dev.pulse.api.models.Today
import dev.pulse.api.models.WidgetReadiness
import dev.pulse.api.models.WidgetSnapshot
import dev.pulse.api.models.ZoneBand
import dev.pulse.app.core.Azm
import dev.pulse.app.core.Baseline
import dev.pulse.app.core.Derived
import dev.pulse.app.core.Series
import dev.pulse.app.core.Status
import dev.pulse.app.core.Summary
import dev.pulse.app.db.PulseDb
import dev.pulse.app.db.Tag
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import dev.pulse.api.models.Goals as ApiGoals
import dev.pulse.api.models.Summary as ApiSummary

/** Metric facts used by tiles (subset of the server's metrics.CATALOG). */
data class MetricMeta(val label: String, val unit: String, val better: Tile.Better)

object Catalog {
    val M =
        mapOf(
            "readiness" to MetricMeta("Readiness", "score", Tile.Better.up),
            "sleep_main_min" to MetricMeta("Main sleep", "min", Tile.Better.up),
            "resting_hr" to MetricMeta("Resting heart rate", "bpm", Tile.Better.down),
            "hrv_rmssd" to MetricMeta("Heart rate variability", "ms", Tile.Better.up),
            "steps" to MetricMeta("Steps", "steps", Tile.Better.up),
            "azm" to MetricMeta("Active zone minutes", "min", Tile.Better.up),
            "spo2_avg" to MetricMeta("Blood oxygen", "%", Tile.Better.up),
            "resp_rate" to MetricMeta("Breathing rate", "brpm", Tile.Better.down),
            "skin_temp_delta" to MetricMeta("Skin temperature variation", "°C", Tile.Better.none),
        )
}

/**
 * Everything the screens need, computed on the phone from Room (port of the server's
 * queries.py). Returns the same model classes the server's API used, so screens are shared.
 */
class LocalRepository(
    val db: PulseDb,
    val prefs: Prefs,
    private val zone: ZoneId = ZoneId.systemDefault(),
    private val now: () -> Instant = Instant::now,
) {
    companion object {
        const val SLOT_MIN = 15
        const val SLOTS = 24 * 60 / SLOT_MIN
        const val SPARK_DAYS = 14
        val ZONE_LABEL = mapOf("moderate" to "fat burn", "vigorous" to "cardio", "peak" to "peak")
    }

    fun today(): LocalDate = now().atZone(zone).toLocalDate()

    private fun iso(ms: Long) = Instant.ofEpochMilli(ms).toString()

    suspend fun values(
        metric: String,
        from: LocalDate,
        to: LocalDate,
    ): Series = db.metrics().series(metric, from.toEpochDay(), to.toEpochDay()).associate { LocalDate.ofEpochDay(it.day) to it.value }

    private fun spark(
        values: Series,
        end: LocalDate,
    ) = (SPARK_DAYS - 1 downTo 0).map { end.minusDays(it.toLong()) }.map { DayValue(it.toString(), values[it]) }

    private fun baselineOut(b: Baseline?) = b?.let { BaselineOut(it.median, it.q1, it.q3, it.n) }

    private fun tileStatus(s: Status) = Tile.Status.valueOf(s.key)

    // ---- tiles -------------------------------------------------------------------------

    suspend fun dailyTile(
        metric: String,
        d: LocalDate,
        fallbackDays: Int = 0,
        label: String? = null,
        goal: Double? = null,
    ): Tile {
        val m = Catalog.M.getValue(metric)
        val values = values(metric, d.minusDays(Derived.BASELINE_DAYS + 7L), d)
        val valueDate = (0..fallbackDays).map { d.minusDays(it.toLong()) }.firstOrNull { it in values }
        val value = valueDate?.let { values[it] }
        val ref = valueDate ?: d
        val b = Derived.baselineAt(values, ref)
        val note =
            if (valueDate != null && valueDate != d) {
                if (d.toEpochDay() - valueDate.toEpochDay() == 1L) "yesterday" else "as of $valueDate"
            } else {
                null
            }
        return Tile(
            key = metric,
            label = label ?: m.label,
            unit = m.unit,
            `value` = value,
            valueDate = valueDate?.toString(),
            delta = Derived.delta(value, b),
            status = tileStatus(Derived.status(value, b)),
            better = m.better,
            baseline = baselineOut(b),
            spark = spark(values, d),
            note = note,
            goal = goal,
        )
    }

    private fun slotOf(ts: Long): Int {
        val t = Instant.ofEpochMilli(ts).atZone(zone)
        return (t.hour * 60 + t.minute) / SLOT_MIN
    }

    private suspend fun stepSlots(
        from: LocalDate,
        to: LocalDate,
    ): Map<LocalDate, DoubleArray> {
        val out = mutableMapOf<LocalDate, DoubleArray>()
        db.intraday().steps(from.toEpochDay(), to.toEpochDay()).forEach { r ->
            out.getOrPut(LocalDate.ofEpochDay(r.day)) { DoubleArray(SLOTS) }[slotOf(r.ts).coerceIn(0, SLOTS - 1)] += r.steps
        }
        return out
    }

    private fun cutSlot(d: LocalDate): Int = if (now().atZone(zone).toLocalDate() == d) slotOf(now().toEpochMilli()) else SLOTS - 1

    suspend fun stepsTile(
        d: LocalDate,
        goal: Int,
    ): Tile {
        val totals = values("steps", d.minusDays(SPARK_DAYS.toLong()), d)
        val cut = cutSlot(d)
        val soFar = stepSlots(d.minusDays(Derived.BASELINE_DAYS.toLong()), d.minusDays(1)).values.map { it.take(cut + 1).sum() }
        val b = Derived.baseline(soFar)
        val v = totals[d]
        return Tile(
            "steps", "Steps so far", "steps", v, if (v != null) d.toString() else null, Derived.delta(v, b),
            tileStatus(Derived.status(v, b)), Tile.Better.up, baselineOut(b), spark(totals, d),
            note = "vs. your usual by this time", goal = goal.toDouble(),
        )
    }

    suspend fun azmTile(
        d: LocalDate,
        weeklyGoal: Int,
        age: Int,
    ): Tile {
        val totals = values("azm", d.minusDays(Derived.BASELINE_DAYS.toLong()), d)
        val rhr = values("resting_hr", d.minusDays(60), d)
        val cutMin = if (now().atZone(zone).toLocalDate() == d) now().atZone(zone).let { it.hour * 60 + it.minute } else 1440
        val soFar = mutableListOf<Double?>()
        for (i in 1..Derived.BASELINE_DAYS) {
            val day = d.minusDays(i.toLong())
            if (day !in totals) continue
            val start = day.atStartOfDay(zone).toInstant()
            val mins = db.intraday().hr(start.toEpochMilli(), start.plusSeconds(cutMin * 60L).toEpochMilli())
            val r = rhr[day] ?: rhr.values.takeIf { it.isNotEmpty() }?.let { Derived.median(it.toList()) } ?: 60.0
            soFar += Azm.minutes(mins.map { it.avg }, Azm.zones(age, r)).total.toDouble()
        }
        val b = Derived.baseline(soFar)
        val v = totals[d]
        val week = Derived.weekToDate(totals, d) ?: 0.0
        return Tile(
            "azm", "Active zone minutes", "min", v, if (v != null) d.toString() else null, Derived.delta(v, b),
            tileStatus(Derived.status(v, b)), Tile.Better.up, baselineOut(b), spark(totals, d),
            note = "${Summary.num(week)} of $weeklyGoal this week", goal = weeklyGoal.toDouble(),
        )
    }

    suspend fun readinessParts(
        d: LocalDate,
        p: UserPrefs,
    ): Derived.Readiness {
        val lo = d.minusDays(Derived.BASELINE_DAYS + 2L)
        return Derived.readiness(
            d,
            values("hrv_rmssd", lo, d),
            values("resting_hr", lo, d),
            values("sleep_main_min", lo, d),
            values("azm", lo, d),
            p.goals.sleepMin.toDouble(),
            p.weights,
        )
    }

    private val componentMeta =
        mapOf(
            "hrv" to ("HRV vs baseline" to "ms"),
            "rhr" to ("Resting HR vs baseline" to "bpm"),
            "sleep" to ("Last night's sleep vs goal" to "min"),
            "strain" to ("Yesterday's strain vs baseline" to "min"),
        )

    suspend fun readinessTile(
        d: LocalDate,
        p: UserPrefs,
    ): Tile {
        val t = dailyTile("readiness", d, fallbackDays = 1)
        val r = readinessParts(LocalDate.parse(t.valueDate ?: d.toString()), p)
        return t.copy(
            components =
                r.components.map { c ->
                    ReadinessComponent(
                        ReadinessComponent.Key.valueOf(c.key),
                        componentMeta.getValue(c.key).first,
                        c.score,
                        Math.round(c.weight * 1000) / 1000.0,
                        c.value,
                        c.reference,
                        componentMeta.getValue(c.key).second,
                    )
                },
            formula = Derived.READINESS_FORMULA,
            note = if (t.value == null) "Not enough data yet · personal heuristic" else "Personal heuristic, not a medical measure" + (t.note?.let { " · $it" } ?: ""),
        )
    }

    // ---- today ---------------------------------------------------------------------------

    suspend fun intradayHeartRate(
        d: LocalDate,
        age: Int,
    ): IntradayHeartRate {
        val start = d.atStartOfDay(zone).toInstant().toEpochMilli()
        val end = d.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        val points = db.intraday().hr(start, end).map { HrPoint(iso(it.ts), Math.round(it.avg * 10) / 10.0, it.min.toInt(), it.max.toInt()) }
        val rhr = values("resting_hr", d.minusDays(28), d)
        val r = rhr[d] ?: rhr.values.takeIf { it.isNotEmpty() }?.let { Derived.median(it.toList()) }
        val zones =
            r?.let {
                val z = Azm.zones(age, it)
                listOf(ZoneBand("moderate", z.fatBurn, z.cardio - 1), ZoneBand("vigorous", z.cardio, z.peak - 1), ZoneBand("peak", z.peak, z.max))
            } ?: emptyList()
        val periods =
            db.sleep().overlapping(start, end).map { Period(Period.Kind.sleep, iso(it.start), iso(it.end), if (it.isMain) "Sleep" else "Nap") } +
                db.exercises().overlapping(start, end).map {
                    Period(Period.Kind.workout, iso(it.start), iso(it.end), it.title ?: it.type.lowercase().replace('_', ' ').replaceFirstChar { c -> c.uppercase() })
                }
        return IntradayHeartRate(d.toString(), points, zones, periods.sortedBy { it.start }, rhr[d])
    }

    suspend fun stepsCurve(d: LocalDate): StepsCurve {
        val slots = stepSlots(d.minusDays(Derived.BASELINE_DAYS.toLong()), d)
        val history = slots.filterKeys { it < d }.values.map { Derived.cumulative(it.toList()) }
        val todayCum = Derived.cumulative((slots[d] ?: DoubleArray(SLOTS)).toList())
        val cut = cutSlot(d)
        return StepsCurve(todayCum.mapIndexed { i, v -> if (i <= cut) v else null }, Derived.medianCurve(history), history.size, SLOT_MIN)
    }

    suspend fun lastSynced(): String? = db.kv().get("last_sync_ms")?.toLongOrNull()?.let { iso(it) }

    suspend fun todayModel(): Today {
        val p = prefs.get()
        val d = today()
        val age = prefs.age(p, d.year)
        val tiles =
            listOf(
                readinessTile(d, p),
                dailyTile("sleep_main_min", d, fallbackDays = 1, label = "Last night's sleep", goal = p.goals.sleepMin.toDouble()),
                dailyTile("resting_hr", d, fallbackDays = 2),
                dailyTile("hrv_rmssd", d, fallbackDays = 2, label = "HRV"),
                stepsTile(d, p.goals.steps),
                azmTile(d, p.goals.azmWeekly, age),
            )
        val s = summary(d, p)
        return Today(
            date = d.toString(),
            generatedAt = now().toString(),
            lastSynced = lastSynced(),
            goals = ApiGoals(p.goals.sleepMin, p.goals.steps, p.goals.azmWeekly),
            tiles = tiles,
            heartRate = intradayHeartRate(d, age),
            stepsCurve = stepsCurve(d),
            summary = s,
        )
    }

    // ---- summary facts ---------------------------------------------------------------------

    private suspend fun reading(
        metric: String,
        d: LocalDate,
    ): Summary.Reading {
        val v = values(metric, d.minusDays(40), d)
        val b = Derived.baselineAt(v, d)
        val bp = Derived.baselineAt(v, d.minusDays(1))
        return Summary.Reading(v[d], b?.median, Derived.status(v[d], b), Derived.status(v[d.minusDays(1)], bp))
    }

    suspend fun summaryFacts(
        d: LocalDate,
        p: UserPrefs,
        extra: List<Summary.Sentence> = emptyList(),
    ): Summary.Facts {
        val isToday = d == today()
        val r = readinessParts(d, p)
        val stored = values("readiness", d.minusDays(30), d)
        val rb = Derived.baselineAt(stored, d)
        val sleepMain = values("sleep_main_min", d.minusDays(10), d)
        val bed = values("bedtime_min", d.minusDays(15), d)
        val usualBed = Derived.trailing(bed, d, Derived.CONSISTENCY_DAYS, includeDay = false).filterNotNull().map { Derived.clockWrap(it) }
        val steps =
            if (isToday) {
                stepsTile(d, p.goals.steps).let { Summary.Reading(it.value, it.baseline?.median, Status.valueOf(it.status.name.uppercase())) }
            } else {
                Summary.Reading(values("steps", d, d)[d])
            }
        val azm = values("azm", d.minusDays(7), d)
        val rec = records(d, p)
        val metNow =
            mapOf(
                "steps" to ((steps.value ?: 0.0) >= p.goals.steps),
                "sleep" to ((sleepMain[d] ?: 0.0) >= p.goals.sleepMin),
                "azm" to ((Derived.weekToDate(azm, d) ?: 0.0) >= p.goals.azmWeekly),
            )
        val recent = if (isToday) setOf(d, d.minusDays(1)) else setOf(d)
        val tags = db.journal().tags().associateBy { it.key }
        val eveningBefore = db.journal().dayTags(d.minusDays(1).toEpochDay()).mapNotNull { k -> tags[k]?.takeIf { it.kind == "evening" }?.label }
        return Summary.Facts(
            date = d,
            isToday = isToday,
            imperial = p.units == "imperial",
            sleepGoalMin = p.goals.sleepMin.toDouble(),
            stepsGoal = p.goals.steps.toDouble(),
            azmGoal = p.goals.azmWeekly.toDouble(),
            readiness = Summary.Reading(r.score, rb?.median, Derived.status(r.score, rb)),
            parts = r.components.map { Summary.Part(it.key, it.score, it.weight) },
            sleepMainMin = sleepMain[d],
            sleepDebtMin = Derived.sleepDebt(sleepMain, d, p.goals.sleepMin.toDouble()),
            bedtimeMin = bed[d],
            bedtimeUsualMin = if (usualBed.size >= 5) Derived.median(usualBed) else null,
            vitals = listOf("resting_hr", "hrv_rmssd", "spo2_avg", "resp_rate").associateWith { reading(it, d) } + ("skin_temp_delta" to Summary.Reading(values("skin_temp_delta", d, d)[d])),
            steps = steps,
            azmWeek = Derived.weekToDate(azm, d),
            daysLeftInWeek = 7 - d.dayOfWeek.value,
            loadRatio = values("load_ratio", d, d)[d],
            streaks = rec.streaks.map { Summary.StreakFact(it.key, it.current, metNow[it.key] ?: false, it.goal) },
            records = rec.bests.filter { it.key in RECORD_LABELS && it.date in recent }.map { Summary.RecordFact(it.key, RECORD_LABELS.getValue(it.key), it.value, it.unit, it.date) },
            eveningTagsBefore = eveningBefore,
            extra = extra,
        )
    }

    suspend fun summary(
        d: LocalDate,
        p: UserPrefs,
    ): ApiSummary {
        val out = Summary.build(summaryFacts(d, p, Premium.sentences(this, d, p)))
        return ApiSummary(
            d.toString(),
            out.headline,
            out.sentences.map { SummarySentence(it.text, SummarySentence.Tone.valueOf(it.tone.name.lowercase()), it.metrics) },
            now().toString(),
        )
    }

    // ---- records & streaks -----------------------------------------------------------------

    data class RecordRow(val key: String, val label: String, val unit: String, val value: Double, val date: LocalDate, val note: String? = null)

    data class StreakRow(val key: String, val label: String, val period: String, val goal: Double, val current: Int, val longest: Int, val longestEnd: LocalDate?)

    data class Records(val bests: List<RecordRow>, val streaks: List<StreakRow>)

    private val RECORD_LABELS =
        mapOf(
            "steps" to "most steps in a day",
            "distance_km" to "longest distance in a day",
            "azm" to "most active zone minutes in a day",
            "sleep_main_min" to "longest main sleep",
            "hrv_rmssd" to "highest HRV",
            "readiness" to "highest readiness",
        )

    suspend fun all(metric: String): Series = db.metrics().all(metric).associate { LocalDate.ofEpochDay(it.day) to it.value }

    suspend fun records(
        today: LocalDate,
        p: UserPrefs,
    ): Records {
        val defs =
            listOf(
                Triple("steps", "Most steps in a day", "steps"),
                Triple("distance_km", "Longest distance in a day", "km"),
                Triple("azm", "Most active zone minutes in a day", "min"),
                Triple("sleep_main_min", "Longest main sleep", "min"),
                Triple("hrv_rmssd", "Highest HRV", "ms"),
                Triple("readiness", "Highest readiness", "score"),
            )
        val bests =
            defs.mapNotNull { (k, label, unit) -> Derived.best(all(k))?.let { RecordRow(k, label, unit, it.value, it.date) } }.toMutableList()
        Derived.best(Derived.rollingMean(all("resting_hr")), lowest = true)?.let {
            bests += RecordRow("resting_hr", "Lowest resting HR", "bpm", Math.round(it.value * 10) / 10.0, it.date, "7-day average")
        }
        val weekly = Derived.weeklyTotals(all("azm"))
        Derived.best(weekly)?.let { bests += RecordRow("azm_week", "Most active zone minutes in a week", "min", it.value, it.date, "Week starting on this Monday") }

        suspend fun daily(
            key: String,
            label: String,
            metric: String,
            goal: Double,
            unit: String,
        ): StreakRow {
            val st = Derived.streak(all(metric).mapValues { it.value >= goal }, today)
            return StreakRow(key, label, "day", goal, st.current, st.longest, st.longestEnd)
        }
        val wk = Derived.streak(weekly.mapValues { it.value >= p.goals.azmWeekly }, Derived.weekStart(today), 7)
        return Records(
            bests,
            listOf(
                daily("steps", "Step goal", "steps", p.goals.steps.toDouble(), "steps"),
                daily("sleep", "Sleep goal", "sleep_main_min", p.goals.sleepMin.toDouble(), "min"),
                StreakRow("azm", "Weekly AZM goal", "week", p.goals.azmWeekly.toDouble(), wk.current, wk.longest, wk.longestEnd),
            ),
        )
    }

    // ---- sleep -------------------------------------------------------------------------

    suspend fun sleepNight(date: LocalDate?): SleepNight {
        val p = prefs.get()
        val day = date ?: db.sleep().latest()?.let { LocalDate.ofEpochDay(it) } ?: today()
        val sessions = db.sleep().night(day.toEpochDay())
        val main = sessions.firstOrNull { it.isMain } ?: sessions.maxByOrNull { it.asleepMin }
        suspend fun out(
            s: dev.pulse.app.db.SleepSession,
            withStages: Boolean,
        ): SleepSessionOut {
            val stages = if (withStages) db.sleep().stages(s.id).map { SleepStageOut(it.stage, iso(it.start), iso(it.end)) } else emptyList()
            val inBed = (s.end - s.start) / 60000.0
            return SleepSessionOut(
                id = s.id, date = day.toString(), start = iso(s.start), end = iso(s.end), isMain = s.isMain, sleepType = "stages",
                minutesInBed = inBed, minutesAsleep = s.asleepMin, minutesAwake = s.awakeMin, minutesToFallAsleep = s.latencyMin,
                deepMin = s.deepMin, lightMin = s.lightMin, remMin = s.remMin, awakeMin = s.awakeMin,
                efficiency = if (inBed > 0) s.asleepMin * 100.0 / inBed else null, stages = stages,
            )
        }
        val hr = main?.let { db.intraday().hr(it.start, it.end) }.orEmpty()
        val dayM = db.metrics().day(day.toEpochDay()).associate { it.metric to it.value }
        return SleepNight(
            date = day.toString(),
            goalMin = p.goals.sleepMin,
            session = main?.let { out(it, true) },
            naps = sessions.filter { it !== main }.map { out(it, false) },
            sleepingHr = if (hr.isNotEmpty()) SleepingHeartRate(Math.round(hr.map { it.avg }.average() * 10) / 10.0, hr.minOf { it.min }.toInt()) else null,
            spo2 = dayM["spo2_avg"]?.let { Spo2(it, dayM["spo2_low"], dayM["spo2_high"]) },
            skinTempDelta = dayM["skin_temp_delta"],
            hrvRmssd = dayM["hrv_rmssd"],
            restingHr = dayM["resting_hr"],
            prevDate = db.sleep().prev(day.toEpochDay())?.let { LocalDate.ofEpochDay(it).toString() },
            nextDate = db.sleep().next(day.toEpochDay())?.let { LocalDate.ofEpochDay(it).toString() },
        )
    }

    // ---- journal ---------------------------------------------------------------------------

    suspend fun ensureDefaultTags() {
        if (db.journal().tags().isEmpty()) db.journal().upsertTags(PulseDb.DEFAULT_TAGS)
    }

    suspend fun tags(): List<TagOut> {
        ensureDefaultTags()
        val usage = db.journal().usage().associateBy { it.metric }
        return db.journal().tags().map {
            TagOut(
                it.key, it.label, if (it.kind == "evening") TagOut.Kind.evening else TagOut.Kind.day, it.archived,
                usage[it.key]?.n ?: 0, usage[it.key]?.lastDay?.let { d -> LocalDate.ofEpochDay(d).toString() },
            )
        }
    }

    suspend fun journal(date: LocalDate): Journal =
        Journal(date.toString(), db.journal().dayTags(date.toEpochDay()), db.journal().note(date.toEpochDay())?.text.orEmpty())

    suspend fun putJournal(
        date: LocalDate,
        tags: List<String>,
        note: String,
    ): Journal {
        require(date <= today()) { "can't write a journal for a future day" }
        require(note.length <= 2000) { "note is limited to 2000 characters" }
        db.journal().replaceDay(date.toEpochDay(), tags.distinct(), note)
        return journal(date)
    }

    suspend fun upsertTag(t: Tag) = db.journal().upsertTags(listOf(t))

    // ---- charts ------------------------------------------------------------------------

    /** Daily points for [days] days ending today, with the rolling 28-day usual range. */
    suspend fun chart(
        metric: String,
        days: Int,
        band: Boolean = true,
    ): List<dev.pulse.app.ui.charts.Pt> {
        val end = today()
        val start = end.minusDays(days - 1L)
        val v = values(metric, start.minusDays(Derived.BASELINE_DAYS.toLong()), end)
        return (0 until days).map { i ->
            val d = start.plusDays(i.toLong())
            val b = if (band) Derived.baselineAt(v, d) else null
            dev.pulse.app.ui.charts.Pt(d, v[d], b?.q1, b?.q3)
        }
    }

    suspend fun available(): Map<String, dev.pulse.app.db.MetricSpan> = db.metrics().available().associateBy { it.metric }

    // ---- widget ------------------------------------------------------------------------

    suspend fun widget(): WidgetSnapshot {
        val p = prefs.get()
        val d = today()
        val r = dailyTile("readiness", d, fallbackDays = 1)
        val dir = if ((r.delta ?: 0.0) > 0) "above" else "below"
        val label =
            when (r.status) {
                Tile.Status.in_range -> "a typical day for you"
                Tile.Status.mild -> "a bit $dir your usual"
                Tile.Status.notable -> "well $dir your usual"
                Tile.Status.none -> "not enough data yet"
            }
        val steps = stepsTile(d, p.goals.steps)
        val sleep = values("sleep_main_min", d.minusDays(1), d)
        return WidgetSnapshot(
            date = d.toString(),
            generatedAt = now().toString(),
            readiness = WidgetReadiness(r.value, WidgetReadiness.Status.valueOf(r.status.name), label),
            steps = steps.value,
            stepsGoal = p.goals.steps,
            stepsStatus = WidgetSnapshot.StepsStatus.valueOf(steps.status.name),
            sleepMainMin = sleep[d] ?: sleep[d.minusDays(1)],
            sleepGoalMin = p.goals.sleepMin,
            azmWeek = Derived.weekToDate(values("azm", d.minusDays(7), d), d),
            azmGoal = p.goals.azmWeekly,
            lastSynced = lastSynced(),
            authOk = true,
        )
    }
}
