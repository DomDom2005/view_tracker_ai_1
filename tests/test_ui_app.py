"""Smoke testy aplikacji Streamlit (SPEC-2.0 §12): start bez `.env`, strony, błędy."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from view_tracker_ai_1 import config as config_module
from view_tracker_ai_1 import storage
from view_tracker_ai_1.models import Offer, Snapshot
from view_tracker_ai_1.ui import state

APP_PATH = Path(__file__).resolve().parents[1] / "src" / "view_tracker_ai_1" / "ui" / "app.py"
NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)

ENVIRONMENT = (
    "ALLEGRO_ENV",
    "ALLEGRO_CLIENT_ID",
    "ALLEGRO_CLIENT_SECRET",
    "ALLEGRO_USER_AGENT",
    "DB_PATH",
    "LOG_LEVEL",
    "TOKEN_STORE_PATH",
    "ALLOW_PROD_WRITES",
)


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Brak `.env`, brak sekretów w env, baza UI w katalogu testu."""
    for name in ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config_module, "load_dotenv", lambda *args, **kwargs: False)

    db_path = tmp_path / "ui.db"
    monkeypatch.setattr(state, "resolve_db_path", lambda name: db_path)
    return db_path


def seed(db_path: Path) -> None:
    conn = storage.connect(db_path)
    storage.init_db(conn)
    storage.save_collection(
        conn,
        offers=[
            Offer(
                offer_id="1",
                name="Suszarka",
                status="ACTIVE",
                first_seen_at=NOW,
                last_seen_at=NOW,
            ),
            Offer(
                offer_id="2",
                name="Lokówka",
                status="ENDED",
                first_seen_at=NOW,
                last_seen_at=NOW,
            ),
        ],
        snapshots=[
            Snapshot(
                offer_id="1",
                captured_at=NOW,
                visits_count=54,
                watchers_count=3,
            )
        ],
    )
    conn.close()


def run_app() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    return at


def run_page(script: str, *, db: str = "sandbox") -> AppTest:
    at = AppTest.from_string(script, default_timeout=30)
    at.session_state["db"] = db
    at.run()
    return at


# --- start aplikacji --------------------------------------------------------
def test_app_starts_without_env_and_shows_overview() -> None:
    at = run_app()

    assert not at.exception
    assert [title.value for title in at.title] == ["Przegląd"]
    assert [box.label for box in at.selectbox] == ["Baza danych"]
    assert any("nie ma jeszcze ofert" in info.value for info in at.info)


def test_app_shows_error_when_configuration_is_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLEGRO_ENV", "staging")

    at = run_app()

    assert not at.exception
    assert any("Błąd konfiguracji" in error.value for error in at.error)


def test_app_renders_metrics_when_database_has_data(isolated_environment: Path) -> None:
    seed(isolated_environment)

    at = run_app()

    assert not at.exception
    labels = [metric.label for metric in at.metric]
    assert "Oferty w bazie" in labels
    values = {metric.label: metric.value for metric in at.metric}
    assert values["Oferty w bazie"] in {"2", 2}
    assert len(at.dataframe) == 1


def test_database_selector_offers_three_databases() -> None:
    at = run_app()
    selector = at.selectbox[0]
    assert selector.value == "sandbox"
    assert selector.options == [
        "Sandbox (API)",
        "Produkcja (tylko odczyt)",
        "Dane demo (syntetyczne)",
    ]


# --- strony -----------------------------------------------------------------
def test_offer_page_without_data_shows_guidance() -> None:
    at = run_page(
        "from view_tracker_ai_1.ui.pages import offer\n"
        "offer.render()\n"
    )

    assert not at.exception
    assert [title.value for title in at.title] == ["Oferta"]
    assert any("Brak ofert" in info.value for info in at.info)


def test_offer_page_with_data_and_no_selection_shows_hint(
    isolated_environment: Path,
) -> None:
    seed(isolated_environment)

    at = run_page(
        "from view_tracker_ai_1.ui.pages import offer\n"
        "offer.render()\n"
    )

    assert not at.exception
    assert any("Wybierz ofertę" in info.value for info in at.info)
    assert len(at.dataframe) == 1

    assert not at.exception
    assert [title.value for title in at.title] == ["Oferta"]
    assert any("Wybierz ofertę" in info.value for info in at.info)


def test_settings_page_shows_versions_and_paths() -> None:
    at = run_page(
        "from view_tracker_ai_1.ui.pages import settings\n"
        "settings.render()\n"
    )

    assert not at.exception
    assert [title.value for title in at.title] == ["Ustawienia"]
    markdown = "\n".join(element.value for element in at.markdown)
    assert "Schemat bazy" in markdown
    assert "Aplikacja" in markdown
    assert at.code


def test_data_page_renders_collector_state() -> None:
    at = run_page(
        "from view_tracker_ai_1.ui.pages import data\n"
        "data.render()\n"
    )

    assert not at.exception
    labels = [metric.label for metric in at.metric]
    assert "Snapshoty" in labels
    assert any("Brak zapisanych przebiegów" in info.value for info in at.info)


def test_data_page_blocks_collection_on_prod() -> None:
    at = run_page(
        "from view_tracker_ai_1.ui.pages import data\n"
        "data.render()\n",
        db="prod",
    )

    assert not at.exception
    assert any("tylko odczyt" in error.value for error in at.error)


def test_comparison_page_is_marked_as_later_step() -> None:
    at = run_page(
        "from view_tracker_ai_1.ui.pages import comparison\n"
        "comparison.render()\n"
    )

    assert not at.exception
    assert any("S3" in warning.value for warning in at.warning)
