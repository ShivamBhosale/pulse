package dev.pulse.app.ui.more

import androidx.browser.customtabs.CustomTabColorSchemeParams
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.net.toUri
import dev.pulse.app.ui.PulseCard
import dev.pulse.app.ui.theme.LocalPulse
import dev.pulse.app.ui.theme.NumStyle

private val PAGES =
    listOf(
        Triple("heart", "Heart & recovery", "Resting HR and HRV with baselines, zones, SpO₂, skin temperature"),
        Triple("activity", "Activity", "Steps, AZM, calories, when you move, workouts"),
        Triple("trends", "Trends & explore", "Compare metrics, correlations, year in pixels, tags"),
        Triple("records", "Records & streaks", "Personal bests and current streaks"),
        Triple("data", "Data health", "Freshness, missing days, re-sync"),
        Triple("settings", "Settings", "Goals, units, passcode, readiness weights, backups"),
    )

/** Deeper pages open the existing web app in a Chrome Custom Tab: one source of truth. */
@Composable
fun MoreScreen(
    baseUrl: String,
    onChangeServer: () -> Unit,
) {
    val p = LocalPulse.current
    val context = LocalContext.current
    fun open(path: String) {
        val colors = CustomTabColorSchemeParams.Builder().setToolbarColor(p.surface.toArgb()).build()
        CustomTabsIntent
            .Builder()
            .setDefaultColorSchemeParams(colors)
            .setShowTitle(true)
            .build()
            .launchUrl(context, (baseUrl + path).toUri())
    }
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { Text("More", color = p.ink, fontSize = 22.sp, fontWeight = FontWeight.SemiBold) }
        item {
            PulseCard(subtitle = null) {
                PAGES.forEachIndexed { i, (path, title, desc) ->
                    if (i > 0) HorizontalDivider(color = p.line)
                    Row(
                        Modifier.fillMaxWidth().clickable { open(path) }.padding(vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(title, color = p.ink, fontSize = 15.sp)
                            Text(desc, color = p.muted, fontSize = 12.sp)
                        }
                        Text("↗", color = p.muted)
                    }
                }
            }
        }
        item {
            val mgr = context.getSystemService(android.appwidget.AppWidgetManager::class.java)
            if (mgr?.isRequestPinAppWidgetSupported == true) {
                PulseCard(title = "Home-screen widget", subtitle = "Readiness, steps, sleep and weekly AZM; refreshes every 30 minutes") {
                    TextButton(
                        onClick = {
                            mgr.requestPinAppWidget(
                                android.content.ComponentName(context, dev.pulse.app.widget.PulseWidgetReceiver::class.java),
                                null,
                                null,
                            )
                        },
                        contentPadding = PaddingValues(0.dp),
                    ) { Text("Add widget to home screen", color = p.accentInk) }
                }
            }
        }
        item {
            PulseCard(title = "Server") {
                Text(baseUrl.removeSuffix("/"), style = NumStyle, fontSize = 12.sp, color = p.ink2)
                Text(
                    "The web pages open in Chrome, which keeps its own passcode session.",
                    color = p.muted,
                    fontSize = 11.sp,
                )
                TextButton(onClick = onChangeServer, contentPadding = PaddingValues(0.dp)) {
                    Text("Change server", color = p.accentInk)
                }
            }
        }
    }
}
