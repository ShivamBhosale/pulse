package dev.pulse.app.ui.health

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.pulse.app.AppContainer
import dev.pulse.app.core.Derived
import dev.pulse.app.ui.Metrics
import dev.pulse.app.ui.PulseCard
import dev.pulse.app.ui.Tone
import dev.pulse.app.ui.ToneLabel
import dev.pulse.app.ui.charts.DayChart
import dev.pulse.app.ui.charts.Pt
import dev.pulse.app.ui.theme.LocalPulse
import dev.pulse.app.ui.theme.NumStyle

private val VITALS = listOf("resting_hr", "hrv_rmssd", "resp_rate", "spo2_avg", "skin_temp_delta")

@Composable
fun RangePicker(
    options: List<Pair<Int, String>>,
    selected: Int,
    onSelect: (Int) -> Unit,
) {
    val p = LocalPulse.current
    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
        options.forEachIndexed { i, (days, label) ->
            SegmentedButton(
                selected = selected == days,
                onClick = { onSelect(days) },
                shape = SegmentedButtonDefaults.itemShape(i, options.size),
                colors =
                    SegmentedButtonDefaults.colors(
                        activeContainerColor = p.surface2,
                        activeContentColor = p.ink,
                        inactiveContainerColor = p.surface,
                        inactiveContentColor = p.muted,
                        activeBorderColor = p.line,
                        inactiveBorderColor = p.line,
                    ),
                icon = {},
            ) { Text(label, fontSize = 13.sp) }
        }
    }
}

/** Health metrics vs your personal ranges (premium-style dashboard). */
@Composable
fun HealthScreen(
    container: AppContainer,
    header: @Composable () -> Unit = {},
) {
    val p = LocalPulse.current
    var days by rememberSaveable { mutableIntStateOf(30) }
    val charts by produceState<Map<String, List<Pt>>?>(null, days) { value = VITALS.associateWith { container.repo.chart(it, days, band = it != "skin_temp_delta") } }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Text("Health", color = p.ink, fontSize = 22.sp, fontWeight = FontWeight.SemiBold) }
        item { header() }
        item { RangePicker(listOf(30 to "30 days", 90 to "90 days", 365 to "1 year"), days) { days = it } }
        val data = charts
        if (data == null) {
            item { Text("Loading…", color = p.muted) }
        } else {
            items(VITALS.filter { k -> data[k]?.any { it.value != null } == true }) { k ->
                val m = Metrics.of(k)!!
                val pts = data.getValue(k)
                val last = pts.lastOrNull { it.value != null }
                val inRange = last?.let { l -> if (l.lo != null && l.hi != null) l.value!! in l.lo..l.hi else null }
                PulseCard {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text(m.label, color = p.ink, fontSize = 14.sp, fontWeight = FontWeight.Medium, modifier = Modifier.weight(1f))
                        when (inRange) {
                            true -> ToneLabel(Tone("●", "In your range", p.good))
                            false -> ToneLabel(Tone("▲", "Outside your range", p.warning))
                            null -> Unit
                        }
                    }
                    last?.let { l ->
                        Text(
                            "Latest ${m.format(l.value!!)}" + (if (l.lo != null && l.hi != null) " · your range ${m.format(l.lo)}–${m.format(l.hi)}" else ""),
                            style = NumStyle,
                            fontSize = 12.sp,
                            color = p.ink2,
                        )
                    }
                    DayChart(pts, m.format, bars = m.bars, diverging = m.diverging, zeroBased = false, description = "${m.label} over $days days")
                }
            }
            item {
                Text(
                    "Your range is the middle half of your own last ${Derived.BASELINE_DAYS} days (median ± IQR). Not medical advice.",
                    color = p.muted,
                    fontSize = 11.sp,
                )
            }
        }
    }
}
