package dev.pulse.app.data

import android.content.SharedPreferences
import androidx.core.content.edit
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/**
 * Persists the passcode session cookie (HttpOnly, HMAC-signed by the server) in app-private
 * SharedPreferences. Nothing else is stored; the cookie is only ever sent back to the server.
 */
class PersistentCookieJar(
    private val prefs: SharedPreferences,
    private val now: () -> Long = System::currentTimeMillis,
) : CookieJar {
    private val memory = mutableMapOf<String, Cookie>()

    init {
        prefs.all.forEach { (key, value) ->
            val parsed = (value as? String)?.let { decode(it) }
            if (parsed != null) memory[key] = parsed
        }
    }

    @Synchronized
    override fun saveFromResponse(
        url: HttpUrl,
        cookies: List<Cookie>,
    ) {
        prefs.edit {
            for (c in cookies) {
                val key = "${c.domain}|${c.path}|${c.name}"
                if (c.expiresAt <= now()) {
                    memory.remove(key)
                    remove(key)
                } else {
                    memory[key] = c
                    putString(key, encode(url, c))
                }
            }
        }
    }

    @Synchronized
    override fun loadForRequest(url: HttpUrl): List<Cookie> {
        val t = now()
        val expired = memory.filterValues { it.expiresAt <= t }.keys
        if (expired.isNotEmpty()) {
            prefs.edit {
                expired.forEach {
                    memory.remove(it)
                    remove(it)
                }
            }
        }
        return memory.values.filter { it.matches(url) }
    }

    @Synchronized
    fun clear() {
        memory.clear()
        prefs.edit { clear() }
    }

    private fun encode(
        url: HttpUrl,
        c: Cookie,
    ): String = "${url.scheme}://${url.host}:${url.port}/\n${c}"

    private fun decode(s: String): Cookie? {
        val (origin, header) = s.split('\n', limit = 2).takeIf { it.size == 2 } ?: return null
        val url = origin.toHttpUrlOrNull() ?: return null
        return Cookie.parse(url, header)
    }
}
