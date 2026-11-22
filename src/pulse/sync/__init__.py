"""Sync pipeline: planner (windows/chunks), parsers (JSON → rows), streams (what to fetch),
engine (run/backfill with locking and sync_state bookkeeping)."""
