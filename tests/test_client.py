"""Testy klienta HTTP: nagłówki, retry, mapowanie błędów i paginacja (SPEC §9, §12).

Wszystkie żądania są mockowane (`responses`); uśpienia podstawiamy listą, więc testy
nie czekają naprawdę.
"""

from __future__ import annotations

import email.utils
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import requests
import responses

from view_tracker_ai_1.auth import DeviceFlowAuth, Tokens, TokenStore
from view_tracker_ai_1.client import (
    MAX_RATE_LIMIT_ATTEMPTS,
    MAX_SERVER_ATTEMPTS,
    PAGE_PAUSE_SECONDS,
    RATE_LIMIT_BASE_DELAY,
    AllegroClient,
)
from view_tracker_ai_1.config import Config
from view_tracker_ai_1.errors import ApiError, AuthError, RateLimitError, ValidationError

API_BASE = "https://api.allegro.pl.allegrosandbox.pl"
OFFERS_URL = f"{API_BASE}/sale/offers"
TOKEN_URL = "https://allegro.pl.allegrosandbox.pl/auth/oauth/token"

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)

REFRESHED_TOKEN = {
    "access_token": "access-2",
    "token_type": "bearer",
    "refresh_token": "refresh-2",
    "expires_in": 43199,
}

EMPTY_PAGE = {"offers": [], "count": 0, "totalCount": 0}


@dataclass
class Harness:
    client: AllegroClient
    sleeps: list[float]
    store: TokenStore


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def page_url(limit: int, offset: int, statuses: str = "ACTIVE") -> str:
    return f"{OFFERS_URL}?limit={limit}&offset={offset}&publication.status={statuses}"


def make_config() -> Config:
    return Config.from_env(
        {"ALLEGRO_CLIENT_ID": "test-id", "ALLEGRO_CLIENT_SECRET": "test-secret"},
        load_env_file=False,
    )


@pytest.fixture()
def harness(tmp_path: Path) -> Harness:
    config = make_config()
    store = TokenStore(tmp_path / "tokens.json")
    store.save(
        Tokens(
            access_token="access-1",
            refresh_token="refresh-1",
            expires_at=NOW + timedelta(hours=1),
        )
    )
    sleeps: list[float] = []
    auth = DeviceFlowAuth(config=config, store=store, sleep=lambda seconds: None, now=lambda: NOW)
    client = AllegroClient(config=config, auth=auth, sleep=sleeps.append, rng=lambda: 0.5)
    return Harness(client=client, sleeps=sleeps, store=store)


# --- paginacja ---------------------------------------------------------------
@responses.activate
def test_iter_offers_paginates_three_pages(harness: Harness) -> None:
    responses.add(responses.GET, page_url(2, 0), json=load_fixture("offers_page1.json"))
    responses.add(responses.GET, page_url(2, 2), json=load_fixture("offers_page2.json"))
    responses.add(responses.GET, page_url(2, 4), json=load_fixture("offers_page3.json"))

    offers = list(harness.client.iter_offers(limit=2))

    assert [offer.offer_id for offer in offers] == [
        "61001001001",
        "61001001002",
        "61001001003",
        "61001001004",
        "61001001005",
    ]
    assert offers[0].visits_count == 54
    assert offers[0].watchers_count == 3
    assert offers[0].status == "ACTIVE"
    assert harness.sleeps == [PAGE_PAUSE_SECONDS, PAGE_PAUSE_SECONDS]
    assert len(responses.calls) == 3


@responses.activate
def test_iter_offers_stops_at_total_count(harness: Harness) -> None:
    page = {"offers": [{"id": "1", "name": "A"}, {"id": "2", "name": "B"}], "count": 2,
            "totalCount": 4}
    responses.add(responses.GET, page_url(2, 0), json=page)
    responses.add(responses.GET, page_url(2, 2), json=page)

    collected = list(harness.client.iter_offers(limit=2))

    assert [offer.offer_id for offer in collected] == ["1", "2", "1", "2"]
    assert len(responses.calls) == 2


@responses.activate
def test_iter_offers_sends_required_headers(harness: Harness) -> None:
    responses.add(responses.GET, page_url(2, 0), json=EMPTY_PAGE)

    list(harness.client.iter_offers(limit=2))
    request = responses.calls[0].request

    assert request.headers["Accept"] == "application/vnd.allegro.public.v1+json"
    assert request.headers["User-Agent"].startswith("view_tracker_ai_1/")
    assert request.headers["Authorization"] == "Bearer access-1"


@responses.activate
def test_iter_offers_repeats_status_parameter(harness: Harness) -> None:
    responses.add(
        responses.GET,
        page_url(2, 0, statuses="ACTIVE&publication.status=ENDED"),
        json=EMPTY_PAGE,
    )

    list(harness.client.iter_offers(statuses=("ACTIVE", "ENDED"), limit=2))
    assert "publication.status=ENDED" in responses.calls[0].request.url


@pytest.mark.parametrize("limit", [0, -5, 1001])
def test_iter_offers_rejects_invalid_limit(harness: Harness, limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        list(harness.client.iter_offers(limit=limit))


@pytest.mark.parametrize(
    "payload",
    [
        {"offers": [{"name": "bez id"}], "totalCount": 1},
        {"offers": [{"id": "1", "stats": {"visitsCount": "dużo"}}], "totalCount": 1},
        {"offers": ["nie-obiekt"], "totalCount": 1},
    ],
)
@responses.activate
def test_malformed_offers_raise_api_error(harness: Harness, payload: dict[str, object]) -> None:
    responses.add(responses.GET, page_url(2, 0), json=payload)

    with pytest.raises(ApiError):
        list(harness.client.iter_offers(limit=2))


# --- 422 ---------------------------------------------------------------------
@responses.activate
def test_422_becomes_validation_error_without_retry(harness: Harness) -> None:
    responses.add(
        responses.GET,
        OFFERS_URL,
        status=422,
        json={"errors": [{"code": "PARAMETER_MISMATCH", "message": "Zły limit",
                          "path": "limit"}]},
    )

    with pytest.raises(ValidationError) as exc_info:
        harness.client.get("/sale/offers")

    assert exc_info.value.errors[0]["code"] == "PARAMETER_MISMATCH"
    assert exc_info.value.describe() == ["PARAMETER_MISMATCH: Zły limit (pole: limit)"]
    assert len(responses.calls) == 1
    assert harness.sleeps == []


# --- 429 ---------------------------------------------------------------------
@responses.activate
def test_429_honours_retry_after(harness: Harness) -> None:
    responses.add(responses.GET, OFFERS_URL, status=429, headers={"Retry-After": "7"})
    responses.add(responses.GET, OFFERS_URL, json=EMPTY_PAGE)

    harness.client.get("/sale/offers")

    assert harness.sleeps == [7.0]
    assert len(responses.calls) == 2


@responses.activate
def test_429_without_header_uses_exponential_backoff(harness: Harness) -> None:
    responses.add(responses.GET, OFFERS_URL, status=429)
    responses.add(responses.GET, OFFERS_URL, json=EMPTY_PAGE)

    harness.client.get("/sale/offers")

    assert harness.sleeps == [RATE_LIMIT_BASE_DELAY]


@responses.activate
def test_429_exhausted_raises_rate_limit_error(harness: Harness) -> None:
    for _ in range(MAX_RATE_LIMIT_ATTEMPTS):
        responses.add(responses.GET, OFFERS_URL, status=429)

    with pytest.raises(RateLimitError) as exc_info:
        harness.client.get("/sale/offers")

    assert exc_info.value.retry_after is not None
    assert len(responses.calls) == MAX_RATE_LIMIT_ATTEMPTS
    assert harness.sleeps == [60.0, 120.0, 240.0, 480.0]


@responses.activate
def test_429_accepts_http_date_retry_after(harness: Harness) -> None:
    moment = datetime.now(UTC) + timedelta(seconds=30)
    responses.add(
        responses.GET,
        OFFERS_URL,
        status=429,
        headers={"Retry-After": email.utils.format_datetime(moment, usegmt=True)},
    )
    responses.add(responses.GET, OFFERS_URL, json=EMPTY_PAGE)

    harness.client.get("/sale/offers")

    assert 25 <= harness.sleeps[0] <= 30


@responses.activate
def test_429_with_garbage_retry_after_falls_back_to_backoff(harness: Harness) -> None:
    responses.add(responses.GET, OFFERS_URL, status=429, headers={"Retry-After": "niedługo"})
    responses.add(responses.GET, OFFERS_URL, json=EMPTY_PAGE)

    harness.client.get("/sale/offers")

    assert harness.sleeps == [RATE_LIMIT_BASE_DELAY]


# --- 5xx, timeout, inne 4xx --------------------------------------------------
@responses.activate
def test_5xx_is_retried_then_succeeds(harness: Harness) -> None:
    responses.add(responses.GET, OFFERS_URL, status=500)
    responses.add(responses.GET, OFFERS_URL, status=502)
    responses.add(responses.GET, OFFERS_URL, json=EMPTY_PAGE)

    harness.client.get("/sale/offers")

    assert harness.sleeps == [1.0, 2.0]
    assert len(responses.calls) == 3


@responses.activate
def test_5xx_exhausted_raises_api_error(harness: Harness) -> None:
    for _ in range(MAX_SERVER_ATTEMPTS):
        responses.add(responses.GET, OFFERS_URL, status=503, body="awaria")

    with pytest.raises(ApiError) as exc_info:
        harness.client.get("/sale/offers")

    assert exc_info.value.status == 503
    assert len(responses.calls) == MAX_SERVER_ATTEMPTS


@responses.activate
def test_timeout_is_retried_then_raises(harness: Harness) -> None:
    for _ in range(MAX_SERVER_ATTEMPTS):
        responses.add(responses.GET, OFFERS_URL, body=requests.exceptions.Timeout("timeout"))

    with pytest.raises(ApiError, match="Błąd sieci"):
        harness.client.get("/sale/offers")

    assert len(responses.calls) == MAX_SERVER_ATTEMPTS
    assert harness.sleeps == [1.0, 2.0]


@responses.activate
def test_other_4xx_is_not_retried(harness: Harness) -> None:
    responses.add(responses.GET, OFFERS_URL, status=404, body='{"errors": []}')

    with pytest.raises(ApiError) as exc_info:
        harness.client.get("/sale/offers")

    assert exc_info.value.status == 404
    assert len(responses.calls) == 1
    assert harness.sleeps == []


# --- 401 i odświeżanie -------------------------------------------------------
@responses.activate
def test_401_refreshes_token_and_retries_once(harness: Harness) -> None:
    responses.add(responses.GET, OFFERS_URL, status=401, json={"errors": []})
    responses.add(responses.POST, TOKEN_URL, json=REFRESHED_TOKEN)
    responses.add(responses.GET, OFFERS_URL, json=EMPTY_PAGE)

    harness.client.get("/sale/offers")

    assert len(responses.calls) == 3
    assert responses.calls[1].request.url == TOKEN_URL
    assert responses.calls[2].request.headers["Authorization"] == "Bearer access-2"


@responses.activate
def test_second_401_raises_auth_error(harness: Harness) -> None:
    responses.add(responses.GET, OFFERS_URL, status=401, json={"errors": []})
    responses.add(responses.POST, TOKEN_URL, json=REFRESHED_TOKEN)
    responses.add(responses.GET, OFFERS_URL, status=401, json={"errors": []})

    with pytest.raises(AuthError, match="zaloguj się ponownie"):
        harness.client.get("/sale/offers")

    assert len(responses.calls) == 3


@responses.activate
def test_failed_refresh_propagates_auth_error(harness: Harness) -> None:
    responses.add(responses.GET, OFFERS_URL, status=401, json={"errors": []})
    responses.add(responses.POST, TOKEN_URL, status=400, json={"error": "invalid_grant"})

    with pytest.raises(AuthError):
        harness.client.get("/sale/offers")


# --- odpowiedzi niepoprawne --------------------------------------------------
@responses.activate
def test_invalid_json_raises_api_error(harness: Harness) -> None:
    responses.add(responses.GET, OFFERS_URL, body="to nie jest json")
    with pytest.raises(ApiError, match="JSON"):
        harness.client.get("/sale/offers")


@responses.activate
def test_json_array_is_rejected(harness: Harness) -> None:
    responses.add(responses.GET, OFFERS_URL, body="[]")
    with pytest.raises(ApiError, match="obiektem JSON"):
        harness.client.get("/sale/offers")


# --- brak wycieku tokenów ----------------------------------------------------
@responses.activate
def test_token_never_appears_in_logs(harness: Harness, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    for _ in range(MAX_SERVER_ATTEMPTS):
        responses.add(responses.GET, OFFERS_URL, status=500)

    with pytest.raises(ApiError):
        harness.client.get("/sale/offers")

    assert "access-1" not in caplog.text
    assert "Bearer" not in caplog.text
