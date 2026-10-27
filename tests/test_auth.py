"""Testy OAuth device flow i magazynu tokenów (SPEC §6 FR-1, §13).

Wszystkie żądania HTTP są mockowane (`responses`) — żaden test nie dotyka sieci.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import responses

from view_tracker_ai_1 import auth as auth_module
from view_tracker_ai_1.auth import (
    DeviceFlowAuth,
    Tokens,
    TokenStore,
    new_session,
)
from view_tracker_ai_1.config import Config
from view_tracker_ai_1.errors import ApiError, AuthError, ConfigError

AUTH_BASE = "https://allegro.pl.allegrosandbox.pl/auth/oauth"
DEVICE_URL = f"{AUTH_BASE}/device"
TOKEN_URL = f"{AUTH_BASE}/token"

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)

DEVICE_PAYLOAD = {
    "user_code": "cbt3zdu4g",
    "device_code": "645629715",
    "expires_in": "3600",
    "interval": "5",
    "verification_uri": "https://allegro.pl/skojarz-aplikacje",
    "verification_uri_complete": "https://allegro.pl/skojarz-aplikacje?code=cbt3zdu4g",
}

TOKEN_PAYLOAD = {
    "access_token": "access-1",
    "token_type": "bearer",
    "refresh_token": "refresh-1",
    "expires_in": 43199,
    "scope": "allegro:api:sale:offers:read",
}


class FakeClock:
    def __init__(self, moment: datetime = NOW) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, seconds: float) -> None:
        self.moment += timedelta(seconds=seconds)


def make_config(**overrides: str) -> Config:
    environ = {"ALLEGRO_CLIENT_ID": "test-id", "ALLEGRO_CLIENT_SECRET": "test-secret"}
    environ.update(overrides)
    return Config.from_env(environ, load_env_file=False)


def make_auth(
    tmp_path: Path,
    *,
    clock: FakeClock | None = None,
    store: TokenStore | None = None,
    sleep_calls: list[float] | None = None,
) -> tuple[DeviceFlowAuth, FakeClock, list[float]]:
    clock = clock or FakeClock()
    calls = sleep_calls if sleep_calls is not None else []

    def fake_sleep(seconds: float) -> None:
        calls.append(seconds)
        clock.advance(seconds)

    auth = DeviceFlowAuth(
        config=make_config(),
        store=store or TokenStore(tmp_path / "tokens.json"),
        sleep=fake_sleep,
        now=clock,
    )
    return auth, clock, calls


def save_tokens(store: TokenStore, *, expires_in: int = 3600) -> Tokens:
    tokens = Tokens(
        access_token="access-1",
        refresh_token="refresh-1",
        expires_at=NOW + timedelta(seconds=expires_in),
    )
    store.save(tokens)
    return tokens


def device_authorization(
    *, expires_in: int = 3600, interval: int = 5
) -> auth_module.DeviceAuthorization:
    return auth_module.DeviceAuthorization(
        device_code="645629715",
        user_code="cbt3zdu4g",
        verification_uri="https://allegro.pl/skojarz-aplikacje",
        expires_in=expires_in,
        interval=interval,
    )


# --- start -------------------------------------------------------------------
@responses.activate
def test_start_requests_device_code(tmp_path: Path) -> None:
    responses.add(
        responses.POST, f"{DEVICE_URL}?client_id=test-id", json=DEVICE_PAYLOAD, status=200
    )

    auth, _clock, _calls = make_auth(tmp_path)
    authorization = auth.start()

    assert authorization.device_code == "645629715"
    assert authorization.user_code == "cbt3zdu4g"
    assert authorization.verification_uri == "https://allegro.pl/skojarz-aplikacje"
    assert authorization.interval == 5
    assert authorization.expires_in == 3600

    request = responses.calls[0].request
    assert request.headers["Authorization"].startswith("Basic ")
    assert request.headers["Accept"] == "application/vnd.allegro.public.v1+json"
    assert request.headers["User-Agent"].startswith("view_tracker_ai_1/")


@responses.activate
def test_start_passes_scope_in_query(tmp_path: Path) -> None:
    scope = "allegro:api:sale:offers:read"
    encoded = "allegro%3Aapi%3Asale%3Aoffers%3Aread"
    responses.add(
        responses.POST,
        f"{DEVICE_URL}?client_id=test-id&scope={encoded}",
        json=DEVICE_PAYLOAD,
        status=200,
    )

    auth, _clock, _calls = make_auth(tmp_path)
    auth.start(scope=scope)
    assert "scope=" in responses.calls[0].request.url


@responses.activate
def test_start_requires_credentials(tmp_path: Path) -> None:
    config = Config.from_env({}, load_env_file=False)
    auth = DeviceFlowAuth(config=config, store=TokenStore(tmp_path / "tokens.json"))
    with pytest.raises(ConfigError, match="ALLEGRO_CLIENT_ID"):
        auth.start()


# --- polling -----------------------------------------------------------------
@responses.activate
def test_login_end_to_end(tmp_path: Path) -> None:
    responses.add(
        responses.POST, f"{DEVICE_URL}?client_id=test-id", json=DEVICE_PAYLOAD, status=200
    )
    responses.add(responses.POST, TOKEN_URL, json={"error": "authorization_pending"}, status=400)
    responses.add(responses.POST, TOKEN_URL, json=TOKEN_PAYLOAD, status=200)

    auth, clock, sleeps = make_auth(tmp_path)
    announced = []
    tokens = auth.login(announce=announced.append)

    assert tokens.access_token == "access-1"
    assert announced and announced[0].user_code == "cbt3zdu4g"
    assert sleeps == [5]
    assert len(responses.calls) == 3
    stored = auth.store.load()
    assert stored is not None
    assert stored.access_token == "access-1"
    assert clock.moment > NOW


@responses.activate
def test_poll_waits_until_authorized(tmp_path: Path) -> None:
    responses.add(responses.POST, TOKEN_URL, json={"error": "authorization_pending"}, status=400)
    responses.add(responses.POST, TOKEN_URL, json={"error": "authorization_pending"}, status=400)
    responses.add(responses.POST, TOKEN_URL, json=TOKEN_PAYLOAD, status=200)

    auth, clock, sleeps = make_auth(tmp_path)
    tokens = auth.poll(device_authorization())

    assert tokens.access_token == "access-1"
    assert sleeps == [5, 5]
    assert len(responses.calls) == 3
    stored = auth.store.load()
    assert stored is not None
    assert stored.access_token == "access-1"
    assert clock.moment > NOW


@responses.activate
def test_poll_slow_down_increases_interval(tmp_path: Path) -> None:
    responses.add(responses.POST, TOKEN_URL, json={"error": "slow_down"}, status=400)
    responses.add(responses.POST, TOKEN_URL, json={"error": "authorization_pending"}, status=400)
    responses.add(responses.POST, TOKEN_URL, json=TOKEN_PAYLOAD, status=200)

    auth, _clock, sleeps = make_auth(tmp_path)
    auth.poll(device_authorization())

    assert sleeps == [10, 10]


@responses.activate
def test_poll_access_denied_raises(tmp_path: Path) -> None:
    responses.add(responses.POST, TOKEN_URL, json={"error": "access_denied"}, status=400)

    auth, _clock, _sleeps = make_auth(tmp_path)
    with pytest.raises(AuthError, match="Odmówiono"):
        auth.poll(device_authorization())
    assert auth.store.load() is None


@responses.activate
def test_poll_unknown_error_raises(tmp_path: Path) -> None:
    responses.add(responses.POST, TOKEN_URL, json={"error": "Invalid device code"}, status=400)

    auth, _clock, _sleeps = make_auth(tmp_path)
    with pytest.raises(AuthError, match="Invalid device code"):
        auth.poll(device_authorization())


@responses.activate
def test_poll_stops_when_code_expires(tmp_path: Path) -> None:
    for _ in range(3):
        responses.add(
            responses.POST, TOKEN_URL, json={"error": "authorization_pending"}, status=400
        )

    auth, _clock, _sleeps = make_auth(tmp_path)
    with pytest.raises(AuthError, match="wygasł"):
        auth.poll(device_authorization(expires_in=10, interval=5))
    assert len(responses.calls) == 3


# --- odświeżanie -------------------------------------------------------------
@responses.activate
def test_refresh_rotates_and_saves_new_token(tmp_path: Path) -> None:
    responses.add(responses.POST, TOKEN_URL, json=TOKEN_PAYLOAD, status=200)

    store = TokenStore(tmp_path / "tokens.json")
    save_tokens(store, expires_in=-10)
    auth, clock, _sleeps = make_auth(tmp_path, store=store)

    refreshed = auth.refresh()

    assert refreshed.access_token == "access-1"
    stored = store.load()
    assert stored is not None
    assert stored.refresh_token == "refresh-1"
    assert stored.expires_at > clock.moment

    request = responses.calls[0].request
    body = request.body.decode() if isinstance(request.body, bytes) else request.body
    assert body == "grant_type=refresh_token&refresh_token=refresh-1"


@responses.activate
def test_refresh_failure_raises_and_keeps_store(tmp_path: Path) -> None:
    responses.add(responses.POST, TOKEN_URL, json={"error": "invalid_grant"}, status=400)

    store = TokenStore(tmp_path / "tokens.json")
    save_tokens(store, expires_in=-10)
    auth, _clock, _sleeps = make_auth(tmp_path, store=store)

    with pytest.raises(AuthError, match="zaloguj się ponownie"):
        auth.refresh()

    stored = store.load()
    assert stored is not None
    assert stored.refresh_token == "refresh-1"


def test_refresh_without_tokens_raises(tmp_path: Path) -> None:
    auth, _clock, _sleeps = make_auth(tmp_path)
    with pytest.raises(AuthError, match="Brak refresh tokena"):
        auth.refresh()


@responses.activate
def test_refresh_keeps_old_refresh_token_when_server_omits_it(tmp_path: Path) -> None:
    payload = {key: value for key, value in TOKEN_PAYLOAD.items() if key != "refresh_token"}
    responses.add(responses.POST, TOKEN_URL, json=payload, status=200)

    store = TokenStore(tmp_path / "tokens.json")
    save_tokens(store, expires_in=-10)
    auth, _clock, _sleeps = make_auth(tmp_path, store=store)

    auth.refresh()
    stored = store.load()
    assert stored is not None
    assert stored.refresh_token == "refresh-1"


# --- get_valid_token / status ------------------------------------------------
@responses.activate
def test_get_valid_token_uses_stored_token_without_http(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    save_tokens(store)
    auth, _clock, _sleeps = make_auth(tmp_path, store=store)

    assert auth.get_valid_token() == "access-1"
    assert len(responses.calls) == 0


@responses.activate
def test_get_valid_token_refreshes_expired_token(tmp_path: Path) -> None:
    responses.add(responses.POST, TOKEN_URL, json=TOKEN_PAYLOAD, status=200)

    store = TokenStore(tmp_path / "tokens.json")
    save_tokens(store, expires_in=-60)
    auth, _clock, _sleeps = make_auth(tmp_path, store=store)

    assert auth.get_valid_token() == "access-1"
    assert len(responses.calls) == 1


@responses.activate
def test_get_valid_token_refreshes_within_margin(tmp_path: Path) -> None:
    responses.add(responses.POST, TOKEN_URL, json=TOKEN_PAYLOAD, status=200)

    store = TokenStore(tmp_path / "tokens.json")
    save_tokens(store, expires_in=60)  # mniej niż EXPIRY_MARGIN (5 min)
    auth, _clock, _sleeps = make_auth(tmp_path, store=store)

    assert auth.get_valid_token() == "access-1"
    assert len(responses.calls) == 1


def test_get_valid_token_without_store_raises(tmp_path: Path) -> None:
    auth, _clock, _sleeps = make_auth(tmp_path)
    with pytest.raises(AuthError, match="Brak zapisanych tokenów"):
        auth.get_valid_token()


def test_status_reports_login_state(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    auth, _clock, _sleeps = make_auth(tmp_path, store=store)

    assert auth.status().logged_in is False

    save_tokens(store, expires_in=3600)
    status = auth.status()
    assert status.logged_in is True
    assert status.expired is False
    assert status.expires_at == NOW + timedelta(seconds=3600)


def test_status_marks_expired_token(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    save_tokens(store, expires_in=-60)
    auth, _clock, _sleeps = make_auth(tmp_path, store=store)

    assert auth.status().expired is True


# --- magazyn tokenów ---------------------------------------------------------
def test_store_roundtrip_and_permissions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    modes: list[int] = []
    real_chmod = os.chmod
    monkeypatch.setattr(
        auth_module.os, "chmod", lambda path, mode: (modes.append(mode), real_chmod(path, mode))
    )

    store = TokenStore(tmp_path / "nested" / "tokens.json")
    saved = save_tokens(store, expires_in=120)

    assert store.load() == saved
    assert 0o700 in modes
    assert 0o600 in modes
    assert directories_leftovers(tmp_path) == []


def test_store_clear_removes_file(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    save_tokens(store)
    assert store.path.exists()

    store.clear()
    assert not store.path.exists()
    assert store.load() is None


def test_corrupted_token_file_raises(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    store.path.write_text("{to nie jest json", encoding="utf-8")

    with pytest.raises(AuthError, match="uszkodzony"):
        store.load()


def test_token_file_is_readable_json(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    save_tokens(store)

    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert payload["access_token"] == "access-1"
    assert payload["expires_at"].endswith("+00:00")


def test_tokens_repr_hides_secrets(tmp_path: Path) -> None:
    tokens = save_tokens(TokenStore(tmp_path / "tokens.json"))
    assert "access-1" not in repr(tokens)
    assert "refresh-1" not in repr(tokens)


def test_device_code_is_hidden_in_repr() -> None:
    assert "645629715" not in repr(device_authorization())


@responses.activate
def test_refresh_error_message_has_no_token(tmp_path: Path) -> None:
    responses.add(responses.POST, TOKEN_URL, json={"error": "invalid_grant"}, status=400)

    store = TokenStore(tmp_path / "tokens.json")
    save_tokens(store, expires_in=-10)
    auth, _clock, _sleeps = make_auth(tmp_path, store=store)

    with pytest.raises(AuthError) as exc_info:
        auth.refresh()
    message = str(exc_info.value)
    assert "refresh-1" not in message
    assert "access-1" not in message


@pytest.mark.skipif(sys.platform == "win32", reason="uprawnienia POSIX nie dotyczą Windows")
def test_store_sets_posix_modes(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    save_tokens(store)

    assert store.path.stat().st_mode & 0o777 == 0o600
    assert store.path.parent.stat().st_mode & 0o777 == 0o700


# --- błędy sieci -------------------------------------------------------------
@responses.activate
def test_network_error_becomes_api_error(tmp_path: Path) -> None:
    auth, _clock, _sleeps = make_auth(tmp_path)
    with pytest.raises(ApiError, match="Błąd sieci"):
        auth.start()


def test_new_session_sets_required_headers() -> None:
    session = new_session(make_config())
    assert session.headers["Accept"] == "application/vnd.allegro.public.v1+json"
    assert session.headers["User-Agent"].startswith("view_tracker_ai_1/")


def directories_leftovers(root: Path) -> list[str]:
    return [path.name for path in root.rglob(".tokens-*.tmp")]
