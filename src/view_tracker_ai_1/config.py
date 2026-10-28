"""Konfiguracja aplikacji: wczytywanie env, walidacja, logowanie z redakcją sekretów.

Zasady (SPEC §6 NFR-6, §13):
- brak globalnego stanu — `Config` jest przekazywany jawnie,
- komendy niewymagające API nie potrzebują sekretów Allegro (sprawdzane dopiero przez
  `require_allegro_credentials()`),
- każdy log przechodzi przez filtr maskujący tokeny, nagłówki `Authorization` i klucze API.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TextIO

from dotenv import load_dotenv

from view_tracker_ai_1 import __version__
from view_tracker_ai_1.errors import ConfigError

REPO_URL = "https://github.com/DomDom2005/view_tracker_ai_1"
DEFAULT_USER_AGENT = f"view_tracker_ai_1/{__version__} (+{REPO_URL})"

VALID_ENVS: tuple[str, ...] = ("sandbox", "prod")
VALID_LLM_PROVIDERS: tuple[str, ...] = ("anthropic", "none")

API_BASE_URLS: Mapping[str, str] = {
    "sandbox": "https://api.allegro.pl.allegrosandbox.pl",
    "prod": "https://api.allegro.pl",
}
AUTH_BASE_URLS: Mapping[str, str] = {
    "sandbox": "https://allegro.pl.allegrosandbox.pl/auth/oauth",
    "prod": "https://allegro.pl/auth/oauth",
}

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"", "0", "false", "no", "off"})

DEFAULT_ENV = "sandbox"
DEFAULT_LOG_LEVEL = "INFO"


def default_token_store_path() -> Path:
    """Domyślna ścieżka pliku tokenów — poza repo (SPEC §13)."""
    return Path.home() / ".config" / "view_tracker_ai_1" / "tokens.json"


def default_db_path(env: str) -> Path:
    """Osobna baza per środowisko (SPEC §7): `data/sandbox.db` albo `data/prod.db`."""
    return Path("data") / f"{env}.db"


@dataclass(frozen=True, slots=True)
class Config:
    """Konfiguracja aplikacji. Tworzona jawnie; brak stanu globalnego."""

    env: str = DEFAULT_ENV
    client_id: str | None = None
    client_secret: str | None = None
    user_agent: str = DEFAULT_USER_AGENT
    token_store_path: Path = field(default_factory=default_token_store_path)
    db_path: Path | None = None
    llm_provider: str = "none"
    anthropic_api_key: str | None = None
    llm_model: str | None = None
    allow_prod_writes: bool = False
    log_level: str = DEFAULT_LOG_LEVEL

    # --- pochodne -----------------------------------------------------------
    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def api_base_url(self) -> str:
        return API_BASE_URLS[self.env]

    @property
    def auth_base_url(self) -> str:
        return AUTH_BASE_URLS[self.env]

    @property
    def effective_db_path(self) -> Path:
        return self.db_path if self.db_path is not None else default_db_path(self.env)

    # --- wymagania uruchamiane dopiero tam, gdzie są potrzebne --------------
    def require_allegro_credentials(self) -> tuple[str, str]:
        """Zwróć `(client_id, client_secret)` albo rzuć `ConfigError` z podpowiedzią."""
        if not self.client_id or not self.client_secret:
            raise ConfigError(
                "Brak ALLEGRO_CLIENT_ID / ALLEGRO_CLIENT_SECRET. Uzupełnij `.env` "
                "(wzór w `.env.example`) i ponów."
            )
        return self.client_id, self.client_secret

    def require_write_permission(self) -> None:
        """Zapisy do API: na produkcji tylko przy `ALLOW_PROD_WRITES=1` (SPEC §6 FR-9)."""
        if self.is_prod and not self.allow_prod_writes:
            raise ConfigError(
                "Zapisy do API na produkcji są zablokowane. Ustaw ALLOW_PROD_WRITES=1, "
                "jeśli naprawdę chcesz zmieniać dane poza sandboxem."
            )

    def require_llm(self) -> tuple[str, str]:
        """Zwróć `(api_key, model)` albo rzuć `ConfigError` z podpowiedzią (SPEC §13)."""
        if self.llm_provider != "anthropic":
            raise ConfigError(
                "Komentarz AI jest wyłączony (LLM_PROVIDER=none). Ustaw LLM_PROVIDER=anthropic "
                "albo użyj --no-ai."
            )
        if not self.anthropic_api_key:
            raise ConfigError("LLM_PROVIDER=anthropic wymaga ANTHROPIC_API_KEY (w `.env`).")
        if not self.llm_model:
            raise ConfigError(
                "LLM_PROVIDER=anthropic wymaga LLM_MODEL — nazwy modelu nie zgadujemy "
                "(SPEC §0 pkt 2)."
            )
        return self.anthropic_api_key, self.llm_model

    def with_overrides(self, **changes: object) -> Config:
        """Kopia konfiguracji z nadpisanymi polami (np. `--env`/`--db` z CLI)."""
        return replace(self, **changes)  # type: ignore[arg-type]

    # --- konstrukcja --------------------------------------------------------
    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        dotenv_path: str | Path | None = None,
        load_env_file: bool = True,
    ) -> Config:
        """Zbuduj konfigurację z env (opcjonalnie doładowując plik `.env`)."""
        if environ is None:
            if load_env_file:
                load_dotenv(dotenv_path=dotenv_path, override=False)
            source: Mapping[str, str] = os.environ
        else:
            source = environ

        env = (_clean(source.get("ALLEGRO_ENV")) or "").lower() or DEFAULT_ENV
        if env not in VALID_ENVS:
            raise ConfigError(
                f"ALLEGRO_ENV={env!r} jest niepoprawne — dozwolone: {', '.join(VALID_ENVS)}."
            )

        provider = (_clean(source.get("LLM_PROVIDER")) or "").lower() or "none"
        if provider not in VALID_LLM_PROVIDERS:
            raise ConfigError(
                f"LLM_PROVIDER={provider!r} jest niepoprawne — "
                f"dozwolone: {', '.join(VALID_LLM_PROVIDERS)}."
            )

        api_key = _clean(source.get("ANTHROPIC_API_KEY"))
        if provider == "anthropic" and api_key is None:
            raise ConfigError("LLM_PROVIDER=anthropic wymaga ANTHROPIC_API_KEY.")

        log_level = (_clean(source.get("LOG_LEVEL")) or DEFAULT_LOG_LEVEL).upper()
        if log_level not in logging.getLevelNamesMapping():
            raise ConfigError(f"LOG_LEVEL={log_level!r} nie jest poziomem logowania.")

        db_path_value = _clean(source.get("DB_PATH"))
        token_path_value = _clean(source.get("TOKEN_STORE_PATH"))

        return cls(
            env=env,
            client_id=_clean(source.get("ALLEGRO_CLIENT_ID")),
            client_secret=_clean(source.get("ALLEGRO_CLIENT_SECRET")),
            user_agent=_clean(source.get("ALLEGRO_USER_AGENT")) or DEFAULT_USER_AGENT,
            token_store_path=(
                Path(token_path_value).expanduser()
                if token_path_value is not None
                else default_token_store_path()
            ),
            db_path=Path(db_path_value).expanduser() if db_path_value is not None else None,
            llm_provider=provider,
            anthropic_api_key=api_key,
            llm_model=_clean(source.get("LLM_MODEL")),
            allow_prod_writes=_as_bool(source.get("ALLOW_PROD_WRITES"), name="ALLOW_PROD_WRITES"),
            log_level=log_level,
        )


# --- redakcja logów ---------------------------------------------------------

REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)\S+"), r"\1***"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 ***"),
    (
        re.compile(
            r"(?i)\b(access_token|refresh_token|client_secret|api_key|apikey|"
            r"anthropic_api_key)(\s*[=:]\s*)[^\s,;&\"']+"
        ),
        r"\1\2***",
    ),
    (re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"), "***JWT***"),
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{6,}"), "***API_KEY***"),
)


def redact(text: str) -> str:
    """Zamaskuj sekrety w dowolnym tekście (używane też w testach i raportach)."""
    for pattern, replacement in REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RedactionFilter(logging.Filter):
    """Filtr loggingu maskujący sekrety w treści komunikatu."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - logowanie nie może wywrócić aplikacji
            return True
        cleaned = redact(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = ()
        return True


def setup_logging(level: str = DEFAULT_LOG_LEVEL, stream: TextIO | None = None) -> logging.Logger:
    """Skonfiguruj logowanie na stderr (lub podany strumień) z filtrem redakcji."""
    numeric_level = _log_level(level)
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactionFilter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(numeric_level)
    return logging.getLogger("view_tracker_ai_1")


# --- pomocnicze -------------------------------------------------------------


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _as_bool(value: str | None, *, name: str) -> bool:
    normalized = _clean(value)
    lowered = (normalized or "").lower()
    if lowered in _TRUTHY:
        return True
    if lowered in _FALSY:
        return False
    raise ConfigError(f"{name}={normalized!r} nie jest wartością logiczną (użyj 1/0).")


def _log_level(level: str) -> int:
    normalized = (level or DEFAULT_LOG_LEVEL).upper()
    mapping = logging.getLevelNamesMapping()
    if normalized not in mapping:
        raise ConfigError(f"LOG_LEVEL={level!r} nie jest poziomem logowania.")
    return mapping[normalized]
