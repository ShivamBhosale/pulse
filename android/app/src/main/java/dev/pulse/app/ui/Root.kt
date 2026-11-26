package dev.pulse.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.dp
import dev.pulse.app.AppContainer
import dev.pulse.app.data.ApiResult
import dev.pulse.app.ui.more.MoreScreen
import dev.pulse.app.ui.onboarding.PasscodeScreen
import dev.pulse.app.ui.onboarding.ServerScreen
import dev.pulse.app.ui.sleep.SleepScreen
import dev.pulse.app.ui.theme.LocalPulse
import dev.pulse.app.ui.today.TodayScreen

private enum class Tab(val label: String, val path: String) {
    Today("Today", "M3 12h4l3-8 4 16 3-8h4"),
    Sleep("Sleep", "M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"),
    More("More", "M5 12h.01M12 12h.01M19 12h.01"),
}

private sealed interface Gate {
    data object Checking : Gate

    data object NeedsServer : Gate

    data object NeedsPasscode : Gate

    data object Ready : Gate
}

/** Onboarding gate (server URL → passcode if required) and the three-tab app. */
@Composable
fun PulseRoot(container: AppContainer) {
    val url by container.config.serverUrl.collectAsState(initial = "…")
    var gate by remember { mutableStateOf<Gate>(Gate.Checking) }
    var recheck by remember { mutableIntStateOf(0) }

    LaunchedEffect(url, recheck) {
        if (url == "…") return@LaunchedEffect
        val u = url
        gate =
            if (u == null) {
                Gate.NeedsServer
            } else {
                when (val s = container.repository(u).sessionState()) {
                    is ApiResult.Ok -> if (s.value.authenticated) Gate.Ready else Gate.NeedsPasscode
                    is ApiResult.Locked -> Gate.NeedsPasscode
                    else -> Gate.Ready // offline: show the app; screens explain the error
                }
            }
    }

    val p = LocalPulse.current
    Box(Modifier.fillMaxSize().background(p.page)) {
        when (gate) {
            Gate.Checking ->
                CircularProgressIndicator(Modifier.align(Alignment.Center), color = p.accent)
            Gate.NeedsServer -> ServerScreen(container, initial = url?.takeIf { it != "…" }, onSaved = { recheck++ })
            Gate.NeedsPasscode ->
                PasscodeScreen(container, url ?: "", onUnlocked = { recheck++ }, onChangeServer = {
                    gate = Gate.NeedsServer
                })
            Gate.Ready -> MainTabs(container, url ?: "", onLocked = { gate = Gate.NeedsPasscode }, onChangeServer = {
                gate = Gate.NeedsServer
            })
        }
    }
}

@Composable
private fun MainTabs(
    container: AppContainer,
    url: String,
    onLocked: () -> Unit,
    onChangeServer: () -> Unit,
) {
    var tab by rememberSaveable { mutableStateOf(Tab.Today) }
    val repo = remember(url) { container.repository(url) }
    val p = LocalPulse.current
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
        Box(Modifier.padding(pad)) {
            when (tab) {
                Tab.Today -> TodayScreen(repo, onLocked)
                Tab.Sleep -> SleepScreen(repo, onLocked)
                Tab.More -> MoreScreen(url, onChangeServer = onChangeServer)
            }
        }
    }
}

/** 24-unit line icons from the web app's nav (stroke-only). */
@Composable
private fun lineIcon(path: String): ImageVector =
    remember(path) {
        ImageVector
            .Builder(defaultWidth = 22.dp, defaultHeight = 22.dp, viewportWidth = 24f, viewportHeight = 24f)
            .addPath(
                pathData = PathParser().parsePathString(path).toNodes(),
                fill = null,
                stroke = androidx.compose.ui.graphics.SolidColor(androidx.compose.ui.graphics.Color.Black),
                strokeLineWidth = 1.8f,
                strokeLineCap = androidx.compose.ui.graphics.StrokeCap.Round,
                strokeLineJoin = androidx.compose.ui.graphics.StrokeJoin.Round,
            ).build()
    }
