"""OAuth 2.0 device flow, magazyn tokenów i odświeżanie (SPEC §6 FR-1).

Fakty o API pochodzą z `docs/api-notes.md` §1–3 (zweryfikowane 2026-10-27):
- device code: `POST {auth}/device?client_id=...` z Basic auth,
- token: `POST {auth}/token`, grant_type=device_code albo refresh_token,
- access token żyje 12 h, refresh token 3 miesiące i jest **rotowany przy każdym
  odświeżeniu** (stary działa jeszcze 60 s) — dlatego nowy token zapisujemy natychmiast,
  atomowo i z prawami 600.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

from view_tracker_ai_1.config import Config
from view_tracker_ai_1.errors import ApiError, AuthError

DEVICE_PATH = "/device"
TOKEN_PATH = "/token"

GRANT_TYPE_DEVICE = "urn:ietf:params:oauth:grant-type:device_code"
GRANT_TYPE_REFRESH = "refresh_token"

# Statusy i kody błędów pollingu (docs/api-notes.md §3)
ERROR_PENDING = "authorization_pending"
ERROR_SLOW_DOWN = "slow_down"
ERROR_ACCESS_DENIED = "access_denied"

#: Odświeżamy token, zanim wygaśnie — bufor na zegar i czas odpowiedzi.
EXPIRY_MARGIN = timedelta(minutes=5)
#: Zwiększenie interwału pollingu po odpowiedzi `slow_down`.
SLOW_DOWN_STEP = 5

CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 30.0

DIRECTORY_MODE = 0o700
FILE_MODE = 0o600


@dataclass(frozen=True, slots=True)
class Tokens:
    """Para tokenów; pola z sekretami nie trafiają do `repr`."""

    access_token: str = field(repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    token_type: str = "bearer"
    scope: str | None = None

    def is_expired(
        self,
        *,
        now: datetime,
        margin: timedelta = EXPIRY_MARGIN,
    ) -> bool:
        """Czy token wymaga odświeżenia (z buforem `margin`)."""
        return now + margin >= self.expires_at

    def to_record(self) -> dict[str, object]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": _to_iso(self.expires_at),
            "token_type": self.token_type,
            "scope": self.scope,
        }


@dataclass(frozen=True, slots=True)
class DeviceAuthorization:
    """Odpowiedź na żądanie kodu — to, co pokazujemy użytkownikowi."""

    device_code: str = field(repr=False)
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int
    verification_uri_complete: str | None = None


@dataclass(frozen=True, slots=True)
class TokenStatus:
    """Stan logowania do pokazania w `auth status` — bez wartości tokenów."""

    logged_in: bool
    expires_at: datetime | None = None
    scope: str | None = None
    expired: bool = False


class TokenStore:
    """Plik JSON z tokenami: katalog 700, plik 600, zapis atomowy."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> Tokens | None:
        """Wczytaj tokeny albo `None`, gdy pliku nie ma."""
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise AuthError(f"Nie mogę odczytać pliku tokenów: {self._path}") from exc

        try:
            payload = json.loads(raw)
            return Tokens(
                access_token=str(payload["access_token"]),
                refresh_token=(
                    None if payload.get("refresh_token") is None else str(payload["refresh_token"])
                ),
                expires_at=_from_iso(str(payload["expires_at"])),
                token_type=str(payload.get("token_type") or "bearer"),
                scope=None if payload.get("scope") is None else str(payload["scope"]),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise AuthError(
                "Plik tokenów jest uszkodzony — zaloguj się ponownie: `auth login`."
            ) from exc

    def save(self, tokens: Tokens) -> None:
        """Zapisz tokeny atomowo (plik tymczasowy + `os.replace`)."""
        directory = self._path.parent
        directory.mkdir(parents=True, exist_ok=True)
        _restrict_permissions(directory, DIRECTORY_MODE)

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".tokens-", suffix=".tmp", dir=directory
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(tokens.to_record(), stream, ensure_ascii=False, indent=2)
            _restrict_permissions(temporary_path, FILE_MODE)
            os.replace(temporary_path, self._path)
        except OSError as exc:
            temporary_path.unlink(missing_ok=True)
            raise AuthError("Nie udało się zapisać tokenów (zapis atomowy).") from exc
        _restrict_permissions(self._path, FILE_MODE)

    def clear(self) -> None:
        """Usuń zapisane tokeny (wylogowanie)."""
        self._path.unlink(missing_ok=True)


def new_session(config: Config) -> requests.Session:
    """Sesja HTTP z nagłówkami wymaganymi przez API (SPEC §4.1)."""
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.allegro.public.v1+json",
            "User-Agent": config.user_agent,
        }
    )
    return session


class DeviceFlowAuth:
    """Device flow: start → polling → tokeny; plus odświeżanie i `get_valid_token()`."""

    def __init__(
        self,
        *,
        config: Config,
        store: TokenStore | None = None,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._store = store if store is not None else TokenStore(config.token_store_path)
        self._session = session if session is not None else new_session(config)
        self._sleep = sleep
        self._now = now if now is not None else (lambda: datetime.now(UTC))

    @property
    def store(self) -> TokenStore:
        return self._store

    # --- device flow --------------------------------------------------------
    def start(self, *, scope: str | None = None) -> DeviceAuthorization:
        """Poproś o kod device flow (SPEC §6 FR-1)."""
        client_id, _ = self._config.require_allegro_credentials()
        # TODO(verify): docs nie mówią jasno, czy `scope` idzie w query, czy w body
        # (docs/api-notes.md §8 poz. 1). Wysyłamy w query razem z client_id.
        params = {"client_id": client_id}
        if scope:
            params["scope"] = scope

        response = self._post(f"{self._config.auth_base_url}{DEVICE_PATH}", data={}, params=params)
        payload = self._json(response, context="żądanie kodu")
        try:
            return DeviceAuthorization(
                device_code=str(payload["device_code"]),
                user_code=str(payload["user_code"]),
                verification_uri=str(payload["verification_uri"]),
                expires_in=int(payload.get("expires_in", 600)),
                interval=max(1, int(payload.get("interval", 5))),
                verification_uri_complete=(
                    None
                    if payload.get("verification_uri_complete") is None
                    else str(payload["verification_uri_complete"])
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AuthError("Niepoprawna odpowiedź serwera autoryzacji (brak kodu).") from exc

    def poll(self, authorization: DeviceAuthorization) -> Tokens:
        """Czekaj, aż użytkownik zatwierdzi kod; respektuj `interval` i `slow_down`."""
        deadline = self._now() + timedelta(seconds=authorization.expires_in)
        interval = authorization.interval

        while True:
            response = self._post_token(
                {
                    "grant_type": GRANT_TYPE_DEVICE,
                    "device_code": authorization.device_code,
                }
            )
            if response.status_code == 200:
                tokens = self._tokens_from_payload(self._json(response, context="token"))
                self._store.save(tokens)
                return tokens

            error = self._error_code(response)
            if error == ERROR_PENDING:
                pass
            elif error == ERROR_SLOW_DOWN:
                interval += SLOW_DOWN_STEP
            elif error == ERROR_ACCESS_DENIED:
                raise AuthError("Odmówiono dostępu do konta — spróbuj ponownie: `auth login`.")
            else:
                raise AuthError(
                    f"Autoryzacja nie powiodła się ({error or response.status_code}) — "
                    "zacznij od nowa: `auth login`."
                )

            if self._now() + timedelta(seconds=interval) > deadline:
                raise AuthError("Kod autoryzacji wygasł — zacznij od nowa: `auth login`.")
            self._sleep(interval)

    def login(
        self,
        *,
        announce: Callable[[DeviceAuthorization], None] | None = None,
        scope: str | None = None,
    ) -> Tokens:
        """Pełne logowanie: kod, komunikat dla użytkownika, polling, zapis tokenów."""
        authorization = self.start(scope=scope)
        if announce is not None:
            announce(authorization)
        return self.poll(authorization)

    # --- odświeżanie --------------------------------------------------------
    def refresh(self, tokens: Tokens | None = None) -> Tokens:
        """Odśwież token. Nowy refresh token zapisujemy od razu (rotacja)."""
        current = tokens if tokens is not None else self._store.load()
        if current is None or not current.refresh_token:
            raise AuthError("Brak refresh tokena — zaloguj się ponownie: `auth login`.")

        response = self._post_token(
            {"grant_type": GRANT_TYPE_REFRESH, "refresh_token": current.refresh_token}
        )
        if response.status_code != 200:
            raise AuthError("Nie udało się odświeżyć tokena — zaloguj się ponownie: `auth login`.")

        fresh = self._tokens_from_payload(self._json(response, context="odświeżanie tokena"))
        if fresh.refresh_token is None:
            # Defensywnie: serwer nie odesłał nowego refresh tokena — zachowujemy stary.
            fresh = Tokens(
                access_token=fresh.access_token,
                refresh_token=current.refresh_token,
                expires_at=fresh.expires_at,
                token_type=fresh.token_type,
                scope=fresh.scope,
            )
        self._store.save(fresh)
        return fresh

    def get_valid_token(self) -> str:
        """Zwróć ważny access token, odświeżając go w razie potrzeby.

        Nigdy nie loguje i nie zwraca tokenów w komunikatach błędów.
        """
        tokens = self._store.load()
        if tokens is None:
            raise AuthError("Brak zapisanych tokenów — zaloguj się: `auth login`.")
        if not tokens.is_expired(now=self._now()):
            return tokens.access_token
        return self.refresh(tokens).access_token

    def status(self) -> TokenStatus:
        """Stan logowania bez ujawniania tokenów (dla `auth status`)."""
        tokens = self._store.load()
        if tokens is None:
            return TokenStatus(logged_in=False)
        return TokenStatus(
            logged_in=True,
            expires_at=tokens.expires_at,
            scope=tokens.scope,
            expired=tokens.is_expired(now=self._now()),
        )

    # --- HTTP --------------------------------------------------------------
    def _post(
        self,
        url: str,
        *,
        data: Mapping[str, str],
        params: Mapping[str, str] | None = None,
    ) -> requests.Response:
        client_id, client_secret = self._config.require_allegro_credentials()
        try:
            return self._session.post(
                url,
                data=data,
                params=params,
                auth=HTTPBasicAuth(client_id, client_secret),
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except requests.RequestException as exc:
            raise ApiError(
                f"Błąd sieci przy autoryzacji ({exc.__class__.__name__}).", status=None
            ) from exc

    def _post_token(self, data: Mapping[str, str]) -> requests.Response:
        return self._post(f"{self._config.auth_base_url}{TOKEN_PATH}", data=data)

    # --- parsowanie --------------------------------------------------------
    def _json(self, response: requests.Response, *, context: str) -> Mapping[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise AuthError(f"Niepoprawna odpowiedź serwera autoryzacji ({context}).") from exc
        if not isinstance(payload, Mapping):
            raise AuthError(f"Niepoprawna odpowiedź serwera autoryzacji ({context}).")
        return payload

    def _error_code(self, response: requests.Response) -> str | None:
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, Mapping):
            return None
        error = payload.get("error")
        return None if error is None else str(error)

    def _tokens_from_payload(self, payload: Mapping[str, Any]) -> Tokens:
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise AuthError("Odpowiedź serwera autoryzacji nie zawiera access_token.")
        try:
            expires_in = int(payload.get("expires_in") or 0)
        except (TypeError, ValueError):
            expires_in = 0
        refresh_token = payload.get("refresh_token")
        scope = payload.get("scope")
        return Tokens(
            access_token=access_token,
            refresh_token=None if refresh_token is None else str(refresh_token),
            expires_at=self._now() + timedelta(seconds=expires_in),
            token_type=str(payload.get("token_type") or "bearer"),
            scope=None if scope is None else str(scope),
        )


# --- pomocnicze ------------------------------------------------------------
def _restrict_permissions(path: Path, mode: int) -> None:
    """Ustaw prawa pliku/katalogu; na Windows `chmod` bywa ograniczony — nie blokujemy."""
    with contextlib.suppress(OSError):
        os.chmod(path, mode)


def _to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _from_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
