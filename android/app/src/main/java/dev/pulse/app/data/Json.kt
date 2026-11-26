package dev.pulse.app.data

import kotlinx.serialization.json.Json

val PulseJson =
    Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }
