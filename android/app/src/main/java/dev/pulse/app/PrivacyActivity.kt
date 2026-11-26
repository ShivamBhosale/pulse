package dev.pulse.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.pulse.app.ui.theme.LocalPulse
import dev.pulse.app.ui.theme.PulseTheme

/** Shown by Health Connect ("Why does Pulse need this?"). Required for the permission flow. */
class PrivacyActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            PulseTheme {
                val p = LocalPulse.current
                Column(
                    Modifier.fillMaxSize().systemBarsPadding().verticalScroll(rememberScrollState()).padding(24.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text("How Pulse uses your health data", color = p.ink, fontSize = 22.sp)
                    listOf(
                        "Pulse reads steps, distance, calories, floors, heart rate, HRV, resting heart rate, sleep, " +
                            "blood oxygen, breathing rate, skin temperature and workouts from Health Connect.",
                        "It uses them only to show your dashboard, scores, trends, reports and widget on this phone.",
                        "Pulse has no internet permission. Your data never leaves this phone: no accounts, " +
                            "no analytics, no ads, no cloud backup.",
                        "Pulse only reads. It never writes to or deletes anything in Health Connect.",
                        "You can revoke access at any time in Settings → Health Connect → App permissions → Pulse. " +
                            "Uninstalling Pulse deletes everything it stored.",
                    ).forEach { Text(it, color = p.ink2, fontSize = 15.sp, lineHeight = 21.sp) }
                    Text("Scores in Pulse are personal estimates, not medical advice.", color = p.muted, fontSize = 13.sp)
                }
            }
        }
    }
}
