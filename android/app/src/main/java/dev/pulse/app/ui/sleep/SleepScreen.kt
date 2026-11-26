package dev.pulse.app.ui.sleep

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import dev.pulse.api.models.SleepNight
import dev.pulse.api.models.SleepSessionOut
import dev.pulse.api.models.TagOut
import dev.pulse.app.AppContainer
import dev.pulse.app.ui.Banner
import dev.pulse.app.ui.Eyebrow
import dev.pulse.app.ui.PulseCard
import dev.pulse.app.ui.theme.LocalPulse
import dev.pulse.app.ui.theme.NumStyle
import dev.pulse.app.ui.theme.PulseColors
import dev.pulse.app.util.Fmt
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.time.LocalDate

data class SleepState(
    val loading: Boolean = true,
    val night: SleepNight? = null,
    val eveningTags: List<String> = emptyList(),
    val eveningNote: String = "",
    val error: String? = null,
)

class SleepViewModel(
    private val c: AppContainer,
) : ViewModel() {
    private val _state = MutableStateFlow(SleepState())
    val state: StateFlow<SleepState> = _state

    init {
        load(null)
    }

    fun load(date: String?) =
        viewModelScope.launch {
            _state.update { it.copy(loading = true) }
            try {
                val n = c.repo.sleepNight(date?.let { LocalDate.parse(it) })
                _state.update { it.copy(loading = false, night = n, error = null) }
                val evening = LocalDate.parse(n.date).minusDays(1)
                val tags = c.repo.tags()
                val j = c.repo.journal(evening)
                val labels = tags.filter { it.kind == TagOut.Kind.evening && it.key in j.tags }.map { it.label }
                _state.update { it.copy(eveningTags = labels, eveningNote = j.note) }
            } catch (e: Exception) {
                _state.update { it.copy(loading = false, error = e.message ?: e.javaClass.simpleName) }
            }
        }
}

private val STAGES = listOf("AWAKE", "REM", "LIGHT", "DEEP")
private val STAGE_LABEL = mapOf("DEEP" to "Deep", "LIGHT" to "Light", "REM" to "REM", "AWAKE" to "Awake")

private fun stageColor(
    stage: String,
    p: PulseColors,
): Color =
    when (stage) {
        "DEEP" -> p.deep
        "LIGHT" -> p.light
        "REM" -> p.rem
        else -> p.awake
    }

@Composable
fun SleepScreen(container: AppContainer) {
    val vm: SleepViewModel = viewModel(key = "sleep") { SleepViewModel(container) }
    val s by vm.state.collectAsStateWithLifecycle()
    val p = LocalPulse.current
    val n = s.night
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Sleep", color = p.ink, fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
                    n?.let { Text("Night ending ${Fmt.weekday(it.date)}", color = p.muted, fontSize = 12.sp) }
                }
                OutlinedButton(onClick = { vm.load(n?.prevDate) }, enabled = n?.prevDate != null) { Text("←") }
                OutlinedButton(onClick = { vm.load(n?.nextDate) }, enabled = n?.nextDate != null, modifier = Modifier.padding(start = 6.dp)) {
                    Text("→")
                }
            }
        }
        when {
            s.loading && n == null -> item { Box(Modifier.fillMaxWidth().height(200.dp)) { CircularProgressIndicator(Modifier.align(Alignment.Center), color = p.accent) } }
            s.error != null && n == null -> item { Banner("Couldn't load sleep", s.error) }
            n?.session == null -> item { PulseCard { Text("No sleep recorded for this night.", color = p.muted) } }
            else -> {
                val ses = n.session!!
                item { dev.pulse.app.ui.premium.SleepPremiumCards(container, n.date) }
                if (s.eveningTags.isNotEmpty() || s.eveningNote.isNotBlank()) item { EveningBefore(s) }
                item { Stats(n, ses) }
                item {
                    PulseCard(title = "Stages") {
                        Hypnogram(ses, Modifier.fillMaxWidth().height(150.dp))
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(Fmt.time(ses.start), style = NumStyle, fontSize = 10.sp, color = p.muted)
                            Text(Fmt.time(ses.end), style = NumStyle, fontSize = 10.sp, color = p.muted)
                        }
                    }
                }
                item { StageTable(ses) }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun EveningBefore(s: SleepState) {
    val p = LocalPulse.current
    PulseCard {
        Eyebrow("Evening before")
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            s.eveningTags.forEach {
                Text(
                    it,
                    color = p.ink2,
                    fontSize = 12.sp,
                    modifier = Modifier.clip(RoundedCornerShape(50)).background(p.surface2).padding(horizontal = 10.dp, vertical = 3.dp),
                )
            }
        }
        if (s.eveningNote.isNotBlank()) Text("“${s.eveningNote.lineSequence().first()}”", color = p.ink2, fontSize = 12.sp)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Stats(
    n: SleepNight,
    s: SleepSessionOut,
) {
    PulseCard {
        FlowRow(Modifier.fillMaxWidth(), maxItemsInEachRow = 2, verticalArrangement = Arrangement.spacedBy(12.dp)) {
            val cell = Modifier.weight(1f)
            Stat("Asleep", Fmt.duration(s.minutesAsleep.toDouble()), "goal ${Fmt.duration(n.goalMin.toDouble())}", cell)
            Stat("In bed", Fmt.duration(s.minutesInBed), "${Fmt.time(s.start)} → ${Fmt.time(s.end)}", cell)
            Stat("Efficiency", s.efficiency?.let { "${Fmt.num(it)}%" } ?: "–", "${Fmt.duration(s.minutesToFallAsleep.toDouble())} to fall asleep", cell)
            Stat("Sleeping HR", n.sleepingHr?.let { "${Fmt.num(it.avg)} bpm" } ?: "–", n.sleepingHr?.let { "lowest ${it.min}" }, cell)
            Stat("HRV", n.hrvRmssd?.let { "${Fmt.num(it, 1)} ms" } ?: "–", null, cell)
            Stat("Resting HR", n.restingHr?.let { "${Fmt.num(it)} bpm" } ?: "–", null, cell)
            Stat("SpO₂", n.spo2?.avg?.let { "${Fmt.num(it, 1)}%" } ?: "–", n.spo2?.let { "${Fmt.num(it.low)}–${Fmt.num(it.high)}%" }, cell)
            Stat("Skin temp", n.skinTempDelta?.let { (if (it >= 0) "+" else "−") + Fmt.num(kotlin.math.abs(it), 1) + " °C" } ?: "–", "vs. your baseline", cell)
        }
    }

}

@Composable
private fun Stat(
    label: String,
    value: String,
    hint: String?,
    modifier: Modifier,
) {
    val p = LocalPulse.current
    Column(modifier) {
        Eyebrow(label)
        Text(value, style = NumStyle, fontSize = 18.sp, color = p.ink, fontWeight = FontWeight.Medium)
        hint?.let { Text(it, fontSize = 11.sp, color = p.muted) }
    }
}

/** Rows top→bottom: Awake, REM, Light, Deep (depth reads downward), like the web chart. */
@Composable
fun Hypnogram(
    s: SleepSessionOut,
    modifier: Modifier,
) {
    val p = LocalPulse.current
    val start = Fmt.parseInstant(s.start)?.toEpochMilli() ?: return
    val end = Fmt.parseInstant(s.end)?.toEpochMilli() ?: return
    val span = (end - start).coerceAtLeast(1L).toFloat()
    val labelW = 46.dp
    Row(modifier.semantics { contentDescription = "Hypnogram of sleep stages through the night" }) {
        Column(Modifier.width(labelW).fillMaxHeight(), verticalArrangement = Arrangement.SpaceEvenly) {
            STAGES.forEach { Text(STAGE_LABEL[it]!!, color = p.ink2, fontSize = 11.sp) }
        }
        Canvas(Modifier.weight(1f).fillMaxHeight()) {
            val rowH = size.height / STAGES.size
            for (i in 0..STAGES.size) {
                drawLine(p.line, Offset(0f, i * rowH), Offset(size.width, i * rowH), strokeWidth = 1f)
            }
            s.stages.forEach { st ->
                val row = STAGES.indexOf(st.stage)
                if (row < 0) return@forEach
                val a = Fmt.parseInstant(st.start)?.toEpochMilli() ?: return@forEach
                val b = Fmt.parseInstant(st.end)?.toEpochMilli() ?: return@forEach
                val x = (a - start) / span * size.width
                val w = ((b - a) / span * size.width).coerceAtLeast(1f)
                val h = rowH * 0.62f
                drawRoundRect(
                    stageColor(st.stage, p),
                    topLeft = Offset(x, row * rowH + (rowH - h) / 2),
                    size = Size(w, h),
                    cornerRadius = CornerRadius(2.dp.toPx()),
                )
            }
        }
    }
}

@Composable
private fun StageTable(s: SleepSessionOut) {
    val p = LocalPulse.current
    val mins = mapOf("DEEP" to s.deepMin, "LIGHT" to s.lightMin, "REM" to s.remMin, "AWAKE" to s.awakeMin)
    val total = mins.values.sumOf { it ?: 0 }.takeIf { it > 0 } ?: return
    PulseCard(title = "Time per stage") {
        listOf("AWAKE", "REM", "LIGHT", "DEEP").forEach { k ->
            val m = mins[k] ?: 0
            val pct = m.toFloat() / total
            Column {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(10.dp).clip(RoundedCornerShape(2.dp)).background(stageColor(k, p)))
                    Text("  ${STAGE_LABEL[k]}", color = p.ink, fontSize = 13.sp, modifier = Modifier.weight(1f))
                    Text(Fmt.duration(m.toDouble()), style = NumStyle, fontSize = 13.sp, color = p.ink)
                    Text("  ${(pct * 100).toInt()}%", style = NumStyle, fontSize = 12.sp, color = p.ink2)
                }
                Box(Modifier.fillMaxWidth().height(4.dp).clip(RoundedCornerShape(2.dp)).background(p.surface2)) {
                    Box(Modifier.fillMaxWidth(pct).fillMaxHeight().background(stageColor(k, p)))
                }
            }
        }
    }
}
