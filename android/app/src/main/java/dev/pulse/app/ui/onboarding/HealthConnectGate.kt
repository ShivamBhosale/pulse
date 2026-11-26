package dev.pulse.app.ui.onboarding

import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.net.toUri
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import dev.pulse.app.AppContainer
import dev.pulse.app.hc.Hc
import dev.pulse.app.ui.theme.LocalPulse
import dev.pulse.app.util.Fmt

private enum class Step { CHECKING, NEEDS_HEALTH_CONNECT, NEEDS_PERMISSION, IMPORTING, READY }

/** First-run flow: Health Connect available → permissions → history import → app. */
@Composable
fun HealthConnectGate(
    container: AppContainer,
    content: @Composable () -> Unit,
) {
    val context = LocalContext.current
    val p = LocalPulse.current
    var step by remember { mutableStateOf(Step.CHECKING) }
    var recheck by remember { mutableIntStateOf(0) }
    var importedTo by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    val launcher =
        rememberLauncherForActivityResult(PermissionController.createRequestPermissionResultContract()) { recheck++ }

    LaunchedEffect(recheck) {
        error = null
        step =
            when {
                Hc.status(context) != HealthConnectClient.SDK_AVAILABLE -> Step.NEEDS_HEALTH_CONNECT
                !container.hc.granted().containsAll(Hc.REQUIRED) -> Step.NEEDS_PERMISSION
                !container.sync.importDone() -> Step.IMPORTING
                else -> Step.READY
            }
        if (step == Step.IMPORTING) {
            try {
                container.sync.importHistory { cursor, _ -> importedTo = cursor.toString() }
                step = Step.READY
            } catch (e: Exception) {
                error = e.message ?: e.javaClass.simpleName
            }
        }
    }

    if (step == Step.READY) {
        content()
        return
    }
    Column(
        Modifier.fillMaxSize().statusBarsPadding().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Spacer(Modifier.height(32.dp))
        Text("Pulse", color = p.ink, fontSize = 28.sp)
        when (step) {
            Step.CHECKING -> Text("Checking Health Connect…", color = p.ink2)
            Step.NEEDS_HEALTH_CONNECT -> {
                Text(
                    "Pulse reads your Fitbit data from Health Connect on this phone. Health Connect isn't available yet.",
                    color = p.ink2,
                )
                Button(onClick = {
                    context.startActivity(Intent(Intent.ACTION_VIEW, "market://details?id=com.google.android.apps.healthdata".toUri()))
                }) { Text("Get Health Connect") }
                TextButton(onClick = { recheck++ }) { Text("Check again", color = p.accentInk) }
            }
            Step.NEEDS_PERMISSION -> {
                Text(
                    "Pulse reads your health data from Health Connect, where your Fitbit app already writes it. " +
                        "Everything stays on this phone: Pulse has no internet access.",
                    color = p.ink2,
                    fontSize = 15.sp,
                )
                Text(
                    "Please allow all, including access to past data (your history) and access in the background (the widget).",
                    color = p.muted,
                    fontSize = 13.sp,
                )
                Button(
                    onClick = { launcher.launch(Hc.PERMISSIONS) },
                    colors = ButtonDefaults.buttonColors(containerColor = p.accent, contentColor = p.page),
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Connect Health Connect") }
            }
            Step.IMPORTING -> {
                Text("Importing your history from Health Connect…", color = p.ink2)
                LinearProgressIndicator(Modifier.fillMaxWidth(), color = p.accent, trackColor = p.surface2)
                importedTo?.let { Text("Back to ${Fmt.day(it)}", color = p.muted, fontSize = 13.sp) }
                Text("This runs once. Keep Pulse open until it finishes.", color = p.muted, fontSize = 12.sp)
                error?.let {
                    Text("▲ $it", color = p.ink2, fontSize = 13.sp)
                    TextButton(onClick = { recheck++ }) { Text("Try again", color = p.accentInk) }
                }
            }
            Step.READY -> Unit
        }
    }
}
