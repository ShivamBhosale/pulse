package dev.pulse.app.widget

import android.content.Context
import android.os.Build
import androidx.glance.appwidget.updateAll
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import dev.pulse.api.models.WidgetSnapshot
import dev.pulse.app.PulseApp
import dev.pulse.app.data.ApiResult
import dev.pulse.app.data.PulseJson
import java.util.concurrent.TimeUnit

/**
 * Fetches the compact /widget snapshot and redraws the widget. Battery rules: periodic every
 * 30 minutes, only with a network and never when the battery is low; no wake locks, no
 * foreground service. Also runs once whenever the app opens.
 */
class RefreshWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val container = (applicationContext as PulseApp).container
        val repo = container.repositoryOrNull() ?: return Result.success() // not set up yet
        return when (val r = repo.widget()) {
            is ApiResult.Ok -> {
                container.config.setWidgetJson(PulseJson.encodeToString(WidgetSnapshot.serializer(), r.value))
                PulseWidget().updateAll(applicationContext)
                Result.success()
            }
            is ApiResult.Offline -> Result.retry() // Tailscale off / server asleep; WorkManager backs off
            else -> Result.success() // locked or server error: keep the last snapshot
        }
    }

    companion object {
        private const val PERIODIC = "pulse-widget-refresh"
        private const val NOW = "pulse-widget-refresh-now"

        private val constraints =
            Constraints
                .Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .setRequiresBatteryNotLow(true)
                .build()

        fun schedule(context: Context) {
            val req =
                PeriodicWorkRequestBuilder<RefreshWorker>(30, TimeUnit.MINUTES)
                    .setConstraints(constraints)
                    .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.KEEP, req)
        }

        /** When the app opens: expedited (no deferral), only needs a network. */
        fun refreshNow(context: Context) {
            val b =
                OneTimeWorkRequestBuilder<RefreshWorker>()
                    .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            // Expedited jobs need no foreground notification from Android 12; older versions
            // just run it as normal work.
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                b.setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
            }
            val req = b.build()
            WorkManager.getInstance(context).enqueueUniqueWork(NOW, ExistingWorkPolicy.REPLACE, req)
        }
    }
}
