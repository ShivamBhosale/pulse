package dev.pulse.app.ui.today

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dev.pulse.api.models.Journal
import dev.pulse.api.models.TagOut
import dev.pulse.api.models.Today
import dev.pulse.app.AppContainer
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.time.LocalDate

data class TodayState(
    val loading: Boolean = true,
    val refreshing: Boolean = false,
    val today: Today? = null,
    val error: String? = null,
    val tags: List<TagOut> = emptyList(),
    val journalDate: String? = null,
    val journal: Journal? = null,
    val journalStatus: String? = null,
)

class TodayViewModel(
    private val c: AppContainer,
) : ViewModel() {
    private val repo = c.repo
    private val _state = MutableStateFlow(TodayState())
    val state: StateFlow<TodayState> = _state
    private var noteJob: Job? = null

    init {
        load()
    }

    fun load() =
        viewModelScope.launch {
            try {
                val t = repo.todayModel()
                _state.update { it.copy(loading = false, today = t, error = null) }
                if (_state.value.journalDate == null) selectJournalDate(t.date)
                if (_state.value.tags.isEmpty()) {
                    val tags = repo.tags()
                    _state.update { it.copy(tags = tags) }
                }
            } catch (e: Exception) {
                fail(e)
            }
        }

    /** Pull to refresh: re-read the last 3 days from Health Connect, recompute, reload. */
    fun refresh() =
        viewModelScope.launch {
            _state.update { it.copy(refreshing = true) }
            try {
                c.sync.syncRecent()
            } catch (e: Exception) {
                fail(e)
            }
            load().join()
            _state.update { it.copy(refreshing = false) }
        }

    fun selectJournalDate(date: String) =
        viewModelScope.launch {
            _state.update { it.copy(journalDate = date, journal = null, journalStatus = null) }
            val j = repo.journal(LocalDate.parse(date))
            _state.update { if (it.journalDate == date) it.copy(journal = j) else it }
        }

    fun yesterdayOf(today: String): String = LocalDate.parse(today).minusDays(1).toString()

    fun toggleTag(key: String) {
        val j = _state.value.journal ?: return
        val tags = if (key in j.tags) j.tags - key else j.tags + key
        save(j.copy(tags = tags), immediate = true)
    }

    fun setNote(text: String) {
        val j = _state.value.journal ?: return
        save(j.copy(note = text.take(2000)), immediate = false)
    }

    private fun save(
        next: Journal,
        immediate: Boolean,
    ) {
        val previous = _state.value.journal
        _state.update { it.copy(journal = next, journalStatus = "Saving…") } // optimistic
        noteJob?.cancel()
        noteJob =
            viewModelScope.launch {
                if (!immediate) delay(800)
                try {
                    repo.putJournal(LocalDate.parse(next.date), next.tags, next.note)
                    _state.update { it.copy(journalStatus = "Saved") }
                } catch (e: Exception) {
                    _state.update { it.copy(journal = previous, journalStatus = "Not saved: ${e.message}") }
                }
            }
    }

    private fun fail(e: Exception) {
        _state.update {
            it.copy(
                loading = false,
                error =
                    if (e is SecurityException) {
                        "Health Connect permission missing. Open Settings → Health Connect → Pulse."
                    } else {
                        e.message ?: e.javaClass.simpleName
                    },
            )
        }
    }
}
