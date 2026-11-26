package dev.pulse.app.data

import dev.pulse.api.apis.DashboardApi
import dev.pulse.api.apis.JournalApi
import dev.pulse.api.apis.MetaApi
import dev.pulse.api.apis.SessionApi
import dev.pulse.api.apis.SleepApi
import dev.pulse.api.models.Journal
import dev.pulse.api.models.JournalIn
import dev.pulse.api.models.PasscodeIn
import dev.pulse.api.models.SessionState
import dev.pulse.api.models.SleepNight
import dev.pulse.api.models.Status
import dev.pulse.api.models.TagOut
import dev.pulse.api.models.Today
import dev.pulse.api.models.WidgetSnapshot
import kotlinx.coroutines.delay
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.io.IOException
import java.util.concurrent.TimeUnit

/** Outcome of one API call, with the states the UI cares about. */
sealed interface ApiResult<out T> {
    data class Ok<T>(val value: T) : ApiResult<T>

    /** The server has a passcode and this device has no valid session. */
    data object Locked : ApiResult<Nothing>

    /** Couldn't reach the server (Tailscale off, server down, wrong address). */
    data class Offline(val message: String) : ApiResult<Nothing>

    data class Failed(val code: Int, val message: String) : ApiResult<Nothing>
}

val PulseJson =
    Json {
        ignoreUnknownKeys = true // tolerate newer servers adding fields
        explicitNulls = false
        coerceInputValues = true
    }

/** All network access goes through here. One instance per server URL. */
class PulseRepository(
    val baseUrl: String,
    client: OkHttpClient,
) {
    private val retrofit =
        Retrofit
            .Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(PulseJson.asConverterFactory("application/json".toMediaType()))
            .build()

    private val dashboard = retrofit.create(DashboardApi::class.java)
    private val meta = retrofit.create(MetaApi::class.java)
    private val session = retrofit.create(SessionApi::class.java)
    private val sleep = retrofit.create(SleepApi::class.java)
    private val journal = retrofit.create(JournalApi::class.java)

    suspend fun health() = call { meta.getHealth() }

    suspend fun sessionState(): ApiResult<SessionState> = call { session.getSessionState() }

    suspend fun unlock(passcode: String): ApiResult<Unit> =
        when (val r = call { session.unlock(PasscodeIn(passcode)) }) {
            is ApiResult.Ok -> ApiResult.Ok(Unit)
            is ApiResult.Failed -> if (r.code == 401) ApiResult.Locked else r
            is ApiResult.Locked -> r
            is ApiResult.Offline -> r
        }

    suspend fun today(): ApiResult<Today> = call { dashboard.getToday() }

    suspend fun widget(): ApiResult<WidgetSnapshot> = call { dashboard.getWidget() }

    suspend fun status(): ApiResult<Status> = call { meta.getStatus() }

    suspend fun sleep(date: String?): ApiResult<SleepNight> = call { sleep.getSleep(date) }

    suspend fun tags(): ApiResult<List<TagOut>> = call { journal.listTags() }

    suspend fun journal(date: String): ApiResult<Journal> = call { journal.getJournal(date) }

    suspend fun putJournal(
        date: String,
        tags: List<String>,
        note: String,
    ): ApiResult<Journal> = call { journal.putJournal(date, JournalIn(tags = tags, note = note)) }

    /**
     * Ask the server to sync now, then poll /status until it's done (or [timeoutMs] passes).
     * The server does the Google calls; the phone only waits.
     */
    suspend fun syncAndWait(
        pollMs: Long = 1_500,
        timeoutMs: Long = 90_000,
    ): ApiResult<Unit> {
        when (val started = call { meta.triggerSync() }) {
            is ApiResult.Ok -> Unit
            is ApiResult.Locked -> return started
            is ApiResult.Offline -> return started
            is ApiResult.Failed -> return started
        }
        var waited = 0L
        while (waited < timeoutMs) {
            delay(pollMs)
            waited += pollMs
            when (val st = status()) {
                is ApiResult.Ok -> if (!st.value.syncing) return ApiResult.Ok(Unit)
                is ApiResult.Locked -> return st
                is ApiResult.Offline -> return st
                is ApiResult.Failed -> return st
            }
        }
        return ApiResult.Ok(Unit) // still running in the background; show what's there
    }

    private suspend fun <T> call(block: suspend () -> Response<T>): ApiResult<T> =
        try {
            val r = block()
            when {
                r.isSuccessful -> {
                    @Suppress("UNCHECKED_CAST")
                    ApiResult.Ok((r.body() ?: Unit) as T)
                }
                r.code() == 401 && !r.raw().request.url.encodedPath.endsWith("/session") ->
                    ApiResult.Locked
                else -> ApiResult.Failed(r.code(), errorDetail(r))
            }
        } catch (e: IOException) {
            ApiResult.Offline(e.message ?: "Can't reach the server")
        } catch (e: kotlinx.serialization.SerializationException) {
            ApiResult.Failed(-1, "The server sent data this app version doesn't understand (${e.message?.take(160)})")
        }

    private fun errorDetail(r: Response<*>): String {
        val body = r.errorBody()?.string().orEmpty()
        val detail = Regex("\"detail\"\\s*:\\s*\"([^\"]+)\"").find(body)?.groupValues?.get(1)
        return detail ?: "HTTP ${r.code()}"
    }

    companion object {
        fun client(
            cookies: PersistentCookieJar?,
            debug: Boolean,
        ): OkHttpClient {
            val b =
                OkHttpClient
                    .Builder()
                    .connectTimeout(8, TimeUnit.SECONDS)
                    .readTimeout(30, TimeUnit.SECONDS)
            if (cookies != null) b.cookieJar(cookies)
            if (debug) {
                val log = okhttp3.logging.HttpLoggingInterceptor()
                log.level = okhttp3.logging.HttpLoggingInterceptor.Level.BASIC // no headers/bodies
                b.addInterceptor(log)
            }
            return b.build()
        }
    }
}
