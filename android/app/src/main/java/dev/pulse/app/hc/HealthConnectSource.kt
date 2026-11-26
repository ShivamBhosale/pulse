package dev.pulse.app.hc

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.HealthConnectFeatures
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.FloorsClimbedRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.HeartRateVariabilityRmssdRecord
import androidx.health.connect.client.records.OxygenSaturationRecord
import androidx.health.connect.client.records.Record
import androidx.health.connect.client.records.RespiratoryRateRecord
import androidx.health.connect.client.records.RestingHeartRateRecord
import androidx.health.connect.client.records.SkinTemperatureRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.TotalCaloriesBurnedRecord
import androidx.health.connect.client.request.AggregateGroupByDurationRequest
import androidx.health.connect.client.request.AggregateGroupByPeriodRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.Period
import java.time.ZoneId
import kotlin.reflect.KClass

/** Pulse's view of Health Connect: plain data classes, no Health Connect types leak out. */
object Hc {
    const val FITBIT = "com.fitbit.FitbitMobile"
    const val GOOGLE_HEALTH = "com.google.android.apps.fitness"

    /** Lower is preferred: the band's own app first, like the server's Fitbit-first rule. */
    fun priority(pkg: String): Int =
        when (pkg) {
            FITBIT -> 0
            GOOGLE_HEALTH -> 1
            else -> 2
        }

    val READ_TYPES: List<KClass<out Record>> =
        listOf(
            StepsRecord::class,
            DistanceRecord::class,
            TotalCaloriesBurnedRecord::class,
            FloorsClimbedRecord::class,
            HeartRateRecord::class,
            HeartRateVariabilityRmssdRecord::class,
            RestingHeartRateRecord::class,
            SleepSessionRecord::class,
            OxygenSaturationRecord::class,
            RespiratoryRateRecord::class,
            SkinTemperatureRecord::class,
            ExerciseSessionRecord::class,
        )

    val PERMISSIONS: Set<String> =
        READ_TYPES.map { HealthPermission.getReadPermission(it) }.toSet() +
            setOf(
                HealthPermission.PERMISSION_READ_HEALTH_DATA_HISTORY,
                HealthPermission.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND,
            )

    /** Without these Pulse can't work; everything else is optional and shown as missing. */
    val REQUIRED: Set<String> =
        setOf(StepsRecord::class, HeartRateRecord::class, SleepSessionRecord::class)
            .map { HealthPermission.getReadPermission(it) }
            .toSet()

    fun status(context: Context): Int = HealthConnectClient.getSdkStatus(context)
}

data class DailyTotals(val steps: Double?, val distanceKm: Double?, val kcal: Double?, val floors: Double?)

data class MinuteHr(val ts: Instant, val avg: Double, val min: Double, val max: Double)

data class SlotSteps(val ts: Instant, val steps: Double)

data class HcStage(val stage: String, val start: Instant, val end: Instant)

data class HcSleep(val id: String, val start: Instant, val end: Instant, val source: String, val stages: List<HcStage>)

data class HcSample(val time: Instant, val value: Double, val source: String)

data class HcExercise(val id: String, val start: Instant, val end: Instant, val type: Int, val title: String?, val source: String)

class HealthConnectSource(context: Context) {
    private val client = HealthConnectClient.getOrCreate(context)

    suspend fun granted(): Set<String> = client.permissionController.getGrantedPermissions()

    fun skinTempAvailable(): Boolean =
        client.features.getFeatureStatus(HealthConnectFeatures.FEATURE_SKIN_TEMPERATURE) ==
            HealthConnectFeatures.FEATURE_STATUS_AVAILABLE

    /** Deduplicated daily totals per local day (Health Connect applies source priority). */
    suspend fun dailyTotals(
        from: LocalDate,
        toExclusive: LocalDate,
    ): Map<LocalDate, DailyTotals> {
        val rows =
            client.aggregateGroupByPeriod(
                AggregateGroupByPeriodRequest(
                    metrics =
                        setOf(
                            StepsRecord.COUNT_TOTAL,
                            DistanceRecord.DISTANCE_TOTAL,
                            TotalCaloriesBurnedRecord.ENERGY_TOTAL,
                            FloorsClimbedRecord.FLOORS_CLIMBED_TOTAL,
                        ),
                    timeRangeFilter = TimeRangeFilter.between(from.atStartOfDay(), toExclusive.atStartOfDay()),
                    timeRangeSlicer = Period.ofDays(1),
                ),
            )
        return rows.associate { r ->
            r.startTime.toLocalDate() to
                DailyTotals(
                    steps = r.result[StepsRecord.COUNT_TOTAL]?.toDouble(),
                    distanceKm = r.result[DistanceRecord.DISTANCE_TOTAL]?.inKilometers,
                    kcal = r.result[TotalCaloriesBurnedRecord.ENERGY_TOTAL]?.inKilocalories,
                    floors = r.result[FloorsClimbedRecord.FLOORS_CLIMBED_TOTAL],
                )
        }
    }

    /** Heart rate aggregated per minute for [from, to). Call per day (≤ 1,500 buckets). */
    suspend fun hrMinutes(
        from: Instant,
        to: Instant,
    ): List<MinuteHr> =
        client
            .aggregateGroupByDuration(
                AggregateGroupByDurationRequest(
                    metrics = setOf(HeartRateRecord.BPM_AVG, HeartRateRecord.BPM_MIN, HeartRateRecord.BPM_MAX),
                    timeRangeFilter = TimeRangeFilter.between(from, to),
                    timeRangeSlicer = Duration.ofMinutes(1),
                ),
            ).mapNotNull { r ->
                val avg = r.result[HeartRateRecord.BPM_AVG] ?: return@mapNotNull null
                MinuteHr(
                    r.startTime,
                    avg.toDouble(),
                    (r.result[HeartRateRecord.BPM_MIN] ?: avg).toDouble(),
                    (r.result[HeartRateRecord.BPM_MAX] ?: avg).toDouble(),
                )
            }

    suspend fun steps15(
        from: Instant,
        to: Instant,
    ): List<SlotSteps> =
        client
            .aggregateGroupByDuration(
                AggregateGroupByDurationRequest(
                    metrics = setOf(StepsRecord.COUNT_TOTAL),
                    timeRangeFilter = TimeRangeFilter.between(from, to),
                    timeRangeSlicer = Duration.ofMinutes(15),
                ),
            ).mapNotNull { r -> r.result[StepsRecord.COUNT_TOTAL]?.let { SlotSteps(r.startTime, it.toDouble()) } }

    private suspend fun <T : Record> readAll(
        type: KClass<T>,
        from: Instant,
        to: Instant,
    ): List<T> {
        val out = mutableListOf<T>()
        var token: String? = null
        do {
            val resp =
                client.readRecords(
                    ReadRecordsRequest(type, TimeRangeFilter.between(from, to), pageSize = 1000, pageToken = token),
                )
            out += resp.records
            token = resp.pageToken
        } while (token != null)
        return out
    }

    suspend fun sleep(
        from: Instant,
        to: Instant,
    ): List<HcSleep> =
        readAll(SleepSessionRecord::class, from, to).map { s ->
            HcSleep(
                id = s.metadata.id,
                start = s.startTime,
                end = s.endTime,
                source = s.metadata.dataOrigin.packageName,
                stages = s.stages.mapNotNull { st -> stageName(st.stage)?.let { HcStage(it, st.startTime, st.endTime) } },
            )
        }

    suspend fun hrv(
        from: Instant,
        to: Instant,
    ) = readAll(HeartRateVariabilityRmssdRecord::class, from, to).map {
        HcSample(it.time, it.heartRateVariabilityMillis, it.metadata.dataOrigin.packageName)
    }

    suspend fun restingHr(
        from: Instant,
        to: Instant,
    ) = readAll(RestingHeartRateRecord::class, from, to).map {
        HcSample(it.time, it.beatsPerMinute.toDouble(), it.metadata.dataOrigin.packageName)
    }

    suspend fun spo2(
        from: Instant,
        to: Instant,
    ) = readAll(OxygenSaturationRecord::class, from, to).map {
        HcSample(it.time, it.percentage.value, it.metadata.dataOrigin.packageName)
    }

    suspend fun respiratoryRate(
        from: Instant,
        to: Instant,
    ) = readAll(RespiratoryRateRecord::class, from, to).map {
        HcSample(it.time, it.rate, it.metadata.dataOrigin.packageName)
    }

    /** Skin temperature: one value per record = mean delta from the device's baseline (°C). */
    suspend fun skinTempDelta(
        from: Instant,
        to: Instant,
    ): List<HcSample> {
        if (!skinTempAvailable()) return emptyList()
        return readAll(SkinTemperatureRecord::class, from, to).mapNotNull { r ->
            if (r.deltas.isEmpty()) return@mapNotNull null
            HcSample(r.endTime, r.deltas.map { it.delta.inCelsius }.average(), r.metadata.dataOrigin.packageName)
        }
    }

    suspend fun exercises(
        from: Instant,
        to: Instant,
    ) = readAll(ExerciseSessionRecord::class, from, to).map {
        HcExercise(it.metadata.id, it.startTime, it.endTime, it.exerciseType, it.title, it.metadata.dataOrigin.packageName)
    }

    companion object {
        fun stageName(type: Int): String? =
            when (type) {
                SleepSessionRecord.STAGE_TYPE_DEEP -> "DEEP"
                SleepSessionRecord.STAGE_TYPE_LIGHT, SleepSessionRecord.STAGE_TYPE_SLEEPING -> "LIGHT"
                SleepSessionRecord.STAGE_TYPE_REM -> "REM"
                SleepSessionRecord.STAGE_TYPE_AWAKE, SleepSessionRecord.STAGE_TYPE_AWAKE_IN_BED,
                SleepSessionRecord.STAGE_TYPE_OUT_OF_BED,
                -> "AWAKE"
                else -> null
            }

        fun localDay(
            t: Instant,
            zone: ZoneId,
        ): LocalDate = t.atZone(zone).toLocalDate()
    }
}
