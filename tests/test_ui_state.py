"""Testy stanu UI: parsowanie i budowanie parametrów URL, wybór bazy, konfiguracja."""

from __future__ import annotations

from pathlib import Path

import pytest

from view_tracker_ai_1 import config as config_module
from view_tracker_ai_1.config import default_db_path
from view_tracker_ai_1.ui import state


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ALLEGRO_ENV", "DB_PATH", "ALLEGRO_CLIENT_ID", "ALLEGRO_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config_module, "load_dotenv", lambda *args, **kwargs: False)


# --- parsowanie -------------------------------------------------------------
def test_defaults_when_url_is_empty() -> None:
    parsed = state.parse_params({})
    assert parsed.database == "sandbox"
    assert parsed.offers == ()
    assert parsed.range_key == "30d"
    assert parsed.metric == "visits"


def test_parses_all_supported_values() -> None:
    parsed = state.parse_params(
        {"db": "demo", "offer": "111,222", "range": "7d", "metric": "watchers"}
    )
    assert parsed.database == "demo"
    assert parsed.offers == ("111", "222")
    assert parsed.range_key == "7d"
    assert parsed.metric == "watchers"


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"db": "nieznana"}, "sandbox"),
        ({"range": "13d"}, "30d"),
        ({"metric": "likes"}, "visits"),
    ],
)
def test_invalid_values_fall_back_to_defaults(params: dict[str, str], expected: str) -> None:
    parsed = state.parse_params(params)
    assert expected in {parsed.database, parsed.range_key, parsed.metric}


def test_offers_are_trimmed_and_empty_entries_dropped() -> None:
    assert state.parse_params({"offer": " 1 , ,2 "}).offers == ("1", "2")


def test_params_for_roundtrip() -> None:
    original = state.UiState(
        database="prod", offers=("1", "2"), range_key="90d", metric="watchers"
    )
    params = state.params_for(original)
    assert params == {"db": "prod", "offer": "1,2", "range": "90d", "metric": "watchers"}
    assert state.parse_params(params) == original


def test_params_for_omits_empty_offers() -> None:
    assert "offer" not in state.params_for(state.UiState())


# --- filtry listy ofert (FR-7) ---------------------------------------------
def test_offer_filters_roundtrip() -> None:
    original = state.UiState(
        offer_query="susz",
        offer_status="ACTIVE",
        offer_sort="gain",
        detail_offer="1",
    )
    params = state.params_for(original)

    assert params["q"] == "susz"
    assert params["status"] == "ACTIVE"
    assert params["sort"] == "gain"
    assert params["detail"] == "1"
    assert state.parse_params(params) == original


def test_invalid_sort_falls_back_to_recent() -> None:
    assert state.parse_params({"sort": "losowy"}).offer_sort == "recent"


def test_default_filters_are_omitted_from_url() -> None:
    params = state.params_for(state.UiState())
    assert "q" not in params
    assert "status" not in params
    assert "sort" not in params
    assert "detail" not in params


# --- bazy -------------------------------------------------------------------
def test_resolve_database_paths() -> None:
    assert state.resolve_db_path("sandbox") == default_db_path("sandbox")
    assert state.resolve_db_path("prod") == default_db_path("prod")
    assert state.resolve_db_path("demo") == Path("data") / "demo.db"


def test_environment_for_database() -> None:
    assert state.database_env("sandbox") == "sandbox"
    assert state.database_env("demo") == "sandbox"
    assert state.database_env("prod") == "prod"


def test_config_for_database_overrides_env_and_path(tmp_path: Path) -> None:
    config = state.config_for(state.UiState(database="prod"))
    assert config.env == "prod"
    assert config.effective_db_path == default_db_path("prod")
    assert config.api_base_url == "https://api.allegro.pl"

    demo = state.config_for(state.UiState(database="demo"))
    assert demo.env == "sandbox"
    assert demo.effective_db_path == Path("data") / "demo.db"


def test_with_database_keeps_other_selection() -> None:
    original = state.UiState(database="sandbox", offers=("7",), range_key="7d", metric="watchers")
    changed = state.with_database(original, "demo")
    assert changed.database == "demo"
    assert changed.offers == ("7",)
    assert changed.range_key == "7d"
