package dev.pulse.app.data

import dev.pulse.app.core.Derived
import dev.pulse.app.db.Kv
import dev.pulse.app.db.KvDao
import kotlinx.serialization.Serializable

@Serializable
data class Goals(val sleepMin: Int = 480, val steps: Int = 10_000, val azmWeekly: Int = 150)

@Serializable
data class Profile(val birthYear: Int? = null, val sex: String? = null) // sex: "male" | "female" | null

@Serializable
data class UserPrefs(
    val goals: Goals = Goals(),
    val units: String = "metric",
    val weights: Map<String, Double> = Derived.DEFAULT_WEIGHTS,
    val profile: Profile = Profile(),
)

/** User settings as one JSON row in the kv table. */
class Prefs(private val kv: KvDao) {
    suspend fun get(): UserPrefs =
        kv.get("prefs")?.let { runCatching { PulseJson.decodeFromString(UserPrefs.serializer(), it) }.getOrNull() } ?: UserPrefs()

    suspend fun put(p: UserPrefs) = kv.put(Kv("prefs", PulseJson.encodeToString(UserPrefs.serializer(), p)))

    suspend fun update(f: (UserPrefs) -> UserPrefs) = put(f(get()))

    /** Age used for heart-rate zones; 30 until the user sets a birth year. */
    fun age(
        p: UserPrefs,
        year: Int,
    ): Int = p.profile.birthYear?.let { (year - it).coerceIn(10, 100) } ?: 30
}
