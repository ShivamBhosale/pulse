package dev.pulse.app.ui.premium

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.pulse.app.AppContainer
import dev.pulse.app.core.premium.BodySignals
import dev.pulse.app.core.premium.Fitness
import dev.pulse.app.core.premium.Reports
import dev.pulse.app.core.premium.SleepNeeds
import dev.pulse.app.core.premium.SleepProfile
import dev.pulse.app.core.premium.SleepProfiles
import dev.pulse.app.core.premium.SleepScoring
import dev.pulse.app.core.premium.StressScoring
import dev.pulse.app.core.premium.Training
import dev.pulse.app.data.Premium
import dev.pulse.app.ui.Eyebrow
import dev.pulse.app.ui.PulseCard
import dev.pulse.app.ui.Tone
import dev.pulse.app.ui.ToneLabel
import dev.pulse.app.ui.charts.DayChart
import dev.pulse.app.ui.charts.Pt
import dev.pulse.app.ui.health.RangePicker
import dev.pulse.app.ui.theme.LocalPulse
import dev.pulse.app.ui.theme.NumStyle
import dev.pulse.app.util.Fmt
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@Composable
fun HowCalculated(text: String) {
    val p = LocalPulse.current
    var open by remember { mutableStateOf(false) }
    Text(
        if (open) "▾ How it's calculated" else "ⓘ How it's calculated",
        color = p.muted,
        fontSize = 11.sp,
        modifier = Modifier.clickable { open = !open },
    )
    if (open) Text(text, color = p.ink2, fontSize = 12.sp, lineHeight = 17.sp)
}

@Composable
private fun Bar(
    label: String,
    value: Double,
    max: Double,
) {
    val p = LocalPulse.current
    Column {
        Row(Modifier.fillMaxWidth()) {
            Text(label, color = p.ink2, fontSize = 12.sp, modifier = Modifier.weight(1f))
            Text("${Fmt.num(value)} / ${Fmt.num(max)}", style = NumStyle, fontSize = 12.sp, color = p.muted)
        }
        Box(Modifier.fillMaxWidth().height(4.dp).clip(RoundedCornerShape(2.dp)).background(p.surface2)) {
            Box(Modifier.fillMaxWidth((value / max).toFloat().coerceIn(0f, 1f)).fillMaxHeight().background(p.accent))
        }
    }
}

private suspend fun premiumDay(
    c: AppContainer,
    d: LocalDate,
): Premium.Day {
    val p = c.prefs.get()
    return Premium.day(c.db, d, p, ZoneId.systemDefault(), c.prefs.age(p, d.year))
}

// ---- sleep tab --------------------------------------------------------------------------------

/** Sleep score for the night shown, tonight's need, bedtime and the payback plan. */
@Composable
fun SleepPremiumCards(
    c: AppContainer,
    nightDate: String,
) {
    val p = LocalPulse.current
    val night by produceState<Premium.Day?>(null, nightDate) { value = premiumDay(c, LocalDate.parse(nightDate)) }
    val today by produceState<Premium.Day?>(null) { value = premiumDay(c, c.repo.today()) }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        night?.sleepScore?.let { s ->
            PulseCard {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Eyebrow("Sleep score")
                        Row(verticalAlignment = Alignment.Bottom) {
                            Text("${s.total}", style = NumStyle, fontSize = 34.sp, color = p.ink, fontWeight = FontWeight.Medium)
                            Text(" / 100", color = p.muted, fontSize = 13.sp)
                        }
                    }
                    ToneLabel(
                        when {
                            s.total >= 80 -> Tone("●", s.label, p.good)
                            s.total >= 60 -> Tone("●", s.label, p.warning)
                            else -> Tone("▲", s.label, p.serious)
                        },
                    )
                }
                Bar("Duration vs need", s.duration, 50.0)
                Bar("Quality (deep + REM)", s.quality, 25.0)
                Bar("Restoration (HR, awake, interruptions)", s.restoration, 25.0)
                HowCalculated(SleepScoring.FORMULA)
            }
        }
        today?.let { t ->
            PulseCard(title = "Tonight", subtitle = "Your sleep need and when to be asleep") {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Column {
                        Eyebrow("Sleep need")
                        Text(Fmt.duration(t.need.needMin), style = NumStyle, fontSize = 22.sp, color = p.ink)
                    }
                    t.bedtime?.let { b ->
                        Column(horizontalAlignment = Alignment.End) {
                            Eyebrow("Be asleep by")
                            Text(Fmt.clock(b.asleepBy), style = NumStyle, fontSize = 22.sp, color = p.ink)
                            Text("in bed by ${Fmt.clock(b.inBedBy)} · wake ~${Fmt.clock(b.wakeTarget)}", fontSize = 11.sp, color = p.muted)
                        }
                    }
                }
                Text(
                    buildString {
                        append("Goal ${Fmt.duration(t.need.baseMin)}")
                        if (t.need.paybackMin >= 1) append(" + ${Fmt.duration(t.need.paybackMin)} debt payback")
                        if (t.need.strainMin > 0) append(" + ${Fmt.duration(t.need.strainMin)} after a hard day")
                    },
                    color = p.ink2,
                    fontSize = 12.sp,
                )
                if (t.need.debtMin >= 30) {
                    Text(
                        "Sleep debt (7 nights): ${Fmt.duration(t.need.debtMin)}" +
                            (t.need.nightsToClear?.let { n -> ". About ${Fmt.duration(maxOf(t.need.paybackMin, 15.0))} extra a night clears it in $n night${if (n == 1) "" else "s"}." } ?: "."),
                        color = p.ink2,
                        fontSize = 12.sp,
                    )
                } else {
                    Text("No meaningful sleep debt this week ✓", color = p.ink2, fontSize = 12.sp)
                }
                HowCalculated(SleepNeeds.FORMULA)
            }
        }
        SleepProfileCard(c)
    }
}

@Composable
private fun SleepProfileCard(c: AppContainer) {
    val p = LocalPulse.current
    data class Two(val now: SleepProfile?, val prev: SleepProfile?)
    val prof by produceState<Two?>(null) {
        val today = c.repo.today()
        suspend fun month(
            end: LocalDate,
            days: Int,
        ): SleepProfile? {
            val nights =
                c.db.sleep().range(end.minusDays(days - 1L).toEpochDay(), end.toEpochDay()).filter { it.isMain }.map { s ->
                    val midnight = LocalDate.ofEpochDay(s.day).atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli()
                    SleepProfiles.Night(s.asleepMin.toDouble(), (s.start - midnight) / 60000.0, (s.end - midnight) / 60000.0, s.deepMin?.toDouble(), s.remMin?.toDouble(), s.interruptions)
                }
            return SleepProfiles.profile(nights)
        }
        value = Two(month(today, 30), month(today.minusDays(30), 30))
    }
    val now = prof?.now ?: return
    val prev = prof?.prev
    PulseCard(title = "Sleep profile · last 30 nights", subtitle = "Compared with the 30 nights before") {
        fun row(
            label: String,
            v: String,
            was: String?,
        ) = Triple(label, v, was)
        val rows =
            listOf(
                row("Average sleep", Fmt.duration(now.avgAsleepMin), prev?.let { Fmt.duration(it.avgAsleepMin) }),
                row("Bedtime regularity (SD)", now.bedtimeSdMin?.let { "±${Fmt.num(it)} min" } ?: "–", prev?.bedtimeSdMin?.let { "±${Fmt.num(it)} min" }),
                row("Deep sleep", now.deepPct?.let { "${Fmt.num(it)}%" } ?: "–", prev?.deepPct?.let { "${Fmt.num(it)}%" }),
                row("REM sleep", now.remPct?.let { "${Fmt.num(it)}%" } ?: "–", prev?.remPct?.let { "${Fmt.num(it)}%" }),
                row("Interruptions per night", Fmt.num(now.interruptionsPerNight, 1), prev?.let { Fmt.num(it.interruptionsPerNight, 1) }),
                row("Sleep midpoint", Fmt.clock(now.midpointMin), prev?.let { Fmt.clock(it.midpointMin) }),
            )
        rows.forEach { (label, v, was) ->
            Row(Modifier.fillMaxWidth()) {
                Text(label, color = p.ink2, fontSize = 13.sp, modifier = Modifier.weight(1f))
                Text(v, style = NumStyle, fontSize = 13.sp, color = p.ink)
                Text(was?.let { "  (was $it)" } ?: "", style = NumStyle, fontSize = 11.sp, color = p.muted)
            }
        }
        Text(
            "Chronotype: ${now.chronotype}. Your sleep midpoint is ${Fmt.clock(now.midpointMin)} (early: before 03:00, late: after 04:30).",
            color = p.ink2,
            fontSize = 12.sp,
        )
    }
}

// ---- health tab -------------------------------------------------------------------------------

/** Body signals, stress, training load and fitness above the vitals charts. */
@Composable
fun HealthPremiumHeader(c: AppContainer) {
    val p = LocalPulse.current
    val day by produceState<Premium.Day?>(null) { value = premiumDay(c, c.repo.today()) }
    val stress by produceState<List<Pt>?>(null) { value = c.repo.chart("stress_score", 14, band = false) }
    val vo2 by produceState<List<Pt>?>(null) { value = c.repo.chart("vo2max", 90, band = false) }
    val x = day ?: return
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (x.signals.size >= 2) {
            PulseCard {
                Row(verticalAlignment = Alignment.Top) {
                    Text(if (x.signals.size >= 3) "▲ " else "● ", color = if (x.signals.size >= 3) p.serious else p.warning, fontSize = 13.sp)
                    Column {
                        Text(
                            if (x.signals.size >= 3) "Several body signals are unusual today" else "Two body signals are outside your usual range",
                            color = p.ink,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Medium,
                        )
                        x.signals.forEach { s ->
                            Text("${s.label} ${s.direction} than usual (${Fmt.num(s.value, 1)} vs ${s.usual?.let { Fmt.num(it, 1) } ?: "–"})", color = p.ink2, fontSize = 12.sp)
                        }
                        if (x.signals.size >= 3) Text("Consider taking it easy today.", color = p.ink2, fontSize = 12.sp)
                    }
                }
                HowCalculated(BodySignals.NOTE)
            }
        }
        x.stress?.let { s ->
            PulseCard(title = "Body stress") {
                Row(verticalAlignment = Alignment.Bottom) {
                    Text("${s.score}", style = NumStyle, fontSize = 30.sp, color = p.ink)
                    Text(" / 100  ", color = p.muted, fontSize = 13.sp)
                    ToneLabel(
                        when (s.band) {
                            "Low" -> Tone("●", "Low", p.good)
                            "Moderate" -> Tone("●", "Moderate", p.warning)
                            else -> Tone("▲", "High", p.serious)
                        },
                    )
                }
                Text(
                    s.parts.entries.joinToString(" · ") { (k, v) -> "${mapOf("hrv" to "HRV", "rhr" to "RHR", "sleep" to "sleep", "resp" to "breathing", "daytime" to "daytime HR")[k]} ${Fmt.num(v)}" },
                    style = NumStyle,
                    fontSize = 11.sp,
                    color = p.muted,
                )
                stress?.let { DayChart(it, { v -> Fmt.num(v) }, height = 110.dp, zeroBased = true, description = "Body stress over 14 days") }
                HowCalculated(StressScoring.FORMULA)
            }
        }
        PulseCard(title = "Training load") {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column {
                    Eyebrow("7-day vs 28-day")
                    Text(x.loadRatio?.let { "${Fmt.num(it, 2)}×" } ?: "–", style = NumStyle, fontSize = 22.sp, color = p.ink)
                    Text(x.loadStatus ?: "Needs 3 weeks of data", color = p.ink2, fontSize = 12.sp)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Eyebrow("Today's target")
                    Text(x.strainTarget?.let { "$it min" } ?: "–", style = NumStyle, fontSize = 22.sp, color = p.ink)
                    Text("active zone minutes", color = p.muted, fontSize = 11.sp)
                }
            }
            HowCalculated(Training.TARGET_NOTE + " Load status: under 0.8 detraining, 0.8-1.0 maintaining, 1.0-1.3 building, 1.3-1.5 building fast, over 1.5 overreaching.")
        }
        PulseCard(title = "Cardio fitness") {
            Row(verticalAlignment = Alignment.Bottom) {
                Text(x.vo2?.let { Fmt.num(it, 1) } ?: "–", style = NumStyle, fontSize = 30.sp, color = p.ink)
                Text(" ml/kg/min (VO₂ max est.)", color = p.muted, fontSize = 12.sp)
            }
            Text(
                x.vo2Band?.let { "$it for your age and sex" } ?: "Set your birth year and sex in Settings for an age-based band.",
                color = p.ink2,
                fontSize = 12.sp,
            )
            vo2?.let { DayChart(it, { v -> Fmt.num(v, 1) }, height = 110.dp, description = "VO2 max estimate over 90 days") }
            HowCalculated(Fitness.FORMULA)
        }
    }
}

// ---- reports ------------------------------------------------------------------------------------

@Composable
fun ReportsPage(c: AppContainer) {
    val p = LocalPulse.current
    var days by rememberSaveable { mutableIntStateOf(7) }
    data class Report(val stats: List<dev.pulse.app.core.premium.PeriodStat>, val bestSteps: Pair<LocalDate, Double>?, val bestSleep: Pair<LocalDate, Double>?, val tags: List<Pair<String, Int>>)
    val report by produceState<Report?>(null, days) {
        val today = c.repo.today()
        val end = today.minusDays(1)
        val start = end.minusDays(days - 1L)
        val prevEnd = start.minusDays(1)
        val prevStart = prevEnd.minusDays(days - 1L)
        suspend fun vals(
            k: String,
            a: LocalDate,
            b: LocalDate,
        ) = c.repo.values(k, a, b)
        val defs =
            listOf(
                Triple("sleep_main_min", "Sleep", true),
                Triple("sleep_score", "Sleep score", true),
                Triple("readiness", "Readiness", true),
                Triple("steps", "Steps", true),
                Triple("azm", "Active zone minutes", true),
                Triple("resting_hr", "Resting HR", false),
                Triple("hrv_rmssd", "HRV", true),
                Triple("stress_score", "Body stress", false),
            )
        val stats = defs.map { (k, label, up) -> Reports.compare(k, label, vals(k, start, end).values.toList(), vals(k, prevStart, prevEnd).values.toList(), up) }
        val steps = vals("steps", start, end).maxByOrNull { it.value }?.toPair()
        val sleepScore = vals("sleep_score", start, end).maxByOrNull { it.value }?.toPair()
        val tagLabels = c.repo.tags().associate { it.key to it.label }
        val tagCounts =
            c.db.journal().dayTagsRange(start.toEpochDay(), end.toEpochDay()).groupingBy { it.tagKey }.eachCount().entries
                .sortedByDescending { it.value }.map { (tagLabels[it.key] ?: it.key) to it.value }
        value = Report(stats, steps, sleepScore, tagCounts)
    }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { RangePicker(listOf(7 to "Last week", 30 to "Last month"), days) { days = it } }
        val r = report
        if (r == null) {
            item { Text("Loading…", color = p.muted) }
            return@LazyColumn
        }
        item {
            PulseCard(title = if (days == 7) "Last 7 days vs the 7 before" else "Last 30 days vs the 30 before") {
                r.stats.filter { it.current != null }.forEach { s ->
                    val fmt: (Double) -> String =
                        when (s.key) {
                            "sleep_main_min" -> { v -> Fmt.duration(v) }
                            "hrv_rmssd" -> { v -> "${Fmt.num(v, 1)} ms" }
                            "resting_hr" -> { v -> "${Fmt.num(v)} bpm" }
                            else -> { v -> Fmt.num(v) }
                        }
                    val diff = if (s.current != null && s.previous != null) s.current - s.previous else null
                    val better = diff?.let { d -> s.higherIsBetter?.let { (d > 0) == it } }
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text(s.label, color = p.ink2, fontSize = 13.sp, modifier = Modifier.weight(1f))
                        Text(fmt(s.current!!), style = NumStyle, fontSize = 13.sp, color = p.ink)
                        if (diff != null && kotlin.math.abs(diff) > 1e-9) {
                            Text(
                                "  ${if (diff > 0) "▲" else "▼"} ${fmt(kotlin.math.abs(diff))}",
                                style = NumStyle,
                                fontSize = 11.sp,
                                color = if (better == true) p.goodInk else if (better == false) p.serious else p.muted,
                            )
                        }
                    }
                }
                Text("Averages per day. ▲▼ is the change from the period before; green means better for you.", color = p.muted, fontSize = 11.sp)
            }
        }
        item {
            PulseCard(title = "Highlights") {
                val df = DateTimeFormatter.ofPattern("EEE d MMM")
                r.bestSteps?.let { (d, v) -> Text("Most steps: ${Fmt.num(v)} on ${d.format(df)}", color = p.ink2, fontSize = 13.sp) }
                r.bestSleep?.let { (d, v) -> Text("Best sleep score: ${Fmt.num(v)} on ${d.format(df)}", color = p.ink2, fontSize = 13.sp) }
                if (r.tags.isNotEmpty()) {
                    Text("Tags: " + r.tags.joinToString(", ") { (l, n) -> "$l ×$n" }, color = p.ink2, fontSize = 13.sp)
                }
                Text("Weekly report covers the 7 full days before today; monthly covers 30.", color = p.muted, fontSize = 11.sp)
            }
        }
    }
}
