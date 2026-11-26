package dev.pulse.app.ui.more

import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.health.connect.client.HealthConnectClient
import dev.pulse.app.AppContainer
import dev.pulse.app.core.Derived
import dev.pulse.app.data.Goals
import dev.pulse.app.data.Profile
import dev.pulse.app.data.UserPrefs
import dev.pulse.app.db.Kv
import dev.pulse.app.hc.Hc
import dev.pulse.app.ui.Eyebrow
import dev.pulse.app.ui.PulseCard
import dev.pulse.app.ui.theme.LocalPulse
import dev.pulse.app.ui.theme.NumStyle
import dev.pulse.app.util.Fmt
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate

// ---- records -------------------------------------------------------------------------------

@Composable
fun RecordsPage(container: AppContainer) {
    val p = LocalPulse.current
    val rec by produceState<dev.pulse.app.data.LocalRepository.Records?>(null) {
        value = container.repo.records(container.repo.today(), container.prefs.get())
    }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        val r = rec
        if (r == null) {
            item { Text("Loading…", color = p.muted) }
            return@LazyColumn
        }
        item {
            PulseCard(title = "Streaks", subtitle = "Today and this week are in progress: they extend a streak but never break it") {
                r.streaks.forEach { s ->
                    val unit = if (s.period == "day") "days" else "weeks"
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(s.label, color = p.ink, fontSize = 14.sp)
                            Text("Longest ${s.longest} $unit" + (s.longestEnd?.let { " · ended ${Fmt.day(it.toString())}" } ?: ""), color = p.muted, fontSize = 11.sp)
                        }
                        Text("${s.current}", style = NumStyle, fontSize = 24.sp, color = p.ink)
                        Text(" $unit now", color = p.muted, fontSize = 12.sp)
                    }
                }
            }
        }
        item {
            PulseCard(title = "Personal bests") {
                r.bests.forEachIndexed { i, b ->
                    if (i > 0) HorizontalDivider(color = p.line)
                    val value =
                        when {
                            b.key == "sleep_main_min" -> Fmt.duration(b.value)
                            b.unit == "km" -> "${Fmt.num(b.value, 2)} km"
                            b.unit == "ms" || b.unit == "bpm" -> "${Fmt.num(b.value, 1)} ${b.unit}"
                            b.unit == "min" -> "${Fmt.num(b.value)} min"
                            else -> Fmt.num(b.value)
                        }
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(b.label, color = p.ink2, fontSize = 13.sp)
                            Text(Fmt.day(b.date.toString()) + (b.note?.let { " · $it" } ?: ""), color = p.muted, fontSize = 11.sp)
                        }
                        Text(value, style = NumStyle, fontSize = 16.sp, color = p.ink)
                    }
                }
            }
        }
    }
}

// ---- data & sync -----------------------------------------------------------------------------

@Composable
fun DataPage(container: AppContainer) {
    val p = LocalPulse.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var refresh by remember { mutableIntStateOf(0) }
    var busy by remember { mutableStateOf<String?>(null) }

    data class Info(
        val granted: Set<String>,
        val lastSync: Long?,
        val latestHr: Long?,
        val latestSleep: Long?,
        val coverage: List<Triple<String, Int, Int>>,
    )
    val info by produceState<Info?>(null, refresh) {
        val repo = container.repo
        val today = repo.today()
        val from = today.minusDays(90)
        val spans = repo.available()
        val cov =
            listOf("steps" to "Steps", "sleep_main_min" to "Sleep", "resting_hr" to "Resting HR", "hrv_rmssd" to "HRV", "spo2_avg" to "Blood oxygen", "resp_rate" to "Breathing rate", "skin_temp_delta" to "Skin temp")
                .map { (k, label) ->
                    val first = spans[k]?.firstDay?.let { LocalDate.ofEpochDay(it) }
                    val expected = if (first == null) 0 else (today.toEpochDay() - maxOf(first, from).toEpochDay()).toInt().coerceAtLeast(0)
                    val have = repo.values(k, from, today.minusDays(1)).size
                    Triple(label, have, expected)
                }
        value =
            Info(
                granted = runCatching { container.hc.granted() }.getOrDefault(emptySet()),
                lastSync = container.db.kv().get("last_sync_ms")?.toLongOrNull(),
                latestHr = container.db.intraday().latestHr(),
                latestSleep = container.db.sleep().latestEnd(),
                coverage = cov,
            )
    }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        val i = info
        if (i == null) {
            item { Text("Loading…", color = p.muted) }
            return@LazyColumn
        }
        item {
            PulseCard(title = "Freshness") {
                fun ago(ms: Long?) = ms?.let { Fmt.ago(Instant.ofEpochMilli(it).toString()) } ?: "never"
                Text("Band heart rate up to ${i.latestHr?.let { Fmt.time(Instant.ofEpochMilli(it + 60_000).toString()) } ?: "–"} (${ago(i.latestHr)})", color = p.ink2, fontSize = 13.sp)
                Text("Last sleep ended ${ago(i.latestSleep)}", color = p.ink2, fontSize = 13.sp)
                Text("Pulse read Health Connect ${ago(i.lastSync)}", color = p.ink2, fontSize = 13.sp)
                Text("If the band data is old, open the Fitbit app so it syncs the band into Health Connect.", color = p.muted, fontSize = 11.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(
                        enabled = busy == null,
                        onClick = {
                            scope.launch {
                                busy = "Syncing…"
                                runCatching { container.sync.syncRecent() }
                                busy = null
                                refresh++
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = p.accent, contentColor = p.page),
                    ) { Text("Sync now") }
                    OutlinedButton(
                        enabled = busy == null,
                        onClick = {
                            scope.launch {
                                busy = "Re-importing history…"
                                container.db.kv().put(Kv("import_cursor", LocalDate.now().plusDays(1).toString()))
                                runCatching { container.sync.importHistory() }
                                busy = null
                                refresh++
                            }
                        },
                    ) { Text("Re-import history") }
                }
                busy?.let { Text(it, color = p.accentInk, fontSize = 12.sp) }
            }
        }
        item {
            PulseCard(title = "Last 90 days", subtitle = "Days with data, counted from each signal's first day") {
                i.coverage.forEach { (label, have, expected) ->
                    Row(Modifier.fillMaxWidth()) {
                        Text(label, color = p.ink2, fontSize = 13.sp, modifier = Modifier.weight(1f))
                        Text(if (expected == 0) "not tracked" else "$have of $expected", style = NumStyle, fontSize = 13.sp, color = if (expected > 0 && have < expected) p.ink else p.muted)
                    }
                }
                Text("Missing days usually mean the band wasn't worn or the Fitbit app hadn't synced.", color = p.muted, fontSize = 11.sp)
            }
        }
        item {
            PulseCard(title = "Health Connect access") {
                val names =
                    Hc.READ_TYPES.map { it.simpleName.orEmpty().removeSuffix("Record") }
                        .zip(Hc.READ_TYPES.map { androidx.health.connect.client.permission.HealthPermission.getReadPermission(it) })
                names.forEach { (name, perm) ->
                    val ok = perm in i.granted
                    Row(Modifier.fillMaxWidth()) {
                        Text(name.replace(Regex("([a-z])([A-Z])"), "$1 $2"), color = p.ink2, fontSize = 13.sp, modifier = Modifier.weight(1f))
                        Text(if (ok) "● allowed" else "○ not allowed", color = if (ok) p.goodInk else p.muted, fontSize = 12.sp)
                    }
                }
                androidx.compose.material3.TextButton(
                    onClick = { context.startActivity(Intent(HealthConnectClient.ACTION_HEALTH_CONNECT_SETTINGS)) },
                    contentPadding = PaddingValues(0.dp),
                ) { Text("Open Health Connect settings", color = p.accentInk) }
            }
        }
    }
}

// ---- settings ------------------------------------------------------------------------------

@Composable
fun SettingsPage(container: AppContainer) {
    val p = LocalPulse.current
    val scope = rememberCoroutineScope()
    val loaded by produceState<UserPrefs?>(null) { value = container.prefs.get() }
    val start = loaded ?: return
    var sleepH by remember { mutableStateOf((start.goals.sleepMin / 60.0).toString()) }
    var steps by remember { mutableStateOf(start.goals.steps.toString()) }
    var azm by remember { mutableStateOf(start.goals.azmWeekly.toString()) }
    var birth by remember { mutableStateOf(start.profile.birthYear?.toString() ?: "") }
    var sex by remember { mutableStateOf(start.profile.sex) }
    var units by remember { mutableStateOf(start.units) }
    var weights by remember { mutableStateOf(start.weights) }
    var status by remember { mutableStateOf<String?>(null) }

    @Composable
    fun field(
        label: String,
        value: String,
        onChange: (String) -> Unit,
        hint: String? = null,
    ) {
        OutlinedTextField(
            value = value,
            onValueChange = onChange,
            label = { Text(label) },
            supportingText = hint?.let { { Text(it) } },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = p.accent, unfocusedBorderColor = p.line, focusedTextColor = p.ink, unfocusedTextColor = p.ink),
            modifier = Modifier.fillMaxWidth(),
        )
    }

    @Composable
    fun segmented(
        options: List<Pair<String?, String>>,
        selected: String?,
        onSelect: (String?) -> Unit,
    ) {
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            options.forEachIndexed { i, (v, label) ->
                SegmentedButton(
                    selected = selected == v,
                    onClick = { onSelect(v) },
                    shape = SegmentedButtonDefaults.itemShape(i, options.size),
                    colors = SegmentedButtonDefaults.colors(activeContainerColor = p.surface2, activeContentColor = p.ink, inactiveContainerColor = p.surface, inactiveContentColor = p.muted),
                    icon = {},
                ) { Text(label, fontSize = 13.sp) }
            }
        }
    }

    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            PulseCard(title = "Goals") {
                field("Sleep (hours)", sleepH, { sleepH = it }, Fmt.duration(sleepH.toDoubleOrNull()?.times(60)))
                field("Steps per day", steps, { steps = it })
                field("Active zone minutes per week", azm, { azm = it })
            }
        }
        item {
            PulseCard(title = "You", subtitle = "Used for heart-rate zones (active minutes) and the fitness estimate. Stays on this phone.") {
                field("Birth year", birth, { birth = it.filter(Char::isDigit).take(4) }, if (birth.isBlank()) "Until set, zones assume age 30" else null)
                Eyebrow("Sex (optional, for fitness reference ranges)")
                segmented(listOf("female" to "Female", "male" to "Male", null to "Not set"), sex) { sex = it }
            }
        }
        item {
            PulseCard(title = "Units") {
                segmented(listOf("metric" to "Metric (km, °C)", "imperial" to "Imperial (mi, °F)"), units) { units = it ?: "metric" }
            }
        }
        item {
            PulseCard(title = "Readiness weights", subtitle = "Personal heuristic, not a medical measure") {
                val total = weights.values.sum().takeIf { it > 0 } ?: 1.0
                listOf("hrv" to "HRV vs baseline", "rhr" to "Resting HR vs baseline", "sleep" to "Sleep vs goal", "strain" to "Yesterday's strain").forEach { (k, label) ->
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text(label, color = p.ink2, fontSize = 13.sp, modifier = Modifier.weight(1f))
                        Text("${Math.round((weights[k] ?: 0.0) / total * 100)}%", style = NumStyle, fontSize = 13.sp, color = p.ink)
                    }
                    Slider(
                        value = (weights[k] ?: 0.0).toFloat(),
                        onValueChange = { weights = weights + (k to Math.round(it / 5f) * 5.0) },
                        valueRange = 0f..100f,
                        colors = SliderDefaults.colors(thumbColor = p.accent, activeTrackColor = p.accent, inactiveTrackColor = p.surface2),
                    )
                }
                androidx.compose.material3.TextButton(onClick = { weights = Derived.DEFAULT_WEIGHTS }, contentPadding = PaddingValues(0.dp)) {
                    Text("Reset to 35 / 25 / 25 / 15", color = p.accentInk)
                }
            }
        }
        item {
            Button(
                onClick = {
                    scope.launch {
                        val sleepMin = ((sleepH.toDoubleOrNull() ?: 8.0) * 60).toInt().coerceIn(180, 720)
                        val by = birth.toIntOrNull()?.takeIf { it in 1900..LocalDate.now().year }
                        val ageChanged = by != start.profile.birthYear
                        container.prefs.put(
                            UserPrefs(
                                goals = Goals(sleepMin, (steps.toIntOrNull() ?: 10_000).coerceIn(1000, 50_000), (azm.toIntOrNull() ?: 150).coerceIn(10, 1500)),
                                units = units,
                                weights = if (weights.values.sum() > 0) weights else Derived.DEFAULT_WEIGHTS,
                                profile = Profile(by, sex),
                            ),
                        )
                        status = "Saving…"
                        container.sync.recompute()
                        if (ageChanged) {
                            status = "Recalculating active minutes for your history…"
                            container.db.kv().put(Kv("import_cursor", LocalDate.now().plusDays(1).toString()))
                            runCatching { container.sync.importHistory() }
                        }
                        status = "Saved"
                    }
                },
                colors = ButtonDefaults.buttonColors(containerColor = p.accent, contentColor = p.page),
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Save") }
            status?.let { Text(it, color = p.ink2, fontSize = 12.sp) }
        }
    }
}
