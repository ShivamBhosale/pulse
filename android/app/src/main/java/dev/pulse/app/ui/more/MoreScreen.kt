package dev.pulse.app.ui.more

import android.appwidget.AppWidgetManager
import android.content.ComponentName
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.pulse.app.AppContainer
import dev.pulse.app.ui.PulseCard
import dev.pulse.app.ui.theme.LocalPulse
import dev.pulse.app.widget.PulseWidgetReceiver

private enum class Page(val title: String, val desc: String) {
    RECORDS("Records & streaks", "Personal bests and current streaks"),
    DATA("Data & sync", "Health Connect access, freshness, missing days, re-import"),
    SETTINGS("Settings", "Goals, birth year, units, readiness weights"),
}

@Composable
fun MoreScreen(container: AppContainer) {
    var page by rememberSaveable { mutableStateOf<Page?>(null) }
    BackHandler(enabled = page != null) { page = null }
    when (page) {
        Page.RECORDS -> SubPage("Records & streaks", { page = null }) { RecordsPage(container) }
        Page.DATA -> SubPage("Data & sync", { page = null }) { DataPage(container) }
        Page.SETTINGS -> SubPage("Settings", { page = null }) { SettingsPage(container) }
        null -> MoreList(container) { page = it }
    }
}

@Composable
private fun SubPage(
    title: String,
    onBack: () -> Unit,
    content: @Composable () -> Unit,
) {
    val p = LocalPulse.current
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 6.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("← More", color = p.accentInk) }
            Text(title, color = p.ink, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
        }
        content()
    }
}

@Composable
private fun MoreList(
    container: AppContainer,
    open: (Page) -> Unit,
) {
    val p = LocalPulse.current
    val context = LocalContext.current
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { Text("More", color = p.ink, fontSize = 22.sp, fontWeight = FontWeight.SemiBold) }
        item {
            PulseCard {
                Page.entries.forEachIndexed { i, pg ->
                    if (i > 0) HorizontalDivider(color = p.line)
                    Row(Modifier.fillMaxWidth().clickable { open(pg) }.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(pg.title, color = p.ink, fontSize = 15.sp)
                            Text(pg.desc, color = p.muted, fontSize = 12.sp)
                        }
                        Text("›", color = p.muted, fontSize = 18.sp)
                    }
                }
            }
        }
        item {
            val mgr = context.getSystemService(AppWidgetManager::class.java)
            if (mgr?.isRequestPinAppWidgetSupported == true) {
                PulseCard(title = "Home-screen widget", subtitle = "Readiness, steps, sleep and weekly AZM; refreshes every 30 minutes") {
                    TextButton(
                        onClick = { mgr.requestPinAppWidget(ComponentName(context, PulseWidgetReceiver::class.java), null, null) },
                        contentPadding = PaddingValues(0.dp),
                    ) { Text("Add widget to home screen", color = p.accentInk) }
                }
            }
        }
        item {
            PulseCard(title = "Privacy") {
                Text(
                    "Pulse reads Health Connect on this phone and has no internet permission. Your data never leaves the phone.",
                    color = p.ink2,
                    fontSize = 13.sp,
                )
            }
        }
    }
}
