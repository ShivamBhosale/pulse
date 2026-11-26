package dev.pulse.app.ui

import dev.pulse.app.util.Fmt

/** How each metric is labelled and formatted in the native charts. */
data class MetricUi(val key: String, val label: String, val format: (Double) -> String, val bars: Boolean = false, val band: Boolean = true, val diverging: Boolean = false)

object Metrics {
    private fun n(dec: Int, unit: String) = { v: Double -> Fmt.num(v, dec) + if (unit.isEmpty()) "" else " $unit" }

    val ALL =
        listOf(
            MetricUi("readiness", "Readiness", n(0, "")),
            MetricUi("sleep_score", "Sleep score", n(0, ""), bars = true, band = false),
            MetricUi("stress_score", "Body stress", n(0, ""), band = false),
            MetricUi("sleep_need_min", "Sleep need", { Fmt.duration(it) }, band = false),
            MetricUi("vo2max", "Cardio fitness (VO₂ max est.)", n(1, ""), band = false),
            MetricUi("resting_hr", "Resting heart rate", n(0, "bpm")),
            MetricUi("hrv_rmssd", "Heart rate variability", n(1, "ms")),
            MetricUi("resp_rate", "Breathing rate", n(1, "brpm")),
            MetricUi("spo2_avg", "Blood oxygen", n(1, "%")),
            MetricUi("skin_temp_delta", "Skin temperature variation", { v -> (if (v > 0) "+" else "") + Fmt.num(v, 2) + " °C" }, bars = true, band = false, diverging = true),
            MetricUi("sleep_main_min", "Main sleep", { Fmt.duration(it) }, bars = true),
            MetricUi("sleep_deep_min", "Deep sleep", { Fmt.duration(it) }, bars = true),
            MetricUi("sleep_rem_min", "REM sleep", { Fmt.duration(it) }, bars = true),
            MetricUi("sleep_efficiency", "Sleep efficiency", n(0, "%")),
            MetricUi("sleep_debt_min", "Sleep debt (7 nights)", { Fmt.duration(it) }, band = false),
            MetricUi("bedtime_min", "Bedtime", { Fmt.clock(it) }, band = false),
            MetricUi("waketime_min", "Wake time", { Fmt.clock(it) }, band = false),
            MetricUi("steps", "Steps", n(0, ""), bars = true, band = false),
            MetricUi("distance_km", "Distance", n(2, "km"), bars = true, band = false),
            MetricUi("calories_total", "Calories burned", n(0, "kcal"), bars = true, band = false),
            MetricUi("floors", "Floors", n(0, ""), bars = true, band = false),
            MetricUi("azm", "Active zone minutes", n(0, "min"), bars = true, band = false),
            MetricUi("load_ratio", "Training load (7d:28d)", n(2, "×"), band = false),
        )

    fun of(key: String) = ALL.firstOrNull { it.key == key }
}
