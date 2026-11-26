package dev.pulse.app.core.premium

import dev.pulse.app.core.Baseline
import dev.pulse.app.core.Derived
import dev.pulse.app.core.Status
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.roundToInt

/**
 * Pulse's own premium-style scores. Pure functions with documented, deliberately simple formulas,
 * so every number can be explained in a "How it's calculated" sheet. Personal estimates, not
 * medical advice.
 */

private fun lerp01(
    value: Double,
    full: Double,
    zero: Double,
): Double {
    // 1.0 at `full`, 0.0 at `zero`, linear between (works for either direction).
    if (full == zero) return if (value == full) 1.0 else 0.0
    return ((value - zero) / (full - zero)).coerceIn(0.0, 1.0)
}

/** 1.0 inside [lo, hi]; falls to 0 at `slack` outside the range. */
private fun inRange(
    v: Double,
    lo: Double,
    hi: Double,
    slack: Double,
): Double =
    when {
        v < lo -> lerp01(v, lo, lo - slack)
        v > hi -> lerp01(v, hi, hi + slack)
        else -> 1.0
    }

// ---- sleep score ------------------------------------------------------------------------------

data class SleepScore(
    val total: Int,
    val duration: Double, // of 50
    val quality: Double, // of 25
    val restoration: Double, // of 25
    val label: String,
)

object SleepScoring {
    const val FORMULA =
        "Sleep score (0-100), a personal estimate. Duration, 50 points: time asleep vs tonight's sleep need. " +
            "Quality, 25 points: deep sleep within 13-23 % and REM within 18-28 % of sleep (typical adult ranges), " +
            "fading to 0 ten points outside. Restoration, 25 points: average sleeping heart rate at or below your " +
            "resting HR (10), awake time under 20 min (8) and at most 2 interruptions of 5+ min (7), fading to 0 at " +
            "15 % above resting HR, 60 min awake and 8 interruptions. 90+ Excellent, 80-89 Good, 60-79 Fair, under 60 Poor."

    fun label(score: Int) =
        when {
            score >= 90 -> "Excellent"
            score >= 80 -> "Good"
            score >= 60 -> "Fair"
            else -> "Poor"
        }

    fun score(
        asleepMin: Double,
        needMin: Double,
        deepMin: Double?,
        remMin: Double?,
        sleepingHrAvg: Double?,
        restingHr: Double?,
        awakeMin: Double,
        interruptions: Int,
    ): SleepScore {
        val duration = 50.0 * (asleepMin / needMin).coerceIn(0.0, 1.0)
        val quality =
            if (deepMin != null && remMin != null && asleepMin > 0) {
                12.5 * inRange(deepMin / asleepMin * 100, 13.0, 23.0, 10.0) + 12.5 * inRange(remMin / asleepMin * 100, 18.0, 28.0, 10.0)
            } else {
                12.5 // no stage data: neutral half credit
            }
        val hr =
            if (sleepingHrAvg != null && restingHr != null && restingHr > 0) {
                10.0 * lerp01(sleepingHrAvg / restingHr, 1.0, 1.15)
            } else {
                5.0
            }
        val restoration = hr + 8.0 * lerp01(awakeMin, 20.0, 60.0) + 7.0 * lerp01(interruptions.toDouble(), 2.0, 8.0)
        val total = (duration + quality + restoration).roundToInt().coerceIn(0, 100)
        return SleepScore(total, duration, quality, restoration, label(total))
    }
}

// ---- sleep need, debt payback, bedtime ------------------------------------------------------

data class SleepNeed(
    val needMin: Double,
    val baseMin: Double,
    val paybackMin: Double,
    val strainMin: Double,
    val debtMin: Double,
    val nightsToClear: Int?,
)

object SleepNeeds {
    const val FORMULA =
        "Tonight's sleep need = your sleep goal + debt payback (one seventh of your 7-night sleep debt, at most " +
            "60 min) + 10 min when yesterday's activity load was well above your usual. The bedtime suggestion " +
            "works back from your typical wake time (14-night median) by tonight's need and your usual time to " +
            "fall asleep."

    fun need(
        goalMin: Double,
        debtMin: Double?,
        yesterdayStrain: Double?,
        strainBaseline: Baseline?,
    ): SleepNeed {
        val debt = debtMin ?: 0.0
        val payback = minOf(60.0, debt / 7.0)
        val hard =
            yesterdayStrain != null && strainBaseline != null &&
                yesterdayStrain > strainBaseline.median + 1.5 * maxOf(strainBaseline.iqr, 5.0)
        val strain = if (hard) 10.0 else 0.0
        val nights = if (debt <= 0) 0 else if (payback > 0) ceil(debt / maxOf(payback, 15.0)).toInt() else null
        return SleepNeed(goalMin + payback + strain, goalMin, payback, strain, debt, nights)
    }

    /** Minutes from midnight (may be negative = evening): asleep-by and in-bed-by. */
    data class Bedtime(val asleepBy: Double, val inBedBy: Double, val wakeTarget: Double)

    fun bedtime(
        recentWakeMin: List<Double>,
        recentLatencyMin: List<Double>,
        needMin: Double,
    ): Bedtime? {
        if (recentWakeMin.size < 5) return null
        val wake = Derived.median(recentWakeMin.map { Derived.clockWrap(it) })
        val latency = if (recentLatencyMin.isNotEmpty()) Derived.median(recentLatencyMin) else 10.0
        val asleep = wake - needMin
        return Bedtime(asleep, asleep - latency, wake)
    }
}

// ---- sleep profile (monthly) ----------------------------------------------------------------

data class SleepProfile(
    val nights: Int,
    val avgAsleepMin: Double,
    val bedtimeSdMin: Double?,
    val deepPct: Double?,
    val remPct: Double?,
    val interruptionsPerNight: Double,
    val midpointMin: Double,
    val chronotype: String,
)

object SleepProfiles {
    data class Night(val asleepMin: Double, val bedMin: Double, val wakeMin: Double, val deepMin: Double?, val remMin: Double?, val interruptions: Int)

    /** Chronotype from the median sleep midpoint: before 03:00 early, after 04:30 late. */
    fun chronotype(midpointMin: Double): String =
        when {
            midpointMin < 180 -> "Early"
            midpointMin <= 270 -> "Intermediate"
            else -> "Late"
        }

    fun profile(nights: List<Night>): SleepProfile? {
        if (nights.size < 7) return null
        val beds = nights.map { Derived.clockWrap(it.bedMin) }
        val wakes = nights.map { Derived.clockWrap(it.wakeMin) }
        val mid = Derived.median(beds.zip(wakes).map { (b, w) -> (b + w) / 2 })
        val staged = nights.filter { it.deepMin != null && it.remMin != null && it.asleepMin > 0 }
        return SleepProfile(
            nights = nights.size,
            avgAsleepMin = nights.map { it.asleepMin }.average(),
            bedtimeSdMin = Derived.pstdev(beds),
            deepPct = if (staged.isEmpty()) null else staged.map { it.deepMin!! / it.asleepMin * 100 }.average(),
            remPct = if (staged.isEmpty()) null else staged.map { it.remMin!! / it.asleepMin * 100 }.average(),
            interruptionsPerNight = nights.map { it.interruptions }.average(),
            midpointMin = mid,
            chronotype = chronotype(mid),
        )
    }
}

// ---- body signals ---------------------------------------------------------------------------

data class Signal(val key: String, val label: String, val value: Double, val usual: Double?, val direction: String)

object BodySignals {
    const val NOTE =
        "Shown when 3 or more of resting heart rate (up), HRV (down), breathing rate (up), skin temperature " +
            "(0.5 °C or more above baseline) and blood oxygen (down) are notably outside your usual range on the " +
            "same day. It can follow hard training, poor sleep, alcohol, stress or getting ill. It is not a diagnosis."

    data class In(val value: Double?, val baseline: Baseline?)

    /** Metrics notably off in the strain direction (each needs a meaningful absolute difference too). */
    fun unusual(
        rhr: In,
        hrv: In,
        resp: In,
        spo2: In,
        skinTempDelta: Double?,
    ): List<Signal> {
        val out = mutableListOf<Signal>()
        fun check(
            key: String,
            label: String,
            x: In,
            up: Boolean,
            minDiff: Double,
        ) {
            val v = x.value ?: return
            val b = x.baseline ?: return
            if (Derived.status(v, b) != Status.NOTABLE) return
            val d = v - b.median
            if ((d > 0) != up || abs(d) < minDiff) return
            out += Signal(key, label, v, b.median, if (up) "higher" else "lower")
        }
        check("resting_hr", "Resting heart rate", rhr, up = true, minDiff = 3.0)
        check("hrv_rmssd", "HRV", hrv, up = false, minDiff = 4.0)
        check("resp_rate", "Breathing rate", resp, up = true, minDiff = 0.8)
        check("spo2_avg", "Blood oxygen", spo2, up = false, minDiff = 1.5)
        if (skinTempDelta != null && skinTempDelta >= 0.5) out += Signal("skin_temp_delta", "Skin temperature", skinTempDelta, 0.0, "higher")
        return out
    }
}

// ---- stress -----------------------------------------------------------------------------------

data class Stress(val score: Int, val band: String, val parts: Map<String, Double>)

object StressScoring {
    const val FORMULA =
        "Body stress (0-100, higher = more strain on your body), a personal estimate. Weighted mix of: HRV below " +
            "your usual (30 %), resting HR above your usual (20 %), last night's sleep short of your need (20 %), " +
            "breathing rate above your usual (10 %) and how much of your waking day (07:00-22:00) your heart rate " +
            "was 20+ bpm above resting while you were barely moving (20 %). Each part is 50 at your usual and " +
            "0-100 at 1.5 x IQR either side; missing parts are left out. Under 35 Low, 35-65 Moderate, over 65 High."

    val WEIGHTS = mapOf("hrv" to 0.30, "rhr" to 0.20, "sleep" to 0.20, "resp" to 0.10, "daytime" to 0.20)

    fun band(score: Int) =
        when {
            score < 35 -> "Low"
            score <= 65 -> "Moderate"
            else -> "High"
        }

    /** Share of waking minutes with HR ≥ resting + 20 while the 15-min slot had < 100 steps. */
    fun elevatedStillShare(
        wakingMinutes: List<Pair<Double, Double>>, // (bpm, steps in that minute's 15-min slot)
        restingHr: Double,
    ): Double? {
        if (wakingMinutes.size < 120) return null
        val n = wakingMinutes.count { (bpm, steps) -> bpm >= restingHr + 20 && steps < 100 }
        return n.toDouble() / wakingMinutes.size
    }

    fun score(
        hrv: Pair<Double, Baseline>?,
        rhr: Pair<Double, Baseline>?,
        asleepMin: Double?,
        needMin: Double,
        resp: Pair<Double, Baseline>?,
        elevatedShare: Double?,
    ): Stress? {
        val parts = mutableMapOf<String, Double>()
        hrv?.let { (v, b) -> parts["hrv"] = 100 - Derived.robustScore(v, b) }
        rhr?.let { (v, b) -> parts["rhr"] = Derived.robustScore(v, b) }
        asleepMin?.let { parts["sleep"] = (100 * (1 - it / needMin) * 2).coerceIn(0.0, 100.0) }
        resp?.let { (v, b) -> parts["resp"] = Derived.robustScore(v, b) }
        elevatedShare?.let { parts["daytime"] = (it * 400).coerceIn(0.0, 100.0) } // 25 % of the day = 100
        if (parts.size < 2 || (parts.keys intersect setOf("hrv", "rhr")).isEmpty()) return null
        val w = parts.keys.sumOf { WEIGHTS.getValue(it) }
        val s = (parts.entries.sumOf { (k, v) -> v * WEIGHTS.getValue(k) } / w).roundToInt().coerceIn(0, 100)
        return Stress(s, band(s), parts)
    }
}

// ---- strain target, training load ------------------------------------------------------------

object Training {
    const val TARGET_NOTE =
        "Today's active-minutes target = your 28-day daily average x 0.6 when readiness is below your usual " +
            "range, x 1.0 inside it and x 1.3 above it (rounded to 5 min, at least 10)."

    fun target(
        chronicDailyAzm: Double?,
        readiness: Double?,
        readinessBaseline: Baseline?,
    ): Int? {
        val base = chronicDailyAzm ?: return null
        val factor =
            when {
                readiness == null || readinessBaseline == null -> 1.0
                readiness < readinessBaseline.q1 -> 0.6
                readiness > readinessBaseline.q3 -> 1.3
                else -> 1.0
            }
        return maxOf(10, (Math.round(base * factor / 5.0) * 5).toInt())
    }

    fun loadStatus(ratio: Double?): String? =
        when {
            ratio == null -> null
            ratio < 0.8 -> "Detraining"
            ratio < 1.0 -> "Maintaining"
            ratio <= 1.3 -> "Building"
            ratio <= 1.5 -> "Building fast"
            else -> "Overreaching"
        }
}

// ---- cardio fitness -------------------------------------------------------------------------

data class Vo2(val value: Double, val band: String?)

object Fitness {
    const val FORMULA =
        "VO2 max estimate (ml/kg/min) = 15.3 x max HR / resting HR (Uth-Sorensen), with max HR = 208 - 0.7 x age " +
            "(Tanaka) and resting HR averaged over 7 days. Bands are approximate, adapted from published age- and " +
            "sex-based norms. It is an estimate from heart rate alone, not a lab test."

    fun estimate(
        age: Int,
        restingHr7d: Double,
    ): Double = 15.3 * (208 - 0.7 * age) / restingHr7d

    /** Approximate fitness bands (lower bounds of Fair/Good/Excellent/Superior) by age and sex. */
    private val MALE = listOf(20 to listOf(38, 44, 50, 56), 30 to listOf(35, 41, 47, 53), 40 to listOf(33, 38, 44, 50), 50 to listOf(30, 35, 41, 47), 60 to listOf(27, 32, 37, 43))
    private val FEMALE = listOf(20 to listOf(32, 37, 42, 48), 30 to listOf(30, 35, 40, 45), 40 to listOf(28, 32, 37, 42), 50 to listOf(25, 29, 34, 39), 60 to listOf(23, 27, 31, 36))

    fun band(
        vo2: Double,
        age: Int,
        sex: String?,
    ): String? {
        val table =
            when (sex) {
                "male" -> MALE
                "female" -> FEMALE
                else -> return null
            }
        val cuts = table.lastOrNull { age >= it.first }?.second ?: table.first().second
        val labels = listOf("Poor", "Fair", "Good", "Excellent", "Superior")
        return labels[cuts.count { vo2 >= it }]
    }
}

// ---- reports ---------------------------------------------------------------------------------

data class PeriodStat(val key: String, val label: String, val current: Double?, val previous: Double?, val higherIsBetter: Boolean?)

object Reports {
    /** Average of a metric over the current and the previous period of equal length. */
    fun compare(
        key: String,
        label: String,
        current: List<Double>,
        previous: List<Double>,
        higherIsBetter: Boolean?,
    ) = PeriodStat(key, label, current.takeIf { it.isNotEmpty() }?.average(), previous.takeIf { it.isNotEmpty() }?.average(), higherIsBetter)
}
