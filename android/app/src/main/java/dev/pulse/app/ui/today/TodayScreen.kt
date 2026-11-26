package dev.pulse.app.ui.today

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import dev.pulse.api.models.SummarySentence
import dev.pulse.api.models.TagOut
import dev.pulse.api.models.Tile
import dev.pulse.api.models.Today
import dev.pulse.app.AppContainer
import dev.pulse.app.ui.Banner
import dev.pulse.app.ui.Eyebrow
import dev.pulse.app.ui.PulseCard
import dev.pulse.app.ui.theme.LocalPulse
import dev.pulse.app.ui.theme.NumStyle
import dev.pulse.app.util.Fmt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TodayScreen(container: AppContainer) {
    val vm: TodayViewModel = viewModel(key = "today") { TodayViewModel(container) }
    val s by vm.state.collectAsStateWithLifecycle()
    val p = LocalPulse.current
    var readiness by remember { mutableStateOf<Tile?>(null) }

    PullToRefreshBox(isRefreshing = s.refreshing, onRefresh = { vm.refresh() }, modifier = Modifier.fillMaxSize()) {
        val today = s.today
        when {
            today == null && s.loading -> Box(Modifier.fillMaxSize()) { CircularProgressIndicator(Modifier.align(Alignment.Center), color = p.accent) }
            today == null ->
                LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp)) {
                    item { Banner("Couldn't load today", s.error) }
                    item { Text("Pull down to try again.", color = p.muted, fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp)) }
                }
            else -> TodayContent(today, s, vm, onReadiness = { readiness = it })
        }
    }
    readiness?.let { t ->
        ModalBottomSheet(onDismissRequest = { readiness = null }, containerColor = p.surface) { ReadinessDetails(t) }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun TodayContent(
    today: Today,
    s: TodayState,
    vm: TodayViewModel,
    onReadiness: (Tile) -> Unit,
) {
    val p = LocalPulse.current
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 14.dp, end = 14.dp, top = 12.dp, bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(Fmt.weekday(today.date), color = p.ink, fontSize = 22.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                Text(
                    if (s.refreshing) "Syncing…" else "Synced ${Fmt.ago(today.lastSynced)}",
                    style = NumStyle,
                    fontSize = 11.sp,
                    color = p.muted,
                )
            }
        }
        s.error?.let { item { Banner("Showing the last data loaded", it) } }
        item { SummaryCard(today) }
        item {
            FlowRow(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                maxItemsInEachRow = 2,
            ) {
                today.tiles.forEach { t ->
                    TileCard(
                        t,
                        Modifier.weight(1f),
                        onClick = if (t.key == "readiness" && t.components != null) ({ onReadiness(t) }) else null,
                    )
                }
            }
        }
        item { JournalCard(today.date, s, vm) }
        item {
            Text(
                "Pull down to read the latest from Health Connect.",
                color = p.muted,
                fontSize = 11.sp,
            )
        }
    }
}

@Composable
private fun SummaryCard(today: Today) {
    val p = LocalPulse.current
    PulseCard {
        Eyebrow("Today so far")
        Text(today.summary.headline, color = p.ink, fontSize = 17.sp, fontWeight = FontWeight.Medium)
        today.summary.sentences.forEach { x ->
            val (icon, color, word) =
                when (x.tone) {
                    SummarySentence.Tone.good -> Triple("●", p.good, "Good")
                    SummarySentence.Tone.attention -> Triple("▲", p.warning, "Worth a look")
                    SummarySentence.Tone.neutral -> Triple("·", p.muted, "Note")
                }
            Row(Modifier.androidxSemanticsLabel("$word: ${x.text}")) {
                Text(
                    icon,
                    color = color,
                    fontSize = 11.sp,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.width(14.dp).padding(top = 2.dp),
                )
                Spacer(Modifier.width(8.dp))
                Text(x.text, color = p.ink2, fontSize = 14.sp, lineHeight = 19.sp)
            }
        }
        Text("Written by fixed rules from your own data. Not medical advice.", color = p.muted, fontSize = 10.sp)
    }
}

private fun Modifier.androidxSemanticsLabel(label: String) =
    this.semantics(mergeDescendants = true) { contentDescription = label }

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun JournalCard(
    today: String,
    s: TodayState,
    vm: TodayViewModel,
) {
    val p = LocalPulse.current
    val yesterday = vm.yesterdayOf(today)
    val date = s.journalDate ?: today
    PulseCard(title = "Journal", subtitle = "Evening tags are compared with the following night") {
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            listOf(yesterday to "Yesterday", today to "Today").forEachIndexed { i, (d, label) ->
                SegmentedButton(
                    selected = date == d,
                    onClick = { vm.selectJournalDate(d) },
                    shape = SegmentedButtonDefaults.itemShape(i, 2),
                    colors =
                        SegmentedButtonDefaults.colors(
                            activeContainerColor = p.surface2,
                            activeContentColor = p.ink,
                            inactiveContainerColor = p.surface,
                            inactiveContentColor = p.muted,
                            activeBorderColor = p.line,
                            inactiveBorderColor = p.line,
                        ),
                ) { Text(label, fontSize = 13.sp) }
            }
        }
        val j = s.journal
        if (j == null) {
            Text("Loading…", color = p.muted, fontSize = 12.sp)
            return@PulseCard
        }
        val shown = s.tags.filter { !it.archived || it.key in j.tags }
        listOf(TagOut.Kind.evening to "Evening", TagOut.Kind.day to "Day").forEach { (kind, title) ->
            val group = shown.filter { it.kind == kind }
            if (group.isNotEmpty()) {
                Text(title, color = p.muted, fontSize = 11.sp)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    group.forEach { t ->
                        val on = t.key in j.tags
                        FilterChip(
                            selected = on,
                            onClick = { vm.toggleTag(t.key) },
                            label = { Text(t.label) },
                            colors =
                                FilterChipDefaults.filterChipColors(
                                    selectedContainerColor = p.accentSoft,
                                    selectedLabelColor = p.accentInk,
                                    labelColor = p.ink2,
                                    selectedLeadingIconColor = p.accentInk,
                                ),
                            leadingIcon = if (on) ({ Text("✓", color = p.accentInk) }) else null,
                        )
                    }
                }
            }
        }
        OutlinedTextField(
            value = j.note,
            onValueChange = { vm.setNote(it) },
            placeholder = { Text("Note (optional)") },
            minLines = 2,
            colors =
                OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = p.accent,
                    unfocusedBorderColor = p.line,
                    focusedTextColor = p.ink,
                    unfocusedTextColor = p.ink,
                    cursorColor = p.accent,
                ),
            modifier = Modifier.fillMaxWidth(),
        )
        Text(s.journalStatus ?: "Changes save automatically", color = p.muted, fontSize = 11.sp)
    }
}
