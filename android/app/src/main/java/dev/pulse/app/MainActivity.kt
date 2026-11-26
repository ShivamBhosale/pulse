package dev.pulse.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import dev.pulse.app.ui.PulseRoot
import dev.pulse.app.ui.theme.PulseTheme
import dev.pulse.app.widget.RefreshWorker

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val container = (application as PulseApp).container
        setContent { PulseTheme { PulseRoot(container) } }
    }

    override fun onResume() {
        super.onResume()
        RefreshWorker.refreshNow(this)
    }
}
