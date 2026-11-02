"""Testy warstwy usług 2.0: oferta, przegląd, porównania, kolektor, logowanie."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import responses

from view_tracker_ai_1 import services, storage
from view_tracker_ai_1.client import RemoteOffer
from view_tracker_ai_1.config import Config
from view_tracker_ai_1.errors import ApiError, AuthError
from view_tracker_ai_1.models import Offer, Snapshot

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
DEVICE_URL = "https://allegro.pl.allegrosandbox.pl/auth/oauth/device?client_id=test-id"
TOKEN_URL = "https://allegro.pl.allegrosandbox.pl/auth/oauth/token"


def make_config(tmp_path: Path) -> Config:
    config = Config.from_env(
        {"ALLEGRO_CLIENT_ID": "test-id", "ALLEGRO_CLIENT_SECRET": "test-secret"},
        load_env_file=False,
    )
    return config.with_overrides(
        db_path=tmp_path / "dane.db",
        token_store_path=tmp_path / "tokens.json",
    )


def add_offer(conn: sqlite3.Connection, offer_id: str, name: str, status: str = "ACTIVE") -> None:
    storage.upsert_offer(
        conn,
        Offer(
            offer_id=offer_id,
            name=name,
            status=status,
            first_seen_at=NOW - timedelta(days=30),
            last_seen_at=NOW,
        ),
    )


def add_point(
    conn: sqlite3.Connection,
    offer_id: str,
    delta: timedelta,
    visits: int,
    watchers: int = 1,
    source: str = "api",
) -> None:
    storage.insert_snapshots(
        conn,
        [
            Snapshot(
                offer_id=offer_id,
                captured_at=NOW - delta,
                visits_count=visits,
                watchers_count=watchers,
                source=source,  # type: ignore[arg-type]
            )
        ],
    )


@pytest.fixture()
def db(tmp_path: Path) -> sqlite3.Connection:
    conn = services.open_database(make_config(tmp_path))
    add_offer(conn, "1", "Suszarka")
    add_offer(conn, "2", "Lokówka")
    for days, visits in ((10, 60), (8, 100), (1, 150)):
        add_point(conn, "1", timedelta(days=days), visits)
    for days, visits in ((8, 20), (1, 30)):
        add_point(conn, "2", timedelta(days=days), visits)
    yield conn
    conn.close()


# --- baza -------------------------------------------------------------------
def test_open_database_creates_v2_schema(tmp_path: Path) -> None:
    conn = services.open_database(make_config(tmp_path))
    assert storage.schema_version(conn) == storage.SCHEMA_VERSION
    conn.close()


# --- lista ofert ------------------------------------------------------------
def test_list_offers_and_search(db: sqlite3.Connection) -> None:
    items = services.list_offers(db)
    assert [item.offer.offer_id for item in items] == ["1", "2"]
    assert items[0].visits == 150
    assert items[0].snapshots == 3

    assert [item.offer.offer_id for item in services.list_offers(db, search="lok")] == ["2"]
    assert [item.offer.offer_id for item in services.list_offers(db, search="1")] == ["1"]
    assert services.list_offers(db, status="ENDED") == []


# --- pojedyncza oferta ------------------------------------------------------
def test_offer_view_returns_series_and_summary(db: sqlite3.Connection) -> None:
    view = services.offer_view(db, "1", range_key="30d", metric="visits", now=NOW)

    assert view is not None
    assert view.offer.name == "Suszarka"
    assert view.snapshots == 3
    assert view.summary.n_points == 3
    assert view.summary.gained_total == 90  # 60→100→150 (40 + 50)
    assert view.summary.coverage > 0
    assert view.freshness.last_captured_at is not None


def test_offer_view_of_missing_offer(db: sqlite3.Connection) -> None:
    assert services.offer_view(db, "404", now=NOW) is None


def test_offer_view_in_thin_range_has_one_point(db: sqlite3.Connection) -> None:
    # W oknie 24h jest tylko ostatni pomiar (dzień wcześniej są już poza zakresem).
    view = services.offer_view(db, "1", range_key="24h", metric="watchers", now=NOW)
    assert view is not None
    assert view.summary.n_points == 1
    assert view.summary.gained_total == 0


# --- przegląd ---------------------------------------------------------------
def test_overview_sums_levels_once_and_gains_per_offer(db: sqlite3.Connection) -> None:
    overview = services.overview(db, range_key="30d", metric="visits", now=NOW)

    assert overview.levels.visits == 180  # 150 + 30 (najnowsze snapshoty)
    assert overview.levels.offers == 2
    assert overview.gains.gained == 100  # 90 (oferta 1) + 10 (oferta 2)
    assert [row.offer.offer_id for row in overview.ranking] == ["1", "2"]
    assert overview.ranking[0].gained == 90
    assert overview.median_gain == 50.0
    assert overview.period_start == NOW - timedelta(days=30)


def test_overview_can_limit_offers(db: sqlite3.Connection) -> None:
    overview = services.overview(db, offer_ids=["2"], range_key="30d", metric="visits", now=NOW)

    assert overview.levels.visits == 30
    assert overview.levels.offers == 1
    assert [row.offer.offer_id for row in overview.ranking] == ["2"]


def test_overview_of_empty_database(tmp_path: Path) -> None:
    conn = services.open_database(make_config(tmp_path))
    overview = services.overview(conn, range_key="7d", now=NOW)
    assert overview.gains.gained == 0
    assert overview.median_gain is None
    assert overview.ranking == ()
    conn.close()


# --- porównania -------------------------------------------------------------
def test_compare_periods_computes_change(db: sqlite3.Connection) -> None:
    comparison = services.compare_periods(db, range_key="7d", metric="visits", now=NOW)

    assert comparison.current.gained == 60  # 50 (oferta 1) + 10 (oferta 2)
    assert comparison.previous.gained == 40  # tylko oferta 1 ma wcześniejszy punkt
    assert comparison.change_pct == pytest.approx(0.5)


def test_compare_periods_for_all_range_has_no_comparison(db: sqlite3.Connection) -> None:
    comparison = services.compare_periods(db, range_key="all", metric="visits", now=NOW)

    assert comparison.previous.gained == 0
    assert comparison.change_pct is None


def test_compare_periods_for_single_offer(db: sqlite3.Connection) -> None:
    comparison = services.compare_periods(
        db, range_key="7d", metric="visits", now=NOW, offer_id="2"
    )
    assert comparison.current.gained == 10
    assert comparison.previous.gained == 0


def test_compare_offers_skips_unknown_ids(db: sqlite3.Connection) -> None:
    series = services.compare_offers(db, ["1", "404", "2"], range_key="30d", metric="visits")
    assert [item.offer.offer_id for item in series] == ["1", "2"]
    assert len(series[0].series) == 3


def test_previous_period_bounds() -> None:
    bounds = services.previous_period("7d", NOW)
    assert bounds == (NOW - timedelta(days=14), NOW - timedelta(days=7))
    assert services.previous_period("all", NOW) is None


# --- kolektor ---------------------------------------------------------------
class FakeClient:
    def __init__(self, offers=(), *, error: Exception | None = None) -> None:
        self.offers = tuple(offers)
        self.error = error

    def iter_offers(self, *, statuses, limit):  # noqa: ANN001, ANN202 - stub
        if self.error is not None:
            raise self.error
        yield from self.offers


def remote(offer_id: str) -> RemoteOffer:
    return RemoteOffer(
        offer_id=offer_id,
        name=f"Oferta {offer_id}",
        status="ACTIVE",
        visits_count=10,
        watchers_count=1,
    )


def test_refresh_once_records_success_run(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    conn = services.open_database(config)

    result = services.refresh_once(
        config, conn, client=FakeClient([remote("1"), remote("2")]), now=NOW
    )

    assert result.inserted == 2
    assert result.offers == 2
    run = storage.recent_collect_runs(conn)[0]
    assert run["status"] == "ok"
    assert run["inserted"] == 2
    assert services.collector_state(conn).freshness.snapshots == 2
    conn.close()


def test_refresh_once_records_api_error(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    conn = services.open_database(config)

    with pytest.raises(ApiError):
        services.refresh_once(config, conn, client=FakeClient(error=ApiError("awaria")))

    run = storage.recent_collect_runs(conn)[0]
    assert run["status"] == "error"
    assert run["error_message"] == "awaria"
    conn.close()


def test_refresh_once_records_auth_error(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    conn = services.open_database(config)

    with pytest.raises(AuthError):
        services.refresh_once(config, conn, client=FakeClient(error=AuthError("token wygasł")))

    assert storage.recent_collect_runs(conn)[0]["status"] == "auth_error"
    conn.close()


def test_collector_state_is_empty_initially(tmp_path: Path) -> None:
    conn = services.open_database(make_config(tmp_path))
    state = services.collector_state(conn)
    assert state.runs == ()
    assert state.freshness.snapshots == 0
    conn.close()


# --- logowanie --------------------------------------------------------------
def test_token_status_without_tokens(tmp_path: Path) -> None:
    status = services.token_status(make_config(tmp_path))
    assert status.logged_in is False


@responses.activate
def test_begin_and_complete_login(tmp_path: Path) -> None:
    responses.add(
        responses.POST,
        DEVICE_URL,
        json={
            "device_code": "device-code",
            "user_code": "ABC-123",
            "verification_uri": "https://allegro.pl/skojarz-aplikacje",
            "expires_in": "600",
            "interval": "5",
        },
        status=200,
    )
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_in": 43199,
            "token_type": "bearer",
        },
        status=200,
    )

    config = make_config(tmp_path)
    auth, authorization = services.begin_login(config)
    assert authorization.user_code == "ABC-123"

    tokens = services.complete_login(auth, authorization)
    assert tokens.access_token == "access-1"
    assert services.token_status(config).logged_in is True
