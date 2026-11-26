package dev.pulse.app.util

import java.text.NumberFormat
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt
import kotlin.math.roundToLong

/** Formatting shared by screens and the widget; mirrors frontend/src/lib/format.ts. */
object Fmt {
    fun num(
        v: Double?,
        decimals: Int = 0,
        locale: Locale = Locale.getDefault(),
    ): String {
        if (v == null || v.isNaN()) return "–"
        val f = NumberFormat.getNumberInstance(locale)
        f.minimumFractionDigits = decimals
        f.maximumFractionDigits = decimals
        return f.format(v)
    }

    /** 301 → "5h 01m", 480 → "8h", 45 → "45m". */
    fun duration(minutes: Double?): String {
        if (minutes == null) return "–"
        val m = abs(minutes).roundToLong()
        val h = m / 60
        val rest = m % 60
        return when {
            h > 0 && rest == 0L -> "${h}h"
            h > 0 -> "${h}h ${rest.toString().padStart(2, '0')}m"
            else -> "${rest}m"
        }
    }

    /** Minutes from local midnight (negative = evening before) → "23:40". */
    fun clock(minutes: Double?): String {
        if (minutes == null) return "–"
        val m = ((minutes.roundToInt() % 1440) + 1440) % 1440
        return "%02d:%02d".format(m / 60, m % 60)
    }

    fun time(
        iso: String?,
        zone: ZoneId = ZoneId.systemDefault(),
    ): String {
        if (iso == null) return "–"
        val t = parseInstant(iso) ?: return "–"
        return DateTimeFormatter.ofPattern("HH:mm").withZone(zone).format(t)
    }

    fun ago(
        iso: String?,
        now: Instant = Instant.now(),
    ): String {
        val t = iso?.let { parseInstant(it) } ?: return "never"
        val s = Duration.between(t, now).seconds.coerceAtLeast(0)
        return when {
            s < 60 -> "just now"
            s < 3600 -> "${s / 60} min ago"
            s < 86400 -> "${s / 3600} h ago"
            else -> "${s / 86400} d ago"
        }
    }

    fun signed(
        v: Double,
        decimals: Int = 0,
    ): String {
        val s = num(abs(v), decimals)
        return when {
            v > 0 -> "+$s"
            v < 0 -> "−$s"
            else -> s
        }
    }

    fun day(
        isoDate: String,
        style: FormatStyle = FormatStyle.MEDIUM,
    ): String =
        try {
            LocalDate.parse(isoDate).format(DateTimeFormatter.ofLocalizedDate(style))
        } catch (_: Exception) {
            isoDate
        }

    fun weekday(isoDate: String): String =
        try {
            LocalDate.parse(isoDate).format(DateTimeFormatter.ofPattern("EEEE, d MMMM"))
        } catch (_: Exception) {
            isoDate
        }

    /** The API sends instants with an offset ("…+00:00") or "Z"; be lenient. */
    fun parseInstant(iso: String): Instant? =
        try {
            java.time.OffsetDateTime.parse(iso).toInstant()
        } catch (_: Exception) {
            try {
                Instant.parse(iso)
            } catch (_: Exception) {
                null
            }
        }
}
