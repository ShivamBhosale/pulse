package dev.pulse.app

import dev.pulse.app.core.Azm
import dev.pulse.app.core.Baseline
import dev.pulse.app.core.DeriveDaily
import dev.pulse.app.core.Derived
import dev.pulse.app.core.Status
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

/** Same cases as the server's tests/test_derived.py, so phone and server agree. */
class DerivedTest {
    private val d0 = LocalDate.of(2026, 3, 1)

    private fun series(
        values: List<Double?>,
        end: LocalDate,
    ): Map<LocalDate, Double> =
        values.withIndex().mapNotNull { (i, v) -> v?.let { end.minusDays((values.size - 1 - i).toLong()) to it } }.toMap()

    private fun flat(
        v: Double,
        end: LocalDate,
        days: Int = 29,
    ) = series(List(days) { v }, end)

    @Test fun robustScoreMidpointAndClamps() {
        val b = Baseline(50.0, 45.0, 55.0, 28)
        assertEquals(50.0, Derived.robustScore(50.0, b), 1e-9)
        assertEquals(100.0, Derived.robustScore(65.0, b), 1e-9)
        assertEquals(0.0, Derived.robustScore(35.0, b), 1e-9)
        assertEquals(0.0, Derived.robustScore(65.0, b, invert = true), 1e-9)
        val flatB = Baseline(60.0, 60.0, 60.0, 28)
        assertEquals(75.0, Derived.robustScore(61.5, flatB), 1e-9)
    }

    @Test fun baselineMatchesPythonInclusiveQuartiles() {
        val b = Derived.baseline(listOf(1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0))!!
        assertEquals(4.5, b.median, 1e-9)
        assertEquals(2.75, b.q1, 1e-9)
        assertEquals(6.25, b.q3, 1e-9)
        assertNull(Derived.baseline(listOf(1.0, 2.0)))
        assertEquals(Status.IN_RANGE, Derived.status(5.0, b))
        assertEquals(Status.NOTABLE, Derived.status(20.0, b))
        assertEquals(Status.MILD, Derived.status(8.0, b))
    }

    @Test fun readinessAtBaselineWithFullSleep() {
        val d = d0.plusDays(40)
        val r = Derived.readiness(d, flat(40.0, d), flat(60.0, d), flat(480.0, d), flat(30.0, d.minusDays(1)), 480.0)
        assertEquals(62.5, r.score!!, 1e-9)
        assertEquals(1.0, r.components.sumOf { it.weight }, 1e-9)
    }

    @Test fun readinessRenormalisesAndNeedsTwoParts() {
        val d = d0.plusDays(40)
        val r = Derived.readiness(d, flat(40.0, d), emptyMap(), mapOf(d to 240.0), emptyMap(), 480.0)
        assertEquals(50 * 35.0 / 60 + 50 * 25.0 / 60, r.score!!, 1e-6)
        assertNull(Derived.readiness(d, emptyMap(), emptyMap(), mapOf(d to 480.0), emptyMap(), 480.0).score)
    }

    @Test fun strainRestDayCapped() {
        val d = d0.plusDays(40)
        val strain = flat(30.0, d.minusDays(2)).toMutableMap()
        strain[d.minusDays(1)] = 0.0
        val r = Derived.readiness(d, emptyMap(), emptyMap(), mapOf(d to 480.0), strain, 480.0)
        assertEquals(Derived.STRAIN_REST_CAP, r.components.first { it.key == "strain" }.score!!, 1e-9)
    }

    @Test fun sleepDebtConsistencyLoad() {
        val d = d0.plusDays(10)
        assertEquals(270.0, Derived.sleepDebt(series(listOf(500.0, 420.0, null, 480.0, 300.0, 450.0, 480.0), d), d, 480.0)!!, 1e-9)
        val dd = d0.plusDays(20)
        assertEquals(30.0, Derived.consistencySd(series(listOf(-30.0, 30.0, 1410.0, 30.0, -30.0, 30.0), dd), dd)!!, 1e-9)
        assertEquals(-180.0, Derived.clockWrap(21 * 60.0), 1e-9)
        val dl = d0.plusDays(40)
        val s = series(List(21) { 10.0 } + List(7) { 40.0 }, dl)
        assertEquals(40.0 / ((10 * 21 + 40 * 7) / 28.0), Derived.loadRatio(s, dl)!!, 1e-9)
        assertNull(Derived.loadRatio(series(List(20) { 10.0 }, dl), dl))
    }

    @Test fun weekToDateRunsFromMonday() {
        val monday = LocalDate.of(2026, 11, 16)
        val s = mapOf(monday.minusDays(1) to 99.0, monday to 10.0, monday.plusDays(2) to 5.0)
        assertEquals(15.0, Derived.weekToDate(s, monday.plusDays(3))!!, 1e-9)
        assertEquals(mapOf(monday.minusDays(7) to 99.0, monday to 15.0), Derived.weeklyTotals(s))
    }

    @Test fun streaksAndBests() {
        val today = d0.plusDays(30)
        fun hits(flags: String) =
            flags.withIndex().filter { it.value != '.' }.associate { (i, f) -> today.minusDays((flags.length - 1 - i).toLong()) to (f == '1') }
        assertEquals(0 to 4, Derived.streak(hits("1111011100"), today).let { it.current to it.longest })
        assertEquals(3, Derived.streak(hits("1110"), today).current)
        assertEquals(2 to 2, Derived.streak(hits("11.11"), today).let { it.current to it.longest })
        val s = mapOf(d0 to 5.0, d0.plusDays(1) to 9.0, d0.plusDays(2) to 9.0)
        assertEquals(Derived.Best(9.0, d0.plusDays(1)), Derived.best(s))
        assertEquals(Derived.Best(5.0, d0), Derived.best(s, lowest = true))
    }

    @Test fun pearsonAndZones() {
        assertEquals(1.0, Derived.pearson(listOf(1.0, 2.0, 3.0, 4.0), listOf(2.0, 4.0, 6.0, 8.0))!!, 1e-9)
        assertNull(Derived.pearson(listOf(1.0, 2.0, 3.0), listOf(5.0, 5.0, 5.0)))
        assertEquals("strong negative", Derived.correlationStrength(-0.62))
        val bounds = mapOf("light" to (90 to 110), "moderate" to (111 to 130), "vigorous" to (131 to 160), "peak" to (161 to 220))
        assertEquals(
            mapOf("light" to 1, "moderate" to 2, "vigorous" to 1, "peak" to 1, "below" to 1),
            Derived.timeInZones(listOf(70.0, 95.0, 115.0, 115.0, 140.0, 170.0), bounds),
        )
    }

    @Test fun deriveDailyEmitsKeys() {
        val d = d0.plusDays(40)
        val rows =
            DeriveDaily.derive(
                mapOf(
                    "azm" to series(List(41) { 20.0 }, d),
                    "calories_total" to mapOf(d to 2500.0),
                    "calories_active" to mapOf(d to 600.0),
                    "sleep_main_min" to series(List(41) { 450.0 }, d),
                    "bedtime_min" to series(List(41) { -30.0 }, d),
                    "waketime_min" to series(List(41) { 420.0 }, d),
                    "hrv_rmssd" to series(List(41) { 40.0 }, d),
                    "resting_hr" to series(List(41) { 60.0 }, d),
                ),
                480.0,
            )
        val last = rows.filter { it.date == d }.associate { it.metric to it.value }
        assertEquals(DeriveDaily.UNITS.keys, last.keys)
        assertEquals(1900.0, last["calories_bmr"]!!, 1e-9)
        assertEquals(210.0, last["sleep_debt_min"]!!, 1e-9)
        assertTrue(last["readiness"]!! in 0.0..100.0)
    }

    @Test fun azmFromHeartRate() {
        val z = Azm.zones(age = 30, restingHr = 60.0) // max 187, reserve 127
        assertEquals(187, z.max)
        assertEquals(111, z.fatBurn) // 60 + 0.40 × 127 = 110.8
        assertEquals(136, z.cardio)
        assertEquals(168, z.peak)
        val day = Azm.minutes(listOf(70.0, 115.0, 115.0, 140.0, 170.0), z)
        assertEquals(Azm.DayAzm(fatBurn = 2, cardio = 1, peak = 1), day)
        assertEquals(6, day.total) // 2 + 2×1 + 2×1
    }
}
