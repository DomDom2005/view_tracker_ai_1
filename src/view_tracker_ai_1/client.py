"""Klient HTTP Allegro: nagłówki, retry (401/429/5xx), mapowanie błędów, paginacja ofert."""

from __future__ import annotations

# TODO(PLAN stage 3): sesja requests z Accept + obowiązkowym User-Agent, timeouty 10/30 s,
# 401 → odśwież i powtórz raz, 429 → Retry-After albo backoff ~60 s, 5xx/timeout → 3 próby,
# iter_offers(statuses, limit) z paginacją offset/limit (limit jawnie, domyślnie 20!).
