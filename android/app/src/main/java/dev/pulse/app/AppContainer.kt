package dev.pulse.app

import android.content.Context
import dev.pulse.app.data.PersistentCookieJar
import dev.pulse.app.data.PulseRepository
import dev.pulse.app.data.ServerConfig

/** Manual dependency injection: one place that builds the long-lived objects. */
class AppContainer(context: Context) {
    private val app = context.applicationContext
    val config = ServerConfig(app)
    val cookies = PersistentCookieJar(app.getSharedPreferences("pulse_cookies", Context.MODE_PRIVATE))
    private val client = PulseRepository.client(cookies, BuildConfig.DEBUG)

    @Volatile private var cached: PulseRepository? = null

    /** Repository for [baseUrl], rebuilt only when the URL changes. */
    fun repository(baseUrl: String): PulseRepository =
        cached?.takeIf { it.baseUrl == baseUrl } ?: PulseRepository(baseUrl, client).also { cached = it }

    suspend fun repositoryOrNull(): PulseRepository? = config.currentUrl()?.let { repository(it) }
}
