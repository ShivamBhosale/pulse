package dev.pulse.app

import dev.pulse.app.data.UrlPolicy
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class UrlPolicyTest {
    private fun ok(input: String) = (UrlPolicy.normalize(input) as UrlPolicy.Result.Ok).baseUrl

    private fun rejected(input: String) = UrlPolicy.normalize(input) is UrlPolicy.Result.Rejected

    @Test fun httpsAnyHostIsFine() {
        assertEquals("https://pulse.example.org/", ok("https://pulse.example.org"))
        assertEquals("https://box.tail1234.ts.net/", ok("https://box.tail1234.ts.net/"))
    }

    @Test fun plainHttpOnlyForTailscaleLocalhostAndEmulator() {
        assertEquals("http://100.101.102.103:8000/", ok("100.101.102.103:8000"))
        assertEquals("http://box.tail1234.ts.net:8000/", ok("http://box.tail1234.ts.net:8000"))
        assertEquals("http://10.0.2.2:8000/", ok("http://10.0.2.2:8000"))
        assertEquals("http://localhost:8000/", ok("http://localhost:8000"))
        assertTrue(rejected("http://pulse.example.org"))
        assertTrue(rejected("http://192.168.1.20:8000")) // LAN: use Tailscale or https
        assertTrue(rejected("http://100.128.0.1:8000")) // outside 100.64.0.0/10
        assertTrue(rejected("http://100.63.255.255"))
    }

    @Test fun normalisesTrailingSlashAndApiSuffix() {
        assertEquals("https://p.ts.net/", ok("  https://p.ts.net/api/v1/  "))
        assertEquals("https://host/pulse/", ok("https://host/pulse/"))
    }

    @Test fun rejectsGarbage() {
        assertTrue(rejected(""))
        assertTrue(rejected("ftp://p.ts.net"))
        assertTrue(rejected("http://"))
    }

    @Test fun tailscaleRange() {
        assertTrue(UrlPolicy.isPrivateTransport("100.64.0.0"))
        assertTrue(UrlPolicy.isPrivateTransport("100.127.255.255"))
        assertTrue(!UrlPolicy.isPrivateTransport("100.128.0.0"))
        assertTrue(!UrlPolicy.isPrivateTransport("256.64.0.1"))
    }
}
