"""Faza 3: zmiana ceny przez PATCH /sale/product-offers/{offerId} (dry-run domyślnie)."""

from __future__ import annotations

# TODO(PLAN stage 9): ciało {"sellingMode":{"price":{"amount":"49.99","currency":"PLN"}}},
# 200/202 (Location + retry-after), 422 → czytelne błędy, tylko sandbox, wpis do actions_log.
