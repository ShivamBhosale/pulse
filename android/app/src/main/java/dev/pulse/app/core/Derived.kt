package dev.pulse.app.core

import java.time.DayOfWeek
import java.time.LocalDate
import kotlin.math.abs
import kotlin.math.sqrt

/**
 * Pure derived-metric maths, ported one-to-one from the server's `src/pulse/derived.py`
 * (tests use the same cases as tests/test_derived.py). No I/O.
 */
typealias Series = Map<LocalDate, Double>

enum class Status(val key: String) { IN_RANGE("in_range"), MILD("mild"), NOTABLE("notable"), NONE("none") }

data class Baseline(val median: Double, val q1: Double, val q3: Double, val n: Int) {
    val iqr: Double get() = q3 - q1
}

object Derived {
    const val BASELINE_DAYS = 28
    const val MIN_BASELINE_POINTS = 7
    const val STRAIN_REST_CAP = 70.0
    const val CONSISTENCY_DAYS = 14
    const val CONSISTENCY_MIN_NIGHTS = 5
    const val DEBT_NIGHTS = 7
    const val ACUTE_DAYS = 7
    const val CHRONIC_DAYS = 28
    const val CHRONIC_MIN_POINTS = 21
    val DEFAULT_WEIGHTS = mapOf("hrv" to 35.0, "rhr" to 25.0, "sleep" to 25.0, "strain" to 15.0)

    // ---- statistics (Python statistics module semantics) ----------------------------------

    fun median(values: List<Double>): Double {
        val v = values.sorted()
        val m = v.size / 2
        return if (v.size % 2 == 1) v[m] else (v[m - 1] + v[m]) / 2.0
    }

    /** statistics.quantiles(method="inclusive") at fraction p of a sorted list. */
    fun quantileInclusive(
        sorted: List<Double>,
        p: Double,
    ): Double {
        val pos = (sorted.size - 1) * p
        val lo = pos.toInt()
        val frac = pos - lo
        return if (lo + 1 < sorted.size) sorted[lo] + (sorted[lo + 1] - sorted[lo]) * frac else sorted[lo]
    }

    fun pstdev(values: List<Double>): Double {
        val m = values.average()
        return sqrt(values.sumOf { (it - m) * (it - m) } / values.size)
    }

    fun stdev(values: List<Double?>): Double? {
        val v = values.filterNotNull()
        return if (v.size >= 2) pstdev(v) else null
    }

    // ---- baselines -----------------------------------------------------------------------

    fun baseline(
        values: List<Double?>,
        minPoints: Int = MIN_BASELINE_POINTS,
    ): Baseline? {
        val v = values.filterNotNull().sorted()
        if (v.size < minPoints) return null
        return Baseline(
            median = quantileInclusive(v, 0.5),
            q1 = quantileInclusive(v, 0.25),
            q3 = quantileInclusive(v, 0.75),
            n = v.size,
        )
    }

    fun status(
        value: Double?,
        b: Baseline?,
    ): Status {
        if (value == null || b == null) return Status.NONE
        if (value in b.q1..b.q3) return Status.IN_RANGE
        if (abs(value - b.median) > 1.5 * b.iqr) return Status.NOTABLE
        return Status.MILD
    }

    fun delta(
        value: Double?,
        b: Baseline?,
    ): Double? = if (value == null || b == null) null else value - b.median

    fun trailing(
        values: Series,
        d: LocalDate,
        days: Int,
        includeDay: Boolean,
    ): List<Double?> {
        val first = if (includeDay) 0L else 1L
        return (first until first + days).map { values[d.minusDays(it)] }
    }

    fun baselineAt(
        values: Series,
        d: LocalDate,
        days: Int = BASELINE_DAYS,
    ): Baseline? = baseline(trailing(values, d, days, includeDay = false))

    fun cumulative(slots: List<Double>): List<Double> {
        var t = 0.0
        return slots.map {
            t += it
            t
        }
    }

    fun medianCurve(curves: List<List<Double>>): List<Double> {
        if (curves.isEmpty()) return emptyList()
        return curves[0].indices.map { i -> median(curves.map { it[i] }) }
    }

    // ---- readiness -----------------------------------------------------------------------

    fun robustScore(
        value: Double,
        b: Baseline,
        invert: Boolean = false,
    ): Double {
        val spread = maxOf(1.5 * b.iqr, 0.05 * abs(b.median), 1.0)
        val z = ((value - b.median) / spread).coerceIn(-1.0, 1.0)
        return 50.0 + 50.0 * (if (invert) -z else z)
    }

    data class Component(
        val key: String,
        val score: Double?,
        val weight: Double,
        val value: Double?,
        val reference: Double?,
    )

    data class Readiness(val score: Double?, val components: List<Component>)

    const val READINESS_FORMULA =
        "Personal heuristic, not a medical measure. Weighted mean of four 0-100 parts: " +
            "HRV vs your 28-day median (higher is better), resting HR vs your 28-day median " +
            "(lower is better), last night's main sleep vs your goal (capped at 100), and yesterday's " +
            "strain vs your 28-day median (lower scores higher, capped at 70). HRV and resting HR " +
            "score 50 at your median and reach 0 or 100 at 1.5 x IQR away. Missing parts are left " +
            "out and the remaining weights rescaled; at least two parts, including HRV or sleep, " +
            "are needed."

    fun readiness(
        d: LocalDate,
        hrv: Series,
        rhr: Series,
        sleepMain: Series,
        strain: Series,
        sleepGoalMin: Double,
        weights: Map<String, Double> = DEFAULT_WEIGHTS,
    ): Readiness {
        data class Part(val score: Double?, val value: Double?, val ref: Double?)
        val parts = linkedMapOf<String, Part>()

        fun vsBaseline(
            key: String,
            series: Series,
            day: LocalDate,
            invert: Boolean,
        ) {
            val v = series[day]
            val b = baselineAt(series, day)
            parts[key] = Part(if (v != null && b != null) robustScore(v, b, invert) else null, v, b?.median)
        }
        vsBaseline("hrv", hrv, d, false)
        vsBaseline("rhr", rhr, d, true)
        val s = sleepMain[d]
        parts["sleep"] = Part(if (s != null && sleepGoalMin > 0) minOf(100.0, s / sleepGoalMin * 100.0) else null, s, sleepGoalMin)
        vsBaseline("strain", strain, d.minusDays(1), true)
        parts["strain"]?.let { p -> if (p.score != null) parts["strain"] = p.copy(score = minOf(STRAIN_REST_CAP, p.score)) }

        val present = parts.filterValues { it.score != null }.keys
        val totalW = present.sumOf { maxOf(0.0, weights[it] ?: 0.0) }
        val enough = present.size >= 2 && (present.contains("hrv") || present.contains("sleep")) && totalW > 0
        val comps =
            parts.map { (k, p) ->
                Component(
                    key = k,
                    score = p.score?.let { round1(it) },
                    weight = if (enough && k in present) maxOf(0.0, weights[k] ?: 0.0) / totalW else 0.0,
                    value = p.value,
                    reference = p.ref,
                )
            }
        if (!enough) return Readiness(null, comps)
        return Readiness(round1(comps.sumOf { (it.score ?: 0.0) * it.weight }), comps)
    }

    // ---- sleep, load, weekly ---------------------------------------------------------------

    fun sleepDebt(
        sleepMain: Series,
        d: LocalDate,
        goalMin: Double,
    ): Double? {
        val nights = trailing(sleepMain, d, DEBT_NIGHTS, includeDay = true).filterNotNull()
        return if (nights.isEmpty()) null else nights.sumOf { maxOf(0.0, goalMin - it) }
    }

    fun clockWrap(minutes: Double): Double = ((minutes + 360) % 1440 + 1440) % 1440 - 360

    fun consistencySd(
        times: Series,
        d: LocalDate,
    ): Double? {
        val v = trailing(times, d, CONSISTENCY_DAYS, includeDay = true).filterNotNull().map { clockWrap(it) }
        return if (v.size >= CONSISTENCY_MIN_NIGHTS) pstdev(v) else null
    }

    fun loadRatio(
        strain: Series,
        d: LocalDate,
    ): Double? {
        val chronicVals = trailing(strain, d, CHRONIC_DAYS, includeDay = true)
        if (chronicVals.count { it != null } < CHRONIC_MIN_POINTS) return null
        val chronic = chronicVals.sumOf { it ?: 0.0 } / CHRONIC_DAYS
        val acute = trailing(strain, d, ACUTE_DAYS, includeDay = true).sumOf { it ?: 0.0 } / ACUTE_DAYS
        return if (chronic > 0) acute / chronic else null
    }

    fun weekStart(d: LocalDate): LocalDate = d.minusDays((d.dayOfWeek.value - DayOfWeek.MONDAY.value).toLong())

    fun weekToDate(
        values: Series,
        d: LocalDate,
    ): Double? {
        val present = (0..(d.dayOfWeek.value - 1)).mapNotNull { values[weekStart(d).plusDays(it.toLong())] }
        return if (present.isEmpty()) null else present.sum()
    }

    fun weeklyTotals(values: Series): Map<LocalDate, Double> {
        val out = sortedMapOf<LocalDate, Double>()
        values.forEach { (d, v) -> out[weekStart(d)] = (out[weekStart(d)] ?: 0.0) + v }
        return out
    }

    // ---- records & streaks -----------------------------------------------------------------

    data class Best(val value: Double, val date: LocalDate)

    fun best(
        values: Series,
        lowest: Boolean = false,
    ): Best? {
        if (values.isEmpty()) return null
        val d =
            if (lowest) {
                values.keys.minWith(compareBy<LocalDate>({ values[it]!! }, { it }))
            } else {
                values.keys.maxWith(compareBy<LocalDate>({ values[it]!! }, { -it.toEpochDay() }))
            }
        return Best(values[d]!!, d)
    }

    fun rollingMean(
        values: Series,
        days: Int = 7,
        minPoints: Int = 5,
    ): Map<LocalDate, Double> =
        values.keys
            .mapNotNull { d ->
                val w = trailing(values, d, days, includeDay = true).filterNotNull()
                if (w.size >= minPoints) d to w.average() else null
            }.toMap()

    data class Streak(val current: Int, val currentStart: LocalDate?, val longest: Int, val longestEnd: LocalDate?)

    fun streak(
        hits: Map<LocalDate, Boolean>,
        currentPeriod: LocalDate,
        stepDays: Long = 1,
    ): Streak {
        if (hits.isEmpty()) return Streak(0, null, 0, null)
        var longest = 0
        var longestEnd: LocalDate? = null
        var run = 0
        var runStart: LocalDate? = null
        var p = hits.keys.min()
        while (p < currentPeriod) {
            if (hits[p] == true) {
                if (run == 0) runStart = p
                run++
                if (run > longest) {
                    longest = run
                    longestEnd = p
                }
            } else {
                run = 0
                runStart = null
            }
            p = p.plusDays(stepDays)
        }
        if (hits[currentPeriod] == true) {
            if (run == 0) runStart = currentPeriod
            run++
            if (run > longest) {
                longest = run
                longestEnd = currentPeriod
            }
        }
        return Streak(run, if (run > 0) runStart else null, longest, longestEnd)
    }

    fun pearson(
        xs: List<Double>,
        ys: List<Double>,
    ): Double? {
        if (xs.size != ys.size || xs.size < 3) return null
        val mx = xs.average()
        val my = ys.average()
        val sxx = xs.sumOf { (it - mx) * (it - mx) }
        val syy = ys.sumOf { (it - my) * (it - my) }
        if (sxx == 0.0 || syy == 0.0) return null
        return xs.indices.sumOf { (xs[it] - mx) * (ys[it] - my) } / sqrt(sxx * syy)
    }

    fun correlationStrength(r: Double?): String {
        if (r == null) return "not enough data"
        val a = abs(r)
        val word = if (a < 0.1) "negligible" else if (a < 0.3) "weak" else if (a < 0.5) "moderate" else "strong"
        return if (word == "negligible") word else "$word ${if (r > 0) "positive" else "negative"}"
    }

    fun timeInZones(
        bpms: List<Double>,
        bounds: Map<String, Pair<Int, Int>>,
    ): Map<String, Int> {
        val out = bounds.keys.associateWith { 0 }.toMutableMap()
        out["below"] = 0
        val ordered = bounds.entries.sortedByDescending { it.value.first }
        bpms.forEach { bpm ->
            val z = ordered.firstOrNull { bpm >= it.value.first }?.key ?: "below"
            out[z] = out.getValue(z) + 1
        }
        return out
    }

    private fun round1(v: Double) = Math.round(v * 10.0) / 10.0
}
