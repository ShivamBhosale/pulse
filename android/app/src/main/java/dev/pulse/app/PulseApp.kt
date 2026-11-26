package dev.pulse.app

import android.app.Application
import dev.pulse.app.widget.RefreshWorker

class PulseApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
        RefreshWorker.schedule(this)
    }
}
