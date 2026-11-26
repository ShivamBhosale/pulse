package dev.pulse.app.ui.today

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dev.pulse.api.models.Journal
import dev.pulse.api.models.TagOut
import dev.pulse.api.models.Today
import dev.pulse.app.data.ApiResult
import dev.pulse.app.data.PulseRepository
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
    val locked: Boolean = false,
    val tags: List<TagOut> = emptyList(),
    val journalDate: String? = null,
    val journal: Journal? = null,
    val journalStatus: String? = null,
)

class TodayViewModel(
    private val repo: PulseRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(TodayState())
    val state: StateFlow<TodayState> = _state
    private var noteJob: Job? = null

    init {
        load()
    }

    fun load() =
        viewModelScope.launch {
            when (val r = repo.today()) {
                is ApiResult.Ok -> {
                    _state.update { it.copy(loading = false, today = r.value, error = null) }
                    if (_state.value.journalDate == null) selectJournalDate(r.value.date)
                }
                else -> fail(r)
            }
            if (_state.value.tags.isEmpty()) {
                (repo.tags() as? ApiResult.Ok)?.let { t -> _state.update { it.copy(tags = t.value) } }
            }
        }

    /** Pull to refresh: the server syncs from Google, the phone waits, then reloads. */
    fun refresh() =
        viewModelScope.launch {
            _state.update { it.copy(refreshing = true) }
            when (val r = repo.syncAndWait()) {
                is ApiResult.Ok -> Unit
                else -> fail(r)
            }
            load().join()
            _state.update { it.copy(refreshing = false) }
        }

    fun selectJournalDate(date: String) =
        viewModelScope.launch {
            _state.update { it.copy(journalDate = date, journal = null, journalStatus = null) }
            when (val r = repo.journal(date)) {
                is ApiResult.Ok -> _state.update { if (it.journalDate == date) it.copy(journal = r.value) else it }
                else -> fail(r)
            }
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
                when (val r = repo.putJournal(next.date, next.tags, next.note)) {
                    is ApiResult.Ok -> _state.update { it.copy(journalStatus = "Saved") }
                    is ApiResult.Failed ->
                        _state.update { it.copy(journal = previous, journalStatus = "Not saved: ${r.message}") }
                    is ApiResult.Offline ->
                        _state.update { it.copy(journal = previous, journalStatus = "Not saved: offline") }
                    ApiResult.Locked -> fail(r)
                }
            }
    }

    private fun fail(r: ApiResult<*>) {
        _state.update {
            when (r) {
                ApiResult.Locked -> it.copy(loading = false, locked = true)
                is ApiResult.Offline -> it.copy(loading = false, error = "Can't reach Pulse. Is Tailscale on? (${r.message})")
                is ApiResult.Failed -> it.copy(loading = false, error = r.message)
                is ApiResult.Ok -> it
            }
        }
    }
}
