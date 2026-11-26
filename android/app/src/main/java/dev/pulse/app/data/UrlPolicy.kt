package dev.pulse.app.data

import java.net.URI

/**
 * Which server URLs the app accepts.
 *
 * HTTPS is always fine. Plain HTTP is only accepted for addresses whose traffic is already
 * private: Tailscale (100.64.0.0/10 and *.ts.net, encrypted by WireGuard), localhost, and the
 * Android emulator's host alias 10.0.2.2. Everything else must use HTTPS.
 */
object UrlPolicy {
    sealed interface Result {
        data class Ok(val baseUrl: String) : Result

        data class Rejected(val reason: String) : Result
    }

    fun normalize(input: String): Result {
        var raw = input.trim()
        if (raw.isEmpty()) return Result.Rejected("Enter your Pulse server address")
        if (!raw.contains("://")) raw = "http://$raw"
        val uri =
            try {
                URI(raw)
            } catch (_: Exception) {
                return Result.Rejected("That doesn't look like a web address")
            }
        val scheme = uri.scheme?.lowercase()
        val host = uri.host?.lowercase() ?: return Result.Rejected("The address needs a host name")
        if (scheme != "http" && scheme != "https") {
            return Result.Rejected("Use an http:// or https:// address")
        }
        if (scheme == "http" && !isPrivateTransport(host)) {
            return Result.Rejected(
                "Plain http:// is only allowed for Tailscale addresses (100.x.y.z or *.ts.net). " +
                    "Use https://, for example with `tailscale serve`.",
            )
        }
        val port = if (uri.port == -1) "" else ":${uri.port}"
        var path = (uri.path ?: "").trimEnd('/')
        if (path.endsWith("/api/v1")) path = path.removeSuffix("/api/v1")
        return Result.Ok("$scheme://$host$port$path/")
    }

    fun isPrivateTransport(host: String): Boolean {
        if (host == "localhost" || host == "127.0.0.1" || host == "10.0.2.2") return true
        if (host.endsWith(".ts.net")) return true
        val parts = host.split('.')
        if (parts.size != 4) return false
        val octets = parts.map { it.toIntOrNull() ?: return false }
        if (octets.any { it !in 0..255 }) return false
        // Tailscale's CGNAT range 100.64.0.0/10 = 100.64.0.0 – 100.127.255.255
        return octets[0] == 100 && octets[1] in 64..127
    }
}
