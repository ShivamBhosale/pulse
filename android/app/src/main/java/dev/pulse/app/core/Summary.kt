package dev.pulse.app.core

import java.time.LocalDate
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.roundToLong

/** Rule-based daily summary (port of src/pulse/summary.py; same wording, no AI). */
object Summary {
    const val MAX_SENTENCES = 4

    data class Reading(val value: Double?, val median: Double? = null, val status: Status = Status.NONE, val prevStatus: Status = Status.NONE)

    data class Part(val key: String, val score: Double?, val weight: Double)

    data class StreakFact(val key: String, val current: Int, val metNow: Boolean, val goal: Double)

    data class RecordFact(val key: String, val label: String, val value: Double, val unit: String, val date: LocalDate)

    data class Facts(
        val date: LocalDate,
        val isToday: Boolean,
        val imperial: Boolean = false,
        val sleepGoalMin: Double = 480.0,
        val stepsGoal: Double = 10_000.0,
        val azmGoal: Double = 150.0,
        val readiness: Reading = Reading(null),
        val parts: List<Part> = emptyList(),
        val sleepMainMin: Double? = null,
        val sleepDebtMin: Double? = null,
        val bedtimeMin: Double? = null,
        val bedtimeUsualMin: Double? = null,
        val vitals: Map<String, Reading> = emptyMap(),
        val steps: Reading = Reading(null),
        val azmWeek: Double? = null,
        val daysLeftInWeek: Int = 0,
        val loadRatio: Double? = null,
        val streaks: List<StreakFact> = emptyList(),
        val records: List<RecordFact> = emptyList(),
        val eveningTagsBefore: List<String> = emptyList(),
        /** Extra sentences from premium features (sleep score, stress, …), already ranked. */
        val extra: List<Sentence> = emptyList(),
    )

    enum class Tone { GOOD, NEUTRAL, ATTENTION }

    data class Sentence(val text: String, val tone: Tone, val priority: Int, val metrics: List<String> = emptyList())

    data class Result(val date: LocalDate, val headline: String, val sentences: List<Sentence>)

    // ---- formatting ----------------------------------------------------------------------

    fun num(
        v: Double,
        decimals: Int = 0,
    ): String = String.format(java.util.Locale.US, "%,.${decimals}f", v)

    fun duration(minutes: Double): String {
        val m = abs(minutes).roundToLong()
        val h = m / 60
        val r = m % 60
        return if (h > 0 && r == 0L) "${h}h" else if (h > 0) "${h}h ${r.toString().padStart(2, '0')}m" else "${r}m"
    }

    fun clock(minutes: Double): String {
        val m = ((Math.round(minutes) % 1440) + 1440) % 1440
        return "%02d:%02d".format(m / 60, m % 60)
    }

    private fun tense(
        f: Facts,
        present: String,
        past: String,
    ) = if (f.isToday) present else past

    // ---- rules ---------------------------------------------------------------------------

    private val partLabel = mapOf("hrv" to "HRV", "rhr" to "resting heart rate", "sleep" to "sleep", "strain" to "strain")

    fun ruleReadiness(f: Facts): Sentence? {
        val r = f.readiness
        val v = r.value ?: return null
        val isWord = tense(f, "is", "was")
        if (r.median == null) return Sentence("Readiness $isWord ${num(v)}.", Tone.NEUTRAL, 90, listOf("readiness"))
        val diff = v - r.median
        val where =
            if (r.status == Status.IN_RANGE) {
                "in your usual range"
            } else {
                (if (diff > 0) "above" else "below") + " your usual ${num(r.median)}"
            }
        var text = "Readiness $isWord ${num(v)}, $where"
        val tone =
            when {
                r.status == Status.IN_RANGE || r.status == Status.NONE -> Tone.NEUTRAL
                diff > 0 -> Tone.GOOD
                else -> Tone.ATTENTION
            }
        val parts = f.parts.filter { it.score != null && it.weight > 0 }
        if (parts.isNotEmpty() && r.status != Status.IN_RANGE) {
            val driver = parts.maxBy { (it.score!! - 50) * it.weight * (if (diff > 0) 1 else -1) }
            if ((driver.score!! - 50) * diff > 0) text += ", mostly from ${partLabel[driver.key]}"
        }
        return Sentence("$text.", tone, 90, listOf("readiness"))
    }

    fun ruleSleep(f: Facts): Sentence? {
        val s = f.sleepMainMin ?: return null
        val goal = f.sleepGoalMin
        val short = goal - s
        var (text, tone, prio) =
            if (short > 15) {
                Triple(
                    "You slept ${duration(s)}, ${duration(short)} short of your ${duration(goal)} goal",
                    if (short >= 60) Tone.ATTENTION else Tone.NEUTRAL,
                    if (short >= 60) 80 else 55,
                )
            } else {
                Triple("You slept ${duration(s)}, meeting your ${duration(goal)} goal", Tone.GOOD, 50)
            }
        f.sleepDebtMin?.takeIf { it >= 60 }?.let { text += "; 7-night sleep debt ${tense(f, "is", "was")} ${duration(it)}" }
        return Sentence("$text.", tone, prio, listOf("sleep_main_min", "sleep_debt_min"))
    }

    fun ruleBedtime(f: Facts): Sentence? {
        val bed = f.bedtimeMin ?: return null
        val usual = f.bedtimeUsualMin ?: return null
        val shift = Derived.clockWrap(bed) - usual
        if (abs(shift) < 45) return null
        return Sentence(
            "Bedtime was ${duration(shift)} ${if (shift > 0) "later" else "earlier"} than your usual ${clock(usual)}.",
            if (shift >= 90) Tone.ATTENTION else Tone.NEUTRAL,
            55,
            listOf("bedtime_min"),
        )
    }

    private data class VitalMeta(val label: String, val unit: String, val dec: Int, val higherBetter: Boolean, val minDiff: Double)

    private val vitalMeta =
        linkedMapOf(
            "resting_hr" to VitalMeta("Resting heart rate", " bpm", 0, false, 2.0),
            "hrv_rmssd" to VitalMeta("HRV", " ms", 1, true, 3.0),
            "spo2_avg" to VitalMeta("Overnight blood oxygen", "%", 1, true, 1.5),
            "resp_rate" to VitalMeta("Breathing rate", " brpm", 1, false, 1.0),
        )

    fun ruleVitals(f: Facts): List<Sentence> {
        val out = mutableListOf<Sentence>()
        for ((key, m) in vitalMeta) {
            val r = f.vitals[key] ?: continue
            val v = r.value ?: continue
            val med = r.median ?: continue
            if (abs(v - med) < m.minDiff) continue
            val repeatedMild = r.status == Status.MILD && (r.prevStatus == Status.MILD || r.prevStatus == Status.NOTABLE)
            if (r.status != Status.NOTABLE && !repeatedMild) continue
            val up = v > med
            out +=
                Sentence(
                    "${m.label} ${tense(f, "is", "was")} ${num(v, m.dec)}${m.unit}, ${if (r.status == Status.NOTABLE) "well " else ""}" +
                        "${if (up) "above" else "below"} your usual ${num(med, m.dec)}${if (repeatedMild) " for a second day" else ""}.",
                    if (up == m.higherBetter) Tone.GOOD else Tone.ATTENTION,
                    if (r.status == Status.NOTABLE) 85 else 60,
                    listOf(key),
                )
        }
        f.vitals["skin_temp_delta"]?.value?.takeIf { abs(it) >= 0.5 }?.let { t ->
            val v = if (f.imperial) t * 1.8 else t
            out +=
                Sentence(
                    "Skin temperature ${tense(f, "is", "was")} ${num(abs(v), 1)} °${if (f.imperial) "F" else "C"} " +
                        "${if (t > 0) "above" else "below"} your baseline.",
                    if (abs(t) >= 1.0) Tone.ATTENTION else Tone.NEUTRAL,
                    if (abs(t) >= 1.0) 70 else 45,
                    listOf("skin_temp_delta"),
                )
        }
        return out
    }

    fun ruleAzmWeek(f: Facts): Sentence? {
        val done = f.azmWeek ?: return null
        val goal = f.azmGoal
        if (done >= goal) return Sentence("Weekly active zone minutes: ${num(done)} of ${num(goal)}, goal met ✓.", Tone.GOOD, 45, listOf("azm"))
        val left = goal - done
        return if (f.isToday) {
            val days = f.daysLeftInWeek + 1
            val tail = if (days == 1) ": ${num(left)} to go today" else ": ${num(left)} to go in $days days (~${ceil(left / days).toInt()} a day)"
            Sentence("${num(done)} of ${num(goal)} active zone minutes this week$tail.", Tone.NEUTRAL, if (days <= 2) 70 else 45, listOf("azm"))
        } else {
            Sentence("${num(done)} of ${num(goal)} active zone minutes this week by the end of that day.", Tone.NEUTRAL, 40, listOf("azm"))
        }
    }

    fun ruleSteps(f: Facts): Sentence? {
        val s = f.steps
        val v = s.value ?: return null
        if (!f.isToday) {
            val met = v >= f.stepsGoal
            return Sentence(
                "You walked ${num(v)} steps" + if (met) ", above your ${num(f.stepsGoal)} goal ✓." else " (goal ${num(f.stepsGoal)}).",
                if (met) Tone.GOOD else Tone.NEUTRAL,
                42,
                listOf("steps"),
            )
        }
        val med = s.median ?: return null
        if (s.status == Status.IN_RANGE || s.status == Status.NONE) return null
        val above = v > med
        return Sentence(
            "${num(v)} steps so far, ${if (above) "above" else "below"} your usual ${num(med)} by this time.",
            if (above) Tone.GOOD else Tone.NEUTRAL,
            40,
            listOf("steps"),
        )
    }

    fun ruleStreaks(f: Facts): List<Sentence> =
        f.streaks.mapNotNull { st ->
            when {
                st.key == "steps" && f.isToday && st.current >= 2 && !st.metNow ->
                    Sentence(
                        "Step streak: ${st.current} days. Reach ${num(st.goal)} today to make it ${st.current + 1}.",
                        Tone.NEUTRAL,
                        65,
                        listOf("steps"),
                    )
                st.key == "sleep" && st.metNow && st.current >= 3 ->
                    Sentence("${st.current} nights in a row at your sleep goal.", Tone.GOOD, 50, listOf("sleep_main_min"))
                st.key == "azm" && st.metNow && st.current >= 2 ->
                    Sentence("${st.current} weeks in a row at your active-minutes goal.", Tone.GOOD, 48, listOf("azm"))
                else -> null
            }
        }

    fun ruleRecords(f: Facts): List<Sentence> =
        f.records.map { r ->
            val whenText =
                if (r.date == f.date && f.isToday) "today" else if (f.date.toEpochDay() - r.date.toEpochDay() == 1L) "yesterday" else "on this day"
            val value =
                if (r.unit == "min" && "sleep" in r.key) {
                    duration(r.value)
                } else {
                    num(r.value, if (r.unit == "ms" || r.unit == "km") 1 else 0) + if (r.unit in setOf("count", "steps", "score")) "" else " ${r.unit}"
                }
            Sentence("New record $whenText: ${r.label} ($value).", Tone.GOOD, 75, listOf(r.key))
        }

    fun ruleLoad(f: Facts): Sentence? {
        val lr = f.loadRatio ?: return null
        if (lr in 0.7..1.5) return null
        return if (lr > 1.5) {
            Sentence("Training load ${tense(f, "is", "was")} ${num(lr, 1)}× your 4-week norm.", Tone.ATTENTION, 52, listOf("load_ratio"))
        } else {
            Sentence("A lighter week than usual: load ${num(lr, 1)}× your 4-week norm.", Tone.NEUTRAL, 35, listOf("load_ratio"))
        }
    }

    fun ruleTags(f: Facts): Sentence? {
        if (f.eveningTagsBefore.isEmpty()) return null
        return Sentence(
            "Tagged ${if (f.isToday) "last night" else "the evening before"}: ${f.eveningTagsBefore.joinToString(", ")}.",
            Tone.NEUTRAL,
            58,
            listOf("tags"),
        )
    }

    fun headline(f: Facts): String {
        val r = f.readiness
        val v = r.value ?: return if (f.isToday) "Not enough data for a readiness score yet" else "No readiness score for this day"
        if (r.median == null || r.status == Status.IN_RANGE) return "Readiness ${num(v)}: a typical day for you"
        val above = v > r.median
        return if (r.status == Status.NOTABLE) {
            "Readiness ${num(v)}: well ${if (above) "above" else "below"} your usual"
        } else {
            "Readiness ${num(v)}: a bit ${if (above) "above" else "below"} your usual"
        }
    }

    fun build(
        f: Facts,
        limit: Int = MAX_SENTENCES,
    ): Result {
        val found = mutableListOf<Sentence>()
        listOfNotNull(ruleReadiness(f), ruleSleep(f), ruleBedtime(f)).let { found += it }
        found += ruleVitals(f)
        listOfNotNull(ruleAzmWeek(f), ruleSteps(f)).let { found += it }
        found += ruleStreaks(f)
        found += ruleRecords(f)
        listOfNotNull(ruleLoad(f), ruleTags(f)).let { found += it }
        found += f.extra
        val ranked = found.withIndex().sortedWith(compareBy({ -it.value.priority }, { it.index })).map { it.value }
        return Result(f.date, headline(f), ranked.take(limit))
    }
}
