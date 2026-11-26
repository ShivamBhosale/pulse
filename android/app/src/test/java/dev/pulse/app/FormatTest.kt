package dev.pulse.app

import dev.pulse.app.util.Fmt
import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.Instant
import java.time.ZoneId
import java.util.Locale

class FormatTest {
    @Test fun durations() {
        assertEquals("5h 01m", Fmt.duration(301.0))
        assertEquals("8h", Fmt.duration(480.0))
        assertEquals("45m", Fmt.duration(45.0))
        assertEquals("–", Fmt.duration(null))
    }

    @Test fun clockWrapsAroundMidnight() {
        assertEquals("23:40", Fmt.clock(-20.0))
        assertEquals("01:00", Fmt.clock(1500.0))
        assertEquals("00:00", Fmt.clock(0.0))
    }

    @Test fun numbersAndSigns() {
        assertEquals("31,737", Fmt.num(31737.0, locale = Locale.US))
        assertEquals("53.7", Fmt.num(53.66, 1, Locale.US))
        assertEquals("–", Fmt.num(null))
        assertEquals("−3", Fmt.signed(-3.0).replace(" ", ""))
    }

    @Test fun timesAndAgo() {
        assertEquals("12:21", Fmt.time("2026-11-22T17:21:00+00:00", ZoneId.of("America/New_York")))
        assertEquals("12:21", Fmt.time("2026-11-22T17:21:00Z", ZoneId.of("America/New_York")))
        val now = Instant.parse("2026-11-22T17:30:00Z")
        assertEquals("9 min ago", Fmt.ago("2026-11-22T17:21:00Z", now))
        assertEquals("never", Fmt.ago(null, now))
    }
}
