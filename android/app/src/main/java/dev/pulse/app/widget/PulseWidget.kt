package dev.pulse.app.widget

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.GlanceTheme
import androidx.glance.LocalSize
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.LinearProgressIndicator
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.color.ColorProvider
import androidx.glance.layout.Alignment
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.layout.width
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import dev.pulse.api.models.WidgetSnapshot
import dev.pulse.app.MainActivity
import dev.pulse.app.PulseApp
import dev.pulse.app.data.PulseJson

private val INK = ColorProvider(day = Color(0xFF15161A), night = Color(0xFFECEAE4))
private val INK2 = ColorProvider(day = Color(0xFF4A4A47), night = Color(0xFFB9B6AD))
private val MUTED = ColorProvider(day = Color(0xFF7A7973), night = Color(0xFF858B95))
private val ACCENT = ColorProvider(day = Color(0xFF5B47D6), night = Color(0xFF9D8CFF))
private val TRACK = ColorProvider(day = Color(0xFFF0EFEA), night = Color(0xFF1A1E25))
private val BG = ColorProvider(day = Color(0xFFFBFBF9), night = Color(0xFF14171C))

class PulseWidget : GlanceAppWidget() {
    private val small = DpSize(110.dp, 90.dp)
    private val square = DpSize(110.dp, 150.dp)
    private val wide = DpSize(250.dp, 90.dp)
    override val sizeMode = SizeMode.Responsive(setOf(small, square, wide))

    override suspend fun provideGlance(
        context: Context,
        id: GlanceId,
    ) {
        val json = (context.applicationContext as PulseApp).container.db.kv().get("widget_snapshot")
        val snapshot = json?.let { runCatching { PulseJson.decodeFromString(WidgetSnapshot.serializer(), it) }.getOrNull() }
        val view = WidgetMapper.map(snapshot)
        provideContent { GlanceTheme { Content(view) } }
    }

    @Composable
    private fun Content(v: WidgetView) {
        val size = LocalSize.current
        val showMore = size.width >= wide.width || size.height >= square.height
        Column(
            GlanceModifier
                .fillMaxSize()
                .background(BG)
                .cornerRadius(18.dp)
                .padding(12.dp)
                .clickable(actionStartActivity<MainActivity>()),
        ) {
            Text("READINESS", style = TextStyle(color = MUTED, fontSize = 10.sp, fontWeight = FontWeight.Medium))
            Row(verticalAlignment = Alignment.Bottom) {
                Text(v.readiness, style = TextStyle(color = INK, fontSize = 28.sp, fontWeight = FontWeight.Medium))
                Text(" ${v.readinessIcon}", style = TextStyle(color = ACCENT, fontSize = 12.sp))
            }
            Text(v.readinessLabel, style = TextStyle(color = INK2, fontSize = 11.sp), maxLines = 1)
            Spacer(GlanceModifier.height(8.dp))
            Row(verticalAlignment = Alignment.Bottom) {
                Text(v.steps, style = TextStyle(color = INK, fontSize = 14.sp, fontWeight = FontWeight.Medium))
                Text(" steps ${v.stepsGoal}", style = TextStyle(color = MUTED, fontSize = 10.sp))
            }
            LinearProgressIndicator(
                progress = v.stepsProgress,
                modifier = GlanceModifier.fillMaxWidth().height(4.dp),
                color = ACCENT,
                backgroundColor = TRACK,
            )
            if (showMore) {
                Spacer(GlanceModifier.height(10.dp))
                Row(GlanceModifier.fillMaxWidth()) {
                    Column(GlanceModifier.defaultWeight()) {
                        Text("SLEEP", style = TextStyle(color = MUTED, fontSize = 9.sp, fontWeight = FontWeight.Medium))
                        Text(v.sleep, style = TextStyle(color = INK, fontSize = 13.sp, fontWeight = FontWeight.Medium))
                    }
                    Column(GlanceModifier.defaultWeight()) {
                        Text("AZM THIS WEEK", style = TextStyle(color = MUTED, fontSize = 9.sp, fontWeight = FontWeight.Medium))
                        Text(v.azm, style = TextStyle(color = INK, fontSize = 13.sp, fontWeight = FontWeight.Medium))
                    }
                }
            }
            Spacer(GlanceModifier.defaultWeight())
            Text(v.warning?.let { "▲ $it" } ?: v.asOf, style = TextStyle(color = MUTED, fontSize = 9.sp), maxLines = 1)
        }
    }
}

class PulseWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = PulseWidget()

    override fun onEnabled(context: Context) {
        super.onEnabled(context)
        RefreshWorker.refreshNow(context)
    }
}
