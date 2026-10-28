"""Klient HTTP Allegro: nagłówki, token, retry i paginacja ofert (SPEC §9).

Zasady z SPEC §9:
- `401` → odśwież token **raz** i powtórz żądanie raz; drugi `401` to `AuthError`,
- `422` → `ValidationError` z listą `errors`, bez ponowień,
- `429` → `Retry-After`, a bez niego backoff wykładniczy z jitterem (maks. 5 prób),
- `5xx` i błędy sieci/timeout → do 3 prób, potem `ApiError`,
- inne `4xx` → `ApiError` ze statusem i skróconym ciałem (bez nagłówków).

Baza URL zależy od `ALLEGRO_ENV` (`docs/api-notes.md` §2), a `User-Agent` jest obowiązkowy
(SPEC §4.1). Nagłówek `Authorization` nie trafia do logów ani do komunikatów błędów.
"""

from __future__ import annotations

import email.utils
import logging
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import requests

from view_tracker_ai_1.auth import DeviceFlowAuth, new_session
from view_tracker_ai_1.config import Config
from view_tracker_ai_1.errors import ApiError, AuthError, RateLimitError, ValidationError

logger = logging.getLogger(__name__)

OFFERS_PATH = "/sale/offers"

#: `GET /sale/offers` przyjmuje limit 1..1000, a domyślnie 20 — zawsze ustawiamy jawnie.
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 1000
DEFAULT_STATUSES: tuple[str, ...] = ("ACTIVE",)

#: Krótka pauza między stronami, żeby nie prowokować `429` (SPEC §9).
PAGE_PAUSE_SECONDS = 0.2

MAX_RATE_LIMIT_ATTEMPTS = 5
MAX_SERVER_ATTEMPTS = 3

#: Blokada po `429` trwa około minuty (docs/api-notes.md §5), więc startujemy od 60 s.
RATE_LIMIT_BASE_DELAY = 60.0
SERVER_BASE_DELAY = 1.0
JITTER_SPAN = 0.2  # ±10% wokół wyliczonego opóźnienia

CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 30.0


@dataclass(frozen=True, slots=True)
class RemoteOffer:
    """Oferta tak, jak ją widzi API — z licznikami, ale bez kontekstu bazy."""

    offer_id: str
    name: str
    status: str | None
    visits_count: int
    watchers_count: int


class AllegroClient:
    """Jedno miejsce, które rozmawia z Allegro i poprawnie zachowuje się przy błędach."""

    def __init__(
        self,
        *,
        config: Config,
        auth: DeviceFlowAuth | None = None,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._auth = auth if auth is not None else DeviceFlowAuth(config=config)
        self._session = session if session is not None else new_session(config)
        self._sleep = sleep
        self._rng = rng if rng is not None else _default_rng

    # --- publiczne ----------------------------------------------------------
    def get(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """GET z pełną polityką błędów; zwraca zdekodowany obiekt JSON."""
        return self._request("GET", path, params=params)

    def iter_offers(
        self,
        *,
        statuses: Sequence[str] = DEFAULT_STATUSES,
        limit: int = DEFAULT_PAGE_LIMIT,
        offer_ids: Sequence[str] | None = None,
    ) -> Iterator[RemoteOffer]:
        """Leniwa paginacja `GET /sale/offers` (offset/limit, jawne `limit`)."""
        if not 1 <= limit <= MAX_PAGE_LIMIT:
            raise ValueError(f"limit musi być w zakresie 1..{MAX_PAGE_LIMIT}, jest {limit}.")

        offset = 0
        while True:
            params: dict[str, Any] = {
                "limit": limit,
                "offset": offset,
                "publication.status": list(statuses),
            }
            if offer_ids:
                params["offer.id"] = list(offer_ids)
            payload = self._request("GET", OFFERS_PATH, params=params)
            items = payload.get("offers") or []
            for item in items:
                yield self._parse_offer(item)

            total = payload.get("totalCount")
            offset += limit
            if not items or len(items) < limit:
                break
            if isinstance(total, int) and offset >= total:
                break
            self._sleep(PAGE_PAUSE_SECONDS)

    # --- pojedyncze żądanie z retry ----------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        url = f"{self._config.api_base_url}{path}"
        refreshed = False
        rate_attempts = 0
        server_attempts = 0

        while True:
            response = self._send(method, url, params)
            if response is None:  # błąd sieci/timeout — zaliczony jako próba serwerowa
                server_attempts += 1
                if server_attempts >= MAX_SERVER_ATTEMPTS:
                    raise ApiError("Błąd sieci lub timeout po wyczerpaniu ponowień.")
                self._sleep(self._backoff(server_attempts - 1, SERVER_BASE_DELAY))
                continue

            status = response.status_code

            if status == 401:
                if refreshed:
                    raise AuthError("Token został odrzucony — zaloguj się ponownie: `auth login`.")
                refreshed = True
                logger.warning("401 z API — odświeżam token i powtarzam żądanie raz")
                self._auth.refresh()
                continue

            if status == 422:
                raise self._validation_error(response)

            if status == 429:
                rate_attempts += 1
                delay = self._retry_after(response)
                if delay is None:
                    delay = self._backoff(rate_attempts - 1, RATE_LIMIT_BASE_DELAY)
                if rate_attempts >= MAX_RATE_LIMIT_ATTEMPTS:
                    raise RateLimitError(
                        "Limit zapytań Allegro wyczerpany — spróbuj później.",
                        retry_after=delay,
                    )
                logger.warning("429 z API — czekam %.1f s (próba %d/%d)", delay, rate_attempts,
                               MAX_RATE_LIMIT_ATTEMPTS)
                self._sleep(delay)
                continue

            if status >= 500:
                server_attempts += 1
                if server_attempts >= MAX_SERVER_ATTEMPTS:
                    raise ApiError(
                        f"Błąd serwera Allegro (HTTP {status}) po ponowieniach.",
                        status=status,
                        body=response.text,
                    )
                logger.warning("HTTP %d — ponawiam próbę %d/%d", status, server_attempts,
                               MAX_SERVER_ATTEMPTS)
                self._sleep(self._backoff(server_attempts - 1, SERVER_BASE_DELAY))
                continue

            if status >= 400:
                raise ApiError(
                    f"API zwróciło HTTP {status}.",
                    status=status,
                    body=response.text,
                )

            return self._json(response)

    def _send(
        self,
        method: str,
        url: str,
        params: Mapping[str, Any] | None,
    ) -> requests.Response | None:
        """Wykonaj żądanie; `None` oznacza błąd sieci lub timeout."""
        token = self._auth.get_valid_token()
        try:
            return self._session.request(
                method,
                url,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.RequestException as exc:
            logger.warning("Błąd sieci przy %s %s: %s", method, url, exc.__class__.__name__)
            return None

    # --- parsowanie ---------------------------------------------------------
    def _json(self, response: requests.Response) -> Mapping[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError(
                "Odpowiedź API nie jest poprawnym JSON-em.",
                status=response.status_code,
            ) from exc
        if not isinstance(payload, Mapping):
            raise ApiError("Odpowiedź API nie jest obiektem JSON.", status=response.status_code)
        return payload

    def _validation_error(self, response: requests.Response) -> ValidationError:
        errors: Sequence[Mapping[str, Any]] = ()
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, Mapping) and isinstance(payload.get("errors"), list):
            errors = [error for error in payload["errors"] if isinstance(error, Mapping)]
        return ValidationError("API odrzuciło parametry żądania (HTTP 422).", errors)

    def _parse_offer(self, item: Any) -> RemoteOffer:
        if not isinstance(item, Mapping):
            raise ApiError("Lista ofert zawiera element, który nie jest obiektem.")

        offer_id = item.get("id")
        if not isinstance(offer_id, str) or not offer_id:
            raise ApiError("Oferta w odpowiedzi API nie ma identyfikatora `id`.")

        stats = item.get("stats")
        stats = stats if isinstance(stats, Mapping) else {}
        publication = item.get("publication")
        publication = publication if isinstance(publication, Mapping) else {}
        status = publication.get("status")

        return RemoteOffer(
            offer_id=offer_id,
            name=str(item.get("name") or ""),
            status=None if status is None else str(status),
            visits_count=_as_count(stats.get("visitsCount"), field="visitsCount"),
            watchers_count=_as_count(stats.get("watchersCount"), field="watchersCount"),
        )

    # --- pomocnicze ---------------------------------------------------------
    def _backoff(self, attempt_index: int, base: float) -> float:
        raw = base * (2**attempt_index)
        factor = 1.0 - JITTER_SPAN / 2 + self._rng() * JITTER_SPAN
        return raw * factor

    @staticmethod
    def _retry_after(response: requests.Response) -> float | None:
        raw = response.headers.get("Retry-After")
        if raw is None:
            return None
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
        try:
            moment = email.utils.parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return max(0.0, (moment - datetime.now(UTC)).total_seconds())


def _default_rng() -> float:
    return time.time() % 1.0


def _as_count(value: Any, *, field: str) -> int:
    if value is None:
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError) as exc:
        raise ApiError(f"Licznik `{field}` nie jest liczbą: {value!r}.") from exc
