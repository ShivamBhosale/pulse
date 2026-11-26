package dev.pulse.app.ui.onboarding

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.pulse.app.AppContainer
import dev.pulse.app.data.ApiResult
import dev.pulse.app.data.UrlPolicy
import dev.pulse.app.ui.theme.LocalPulse
import kotlinx.coroutines.launch

@Composable
private fun fieldColors() =
    LocalPulse.current.let { p ->
        OutlinedTextFieldDefaults.colors(
            focusedBorderColor = p.accent,
            unfocusedBorderColor = p.line,
            focusedTextColor = p.ink,
            unfocusedTextColor = p.ink,
            cursorColor = p.accent,
            focusedLabelColor = p.accentInk,
            unfocusedLabelColor = p.muted,
        )
    }

@Composable
fun ServerScreen(
    container: AppContainer,
    initial: String?,
    onSaved: () -> Unit,
) {
    val p = LocalPulse.current
    val scope = rememberCoroutineScope()
    var text by remember { mutableStateOf(initial?.removeSuffix("/") ?: "") }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }

    fun test() {
        when (val r = UrlPolicy.normalize(text)) {
            is UrlPolicy.Result.Rejected -> message = r.reason
            is UrlPolicy.Result.Ok ->
                scope.launch {
                    busy = true
                    message = null
                    when (val h = container.repository(r.baseUrl).health()) {
                        is ApiResult.Ok -> {
                            container.config.setUrl(r.baseUrl)
                            onSaved()
                        }
                        is ApiResult.Offline ->
                            message = "Couldn't reach ${r.baseUrl}. Is Tailscale on, and is Pulse running? (${h.message})"
                        is ApiResult.Failed -> message = "That server answered, but not like Pulse (${h.message})."
                        ApiResult.Locked -> {
                            container.config.setUrl(r.baseUrl)
                            onSaved()
                        }
                    }
                    busy = false
                }
        }
    }

    Column(
        Modifier.fillMaxSize().statusBarsPadding().imePadding().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Spacer(Modifier.height(32.dp))
        Text("Pulse", color = p.ink, fontSize = 28.sp, style = androidx.compose.material3.MaterialTheme.typography.headlineSmall)
        Text(
            "Enter your Pulse server's address. Over Tailscale that's your server's name " +
                "(https://<server>.<tailnet>.ts.net) or its 100.x.y.z address with port 8000.",
            color = p.ink2,
            fontSize = 14.sp,
        )
        OutlinedTextField(
            value = text,
            onValueChange = { text = it },
            label = { Text("Server address") },
            placeholder = { Text("https://pulse.tailnet.ts.net") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Go),
            keyboardActions = androidx.compose.foundation.text.KeyboardActions(onGo = { test() }),
            colors = fieldColors(),
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = { test() },
            enabled = !busy && text.isNotBlank(),
            colors = ButtonDefaults.buttonColors(containerColor = p.accent, contentColor = p.page),
            modifier = Modifier.fillMaxWidth(),
        ) { Text(if (busy) "Testing…" else "Connect") }
        message?.let { Text("▲ $it", color = p.ink2, fontSize = 13.sp) }
        Text(
            "Your health data only travels between this phone and your server.",
            color = p.muted,
            fontSize = 12.sp,
        )
    }
}

@Composable
fun PasscodeScreen(
    container: AppContainer,
    url: String,
    onUnlocked: () -> Unit,
    onChangeServer: () -> Unit,
) {
    val p = LocalPulse.current
    val scope = rememberCoroutineScope()
    var code by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }

    fun unlock() {
        if (code.length !in 4..6) return
        scope.launch {
            busy = true
            message =
                when (val r = container.repository(url).unlock(code)) {
                    is ApiResult.Ok -> {
                        onUnlocked()
                        null
                    }
                    ApiResult.Locked -> "Wrong passcode."
                    is ApiResult.Failed -> if (r.code == 429) "Too many attempts. Wait a minute." else r.message
                    is ApiResult.Offline -> "Couldn't reach the server."
                }
            if (message != null) code = ""
            busy = false
        }
    }

    Column(
        Modifier.fillMaxSize().statusBarsPadding().imePadding().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Spacer(Modifier.height(48.dp))
        Text("Enter passcode", color = p.ink, fontSize = 22.sp)
        Text("This Pulse server is locked with a 4–6 digit passcode.", color = p.ink2, fontSize = 14.sp)
        OutlinedTextField(
            value = code,
            onValueChange = { v -> code = v.filter(Char::isDigit).take(6) },
            label = { Text("Passcode") },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword, imeAction = ImeAction.Done),
            keyboardActions = androidx.compose.foundation.text.KeyboardActions(onDone = { unlock() }),
            colors = fieldColors(),
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = { unlock() },
            enabled = !busy && code.length >= 4,
            colors = ButtonDefaults.buttonColors(containerColor = p.accent, contentColor = p.page),
            modifier = Modifier.fillMaxWidth(),
        ) { Text(if (busy) "Checking…" else "Unlock") }
        message?.let { Text("▲ $it", color = p.ink2, fontSize = 13.sp) }
        TextButton(onClick = onChangeServer) { Text("Use a different server", color = p.muted) }
    }
}
