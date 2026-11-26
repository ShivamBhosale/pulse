package dev.pulse.app

import dev.pulse.app.hc.Hc
import dev.pulse.app.hc.HcExercise
import dev.pulse.app.hc.HcMapping
import dev.pulse.app.hc.HcSample
import dev.pulse.app.hc.HcSleep
import dev.pulse.app.hc.HcStage
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/** Health Connect → Pulse rows, with fake records (no phone needed). */
class HcMappingTest {
    private val tz = ZoneId.of("America/Toronto")

    private fun at(s: String) = Instant.parse(s)

    private fun night(
        id: String,
        source: String,
        start: String,
        end: String,
    ) = HcSleep(
        id,
        at(start),
        at(end),
        source,
        listOf(
            HcStage("LIGHT", at(start), at(start).plusSeconds(1800)),
            HcStage("DEEP", at(start).plusSeconds(1800), at(start).plusSeconds(5400)),
            HcStage("AWAKE", at(start).plusSeconds(5400), at(start).plusSeconds(5400 + 600)),
            HcStage("REM", at(start).plusSeconds(6000), at(end)),
        ),
    )

    @Test fun sleepPrefersFitbitAndUsesWakeDate() {
        // 22:30 → 06:30 local (EST = UTC−5): wake date is Nov 25.
        val fitbit = night("f1", Hc.FITBIT, "2026-11-25T03:30:00Z", "2026-11-25T11:30:00Z")
        val other = night("g1", Hc.GOOGLE_HEALTH, "2026-11-25T03:35:00Z", "2026-11-25T11:20:00Z")
        val out = HcMapping.sleep(listOf(other, fitbit), tz)
        assertEquals(listOf("f1"), out.sessions.map { it.id })
        val s = out.sessions.single()
        assertEquals(LocalDate.of(2026, 11, 25).toEpochDay(), s.day)
        assertEquals(30 + 60 + (480 - 100), s.asleepMin) // light 30 + deep 60 + REM rest
        assertEquals(10, s.awakeMin)
        assertEquals(1, s.interruptions)
        val m = out.metrics.associate { it.metric to it.value }
        assertEquals(-90.0, m["bedtime_min"]!!, 1e-9) // 22:30 the evening before
        assertEquals(390.0, m["waketime_min"]!!, 1e-9) // 06:30
        assertEquals(60.0, m["sleep_deep_min"]!!, 1e-9)
    }

    @Test fun napsCountInTotalButMainIsLongest() {
        val main = night("m", Hc.FITBIT, "2026-11-25T03:30:00Z", "2026-11-25T11:30:00Z")
        val nap = HcSleep("n", at("2026-11-25T19:00:00Z"), at("2026-11-25T19:40:00Z"), Hc.FITBIT, emptyList())
        val out = HcMapping.sleep(listOf(main, nap), tz)
        assertEquals(setOf("m"), out.sessions.filter { it.isMain }.map { it.id }.toSet())
        val m = out.metrics.associate { it.metric to it.value }
        assertEquals(m["sleep_main_min"]!! + 40, m["sleep_min"]!!, 1e-9)
    }

    @Test fun nightlySamplesMapToWakeDayAndPreferredSource() {
        val main = night("m", Hc.FITBIT, "2026-11-25T03:30:00Z", "2026-11-25T11:30:00Z")
        val sessions = HcMapping.sleep(listOf(main), tz).sessions
        val samples =
            listOf(
                HcSample(at("2026-11-25T04:00:00Z"), 40.0, Hc.FITBIT), // 23:00 Nov 24 local, inside sleep
                HcSample(at("2026-11-25T08:00:00Z"), 44.0, Hc.FITBIT),
                HcSample(at("2026-11-25T08:00:00Z"), 99.0, "com.other.app"), // lower priority: ignored
                HcSample(at("2026-11-26T20:00:00Z"), 50.0, Hc.FITBIT), // not in a sleep: its own date
            )
        val byDay = HcMapping.nightly(samples, sessions, tz)
        assertEquals(listOf(40.0, 44.0), byDay[LocalDate.of(2026, 11, 25)])
        assertEquals(listOf(50.0), byDay[LocalDate.of(2026, 11, 26)])
    }

    @Test fun exercisesDedupeAcrossSources() {
        val a = HcExercise("a", at("2026-11-25T15:00:00Z"), at("2026-11-25T15:30:00Z"), 79, null, Hc.FITBIT)
        val b = HcExercise("b", at("2026-11-25T15:02:00Z"), at("2026-11-25T15:31:00Z"), 79, null, Hc.GOOGLE_HEALTH)
        val c = HcExercise("c", at("2026-11-25T20:00:00Z"), at("2026-11-25T20:45:00Z"), 56, "Evening run", Hc.GOOGLE_HEALTH)
        val out = HcMapping.exercises(listOf(b, a, c), tz)
        assertEquals(listOf("a", "c"), out.map { it.id })
        assertEquals("WALKING", out[0].type)
        assertEquals("RUNNING", out[1].type)
        assertTrue(out.all { it.day == LocalDate.of(2026, 11, 25).toEpochDay() })
    }
}
