package dev.pulse.app.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.pulse.app.ui.theme.LocalPulse

@Composable
fun PulseCard(
    modifier: Modifier = Modifier,
    title: String? = null,
    subtitle: String? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val p = LocalPulse.current
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = p.surface),
        border = BorderStroke(1.dp, p.line),
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (title != null) {
                Column {
                    Text(title, color = p.ink, fontWeight = FontWeight.Medium, fontSize = 14.sp)
                    if (subtitle != null) Text(subtitle, color = p.muted, fontSize = 12.sp)
                }
            }
            content()
        }
    }
}

@Composable
fun Eyebrow(text: String) {
    Text(
        text.uppercase(),
        color = LocalPulse.current.muted,
        fontSize = 10.sp,
        letterSpacing = 0.9.sp,
        fontWeight = FontWeight.Medium,
        maxLines = 1,
        overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
    )
}

/** Status shown as icon + word, never colour alone. */
data class Tone(val icon: String, val word: String, val color: androidx.compose.ui.graphics.Color)

@Composable
fun ToneLabel(tone: Tone) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(tone.icon + " ", color = tone.color, fontSize = 11.sp)
        Text(tone.word, color = LocalPulse.current.ink2, fontSize = 11.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
fun Banner(
    text: String,
    detail: String? = null,
) {
    val p = LocalPulse.current
    PulseCard {
        Row(verticalAlignment = Alignment.Top) {
            Text("▲ ", color = p.serious, fontSize = 13.sp)
            Column {
                Text(text, color = p.ink, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                if (detail != null) Text(detail, color = p.ink2, fontSize = 12.sp)
            }
        }
    }
}
