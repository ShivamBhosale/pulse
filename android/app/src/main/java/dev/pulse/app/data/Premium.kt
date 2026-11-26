package dev.pulse.app.data

import dev.pulse.app.core.Summary
import java.time.LocalDate

/** Premium-feature hooks into the summary (filled in Milestone B). */
object Premium {
    @Suppress("UNUSED_PARAMETER")
    suspend fun sentences(
        repo: LocalRepository,
        d: LocalDate,
        p: UserPrefs,
    ): List<Summary.Sentence> = emptyList()
}
