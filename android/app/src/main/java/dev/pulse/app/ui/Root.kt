package dev.pulse.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.layout.fillMaxWidth
import dev.pulse.app.AppContainer
import dev.pulse.app.ui.health.HealthScreen
import dev.pulse.app.ui.more.MoreScreen
import dev.pulse.app.ui.onboarding.HealthConnectGate
import dev.pulse.app.ui.sleep.SleepScreen
import dev.pulse.app.ui.theme.LocalPulse
import dev.pulse.app.ui.today.TodayScreen
import dev.pulse.app.ui.trends.TrendsScreen

private enum class Tab(val label: String, val path: String) {
    Today("Today", "M3 12h4l3-8 4 16 3-8h4"),
    Sleep("Sleep", "M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"),
    Health("Health", "M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z"),
    Trends("Trends", "M4 19V5M4 19h16M8 15l3-4 3 2 5-6"),
    More("More", "M5 12h.01M12 12h.01M19 12h.01"),
}

/** Health Connect gate, then the five-tab app. Everything runs on the phone. */
@Composable
fun PulseRoot(container: AppContainer) {
    val p = LocalPulse.current
    Box(Modifier.fillMaxSize().background(p.page)) {
        HealthConnectGate(container) { MainTabs(container) }
    }
}

@Composable
private fun MainTabs(container: AppContainer) {
    var tab by rememberSaveable { mutableStateOf(Tab.Today) }
    val app = androidx.compose.ui.platform.LocalContext.current.applicationContext as dev.pulse.app.PulseApp
    androidx.compose.runtime.LaunchedEffect(Unit) { app.continueImport() }
    val importing by app.importing.collectAsState()
    val p = LocalPulse.current
    BackHandler(enabled = tab != Tab.Today) { tab = Tab.Today }
    Scaffold(
        containerColor = p.page,
        bottomBar = {
            NavigationBar(containerColor = p.surface, tonalElevation = 0.dp) {
                Tab.entries.forEach { t ->
                    NavigationBarItem(
                        selected = tab == t,
                        onClick = { tab = t },
                        icon = { Icon(lineIcon(t.path), contentDescription = null) },
                        label = { Text(t.label) },
                        colors =
                            NavigationBarItemDefaults.colors(
                                selectedIconColor = p.accentInk,
                                selectedTextColor = p.accentInk,
                                indicatorColor = p.accentSoft,
                                unselectedIconColor = p.muted,
                                unselectedTextColor = p.muted,
                            ),
                    )
                }
            }
        },
    ) { pad ->
        androidx.compose.foundation.layout.Column(Modifier.padding(pad)) {
            importing?.let {
                Text(
                    "Importing older history in the background… back to ${dev.pulse.app.util.Fmt.day(it)}",
                    color = p.muted,
                    fontSize = 11.sp,
                    modifier = Modifier.fillMaxWidth().background(p.surface).padding(horizontal = 14.dp, vertical = 6.dp),
                )
            }
            when (tab) {
                Tab.Today -> TodayScreen(container)
                Tab.Sleep -> SleepScreen(container)
                Tab.Health -> HealthScreen(container, header = { dev.pulse.app.ui.premium.HealthPremiumHeader(container) })
                Tab.Trends -> TrendsScreen(container)
                Tab.More -> MoreScreen(container)
            }
        }
    }
}

/** 24-unit line icons from the web app's nav (stroke-only). */
@Composable
fun lineIcon(path: String): ImageVector =
    remember(path) {
        ImageVector
            .Builder(defaultWidth = 22.dp, defaultHeight = 22.dp, viewportWidth = 24f, viewportHeight = 24f)
            .addPath(
                pathData = PathParser().parsePathString(path).toNodes(),
                fill = null,
                stroke = SolidColor(Color.Black),
                strokeLineWidth = 1.8f,
                strokeLineCap = StrokeCap.Round,
                strokeLineJoin = StrokeJoin.Round,
            ).build()
    }
