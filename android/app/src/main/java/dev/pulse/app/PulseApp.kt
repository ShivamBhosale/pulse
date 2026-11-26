package dev.pulse.app

import android.app.Application
import android.util.Log
import androidx.health.connect.client.HealthConnectClient
import dev.pulse.app.hc.Hc
import dev.pulse.app.widget.RefreshWorker
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class PulseApp : Application() {
    lateinit var container: AppContainer
        private set

    /** App-wide scope for the background history import (lives while the process does). */
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var importJob: Job? = null
    private val _importing = MutableStateFlow<String?>(null)

    /** Null when idle, otherwise "back to <date>". */
    val importing: StateFlow<String?> = _importing

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
        RefreshWorker.schedule(this)
    }

    /** Continue importing older history in the background; resumable, idempotent. */
    fun continueImport() {
        if (importJob?.isActive == true) return
        importJob =
            scope.launch {
                try {
                    if (Hc.status(this@PulseApp) != HealthConnectClient.SDK_AVAILABLE) return@launch
                    if (!container.sync.recentReady()) return@launch
                    container.sync.backfillPremium()
                    if (container.sync.importDone()) return@launch
                    _importing.value = container.sync.importCursor()?.toString()
                    container.sync.importHistory { cursor, _ -> _importing.value = cursor.toString() }
                } catch (e: Exception) {
                    Log.w("PulseSync", "background import paused: ${e.message}")
                } finally {
                    _importing.value = null
                }
            }
    }
}
