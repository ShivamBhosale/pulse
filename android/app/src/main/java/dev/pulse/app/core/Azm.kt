package dev.pulse.app.core

/**
 * Active zone minutes from 1-minute heart rate, because Health Connect has no AZM record.
 *
 * Zones use heart-rate reserve (Karvonen), the method Fitbit documents for AZM:
 * fat burn 40–59 % of reserve, cardio 60–84 %, peak ≥ 85 %. Max HR = 208 − 0.7 × age (Tanaka).
 * Fat-burn minutes count once, cardio and peak minutes twice, like Fitbit.
 */
object Azm {
    data class Zones(val fatBurn: Int, val cardio: Int, val peak: Int, val max: Int)

    data class DayAzm(val fatBurn: Int, val cardio: Int, val peak: Int) {
        val total: Int get() = fatBurn + 2 * cardio + 2 * peak
    }

    fun maxHr(age: Int): Int = Math.round(208 - 0.7 * age).toInt()

    fun zones(
        age: Int,
        restingHr: Double,
    ): Zones {
        val max = maxHr(age)
        val reserve = max - restingHr
        fun at(p: Double) = Math.round(restingHr + p * reserve).toInt()
        return Zones(fatBurn = at(0.40), cardio = at(0.60), peak = at(0.85), max = max)
    }

    /** [minuteAvgBpm]: average BPM of each minute that has heart-rate data. */
    fun minutes(
        minuteAvgBpm: List<Double>,
        z: Zones,
    ): DayAzm {
        var fb = 0
        var c = 0
        var p = 0
        minuteAvgBpm.forEach { bpm ->
            when {
                bpm >= z.peak -> p++
                bpm >= z.cardio -> c++
                bpm >= z.fatBurn -> fb++
            }
        }
        return DayAzm(fb, c, p)
    }
}
