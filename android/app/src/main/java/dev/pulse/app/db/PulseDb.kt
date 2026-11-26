package dev.pulse.app.db

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.Transaction
import androidx.room.Upsert

/*
 * On-phone store. Mirrors the server's tables (src/pulse/models.py) so the maths ports
 * one-to-one. Dates are LocalDate.toEpochDay(); instants are epoch milliseconds (UTC).
 * Lives in app-private storage and is excluded from backup (see data_extraction_rules.xml).
 */

@Entity(tableName = "daily_metrics", primaryKeys = ["day", "metric"], indices = [Index("metric", "day")])
data class DailyMetric(val day: Long, val metric: String, val value: Double, val unit: String)

@Entity(tableName = "hr_minute", indices = [Index("day")])
data class HrMinute(@PrimaryKey val ts: Long, val day: Long, val avg: Double, val min: Double, val max: Double)

@Entity(tableName = "steps_15m", indices = [Index("day")])
data class Steps15(@PrimaryKey val ts: Long, val day: Long, val steps: Double)

@Entity(tableName = "sleep_sessions", indices = [Index("day")])
data class SleepSession(
    @PrimaryKey val id: String,
    val day: Long, // local wake date
    val start: Long,
    val end: Long,
    val isMain: Boolean,
    val asleepMin: Int,
    val awakeMin: Int,
    val deepMin: Int?,
    val lightMin: Int?,
    val remMin: Int?,
    val latencyMin: Int,
    val interruptions: Int,
    val source: String,
)

@Entity(
    tableName = "sleep_stages",
    indices = [Index("sessionId")],
    foreignKeys = [ForeignKey(SleepSession::class, ["id"], ["sessionId"], onDelete = ForeignKey.CASCADE)],
)
data class SleepStage(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val sessionId: String,
    val stage: String,
    val start: Long,
    val end: Long,
)

@Entity(tableName = "exercises", indices = [Index("day")])
data class Exercise(
    @PrimaryKey val id: String,
    val day: Long,
    val start: Long,
    val end: Long,
    val type: String,
    val title: String?,
    val source: String,
)

@Entity(tableName = "tags")
data class Tag(@PrimaryKey val key: String, val label: String, val kind: String, val archived: Boolean, val sort: Int)

@Entity(
    tableName = "day_tags",
    primaryKeys = ["day", "tagKey"],
    indices = [Index("tagKey")],
    foreignKeys = [ForeignKey(Tag::class, ["key"], ["tagKey"], onDelete = ForeignKey.CASCADE)],
)
data class DayTag(val day: Long, val tagKey: String)

@Entity(tableName = "day_notes")
data class DayNote(@PrimaryKey val day: Long, val text: String)

@Entity(tableName = "kv")
data class Kv(@PrimaryKey val key: String, val value: String)

data class DayValue(val day: Long, val value: Double)

data class DayCount(val day: Long, val n: Int)

@Dao
interface MetricsDao {
    @Upsert suspend fun upsert(rows: List<DailyMetric>)

    @Query("DELETE FROM daily_metrics WHERE metric IN (:metrics) AND day BETWEEN :from AND :to")
    suspend fun clear(
        metrics: List<String>,
        from: Long,
        to: Long,
    )

    @Query("DELETE FROM daily_metrics WHERE metric IN (:metrics)")
    suspend fun clearAll(metrics: List<String>)

    @Query("SELECT day, value FROM daily_metrics WHERE metric = :metric AND day BETWEEN :from AND :to ORDER BY day")
    suspend fun series(
        metric: String,
        from: Long,
        to: Long,
    ): List<DayValue>

    @Query("SELECT day, value FROM daily_metrics WHERE metric = :metric ORDER BY day")
    suspend fun all(metric: String): List<DayValue>

    @Query("SELECT metric, COUNT(*) AS n, MIN(day) AS firstDay, MAX(day) AS lastDay FROM daily_metrics GROUP BY metric")
    suspend fun available(): List<MetricSpan>

    @Query("SELECT * FROM daily_metrics WHERE day = :day")
    suspend fun day(day: Long): List<DailyMetric>
}

data class MetricSpan(val metric: String, val n: Int, val firstDay: Long, val lastDay: Long)

@Dao
interface IntradayDao {
    @Upsert suspend fun upsertHr(rows: List<HrMinute>)

    @Upsert suspend fun upsertSteps(rows: List<Steps15>)

    @Query("DELETE FROM hr_minute WHERE day BETWEEN :from AND :to")
    suspend fun clearHr(
        from: Long,
        to: Long,
    )

    @Query("DELETE FROM steps_15m WHERE day BETWEEN :from AND :to")
    suspend fun clearSteps(
        from: Long,
        to: Long,
    )

    @Query("SELECT * FROM hr_minute WHERE ts >= :from AND ts < :to ORDER BY ts")
    suspend fun hr(
        from: Long,
        to: Long,
    ): List<HrMinute>

    @Query("SELECT * FROM steps_15m WHERE day BETWEEN :from AND :to ORDER BY ts")
    suspend fun steps(
        from: Long,
        to: Long,
    ): List<Steps15>

    @Query("SELECT day, COUNT(*) AS n FROM hr_minute WHERE day BETWEEN :from AND :to GROUP BY day")
    suspend fun hrCounts(
        from: Long,
        to: Long,
    ): List<DayCount>

    @Query("SELECT day, COUNT(*) AS n FROM steps_15m WHERE day BETWEEN :from AND :to GROUP BY day")
    suspend fun stepCounts(
        from: Long,
        to: Long,
    ): List<DayCount>

    @Query("SELECT MAX(ts) FROM hr_minute")
    suspend fun latestHr(): Long?

    @Query("SELECT MIN(day) FROM hr_minute")
    suspend fun firstHrDay(): Long?
}

@Dao
interface SleepDao {
    @Upsert suspend fun upsertSessions(rows: List<SleepSession>)

    @Upsert suspend fun upsertStages(rows: List<SleepStage>)

    @Query("DELETE FROM sleep_sessions WHERE day BETWEEN :from AND :to")
    suspend fun clear(
        from: Long,
        to: Long,
    )

    @Query("SELECT * FROM sleep_sessions WHERE day = :day ORDER BY start")
    suspend fun night(day: Long): List<SleepSession>

    @Query("SELECT * FROM sleep_sessions WHERE day BETWEEN :from AND :to ORDER BY start")
    suspend fun range(
        from: Long,
        to: Long,
    ): List<SleepSession>

    @Query("SELECT * FROM sleep_stages WHERE sessionId = :id ORDER BY start")
    suspend fun stages(id: String): List<SleepStage>

    @Query("SELECT MAX(day) FROM sleep_sessions WHERE day < :day")
    suspend fun prev(day: Long): Long?

    @Query("SELECT MIN(day) FROM sleep_sessions WHERE day > :day")
    suspend fun next(day: Long): Long?

    @Query("SELECT MAX(day) FROM sleep_sessions")
    suspend fun latest(): Long?

    @Query("SELECT MAX(`end`) FROM sleep_sessions")
    suspend fun latestEnd(): Long?

    @Query("SELECT * FROM sleep_sessions WHERE `end` > :from AND start < :to")
    suspend fun overlapping(
        from: Long,
        to: Long,
    ): List<SleepSession>
}

@Dao
interface ExerciseDao {
    @Upsert suspend fun upsert(rows: List<Exercise>)

    @Query("DELETE FROM exercises WHERE day BETWEEN :from AND :to")
    suspend fun clear(
        from: Long,
        to: Long,
    )

    @Query("SELECT * FROM exercises WHERE `end` > :from AND start < :to ORDER BY start")
    suspend fun overlapping(
        from: Long,
        to: Long,
    ): List<Exercise>

    @Query("SELECT * FROM exercises WHERE day BETWEEN :from AND :to ORDER BY start DESC")
    suspend fun range(
        from: Long,
        to: Long,
    ): List<Exercise>
}

@Dao
interface JournalDao {
    @Query("SELECT * FROM tags ORDER BY archived, sort, label")
    suspend fun tags(): List<Tag>

    @Upsert suspend fun upsertTags(rows: List<Tag>)

    @Query("SELECT tagKey FROM day_tags WHERE day = :day")
    suspend fun dayTags(day: Long): List<String>

    @Query("SELECT * FROM day_tags WHERE day BETWEEN :from AND :to")
    suspend fun dayTagsRange(
        from: Long,
        to: Long,
    ): List<DayTag>

    @Query("SELECT day FROM day_tags WHERE tagKey = :key")
    suspend fun daysWith(key: String): List<Long>

    @Query("SELECT tagKey AS metric, COUNT(*) AS n, MIN(day) AS firstDay, MAX(day) AS lastDay FROM day_tags GROUP BY tagKey")
    suspend fun usage(): List<MetricSpan>

    @Query("DELETE FROM day_tags WHERE day = :day")
    suspend fun clearDay(day: Long)

    @Upsert suspend fun upsertDayTags(rows: List<DayTag>)

    @Query("SELECT * FROM day_notes WHERE day = :day")
    suspend fun note(day: Long): DayNote?

    @Upsert suspend fun upsertNote(n: DayNote)

    @Query("DELETE FROM day_notes WHERE day = :day")
    suspend fun deleteNote(day: Long)

    @Transaction
    suspend fun replaceDay(
        day: Long,
        tags: List<String>,
        note: String,
    ) {
        clearDay(day)
        upsertDayTags(tags.map { DayTag(day, it) })
        if (note.isBlank()) deleteNote(day) else upsertNote(DayNote(day, note.trim()))
    }
}

@Dao
interface KvDao {
    @Query("SELECT value FROM kv WHERE `key` = :key")
    suspend fun get(key: String): String?

    @Upsert suspend fun put(kv: Kv)
}

@Database(
    entities = [
        DailyMetric::class, HrMinute::class, Steps15::class, SleepSession::class, SleepStage::class,
        Exercise::class, Tag::class, DayTag::class, DayNote::class, Kv::class,
    ],
    version = 1,
    exportSchema = false,
)
abstract class PulseDb : RoomDatabase() {
    abstract fun metrics(): MetricsDao

    abstract fun intraday(): IntradayDao

    abstract fun sleep(): SleepDao

    abstract fun exercises(): ExerciseDao

    abstract fun journal(): JournalDao

    abstract fun kv(): KvDao

    companion object {
        val DEFAULT_TAGS =
            listOf(
                Tag("alcohol", "Alcohol", "evening", false, 0),
                Tag("late-meal", "Late meal", "evening", false, 1),
                Tag("late-caffeine", "Late caffeine", "evening", false, 2),
                Tag("screen-late", "Screen late", "evening", false, 3),
                Tag("sick", "Sick", "day", false, 4),
                Tag("travel", "Travel", "day", false, 5),
                Tag("stress", "Stress", "day", false, 6),
                Tag("rest-day", "Rest day", "day", false, 7),
            )

        fun open(context: Context): PulseDb =
            Room.databaseBuilder(context.applicationContext, PulseDb::class.java, "pulse.db").build()
    }
}
