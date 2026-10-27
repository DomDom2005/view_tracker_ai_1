"""Testy konfiguracji: walidacja env, ścieżki per środowisko, redakcja logów."""

from __future__ import annotations

import io
import logging
from pathlib import Path

import pytest

from view_tracker_ai_1 import __version__
from view_tracker_ai_1.config import (
    API_BASE_URLS,
    AUTH_BASE_URLS,
    DEFAULT_USER_AGENT,
    Config,
    RedactionFilter,
    default_db_path,
    redact,
    setup_logging,
)
from view_tracker_ai_1.errors import ConfigError


def build(**env: str) -> Config:
    return Config.from_env(env, load_env_file=False)


# --- wartości domyślne ------------------------------------------------------
def test_defaults_from_empty_environment() -> None:
    config = build()
    assert config.env == "sandbox"
    assert config.client_id is None
    assert config.client_secret is None
    assert config.user_agent == DEFAULT_USER_AGENT
    assert config.user_agent.startswith(f"view_tracker_ai_1/{__version__}")
    assert config.llm_provider == "none"
    assert config.allow_prod_writes is False
    assert config.log_level == "INFO"
    assert config.effective_db_path == default_db_path("sandbox")


def test_sandbox_and_prod_hosts() -> None:
    sandbox = build()
    prod = build(ALLEGRO_ENV="prod")
    assert sandbox.api_base_url == API_BASE_URLS["sandbox"]
    assert sandbox.auth_base_url == AUTH_BASE_URLS["sandbox"]
    assert prod.api_base_url == "https://api.allegro.pl"
    assert prod.auth_base_url == "https://allegro.pl/auth/oauth"
    assert prod.is_prod and not sandbox.is_prod


def test_env_is_case_insensitive_and_trimmed() -> None:
    assert build(ALLEGRO_ENV="  PROD ").env == "prod"


def test_overrides_change_env_and_db() -> None:
    config = build().with_overrides(env="prod", db_path=Path("data/x.db"))
    assert config.env == "prod"
    assert config.effective_db_path == Path("data/x.db")


def test_explicit_paths_are_used() -> None:
    config = build(TOKEN_STORE_PATH="tokens.json", DB_PATH="data/custom.db")
    assert config.token_store_path == Path("tokens.json")
    assert config.db_path == Path("data/custom.db")


# --- walidacja --------------------------------------------------------------
def test_invalid_env_is_rejected() -> None:
    with pytest.raises(ConfigError, match="ALLEGRO_ENV"):
        build(ALLEGRO_ENV="staging")


def test_invalid_llm_provider_is_rejected() -> None:
    with pytest.raises(ConfigError, match="LLM_PROVIDER"):
        build(LLM_PROVIDER="openai")


def test_anthropic_requires_api_key() -> None:
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        build(LLM_PROVIDER="anthropic")
    config = build(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-ant-test")
    assert config.anthropic_api_key == "sk-ant-test"


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ConfigError, match="LOG_LEVEL"):
        build(LOG_LEVEL="VERBOSE")


def test_log_level_is_normalized() -> None:
    assert build(LOG_LEVEL="debug").log_level == "DEBUG"


@pytest.mark.parametrize(("value", "expected"), [("1", True), ("yes", True), ("0", False)])
def test_allow_prod_writes_parsing(value: str, expected: bool) -> None:
    assert build(ALLOW_PROD_WRITES=value).allow_prod_writes is expected


def test_invalid_boolean_is_rejected() -> None:
    with pytest.raises(ConfigError, match="ALLOW_PROD_WRITES"):
        build(ALLOW_PROD_WRITES="maybe")


# --- wymagania uruchamiane warunkowo ----------------------------------------
def test_credentials_are_required_only_when_asked() -> None:
    config = build()  # budowa bez sekretów jest dozwolona (np. raport z bazy demo)
    with pytest.raises(ConfigError, match="ALLEGRO_CLIENT_ID"):
        config.require_allegro_credentials()

    complete = build(ALLEGRO_CLIENT_ID="id", ALLEGRO_CLIENT_SECRET="secret")
    assert complete.require_allegro_credentials() == ("id", "secret")


def test_prod_writes_are_blocked_by_default() -> None:
    build().require_write_permission()  # sandbox: brak wyjątku

    prod = build(ALLEGRO_ENV="prod")
    with pytest.raises(ConfigError, match="ALLOW_PROD_WRITES"):
        prod.require_write_permission()

    build(ALLEGRO_ENV="prod", ALLOW_PROD_WRITES="1").require_write_permission()


# --- redakcja logów ---------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ("Authorization: Bearer abcdef123456", "abcdef123456"),
        ("access_token=abc123", "abc123"),
        ("refresh_token=def456", "def456"),
        ("client_secret=supersecret", "supersecret"),
        ("api_key=key12345", "key12345"),
        ("sk-ant-api03-abcdef", "sk-ant-api03-abcdef"),
        (
            "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature123",
            "eyJzdWIiOiIxMjM0NTY3ODkwIn0",
        ),
    ],
)
def test_redact_masks_secrets(raw: str, secret: str) -> None:
    cleaned = redact(raw)
    assert secret not in cleaned
    assert "***" in cleaned


def test_redact_keeps_ordinary_text() -> None:
    text = "Zapisano 12 snapshotów dla oferty 123"
    assert redact(text) == text


def test_logging_filter_masks_secret_in_stream() -> None:
    buffer = io.StringIO()
    root = logging.getLogger()
    previous_handlers = list(root.handlers)
    previous_level = root.level
    try:
        logger = setup_logging("INFO", stream=buffer)
        logger.info("Authorization: Bearer topsecret12345")
        logger.warning("client_secret=abcdef")
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in previous_handlers:
            root.addHandler(handler)
        root.setLevel(previous_level)

    output = buffer.getvalue()
    assert "topsecret12345" not in output
    assert "abcdef" not in output
    assert "***" in output


def test_setup_logging_rejects_invalid_level() -> None:
    with pytest.raises(ConfigError, match="LOG_LEVEL"):
        setup_logging("NOT_A_LEVEL", stream=io.StringIO())


def test_redaction_filter_survives_unformattable_record() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "value %d", ("nie-liczba",), None)
    assert RedactionFilter().filter(record) is True  # nie może wywrócić logowania


def test_from_env_uses_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLEGRO_ENV", "prod")
    monkeypatch.setenv("ALLOW_PROD_WRITES", "1")
    config = Config.from_env(load_env_file=False)
    assert config.env == "prod"
    assert config.allow_prod_writes is True
