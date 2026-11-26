package dev.pulse.app

import dev.pulse.app.core.Baseline
import dev.pulse.app.core.premium.BodySignals
import dev.pulse.app.core.premium.Fitness
import dev.pulse.app.core.premium.SleepNeeds
import dev.pulse.app.core.premium.SleepProfiles
import dev.pulse.app.core.premium.SleepScoring
import dev.pulse.app.core.premium.StressScoring
import dev.pulse.app.core.premium.Training
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PremiumMathTest {
    @Test fun sleepScorePerfectAndPoor() {
        val perfect = SleepScoring.score(480.0, 480.0, 86.0, 110.0, 60.0, 62.0, 10.0, 1)
        assertEquals(100, perfect.total)
        assertEquals("Excellent", perfect.label)
        val poor = SleepScoring.score(240.0, 480.0, 10.0, 20.0, 75.0, 60.0, 70.0, 10)
        assertEquals(25.0, poor.duration, 1e-9)
        assertEquals(0.0, poor.restoration, 1e-9)
        assertTrue(poor.total < 60 && poor.label == "Poor")
    }

    @Test fun sleepScoreWithoutStagesGetsNeutralQuality() {
        val s = SleepScoring.score(480.0, 480.0, null, null, null, null, 0.0, 0)
        assertEquals(12.5, s.quality, 1e-9)
        assertEquals(5.0 + 8 + 7, s.restoration, 1e-9)
    }

    @Test fun sleepNeedPaybackCapAndStrain() {
        val b = Baseline(20.0, 10.0, 30.0, 28)
        val n = SleepNeeds.need(480.0, 700.0, 90.0, b) // payback 100 → capped 60; strain way above
        assertEquals(60.0, n.paybackMin, 1e-9)
        assertEquals(10.0, n.strainMin, 1e-9)
        assertEquals(550.0, n.needMin, 1e-9)
        assertEquals(12, n.nightsToClear) // 700 / 60
        val easy = SleepNeeds.need(480.0, 0.0, 20.0, b)
        assertEquals(480.0, easy.needMin, 1e-9)
        assertEquals(0, easy.nightsToClear)
    }

    @Test fun bedtimeWorksBackFromWake() {
        val bt = SleepNeeds.bedtime(List(7) { 390.0 }, List(7) { 12.0 }, 480.0)!!
        assertEquals(-90.0, bt.asleepBy, 1e-9) // 06:30 − 8 h = 22:30
        assertEquals(-102.0, bt.inBedBy, 1e-9)
        assertNull(SleepNeeds.bedtime(listOf(390.0), emptyList(), 480.0))
    }

    @Test fun chronotypeAndProfile() {
        assertEquals("Early", SleepProfiles.chronotype(150.0))
        assertEquals("Intermediate", SleepProfiles.chronotype(240.0))
        assertEquals("Late", SleepProfiles.chronotype(300.0))
        val nights = List(10) { SleepProfiles.Night(420.0, -60.0, 420.0, 70.0, 90.0, 2) }
        val p = SleepProfiles.profile(nights)!!
        assertEquals(180.0, p.midpointMin, 1e-9) // (−60 + 420) / 2 = 03:00
        assertEquals(0.0, p.bedtimeSdMin!!, 1e-9)
        assertEquals(70 / 420.0 * 100, p.deepPct!!, 1e-9)
    }

    @Test fun bodySignalsNeedNotableAndDirection() {
        val b = Baseline(60.0, 58.0, 62.0, 28)
        val hrvB = Baseline(40.0, 36.0, 44.0, 28)
        val out =
            BodySignals.unusual(
                rhr = BodySignals.In(70.0, b), // notable up
                hrv = BodySignals.In(25.0, hrvB), // notable down
                resp = BodySignals.In(null, null),
                spo2 = BodySignals.In(99.0, Baseline(96.0, 95.0, 97.0, 28)), // notable but up: fine
                skinTempDelta = 0.6,
            )
        assertEquals(listOf("resting_hr", "hrv_rmssd", "skin_temp_delta"), out.map { it.key })
        assertTrue(BodySignals.unusual(BodySignals.In(61.0, b), BodySignals.In(41.0, hrvB), BodySignals.In(null, null), BodySignals.In(null, null), 0.1).isEmpty())
    }

    @Test fun stressScoreBandsAndMissingParts() {
        val hrvB = Baseline(40.0, 36.0, 44.0, 28)
        val rhrB = Baseline(60.0, 58.0, 62.0, 28)
        val usual = StressScoring.score(40.0 to hrvB, 60.0 to rhrB, 480.0, 480.0, null, 0.0)!!
        // hrv 50, rhr 50, sleep 0, daytime 0 → (15 + 10 + 0 + 0) / 0.9
        assertEquals(28, usual.score)
        assertEquals("Low", usual.band)
        val hard = StressScoring.score(25.0 to hrvB, 70.0 to rhrB, 240.0, 480.0, null, 0.3)!!
        assertEquals(100, hard.score)
        assertEquals("High", hard.band)
        assertNull(StressScoring.score(null, null, 400.0, 480.0, null, 0.1))
        assertNull(StressScoring.elevatedStillShare(List(60) { 100.0 to 0.0 }, 60.0))
        assertEquals(0.5, StressScoring.elevatedStillShare(List(100) { 90.0 to 0.0 } + List(100) { 60.0 to 0.0 }, 60.0)!!, 1e-9)
    }

    @Test fun strainTargetAndLoad() {
        val rb = Baseline(60.0, 50.0, 70.0, 28)
        assertEquals(15, Training.target(25.0, 40.0, rb)) // 25 × 0.6 = 15
        assertEquals(25, Training.target(25.0, 60.0, rb))
        assertEquals(35, Training.target(25.0, 80.0, rb)) // 32.5 → 35 (half up)
        assertEquals(10, Training.target(5.0, 60.0, rb))
        assertNull(Training.target(null, 60.0, rb))
        assertEquals("Detraining", Training.loadStatus(0.6))
        assertEquals("Building", Training.loadStatus(1.2))
        assertEquals("Overreaching", Training.loadStatus(1.7))
    }

    @Test fun vo2EstimateAndBands() {
        val v = Fitness.estimate(age = 30, restingHr7d = 60.0) // 15.3 × 187 / 60
        assertEquals(15.3 * 187 / 60, v, 1e-9)
        assertEquals("Excellent", Fitness.band(47.7, 30, "male")) // 30s cuts 35/41/47/53
        assertEquals("Good", Fitness.band(45.0, 30, "male"))
        assertEquals("Superior", Fitness.band(47.7, 30, "female"))
        assertNull(Fitness.band(47.7, 30, null))
    }
}
