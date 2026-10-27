"""SQLite: schemat, idempotentne migracje i zapytania. Bez żądań sieciowych."""

from __future__ import annotations

# TODO(PLAN stage 1): schemat z SPEC §7 + schema_version, upsert_offer, insert_snapshots,
# get_series, list_offers, get_last_snapshot, cache komentarzy AI, log_action; czasy w UTC.
