# Data coverage: Fitbit Air on Google Health API v4

Probed on 2026-11-21 over a 7-day window, with the account linked to Google Health.
This file records only which data types and methods work. It contains no health values.

## Types with data (input for Phase 1 and 2)

| Type | Method that works | Filter that worked (list) | Notes |
|---|---|---|---|
| steps | list, dailyRollUp | `steps.interval.civil_start_time` | 1-minute intervals; `count` comes back as a string. dailyRollUp returns `steps.countSum`. |
| heart-rate | list | `heart_rate.sample_time.physical_time` | Very dense: more than 15k points per day. Use rollUp for charts. |
| daily-resting-heart-rate | list | `daily_resting_heart_rate.date` | Includes `dailyRestingHeartRateMetadata` |
| sleep | reconcile | `sleep.interval.civil_end_time` | `type=STAGES`, with summary and stages |
| daily-heart-rate-variability | list | `daily_heart_rate_variability.date` | |
| heart-rate-variability | list | `heart_rate_variability.sample_time.physical_time` | Recorded during sleep |
| active-zone-minutes | list | `active_zone_minutes.interval.civil_start_time` | Split by `heartRateZone` |
| active-energy-burned | list | `active_energy_burned.interval.civil_start_time` | `kcal` |
| total-calories | **dailyRollUp / rollUp only** | — | `totalCalories.kcalSum` |
| calories-in-heart-rate-zone | **dailyRollUp / rollUp only** | — | `caloriesInHeartRateZones[]` |
| daily-oxygen-saturation | list | `daily_oxygen_saturation.date` | |
| oxygen-saturation | list | `oxygen_saturation.sample_time.physical_time` | Recorded during sleep |
| daily-sleep-temperature-derivations | list | `daily_sleep_temperature_derivations.date` | Nightly and baseline °C |
| distance | list | `distance.interval.civil_start_time` | millimeters |
| exercise | list | `exercise.interval.civil_start_time` | Has `metricsSummary` |
| sedentary-period | list | `sedentary_period.interval.civil_start_time` | Interval only, no value fields |
| activity-level | list | `activity_level.interval.civil_start_time` | `activityLevelType` |

## Types with no data on this device or account (hide in the UI)

| Type | Notes |
|---|---|
| floors | Supports only reconcile, rollUp and dailyRollUp. dailyRollUp returned 0 days. Fitbit Air likely has no barometer. |
| altitude | Empty |
| basal-energy-burned | List returned no points. Supports only list and reconcile; dailyRollUp is rejected. |
| vo2-max, run-vo2-max | Empty |
| weight, body-fat | Empty (no manual entries or scale) |

## Rules learned

- Quotas (Cloud Console, 2026-11-22):
  - 300 requests per minute per user. Pulse throttles to at most 120 per minute.
  - 120,000 requests per minute per project.
  - 86.4 million requests per day. A full backfill used about 800 requests; the 15-minute sync uses about 2,100 a day.

- `rollUp` range limits (14 or 90 days) apply to **physical** time. A run of 90 civil days that crosses the fall-back DST change lasts 90 days plus 1 hour, and the API rejects it with a bare `400 INVALID_ARGUMENT`. Pulse chunks 15-minute steps in 60-day pieces.
- For older data, `rollUp` of 15-minute steps sometimes spreads a day's steps across fewer windows. The per-day totals are always exact and match `dailyRollUp`. Repeating the request can return the finer spread. The median-day curve tolerates this, and totals always come from `dailyRollUp`.

- Filters use snake_case data type names, exactly as documented. The camelCase fallback was never needed.
- When a method isn't supported, the API returns a 400 that lists the supported actions. The sync layer should choose a method per type from this table instead of probing.
- The account time zone is `America/Toronto`. Units are kilometres and kilograms.
