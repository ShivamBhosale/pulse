package dev.pulse.app

import dev.pulse.api.models.WidgetSnapshot
import dev.pulse.app.data.PulseJson
import dev.pulse.app.widget.WidgetMapper
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class WidgetMapperTest {
    private val snapshot =
        PulseJson.decodeFromString(
            WidgetSnapshot.serializer(),
            javaClass.getResource("/fixtures/widget.json")!!.readText(),
        )

    @Test fun mapsSnapshot() {
        val v = WidgetMapper.map(snapshot)
        assertEquals("of 10,000".replace(",", ""), v.stepsGoal.replace(",", "").replace(" ", "").replace(".", ""))
        assertEquals(true, v.stepsProgress in 0f..1f)
        assertEquals("Reconnect Google in Pulse", v.warning) // test server has no token
    }

    @Test fun progressIsClamped() {
        val v = WidgetMapper.map(snapshot.copy(steps = 25_000.0, stepsGoal = 10_000, authOk = true))
        assertEquals(1f, v.stepsProgress)
        assertNull(v.warning)
    }

    @Test fun noSnapshotYet() {
        val v = WidgetMapper.map(null)
        assertEquals("–", v.readiness)
        assertEquals("Open Pulse to connect", v.readinessLabel)
    }
}
