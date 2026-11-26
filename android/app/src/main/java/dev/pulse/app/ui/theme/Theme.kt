package dev.pulse.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import dev.pulse.app.R

/** Same tokens as the web app (frontend/src/index.css): one violet accent, status colours for
 *  meaning only (always with an icon + word), validated sleep-stage palette. */
@Immutable
data class PulseColors(
    val page: Color,
    val surface: Color,
    val surface2: Color,
    val line: Color,
    val axis: Color,
    val ink: Color,
    val ink2: Color,
    val muted: Color,
    val accent: Color,
    val accentInk: Color,
    val accentSoft: Color,
    val good: Color,
    val goodInk: Color,
    val warning: Color,
    val serious: Color,
    val critical: Color,
    val deep: Color,
    val light: Color,
    val rem: Color,
    val awake: Color,
)

val DarkPulse =
    PulseColors(
        page = Color(0xFF0E1014),
        surface = Color(0xFF14171C),
        surface2 = Color(0xFF1A1E25),
        line = Color(0xFF242932),
        axis = Color(0xFF3A404A),
        ink = Color(0xFFECEAE4),
        ink2 = Color(0xFFB9B6AD),
        muted = Color(0xFF858B95),
        accent = Color(0xFF9D8CFF),
        accentInk = Color(0xFFB8ABFF),
        accentSoft = Color(0x249D8CFF),
        good = Color(0xFF0CA30C),
        goodInk = Color(0xFF3FCF5A),
        warning = Color(0xFFFAB219),
        serious = Color(0xFFEC835A),
        critical = Color(0xFFD03B3B),
        deep = Color(0xFF3987E5),
        light = Color(0xFFC98500),
        rem = Color(0xFF199E70),
        awake = Color(0xFFD95926),
    )

val LightPulse =
    PulseColors(
        page = Color(0xFFF4F3EF),
        surface = Color(0xFFFBFBF9),
        surface2 = Color(0xFFF0EFEA),
        line = Color(0xFFE1E0D9),
        axis = Color(0xFFC3C2B7),
        ink = Color(0xFF15161A),
        ink2 = Color(0xFF4A4A47),
        muted = Color(0xFF7A7973),
        accent = Color(0xFF5B47D6),
        accentInk = Color(0xFF4A37C4),
        accentSoft = Color(0x1A5B47D6),
        good = Color(0xFF0CA30C),
        goodInk = Color(0xFF006300),
        warning = Color(0xFFFAB219),
        serious = Color(0xFFEC835A),
        critical = Color(0xFFD03B3B),
        deep = Color(0xFF2A78D6),
        light = Color(0xFFEDA100),
        rem = Color(0xFF1BAF7A),
        awake = Color(0xFFEB6834),
    )

val LocalPulse = staticCompositionLocalOf { DarkPulse }

@OptIn(ExperimentalTextApi::class)
private fun plexSans(weight: Int) =
    Font(
        R.font.ibm_plex_sans_variable,
        weight = FontWeight(weight),
        variationSettings = FontVariation.Settings(FontVariation.weight(weight)),
    )

val PlexSans = FontFamily(plexSans(400), plexSans(500), plexSans(600))
val PlexMono =
    FontFamily(
        Font(R.font.ibm_plex_mono_regular, FontWeight.Normal),
        Font(R.font.ibm_plex_mono_medium, FontWeight.Medium),
    )

/** Numbers: monospace with tabular figures, like the web `.num` class. */
val NumStyle = TextStyle(fontFamily = PlexMono, fontFeatureSettings = "tnum", letterSpacing = (-0.2).sp)

@Composable
fun PulseTheme(
    dark: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val p = if (dark) DarkPulse else LightPulse
    val scheme =
        if (dark) {
            darkColorScheme(
                primary = p.accent,
                onPrimary = p.page,
                background = p.page,
                onBackground = p.ink,
                surface = p.surface,
                onSurface = p.ink,
                surfaceVariant = p.surface2,
                onSurfaceVariant = p.ink2,
                outline = p.line,
                secondaryContainer = p.accentSoft,
                onSecondaryContainer = p.accentInk,
            )
        } else {
            lightColorScheme(
                primary = p.accent,
                onPrimary = p.surface,
                background = p.page,
                onBackground = p.ink,
                surface = p.surface,
                onSurface = p.ink,
                surfaceVariant = p.surface2,
                onSurfaceVariant = p.ink2,
                outline = p.line,
                secondaryContainer = p.accentSoft,
                onSecondaryContainer = p.accentInk,
            )
        }
    val base = Typography()
    val type =
        Typography(
            headlineSmall = base.headlineSmall.copy(fontFamily = PlexSans, fontWeight = FontWeight.SemiBold),
            titleLarge = base.titleLarge.copy(fontFamily = PlexSans, fontWeight = FontWeight.SemiBold),
            titleMedium = base.titleMedium.copy(fontFamily = PlexSans, fontWeight = FontWeight.Medium),
            titleSmall = base.titleSmall.copy(fontFamily = PlexSans, fontWeight = FontWeight.Medium),
            bodyLarge = base.bodyLarge.copy(fontFamily = PlexSans),
            bodyMedium = base.bodyMedium.copy(fontFamily = PlexSans),
            bodySmall = base.bodySmall.copy(fontFamily = PlexSans),
            labelLarge = base.labelLarge.copy(fontFamily = PlexSans),
            labelMedium = base.labelMedium.copy(fontFamily = PlexSans),
            labelSmall = base.labelSmall.copy(fontFamily = PlexSans, letterSpacing = 0.8.sp),
        )
    CompositionLocalProvider(LocalPulse provides p) {
        MaterialTheme(colorScheme = scheme, typography = type, content = content)
    }
}
