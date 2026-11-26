package dev.pulse.app

import android.content.Context
import dev.pulse.app.data.LocalRepository
import dev.pulse.app.data.Prefs
import dev.pulse.app.db.PulseDb
import dev.pulse.app.hc.HealthConnectSource
import dev.pulse.app.sync.LocalSync

/** Manual dependency injection: everything lives on the phone. */
class AppContainer(context: Context) {
    private val app = context.applicationContext
    val db: PulseDb = PulseDb.open(app)
    val prefs = Prefs(db.kv())
    val repo = LocalRepository(db, prefs)

    /** Created lazily: Health Connect may not be installed/available yet. */
    val hc: HealthConnectSource by lazy { HealthConnectSource(app) }
    val sync: LocalSync by lazy { LocalSync(db, hc, prefs) }
}
