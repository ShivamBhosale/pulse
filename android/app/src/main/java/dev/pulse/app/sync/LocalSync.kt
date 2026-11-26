package dev.pulse.app.sync

import android.util.Log
import androidx.room.withTransaction
import dev.pulse.app.core.Azm
import dev.pulse.app.core.DeriveDaily
import dev.pulse.app.core.Derived
import dev.pulse.app.data.Prefs
import dev.pulse.app.db.DailyMetric
import dev.pulse.app.db.HrMinute
import dev.pulse.app.db.Kv
import dev.pulse.app.db.PulseDb
import dev.pulse.app.db.Steps15
import dev.pulse.app.hc.HcMapping
import dev.pulse.app.hc.HealthConnectSource
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/**
 * Health Connect → Room. Mirrors the server's design: each run re-reads a rolling window
 * (last 3 days, because the band revises recent data), replacing exactly the rows it owns in
 * that window, then recomputes the derived metrics for all history.
 */
class LocalSync(
    private val db: PulseDb,
    private val hc: HealthConnectSource,
    private val prefs: Prefs,
    private val zone: ZoneId = ZoneId.systemDefault(),
    private val now: () -> Instant = Instant::now,
) {
    companion object {
        const val LOOKBACK_DAYS = 3L
        const val IMPORT_CHUNK_DAYS = 30L
        const val MAX_IMPORT_YEARS = 5L
        private const val TAG = "PulseSync"
        private val lock = Mutex()

        /** Daily metrics this sync owns (derived keys are owned by the recompute step). */
        val OWNED =
            listOf(
                "steps", "distance_km", "calories_total", "floors",
                "sleep_min", "sleep_main_min", "sleep_in_bed_min", "sleep_efficiency",
                "sleep_deep_min", "sleep_light_min", "sleep_rem_min", "sleep_awake_min",
                "bedtime_min", "waketime_min",
                "resting_hr", "hrv_rmssd", "spo2_avg", "spo2_low", "spo2_high", "resp_rate", "skin_temp_delta",
                "azm", "azm_fat_burn", "azm_cardio", "azm_peak",
            )
    }

    fun today(): LocalDate = now().atZone(zone).toLocalDate()

    /** Incremental: last 3 days through today. */
    suspend fun syncRecent(): Int =
        lock.withLock {
            val t = today()
            val n = syncWindow(t.minusDays(LOOKBACK_DAYS), t)
            recompute()
            db.kv().put(Kv("last_sync_ms", now().toEpochMilli().toString()))
            n
        }

    /**
     * History import, newest first in 30-day chunks, resumable via the kv cursor. Stops after
     * 90 days with no steps at all (or 5 years back).
     */
    suspend fun importHistory(progress: (LocalDate, Int) -> Unit = { _, _ -> }): Int {
        // The lock is taken per chunk, so the regular 3-day sync can run in between.
        var cursor = db.kv().get("import_cursor")?.let { LocalDate.parse(it) } ?: today().plusDays(1)
        val limit = today().minusYears(MAX_IMPORT_YEARS)
        var empty = 0
        var total = 0
        while (cursor > limit && empty < 3) {
            val from = cursor.minusDays(IMPORT_CHUNK_DAYS)
            val chunkEnd = cursor.minusDays(1)
            lock.withLock {
                total += syncWindow(from, chunkEnd)
                db.kv().put(Kv("import_cursor", from.toString()))
            }
            val hadSteps = db.metrics().series("steps", from.toEpochDay(), chunkEnd.toEpochDay()).any { it.value > 0 }
            empty = if (hadSteps) 0 else empty + 1
            cursor = from
            progress(cursor, total)
        }
        lock.withLock {
            db.kv().put(Kv("import_done", "true"))
            recompute()
            db.kv().put(Kv("last_sync_ms", now().toEpochMilli().toString()))
        }
        return total
    }

    suspend fun importDone(): Boolean = db.kv().get("import_done") == "true"

    /** The app is usable once the most recent 30 days are in; older history follows. */
    suspend fun recentReady(): Boolean =
        importDone() ||
            db.kv().get("import_cursor")?.let { LocalDate.parse(it) <= today().minusDays(IMPORT_CHUNK_DAYS - 1) } == true

    suspend fun importCursor(): LocalDate? = db.kv().get("import_cursor")?.let { LocalDate.parse(it) }

    /** First 30 days only (fast); call [importHistory] afterwards for the rest. */
    suspend fun importRecent(progress: (LocalDate, Int) -> Unit = { _, _ -> }) {
        if (recentReady()) return
        lock.withLock {
            val cursor = today().plusDays(1)
            val from = cursor.minusDays(IMPORT_CHUNK_DAYS)
            val n = syncWindow(from, cursor.minusDays(1))
            db.kv().put(Kv("import_cursor", from.toString()))
            progress(from, n)
            recompute()
            db.kv().put(Kv("last_sync_ms", now().toEpochMilli().toString()))
        }
    }

    /** Fetch [from, to] (inclusive local days) and replace the rows this sync owns there. */
    suspend fun syncWindow(
        from: LocalDate,
        to: LocalDate,
    ): Int {
        val p = prefs.get()
        val start = from.atStartOfDay(zone).toInstant()
        val end = minOf(to.plusDays(1).atStartOfDay(zone).toInstant(), now())
        if (end <= start) return 0
        // Sleep ending in the window may start the evening before.
        val sleepFrom = start.minus(Duration.ofHours(18))

        val totals = hc.dailyTotals(from, to.plusDays(1))
        val hr = mutableListOf<HrMinute>()
        val steps = mutableListOf<Steps15>()
        var d = from
        while (d <= to) {
            val ds = d.atStartOfDay(zone).toInstant()
            val de = minOf(d.plusDays(1).atStartOfDay(zone).toInstant(), now())
            if (de > ds) {
                hc.hrMinutes(ds, de).forEach { hr += HrMinute(it.ts.toEpochMilli(), d.toEpochDay(), it.avg, it.min, it.max) }
                hc.steps15(ds, de).forEach { steps += Steps15(it.ts.toEpochMilli(), d.toEpochDay(), it.steps) }
            }
            d = d.plusDays(1)
        }
        val sleep = HcMapping.sleep(hc.sleep(sleepFrom, end), zone)
        val inWindow = from.toEpochDay()..to.toEpochDay()
        val sessions = sleep.sessions.filter { it.day in inWindow }
        val sessionIds = sessions.map { it.id }.toSet()
        val stages = sleep.stages.filter { it.sessionId in sessionIds }
        val metrics = mutableListOf<DailyMetric>()
        metrics += sleep.metrics.filter { it.day in inWindow }

        fun nightly(
            samples: List<dev.pulse.app.hc.HcSample>,
            put: (LocalDate, List<Double>) -> Unit,
        ) = HcMapping.nightly(samples, sleep.sessions, zone).forEach { (day, vs) -> if (day.toEpochDay() in inWindow && vs.isNotEmpty()) put(day, vs) }

        fun metric(
            day: LocalDate,
            k: String,
            v: Double?,
            unit: String,
        ) {
            if (v != null && v.isFinite()) metrics += DailyMetric(day.toEpochDay(), k, v, unit)
        }
        totals.forEach { (day, t) ->
            metric(day, "steps", t.steps, "count")
            metric(day, "distance_km", t.distanceKm, "km")
            metric(day, "calories_total", t.kcal, "kcal")
            metric(day, "floors", t.floors, "count")
        }
        nightly(hc.restingHr(sleepFrom, end)) { day, v -> metric(day, "resting_hr", v.average(), "bpm") }
        nightly(hc.hrv(sleepFrom, end)) { day, v -> metric(day, "hrv_rmssd", v.average(), "ms") }
        nightly(hc.respiratoryRate(sleepFrom, end)) { day, v -> metric(day, "resp_rate", v.average(), "brpm") }
        nightly(hc.skinTempDelta(sleepFrom, end)) { day, v -> metric(day, "skin_temp_delta", v.average(), "°C") }
        nightly(hc.spo2(sleepFrom, end)) { day, v ->
            metric(day, "spo2_avg", v.average(), "%")
            metric(day, "spo2_low", v.min(), "%")
            metric(day, "spo2_high", v.max(), "%")
        }
        val exercises = HcMapping.exercises(hc.exercises(start, end), zone)

        // Active zone minutes from heart rate (Health Connect has no AZM record).
        val rhrHistory = db.metrics().series("resting_hr", from.minusDays(28).toEpochDay(), to.toEpochDay()).associate { it.day to it.value }
        val rhrWindow = metrics.filter { it.metric == "resting_hr" }.associate { it.day to it.value }
        val age = prefs.age(p, to.year)
        hr.groupBy { it.day }.forEach { (day, mins) ->
            val rhr = rhrWindow[day] ?: rhrHistory[day] ?: rhrHistory.values.takeIf { it.isNotEmpty() }?.let { Derived.median(it.toList()) } ?: 60.0
            val azm = Azm.minutes(mins.map { it.avg }, Azm.zones(age, rhr))
            val ld = LocalDate.ofEpochDay(day)
            metric(ld, "azm", azm.total.toDouble(), "min")
            metric(ld, "azm_fat_burn", azm.fatBurn.toDouble(), "min")
            metric(ld, "azm_cardio", azm.cardio.toDouble(), "min")
            metric(ld, "azm_peak", azm.peak.toDouble(), "min")
        }

        db.withTransaction {
            val a = from.toEpochDay()
            val b = to.toEpochDay()
            db.metrics().clear(OWNED, a, b)
            db.intraday().clearHr(a, b)
            db.intraday().clearSteps(a, b)
            db.sleep().clear(a, b)
            db.exercises().clear(a, b)
            db.metrics().upsert(metrics)
            db.intraday().upsertHr(hr)
            db.intraday().upsertSteps(steps)
            db.sleep().upsertSessions(sessions)
            db.sleep().upsertStages(stages)
            db.exercises().upsert(exercises)
        }
        // Premium daily metrics (sleep score, sleep need, stress) for the window's days.
        val premium = mutableListOf<DailyMetric>()
        var pd = from
        while (pd <= to) {
            premium += dev.pulse.app.data.Premium.rows(db, pd, p, zone, prefs.age(p, pd.year))
            pd = pd.plusDays(1)
        }
        db.withTransaction {
            db.metrics().clear(dev.pulse.app.data.Premium.DAILY_KEYS, from.toEpochDay(), to.toEpochDay())
            db.metrics().upsert(premium)
        }
        Log.i(TAG, "window $from..$to: ${metrics.size} metrics, ${hr.size} hr min, ${sessions.size} sleeps")
        return metrics.size + hr.size + steps.size + sessions.size
    }

    /** One-time: premium rows for every day already stored (data synced before premium existed). */
    suspend fun backfillPremium() {
        if (db.kv().get("premium_v1") == "done") return
        val p = prefs.get()
        val spans = db.metrics().available().associateBy { it.metric }
        val first = spans["steps"]?.firstDay?.let { LocalDate.ofEpochDay(it) } ?: return
        var d = today()
        while (d >= first) {
            val chunkFrom = maxOf(first, d.minusDays(29))
            lock.withLock {
                val rows = mutableListOf<DailyMetric>()
                var x = chunkFrom
                while (x <= d) {
                    rows += dev.pulse.app.data.Premium.rows(db, x, p, zone, prefs.age(p, x.year))
                    x = x.plusDays(1)
                }
                db.withTransaction {
                    db.metrics().clear(dev.pulse.app.data.Premium.DAILY_KEYS, chunkFrom.toEpochDay(), d.toEpochDay())
                    db.metrics().upsert(rows)
                }
            }
            d = chunkFrom.minusDays(1)
        }
        lock.withLock { recompute() }
        db.kv().put(Kv("premium_v1", "done"))
        Log.i(TAG, "premium backfill done from $first")
    }

    /** Recompute all derived daily metrics (milliseconds for a few years of days). */
    suspend fun recompute() {
        val p = prefs.get()
        val inputs = listOf("azm", "calories_total", "calories_active", "sleep_main_min", "bedtime_min", "waketime_min", "hrv_rmssd", "resting_hr")
        val series = inputs.associateWith { k -> db.metrics().all(k).associate { LocalDate.ofEpochDay(it.day) to it.value } }
        val rows = DeriveDaily.derive(series, p.goals.sleepMin.toDouble(), p.weights)
        val vo2 = dev.pulse.app.data.Premium.vo2Rows(series["resting_hr"].orEmpty(), prefs.age(p, today().year))
        db.withTransaction {
            db.metrics().clearAll(DeriveDaily.UNITS.keys.toList() + "vo2max")
            db.metrics().upsert(rows.map { DailyMetric(it.date.toEpochDay(), it.metric, it.value, DeriveDaily.UNITS.getValue(it.metric)) })
            db.metrics().upsert(vo2)
        }
    }
}
