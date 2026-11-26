package dev.pulse.app.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.store by preferencesDataStore(name = "pulse")

/** Server URL and the widget's last snapshot (JSON), in app-private DataStore. */
class ServerConfig(private val context: Context) {
    private val urlKey = stringPreferencesKey("server_url")
    private val widgetKey = stringPreferencesKey("widget_snapshot")

    val serverUrl: Flow<String?> = context.store.data.map { it[urlKey] }

    suspend fun currentUrl(): String? = serverUrl.first()

    suspend fun setUrl(url: String?) {
        context.store.edit { if (url == null) it.remove(urlKey) else it[urlKey] = url }
    }

    suspend fun widgetJson(): String? = context.store.data.first()[widgetKey]

    suspend fun setWidgetJson(json: String) {
        context.store.edit { it[widgetKey] = json }
    }
}
