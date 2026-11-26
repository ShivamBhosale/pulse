package dev.pulse.app

import dev.pulse.api.models.SummarySentence
import dev.pulse.api.models.Tile
import dev.pulse.app.data.ApiResult
import dev.pulse.app.data.PulseRepository
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** Decodes fixtures dumped from the server's own synthetic test data (scripts/android_fixtures.py). */
class RepositoryTest {
    private lateinit var server: MockWebServer
    private lateinit var repo: PulseRepository

    private fun fixture(name: String) = javaClass.getResource("/fixtures/$name")!!.readText()

    private fun json(body: String) = MockResponse().setHeader("Content-Type", "application/json").setBody(body)

    @Before fun setUp() {
        server = MockWebServer()
        server.start()
        repo = PulseRepository(server.url("/").toString(), PulseRepository.client(null, debug = false))
    }

    @After fun tearDown() = server.shutdown()

    @Test fun decodesToday() =
        runTest {
            server.enqueue(json(fixture("today.json")))
            val r = repo.today()
            assertTrue("$r", r is ApiResult.Ok)
            val today = (r as ApiResult.Ok).value
            assertEquals(listOf("readiness", "sleep_main_min", "resting_hr", "hrv_rmssd", "steps", "azm"), today.tiles.map { it.key })
            assertTrue(today.tiles.all { it.status in Tile.Status.entries })
            assertTrue(today.summary.headline.isNotBlank())
            assertTrue(today.summary.sentences.all { it.tone in SummarySentence.Tone.entries })
            assertEquals("/api/v1/today", server.takeRequest().path)
        }

    @Test fun decodesSleepWidgetTagsJournalStatus() =
        runTest {
            listOf("sleep.json", "widget.json", "tags.json", "journal.json", "status.json").forEach { server.enqueue(json(fixture(it))) }
            assertNotNull((repo.sleep(null) as ApiResult.Ok).value.session)
            val w = (repo.widget() as ApiResult.Ok).value
            assertEquals(10_000, w.stepsGoal)
            val tags = (repo.tags() as ApiResult.Ok).value
            assertTrue(tags.any { it.key == "alcohol" })
            assertEquals(listOf("alcohol"), (repo.journal("2026-11-20") as ApiResult.Ok).value.tags)
            assertNotNull((repo.status() as ApiResult.Ok).value.auth)
        }

    @Test fun passcode401IsLocked() =
        runTest {
            server.enqueue(MockResponse().setResponseCode(401).setBody("{\"detail\":\"passcode required\"}"))
            assertEquals(ApiResult.Locked, repo.today())
        }

    @Test fun wrongPasscodeIsLockedAndTooManyIsFailed() =
        runTest {
            server.enqueue(MockResponse().setResponseCode(401).setBody("{\"detail\":\"wrong passcode\"}"))
            assertEquals(ApiResult.Locked, repo.unlock("0000"))
            server.enqueue(MockResponse().setResponseCode(429).setBody("{\"detail\":\"too many attempts\"}"))
            val r = repo.unlock("0000")
            assertTrue(r is ApiResult.Failed && r.code == 429 && r.message == "too many attempts")
        }

    @Test fun unlockSucceedsOn204() =
        runTest {
            server.enqueue(MockResponse().setResponseCode(204))
            assertEquals(ApiResult.Ok(Unit), repo.unlock("1234"))
        }

    @Test fun offlineWhenServerIsDown() =
        runTest {
            server.shutdown()
            assertTrue(repo.health() is ApiResult.Offline)
        }

    @Test fun syncPollsStatusUntilDone() =
        runTest {
            val status = fixture("status.json")
            var polls = 0
            server.dispatcher =
                object : Dispatcher() {
                    override fun dispatch(request: RecordedRequest): MockResponse =
                        when (request.path) {
                            "/api/v1/sync" -> json("{\"status\":\"started\"}").setResponseCode(202)
                            "/api/v1/status" -> {
                                polls++
                                json(status.replace("\"syncing\": false", "\"syncing\": ${polls < 3}"))
                            }
                            else -> MockResponse().setResponseCode(404)
                        }
                }
            assertEquals(ApiResult.Ok(Unit), repo.syncAndWait(pollMs = 1, timeoutMs = 1_000))
            assertEquals(3, polls)
        }
}
