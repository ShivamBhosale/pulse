package dev.pulse.app.ui.trends

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.pulse.app.AppContainer
import dev.pulse.app.core.Derived
import dev.pulse.app.ui.Metrics
import dev.pulse.app.ui.PulseCard
import dev.pulse.app.ui.charts.DayChart
import dev.pulse.app.ui.charts.Pt
import dev.pulse.app.ui.health.RangePicker
import dev.pulse.app.ui.theme.LocalPulse
import dev.pulse.app.ui.theme.NumStyle

/** Any metric over time, plus how it moves with a second metric. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun TrendsScreen(container: AppContainer) {
    val p = LocalPulse.current
    var days by rememberSaveable { mutableIntStateOf(90) }
    var a by rememberSaveable { mutableStateOf("readiness") }
    var b by rememberSaveable { mutableStateOf("sleep_main_min") }
    val available by produceState<Set<String>>(emptySet()) { value = container.repo.available().keys }
    val ca by produceState<List<Pt>?>(null, a, days) { value = container.repo.chart(a, days, band = Metrics.of(a)?.band ?: false) }
    val cb by produceState<List<Pt>?>(null, b, days) { value = container.repo.chart(b, days, band = Metrics.of(b)?.band ?: false) }
    val metrics = Metrics.ALL.filter { it.key in available }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Text("Trends", color = p.ink, fontSize = 22.sp, fontWeight = FontWeight.SemiBold) }
        item { RangePicker(listOf(30 to "30 days", 90 to "90 days", 365 to "1 year"), days) { days = it } }
        listOf(Triple("A", a, { k: String -> a = k }), Triple("B", b, { k: String -> b = k })).forEach { (name, sel, set) ->
            item {
                PulseCard(title = "Metric $name") {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        metrics.forEach { m ->
                            FilterChip(
                                selected = m.key == sel,
                                onClick = { set(m.key) },
                                label = { Text(m.label, fontSize = 12.sp) },
                                colors = FilterChipDefaults.filterChipColors(selectedContainerColor = p.accentSoft, selectedLabelColor = p.accentInk, labelColor = p.ink2),
                            )
                        }
                    }
                    val m = Metrics.of(sel)
                    val pts = if (name == "A") ca else cb
                    if (m != null && pts != null) DayChart(pts, m.format, bars = m.bars, diverging = m.diverging, zeroBased = m.bars, description = "${m.label} over $days days")
                }
            }
        }
        item {
            val pa = ca
            val pb = cb
            if (pa != null && pb != null && a != b) {
                val pairs = pa.zip(pb).mapNotNull { (x, y) -> if (x.value != null && y.value != null) x.value to y.value else null }
                val r = Derived.pearson(pairs.map { it.first }, pairs.map { it.second })
                PulseCard(title = "${Metrics.of(a)?.label} vs ${Metrics.of(b)?.label}") {
                    Text(
                        "r = ${r?.let { "%.2f".format(it) } ?: "–"} · ${Derived.correlationStrength(r)} · ${pairs.size} days with both",
                        style = NumStyle,
                        fontSize = 13.sp,
                        color = p.ink2,
                    )
                    Text("Shows association, not cause.", color = p.muted, fontSize = 11.sp)
                }
            }
        }
    }
}
