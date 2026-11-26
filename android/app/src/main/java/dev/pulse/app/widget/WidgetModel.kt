package dev.pulse.app.widget

import dev.pulse.api.models.WidgetReadiness
import dev.pulse.api.models.WidgetSnapshot
import dev.pulse.app.util.Fmt

/** What the widget shows, derived from the server's compact snapshot (pure, unit-tested). */
data class WidgetView(
    val readiness: String,
    val readinessLabel: String,
    val readinessIcon: String,
    val steps: String,
    val stepsProgress: Float,
    val stepsGoal: String,
    val sleep: String,
    val azm: String,
    val asOf: String,
    val warning: String?,
)

object WidgetMapper {
    fun map(
        s: WidgetSnapshot?,
        now: java.time.Instant = java.time.Instant.now(),
    ): WidgetView {
        if (s == null) {
            return WidgetView("–", "Open Pulse to set up", "○", "–", 0f, "", "–", "–", "", null)
        }
        val icon =
            when (s.readiness.status) {
                WidgetReadiness.Status.in_range -> "●"
                WidgetReadiness.Status.mild, WidgetReadiness.Status.notable ->
                    if (s.readiness.label.contains("above")) "▲" else "▼"
                WidgetReadiness.Status.none -> "○"
            }
        val steps = s.steps
        return WidgetView(
            readiness = s.readiness.value?.let { Fmt.num(it) } ?: "–",
            readinessLabel = s.readiness.label.replaceFirstChar { it.uppercase() },
            readinessIcon = icon,
            steps = steps?.let { Fmt.num(it) } ?: "–",
            stepsProgress = if (steps != null && s.stepsGoal > 0) (steps / s.stepsGoal).toFloat().coerceIn(0f, 1f) else 0f,
            stepsGoal = "of ${Fmt.num(s.stepsGoal.toDouble())}",
            sleep = s.sleepMainMin?.let { Fmt.duration(it) } ?: "–",
            azm = "${s.azmWeek?.let { Fmt.num(it) } ?: "–"}/${s.azmGoal}",
            asOf = "as of ${Fmt.time(s.generatedAt)}",
            warning = null,
        )
    }
}
