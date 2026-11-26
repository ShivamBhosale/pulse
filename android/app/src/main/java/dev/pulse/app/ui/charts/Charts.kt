package dev.pulse.app.ui.charts

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.pulse.app.ui.theme.LocalPulse
import dev.pulse.app.ui.theme.NumStyle
import java.time.LocalDate
import java.time.format.DateTimeFormatter

/** One point per day; null = no data (a gap, never drawn as zero). */
data class Pt(val day: LocalDate, val value: Double?, val lo: Double? = null, val hi: Double? = null)

private val dayFmt = DateTimeFormatter.ofPattern("d MMM")

/**
 * Line (or bars) over days with an optional usual-range band and goal line. Same conventions as
 * the web charts: thin marks, recessive grid, one axis, values in ink, tap or drag to inspect.
 */
@Composable
fun DayChart(
    points: List<Pt>,
    format: (Double) -> String,
    modifier: Modifier = Modifier,
    bars: Boolean = false,
    goal: Double? = null,
    color: Color? = null,
    height: Dp = 170.dp,
    zeroBased: Boolean = bars,
    diverging: Boolean = false,
    description: String = "Chart",
) {
    val p = LocalPulse.current
    val c = color ?: p.accent
    var selected by remember(points) { mutableStateOf<Int?>(null) }
    val vals = points.flatMap { listOfNotNull(it.value, it.lo, it.hi) } + listOfNotNull(goal)
    if (vals.isEmpty()) {
        Text("No data in this range", color = p.muted, fontSize = 12.sp)
        return
    }
    var lo = vals.min()
    var hi = vals.max()
    if (zeroBased && !diverging) lo = minOf(0.0, lo)
    if (diverging) {
        val m = maxOf(kotlin.math.abs(lo), kotlin.math.abs(hi), 0.1)
        lo = -m
        hi = m
    }
    if (hi - lo < 1e-9) {
        hi += 1
        lo -= 1
    }
    val pad = (hi - lo) * 0.08
    val yMin = if (zeroBased && !diverging && lo >= 0) 0.0 else lo - pad
    val yMax = hi + pad
    val sel = selected?.let { points.getOrNull(it) }
    Column(modifier.semantics { contentDescription = description }) {
        Row(Modifier.fillMaxWidth()) {
            Text(
                if (sel != null) "${sel.day.format(dayFmt)} · ${sel.value?.let(format) ?: "no data"}" +
                    (if (sel.lo != null && sel.hi != null) "  (usual ${format(sel.lo)}–${format(sel.hi)})" else "")
                else "Tap or drag to inspect",
                style = NumStyle,
                fontSize = 11.sp,
                color = if (sel != null) p.ink else p.muted,
            )
        }
        Canvas(
            Modifier
                .fillMaxWidth()
                .height(height)
                .pointerInput(points) {
                    detectTapGestures { o -> selected = ((o.x / size.width) * points.size).toInt().coerceIn(0, points.size - 1) }
                }.pointerInput(points) {
                    detectDragGestures(onDragEnd = {}) { change, _ ->
                        selected = ((change.position.x / size.width) * points.size).toInt().coerceIn(0, points.size - 1)
                    }
                },
        ) {
            val n = points.size
            val step = size.width / n
            fun x(i: Int) = step * i + step / 2
            fun y(v: Double) = (size.height - (v - yMin) / (yMax - yMin) * size.height).toFloat()
            // recessive grid: 3 lines
            for (k in 0..2) {
                val gy = size.height * k / 2f
                drawLine(p.line, Offset(0f, gy), Offset(size.width, gy), strokeWidth = 1f)
            }
            // usual-range band
            if (points.any { it.lo != null }) {
                val band = Path()
                var open = false
                points.forEachIndexed { i, pt ->
                    if (pt.lo != null && pt.hi != null) {
                        if (!open) band.moveTo(x(i), y(pt.hi)) else band.lineTo(x(i), y(pt.hi))
                        open = true
                    }
                }
                points.indices.reversed().forEach { i -> points[i].lo?.let { band.lineTo(x(i), y(it)) } }
                if (open) {
                    band.close()
                    drawPath(band, p.accentSoft)
                }
            }
            if (diverging) drawLine(p.axis, Offset(0f, y(0.0)), Offset(size.width, y(0.0)), strokeWidth = 1f)
            if (bars) {
                val w = (step * 0.62f).coerceAtMost(14.dp.toPx())
                points.forEachIndexed { i, pt ->
                    val v = pt.value ?: return@forEachIndexed
                    val base = if (diverging) 0.0 else yMin.coerceAtLeast(0.0)
                    val top = y(maxOf(v, base))
                    val bottom = y(minOf(v, base))
                    val col = if (diverging) (if (v >= 0) p.awake else p.deep) else c
                    drawRoundRect(
                        col.copy(alpha = if (selected == null || selected == i) 1f else 0.55f),
                        topLeft = Offset(x(i) - w / 2, top),
                        size = Size(w, (bottom - top).coerceAtLeast(1f)),
                        cornerRadius = CornerRadius(3.dp.toPx()),
                    )
                }
            } else {
                val path = Path()
                var started = false
                points.forEachIndexed { i, pt ->
                    val v = pt.value
                    if (v == null) {
                        started = false
                        return@forEachIndexed
                    }
                    if (!started) path.moveTo(x(i), y(v)) else path.lineTo(x(i), y(v))
                    started = true
                }
                drawPath(path, c, style = Stroke(width = 2.dp.toPx(), cap = StrokeCap.Round))
                if (n <= 31) points.forEachIndexed { i, pt -> pt.value?.let { drawCircle(c, 2.5.dp.toPx(), Offset(x(i), y(it))) } }
            }
            goal?.let {
                drawLine(
                    p.ink2,
                    Offset(0f, y(it)),
                    Offset(size.width, y(it)),
                    strokeWidth = 1.dp.toPx(),
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 8f)),
                )
            }
            selected?.let { i ->
                drawLine(p.axis, Offset(x(i), 0f), Offset(x(i), size.height), strokeWidth = 1.dp.toPx())
                points[i].value?.let { v -> if (!bars) drawCircle(c, 4.5.dp.toPx(), Offset(x(i), y(v))) }
            }
        }
        Row(Modifier.fillMaxWidth()) {
            Text(points.first().day.format(dayFmt), style = NumStyle, fontSize = 10.sp, color = p.muted, modifier = Modifier.weight(1f))
            Text(
                "${format(yMin.coerceAtLeast(if (zeroBased) 0.0 else yMin))}–${format(yMax)}",
                style = NumStyle,
                fontSize = 10.sp,
                color = p.muted,
                modifier = Modifier.weight(1f),
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            )
            Text(points.last().day.format(dayFmt), style = NumStyle, fontSize = 10.sp, color = p.muted)
        }
    }
}
