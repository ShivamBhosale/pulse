package dev.pulse.app.hc

import androidx.health.connect.client.records.ExerciseSessionRecord
import dev.pulse.app.db.DailyMetric
import dev.pulse.app.db.Exercise
import dev.pulse.app.db.SleepSession
import dev.pulse.app.db.SleepStage
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/** Pure mapping from Health Connect data to Pulse rows (unit-tested without a phone). */
object HcMapping {
    data class SleepOut(
        val sessions: List<SleepSession>,
        val stages: List<SleepStage>,
        val metrics: List<DailyMetric>,
    )

    private fun minutes(
        a: Instant,
        b: Instant,
    ) = Duration.between(a, b).toMinutes().toInt().coerceAtLeast(0)

    /** Overlapping sessions from several apps: keep the preferred source (Fitbit first). */
    fun dedupeSleep(all: List<HcSleep>): List<HcSleep> {
        val kept = mutableListOf<HcSleep>()
        for (s in all.sortedWith(compareBy({ Hc.priority(it.source) }, { it.start }))) {
            val overlaps =
                kept.any { k ->
                    val lo = maxOf(k.start, s.start)
                    val hi = minOf(k.end, s.end)
                    val shorter = minOf(Duration.between(k.start, k.end), Duration.between(s.start, s.end))
                    hi > lo && !shorter.isZero && Duration.between(lo, hi).toMillis() > shorter.toMillis() / 2
                }
            if (!overlaps) kept += s
        }
        return kept.sortedBy { it.start }
    }

    fun sleep(
        raw: List<HcSleep>,
        zone: ZoneId,
    ): SleepOut {
        val sessions = mutableListOf<SleepSession>()
        val stages = mutableListOf<SleepStage>()
        val byDay = dedupeSleep(raw).groupBy { HealthConnectSource.localDay(it.end, zone) }
        val metrics = mutableListOf<DailyMetric>()
        for ((day, list) in byDay) {
            val main = list.maxBy { Duration.between(it.start, it.end) }
            var total = 0
            for (s in list) {
                val asleepStages = s.stages.filter { it.stage != "AWAKE" }
                val hasStages = s.stages.isNotEmpty()
                val asleep = if (hasStages) asleepStages.sumOf { minutes(it.start, it.end) } else minutes(s.start, s.end)
                val awake = s.stages.filter { it.stage == "AWAKE" }.sumOf { minutes(it.start, it.end) }
                fun stageMin(name: String) = if (hasStages) s.stages.filter { it.stage == name }.sumOf { minutes(it.start, it.end) } else null
                val firstSleep = asleepStages.minOfOrNull { it.start } ?: s.start
                val lastSleep = asleepStages.maxOfOrNull { it.end } ?: s.end
                val interruptions =
                    s.stages.count { it.stage == "AWAKE" && it.start > firstSleep && it.end < lastSleep && minutes(it.start, it.end) >= 5 }
                total += asleep
                sessions +=
                    SleepSession(
                        id = s.id,
                        day = day.toEpochDay(),
                        start = s.start.toEpochMilli(),
                        end = s.end.toEpochMilli(),
                        isMain = s === main,
                        asleepMin = asleep,
                        awakeMin = awake,
                        deepMin = stageMin("DEEP"),
                        lightMin = stageMin("LIGHT"),
                        remMin = stageMin("REM"),
                        latencyMin = minutes(s.start, firstSleep),
                        interruptions = interruptions,
                        source = s.source,
                    )
                s.stages.forEach { st -> stages += SleepStage(0, s.id, st.stage, st.start.toEpochMilli(), st.end.toEpochMilli()) }
            }
            val m = sessions.last { it.id == main.id }
            val inBed = minutes(main.start, main.end)
            val midnight = day.atStartOfDay(zone).toInstant()
            fun put(
                k: String,
                v: Double?,
                unit: String = "min",
            ) {
                if (v != null) metrics += DailyMetric(day.toEpochDay(), k, v, unit)
            }
            put("sleep_min", total.toDouble())
            put("sleep_main_min", m.asleepMin.toDouble())
            put("sleep_in_bed_min", inBed.toDouble())
            put("sleep_efficiency", if (inBed > 0) m.asleepMin * 100.0 / inBed else null, "%")
            put("sleep_deep_min", m.deepMin?.toDouble())
            put("sleep_light_min", m.lightMin?.toDouble())
            put("sleep_rem_min", m.remMin?.toDouble())
            put("sleep_awake_min", m.awakeMin.toDouble())
            put("bedtime_min", Duration.between(midnight, main.start).toMinutes().toDouble())
            put("waketime_min", Duration.between(midnight, main.end).toMinutes().toDouble())
        }
        return SleepOut(sessions, stages, metrics)
    }

    /**
     * Nightly samples (HRV, breathing rate, SpO₂, skin temperature) belong to the night's wake
     * date: a sample inside a sleep session (±1 h) takes that session's wake day; anything else
     * takes its own local date. Within a day, only the preferred source counts.
     */
    fun nightly(
        samples: List<HcSample>,
        sleeps: List<SleepSession>,
        zone: ZoneId,
    ): Map<LocalDate, List<Double>> {
        val pad = Duration.ofHours(1).toMillis()
        val byDay =
            samples.groupBy { s ->
                val t = s.time.toEpochMilli()
                sleeps.firstOrNull { t >= it.start - pad && t <= it.end + pad }?.let { LocalDate.ofEpochDay(it.day) }
                    ?: HealthConnectSource.localDay(s.time, zone)
            }
        return byDay.mapValues { (_, list) ->
            val best = list.minOf { Hc.priority(it.source) }
            list.filter { Hc.priority(it.source) == best }.map { it.value }
        }
    }

    fun exerciseName(type: Int): String =
        when (type) {
            ExerciseSessionRecord.EXERCISE_TYPE_WALKING -> "WALKING"
            ExerciseSessionRecord.EXERCISE_TYPE_RUNNING, ExerciseSessionRecord.EXERCISE_TYPE_RUNNING_TREADMILL -> "RUNNING"
            ExerciseSessionRecord.EXERCISE_TYPE_BIKING, ExerciseSessionRecord.EXERCISE_TYPE_BIKING_STATIONARY -> "BIKING"
            ExerciseSessionRecord.EXERCISE_TYPE_STRENGTH_TRAINING, ExerciseSessionRecord.EXERCISE_TYPE_WEIGHTLIFTING -> "STRENGTH_TRAINING"
            ExerciseSessionRecord.EXERCISE_TYPE_HIKING -> "HIKING"
            ExerciseSessionRecord.EXERCISE_TYPE_SWIMMING_POOL, ExerciseSessionRecord.EXERCISE_TYPE_SWIMMING_OPEN_WATER -> "SWIMMING"
            ExerciseSessionRecord.EXERCISE_TYPE_YOGA -> "YOGA"
            ExerciseSessionRecord.EXERCISE_TYPE_HIGH_INTENSITY_INTERVAL_TRAINING -> "HIIT"
            ExerciseSessionRecord.EXERCISE_TYPE_ELLIPTICAL -> "ELLIPTICAL"
            ExerciseSessionRecord.EXERCISE_TYPE_TENNIS, ExerciseSessionRecord.EXERCISE_TYPE_BADMINTON,
            ExerciseSessionRecord.EXERCISE_TYPE_SQUASH, ExerciseSessionRecord.EXERCISE_TYPE_TABLE_TENNIS,
            -> "RACKET_SPORTS"
            else -> "WORKOUT"
        }

    /** Same workout from the band and another app: keep the preferred source. */
    fun exercises(
        raw: List<HcExercise>,
        zone: ZoneId,
    ): List<Exercise> {
        val kept = mutableListOf<HcExercise>()
        for (e in raw.sortedWith(compareBy({ Hc.priority(it.source) }, { it.start }))) {
            val dup =
                kept.any { k ->
                    val lo = maxOf(k.start, e.start)
                    val hi = minOf(k.end, e.end)
                    val shorter = minOf(Duration.between(k.start, k.end), Duration.between(e.start, e.end))
                    hi > lo && !shorter.isZero && Duration.between(lo, hi).toMillis() > shorter.toMillis() / 2
                }
            if (!dup) kept += e
        }
        return kept.map {
            Exercise(
                id = it.id,
                day = HealthConnectSource.localDay(it.start, zone).toEpochDay(),
                start = it.start.toEpochMilli(),
                end = it.end.toEpochMilli(),
                type = exerciseName(it.type),
                title = it.title,
                source = it.source,
            )
        }
    }
}
