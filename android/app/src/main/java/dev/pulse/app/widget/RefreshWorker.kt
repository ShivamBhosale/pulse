package dev.pulse.app.widget

import android.content.Context
import android.os.Build
import android.util.Log
import androidx.glance.appwidget.updateAll
import androidx.health.connect.client.HealthConnectClient
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import dev.pulse.api.models.WidgetSnapshot
import dev.pulse.app.PulseApp
import dev.pulse.app.data.PulseJson
import dev.pulse.app.db.Kv
import dev.pulse.app.hc.Hc
import java.util.concurrent.TimeUnit

/**
 * Reads the last 3 days from Health Connect into Room, recomputes, and redraws the widget.
 * Battery rules: every 30 minutes, never when the battery is low; no network, no wake locks.
 */
class RefreshWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val c = (applicationContext as PulseApp).container
        if (Hc.status(applicationContext) != HealthConnectClient.SDK_AVAILABLE) return Result.success()
        return try {
            if (c.sync.importDone()) c.sync.syncRecent()
            val snap = c.repo.widget()
            c.db.kv().put(Kv("widget_snapshot", PulseJson.encodeToString(WidgetSnapshot.serializer(), snap)))
            PulseWidget().updateAll(applicationContext)
            Result.success()
        } catch (e: SecurityException) {
            Log.w("PulseWorker", "Health Connect permission missing: ${e.message}")
            Result.success()
        } catch (e: Exception) {
            Log.w("PulseWorker", "refresh failed", e)
            Result.retry()
        }
    }

    companion object {
        private const val PERIODIC = "pulse-widget-refresh"
        private const val NOW = "pulse-widget-refresh-now"

        fun schedule(context: Context) {
            val req =
                PeriodicWorkRequestBuilder<RefreshWorker>(30, TimeUnit.MINUTES)
                    .setConstraints(Constraints.Builder().setRequiresBatteryNotLow(true).build())
                    .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.UPDATE, req)
        }

        fun refreshNow(context: Context) {
            val b = OneTimeWorkRequestBuilder<RefreshWorker>()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) b.setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
            WorkManager.getInstance(context).enqueueUniqueWork(NOW, ExistingWorkPolicy.REPLACE, b.build())
        }
    }
}
