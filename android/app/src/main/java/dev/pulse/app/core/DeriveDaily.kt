package dev.pulse.app.core

import java.time.LocalDate

/** All derived daily rows from synced series (port of derived.derive_daily). */
object DeriveDaily {
    val UNITS =
        mapOf(
            "readiness" to "score",
            "strain" to "min",
            "load_ratio" to "ratio",
            "sleep_debt_min" to "min",
            "bedtime_sd_min" to "min",
            "waketime_sd_min" to "min",
            "azm_week" to "min",
            "calories_bmr" to "kcal",
        )

    data class Row(val date: LocalDate, val metric: String, val value: Double)

    fun derive(
        series: Map<String, Series>,
        sleepGoalMin: Double,
        weights: Map<String, Double> = Derived.DEFAULT_WEIGHTS,
    ): List<Row> {
        fun get(k: String) = series[k] ?: emptyMap()
        val azm = get("azm")
        val total = get("calories_total")
        val active = get("calories_active")
        val sleepMain = get("sleep_main_min")
        val bed = get("bedtime_min")
        val wake = get("waketime_min")
        val strain = azm
        val days = series.values.flatMap { it.keys }.toSortedSet()
        val out = mutableListOf<Row>()

        fun put(
            d: LocalDate,
            k: String,
            v: Double?,
        ) {
            if (v != null && v.isFinite()) out += Row(d, k, v)
        }
        for (d in days) {
            put(d, "strain", strain[d])
            put(d, "load_ratio", Derived.loadRatio(strain, d))
            put(d, "azm_week", Derived.weekToDate(azm, d))
            if (d in total && d in active) put(d, "calories_bmr", maxOf(0.0, total[d]!! - active[d]!!))
            if (sleepMain.isNotEmpty()) {
                put(d, "sleep_debt_min", Derived.sleepDebt(sleepMain, d, sleepGoalMin))
                put(d, "bedtime_sd_min", Derived.consistencySd(bed, d))
                put(d, "waketime_sd_min", Derived.consistencySd(wake, d))
            }
            put(
                d,
                "readiness",
                Derived.readiness(d, get("hrv_rmssd"), get("resting_hr"), sleepMain, strain, sleepGoalMin, weights).score,
            )
        }
        return out
    }
}
