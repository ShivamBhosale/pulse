package dev.pulse.app.ui.today

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.pulse.api.models.Tile
import dev.pulse.app.ui.Eyebrow
import dev.pulse.app.ui.PulseCard
import dev.pulse.app.ui.Tone
import dev.pulse.app.ui.ToneLabel
import dev.pulse.app.ui.theme.LocalPulse
import dev.pulse.app.ui.theme.NumStyle
import dev.pulse.app.ui.theme.PulseColors
import dev.pulse.app.util.Fmt

/** Same rules as the web Tile: status colours only for meaning, always icon + word. */
fun toneFor(
    t: Tile,
    p: PulseColors,
): Tone? {
    val delta = t.delta ?: return null
    if (t.status == Tile.Status.none) return null
    if (t.status == Tile.Status.in_range) return Tone("●", "Usual", p.good)
    val up = delta > 0
    val favourable = t.better != Tile.Better.none && (t.better == Tile.Better.up) == up
    val icon = if (up) "▲" else "▼"
    return when {
        favourable -> Tone(icon, if (up) "Above usual" else "Below usual", p.good)
        t.status == Tile.Status.mild -> Tone(icon, if (up) "A bit high" else "A bit low", p.warning)
        else -> Tone(icon, if (up) "Well above usual" else "Well below usual", p.serious)
    }
}

fun displayValue(t: Tile): Pair<String, String> {
    val v = t.value ?: return "–" to ""
    return when (t.key) {
        "sleep_main_min" -> Fmt.duration(v) to ""
        "hrv_rmssd" -> Fmt.num(v, 1) to "ms"
        "resting_hr" -> Fmt.num(v) to "bpm"
        "azm" -> Fmt.num(v) to "min"
        "steps" -> Fmt.num(v) to ""
        "readiness" -> Fmt.num(v) to "/ 100"
        else -> Fmt.num(v) to t.unit
    }
}

fun deltaText(t: Tile): String? {
    val d = t.delta ?: return null
    if (t.baseline == null) return null
    return if (t.key == "sleep_main_min") {
        (if (d >= 0) "+" else "−") + Fmt.duration(kotlin.math.abs(d)) + " vs usual"
    } else {
        Fmt.signed(d, if (t.key == "hrv_rmssd") 1 else 0) + " vs usual"
    }
}

@Composable
fun TileCard(
    t: Tile,
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
) {
    val p = LocalPulse.current
    val tone = toneFor(t, p)
    val (value, unit) = displayValue(t)
    PulseCard(modifier = modifier.heightIn(min = 140.dp).let { if (onClick != null) it.clickable(onClick = onClick) else it }) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Box(Modifier.weight(1f).padding(end = 6.dp)) { Eyebrow(t.label) }
            tone?.let { ToneLabel(it) }
        }
        Row(verticalAlignment = Alignment.Bottom) {
            Text(value, style = NumStyle, fontSize = 26.sp, color = if (t.value == null) p.muted else p.ink, fontWeight = FontWeight.Medium)
            if (unit.isNotEmpty()) Text(" $unit", color = p.muted, fontSize = 13.sp, modifier = Modifier.padding(bottom = 3.dp))
        }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
            Column(Modifier.weight(1f)) {
                deltaText(t)?.let { Text(it, style = NumStyle, fontSize = 11.sp, color = p.ink2) }
                t.note?.let { Text(it, fontSize = 11.sp, color = p.muted, maxLines = 1, overflow = TextOverflow.Ellipsis) }
            }
            Sparkline(t, Modifier.width(76.dp).height(28.dp))
        }
        val goal = t.goal
        val v = t.value
        if (goal != null && v != null && t.key != "azm" && goal > 0) {
            val pct = (v / goal).coerceIn(0.0, 1.0).toFloat()
            Box(
                Modifier.fillMaxWidth().height(3.dp).clip(RoundedCornerShape(2.dp)).background(p.surface2)
                    .semantics { contentDescription = "${(pct * 100).toInt()}% of goal" },
            ) {
                Box(Modifier.fillMaxWidth(pct).fillMaxHeight().background(p.accent))
            }
        }
        if (t.key == "readiness" && onClick != null) {
            Text("ⓘ How it's calculated", color = p.muted, fontSize = 11.sp)
        }
    }
}

/** 14-day sparkline with the usual-range band, like the web tile. */
@Composable
fun Sparkline(
    t: Tile,
    modifier: Modifier,
) {
    val p = LocalPulse.current
    val values = t.spark.map { it.value }
    val nums = values.filterNotNull()
    if (nums.size < 2) {
        Spacer(modifier)
        return
    }
    val band = if (t.key == "steps" || t.key == "azm") null else t.baseline
    val lo = minOf(nums.min(), band?.q1 ?: nums.min())
    val hi = maxOf(nums.max(), band?.q3 ?: nums.max())
    val span = (hi - lo).takeIf { it > 0 } ?: 1.0
    Canvas(modifier) {
        fun y(v: Double) = size.height - ((v - lo) / span * (size.height - 4) + 2).toFloat()
        val step = size.width / (values.size - 1)
        band?.let {
            drawRect(p.accentSoft, topLeft = Offset(0f, y(it.q3)), size = androidx.compose.ui.geometry.Size(size.width, y(it.q1) - y(it.q3)))
        }
        val path = Path()
        var started = false
        values.forEachIndexed { i, v ->
            if (v == null) {
                started = false
                return@forEachIndexed
            }
            val x = i * step
            if (!started) path.moveTo(x, y(v)) else path.lineTo(x, y(v))
            started = true
        }
        drawPath(path, p.accent, style = Stroke(width = 1.5.dp.toPx(), cap = StrokeCap.Round))
        values.lastOrNull()?.let { drawCircle(p.accent, radius = 2.5.dp.toPx(), center = Offset(size.width, y(it))) }
    }
}

@Composable
fun ReadinessDetails(t: Tile) {
    val p = LocalPulse.current
    val labels = mapOf("hrv" to "HRV", "rhr" to "Resting HR", "sleep" to "Sleep", "strain" to "Strain")
    Column(Modifier.padding(horizontal = 20.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Readiness ${t.value?.let { Fmt.num(it) } ?: "–"} / 100", color = p.ink, fontSize = 18.sp, fontWeight = FontWeight.Medium)
        Text("Personal heuristic, not a medical measure.", color = p.muted, fontSize = 12.sp)
        t.components.orEmpty().forEach { c ->
            val key = c.key.value
            Column {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(labels[key] ?: c.label, color = p.ink2, fontSize = 13.sp)
                    Text(
                        (c.score?.let { Fmt.num(it) } ?: "missing") + if (c.weight > 0) " × ${(c.weight * 100).toInt()}%" else "",
                        style = NumStyle,
                        fontSize = 12.sp,
                        color = p.muted,
                    )
                }
                Box(Modifier.fillMaxWidth().height(4.dp).clip(RoundedCornerShape(2.dp)).background(p.surface2)) {
                    c.score?.let { s -> Box(Modifier.fillMaxWidth((s / 100).toFloat().coerceIn(0f, 1f)).fillMaxHeight().background(p.accent)) }
                }
                Text(componentText(key, c.value, c.reference), color = p.muted, fontSize = 11.sp, style = NumStyle)
            }
        }
        t.formula?.let { Text(it, color = p.ink2, fontSize = 12.sp, lineHeight = 17.sp) }
        Text("Change the weights in Pulse → Settings.", color = p.muted, fontSize = 11.sp)
        Spacer(Modifier.size(16.dp))
    }
}

private fun componentText(
    key: String,
    value: Double?,
    ref: Double?,
): String {
    if (value == null) return "no data"
    return when (key) {
        "sleep" -> "${Fmt.duration(value)} of ${Fmt.duration(ref)}"
        "hrv" -> "${Fmt.num(value, 1)} ms" + (ref?.let { " · usual ${Fmt.num(it, 1)}" } ?: "")
        "rhr" -> "${Fmt.num(value)} bpm" + (ref?.let { " · usual ${Fmt.num(it)}" } ?: "")
        else -> "${Fmt.num(value)} min" + (ref?.let { " · usual ${Fmt.num(it)}" } ?: "")
    }
}
