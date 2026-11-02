"""Testy warstwy SQLite: schemat, idempotencja, ograniczenia i zapytania."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from view_tracker_ai_1 import storage
from view_tracker_ai_1.errors import StorageError
from view_tracker_ai_1.models import Offer, Snapshot

T0 = datetime(2026, 10, 27, 10, 0, tzinfo=UTC)


def make_offer(
    offer_id: str = "123",
    name: str = "Oferta testowa",
    status: str | None = "ACTIVE",
) -> Offer:
    return Offer(
        offer_id=offer_id,
        name=name,
        status=status,
        first_seen_at=T0,
        last_seen_at=T0,
    )


def make_snapshot(
    *,
    offer_id: str = "123",
    at: datetime = T0,
    visits: int = 10,
    watchers: int = 1,
    source: str = "api",
) -> Snapshot:
    return Snapshot(
        offer_id=offer_id,
        captured_at=at,
        visits_count=visits,
        watchers_count=watchers,
        source=source,  # type: ignore[arg-type]
    )


@pytest.fixture()
def conn() -> sqlite3.Connection:
    connection = storage.connect(storage.MEMORY_DB)
    storage.init_db(connection)
    yield connection
    connection.close()


# --- schemat -----------------------------------------------------------------
def test_init_db_is_idempotent_and_sets_version(conn: sqlite3.Connection) -> None:
    assert storage.schema_version(conn) == storage.SCHEMA_VERSION
    assert storage.init_db(conn) == storage.SCHEMA_VERSION
    assert storage.schema_version(conn) == storage.SCHEMA_VERSION


def test_init_db_creates_expected_tables(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    names = {row["name"] for row in rows}
    assert {
        "schema_version",
        "offers",
        "snapshots",
        "actions_log",
        "collect_runs",
        "offer_events",
        "annotations",
        "alert_rules",
        "app_state",
    } <= names
    assert "ai_comments" not in names  # AI wycofane w 2.0 (SPEC-2.0 §10)


V1_SCHEMA_SQL = """
CREATE TABLE schema_version (version INTEGER NOT NULL);
CREATE TABLE offers (
  offer_id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT,
  first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL
);
CREATE TABLE snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  offer_id TEXT NOT NULL REFERENCES offers(offer_id),
  captured_at TEXT NOT NULL,
  visits_count INTEGER NOT NULL CHECK (visits_count >= 0),
  watchers_count INTEGER NOT NULL CHECK (watchers_count >= 0),
  source TEXT NOT NULL CHECK (source IN ('api','synthetic')),
  UNIQUE (offer_id, captured_at)
);
CREATE TABLE ai_comments (
  offer_id TEXT NOT NULL, range_key TEXT NOT NULL, metric TEXT NOT NULL,
  input_hash TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (offer_id, range_key, metric, input_hash)
);
CREATE TABLE actions_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, offer_id TEXT NOT NULL,
  action TEXT NOT NULL, request_json TEXT NOT NULL, response_status INTEGER,
  response_summary TEXT
);
"""


def _build_v1_database(path) -> None:  # noqa: ANN001 - pomocnik testowy
    connection = sqlite3.connect(path)
    connection.executescript(V1_SCHEMA_SQL)
    connection.executescript(
        """
        INSERT INTO schema_version (version) VALUES (1);
        INSERT INTO offers VALUES ('1', 'Suszarka', 'ACTIVE',
            '2026-10-28T10:00:00+00:00', '2026-10-28T10:00:00+00:00');
        INSERT INTO snapshots (offer_id, captured_at, visits_count, watchers_count, source)
            VALUES ('1', '2026-10-28T10:00:00+00:00', 10, 2, 'api');
        INSERT INTO ai_comments VALUES ('1', '7d', 'visits', 'hash', 'komentarz',
            '2026-10-28T10:00:00+00:00');
        """
    )
    connection.commit()
    connection.close()


def test_migration_from_v1_keeps_data_and_drops_ai_table(tmp_path) -> None:
    path = tmp_path / "stara.db"
    _build_v1_database(path)

    connection = storage.connect(path)
    assert storage.schema_version(connection) == 1
    assert storage.init_db(connection) == storage.SCHEMA_VERSION
    assert storage.schema_version(connection) == storage.SCHEMA_VERSION
    assert storage.count_snapshots(connection) == 1
    assert [offer.name for offer in storage.list_offers(connection)] == ["Suszarka"]

    names = {
        row["name"]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert "ai_comments" not in names
    assert "collect_runs" in names
    connection.close()

    backups = list(tmp_path.glob("stara.db.bak-*"))
    assert len(backups) == 1


def test_migration_is_idempotent(tmp_path) -> None:
    path = tmp_path / "stara.db"
    _build_v1_database(path)

    connection = storage.connect(path)
    assert storage.init_db(connection) == storage.SCHEMA_VERSION
    assert storage.init_db(connection) == storage.SCHEMA_VERSION
    connection.close()


def test_init_db_rejects_future_schema_version() -> None:
    connection = sqlite3.connect(storage.MEMORY_DB)
    connection.row_factory = sqlite3.Row
    connection.executescript(storage.SCHEMA_SQL)
    connection.execute("INSERT INTO schema_version (version) VALUES (99)")
    connection.commit()
    with pytest.raises(StorageError, match="Nieobsługiwana wersja"):
        storage.init_db(connection)
    connection.close()


def test_schema_version_of_empty_db_is_none(tmp_path) -> None:
    path = tmp_path / "empty.db"
    connection = storage.connect(path)
    assert storage.schema_version(connection) is None
    connection.close()
    assert path.exists()


# --- oferty ------------------------------------------------------------------
def test_upsert_offer_inserts_then_updates(conn: sqlite3.Connection) -> None:
    storage.upsert_offer(conn, make_offer(name="Pierwsza"))

    newer = datetime(2026, 10, 28, 10, 0, tzinfo=UTC)
    storage.upsert_offer(
        conn,
        Offer(
            offer_id="123",
            name="Zmieniona",
            status="ENDED",
            first_seen_at=T0,
            last_seen_at=newer,
        ),
    )

    offers = storage.list_offers(conn)
    assert len(offers) == 1
    assert offers[0].name == "Zmieniona"
    assert offers[0].status == "ENDED"
    assert offers[0].first_seen_at == T0
    assert offers[0].last_seen_at == newer


def test_list_offers_filters_by_status(conn: sqlite3.Connection) -> None:
    storage.upsert_offer(conn, make_offer("1", status="ACTIVE"))
    storage.upsert_offer(conn, make_offer("2", status="ENDED"))

    assert [offer.offer_id for offer in storage.list_offers(conn)] == ["1", "2"]
    assert [offer.offer_id for offer in storage.list_offers(conn, status="ENDED")] == ["2"]


# --- snapshoty ---------------------------------------------------------------
def test_insert_snapshots_is_idempotent(conn: sqlite3.Connection) -> None:
    storage.upsert_offer(conn, make_offer())
    snapshots = [make_snapshot(at=T0), make_snapshot(at=T0 + timedelta(hours=1), visits=12)]

    assert storage.insert_snapshots(conn, snapshots) == 2
    assert storage.insert_snapshots(conn, snapshots) == 0
    assert storage.count_snapshots(conn) == 2


def test_insert_snapshots_returns_zero_for_empty_input(conn: sqlite3.Connection) -> None:
    assert storage.insert_snapshots(conn, []) == 0


def test_snapshot_requires_existing_offer(conn: sqlite3.Connection) -> None:
    with pytest.raises(StorageError, match="ofertę, której nie ma"):
        storage.insert_snapshots(conn, [make_snapshot(offer_id="nieznana")])


def test_negative_counters_are_rejected(conn: sqlite3.Connection) -> None:
    storage.upsert_offer(conn, make_offer())
    with pytest.raises(StorageError, match="Liczniki"):
        storage.insert_snapshots(conn, [make_snapshot(visits=-1)])


def test_unknown_source_is_rejected(conn: sqlite3.Connection) -> None:
    storage.upsert_offer(conn, make_offer())
    with pytest.raises(StorageError, match="Liczniki"):
        storage.insert_snapshots(conn, [make_snapshot(source="demo")])


def test_get_series_orders_and_filters_by_range(conn: sqlite3.Connection) -> None:
    storage.upsert_offer(conn, make_offer())
    moments = [T0, T0 + timedelta(hours=1), T0 + timedelta(hours=2)]
    storage.insert_snapshots(
        conn,
        [make_snapshot(at=moment, visits=10 + index) for index, moment in enumerate(moments)],
    )

    all_points = storage.get_series(conn, "123")
    assert [point.captured_at for point in all_points] == moments
    assert [point.visits_count for point in all_points] == [10, 11, 12]

    assert [point.visits_count for point in storage.get_series(conn, "123", since=moments[1])] == [
        11,
        12,
    ]
    assert [point.visits_count for point in storage.get_series(conn, "123", until=moments[1])] == [
        10,
        11,
    ]
    assert storage.get_series(conn, "123", since=moments[2] + timedelta(hours=1)) == []


def test_get_series_filters_by_source(conn: sqlite3.Connection) -> None:
    storage.upsert_offer(conn, make_offer())
    storage.insert_snapshots(
        conn,
        [
            make_snapshot(at=T0, source="api"),
            make_snapshot(at=T0 + timedelta(hours=1), source="synthetic"),
        ],
    )

    assert [point.source for point in storage.get_series(conn, "123", source="api")] == ["api"]
    assert len(storage.get_series(conn, "123")) == 2


def test_get_last_snapshot(conn: sqlite3.Connection) -> None:
    storage.upsert_offer(conn, make_offer())
    assert storage.get_last_snapshot(conn, "123") is None

    storage.insert_snapshots(
        conn,
        [make_snapshot(at=T0, visits=5), make_snapshot(at=T0 + timedelta(hours=1), visits=9)],
    )
    last = storage.get_last_snapshot(conn, "123")
    assert last is not None
    assert last.visits_count == 9
    assert last.captured_at == T0 + timedelta(hours=1)


def test_count_snapshots_per_offer(conn: sqlite3.Connection) -> None:
    storage.upsert_offer(conn, make_offer("1"))
    storage.upsert_offer(conn, make_offer("2"))
    storage.insert_snapshots(conn, [make_snapshot(offer_id="1"), make_snapshot(offer_id="2")])

    assert storage.count_snapshots(conn) == 2
    assert storage.count_snapshots(conn, offer_id="1") == 1


# --- przebiegi kolektora i stan UI ------------------------------------------
def test_collect_run_lifecycle(conn: sqlite3.Connection) -> None:
    run_id = storage.start_collect_run(conn, started_at=T0)
    assert run_id > 0
    assert storage.recent_collect_runs(conn)[0]["status"] == "running"

    finished = T0 + timedelta(seconds=30)
    storage.finish_collect_run(
        conn,
        run_id,
        finished_at=finished,
        status="ok",
        offers_count=3,
        inserted=3,
    )

    run = storage.recent_collect_runs(conn)[0]
    assert run["status"] == "ok"
    assert run["offers_count"] == 3
    assert run["inserted"] == 3
    assert run["finished_at"] == storage.to_iso(finished)
    assert run["error_message"] is None


def test_collect_run_error_status(conn: sqlite3.Connection) -> None:
    run_id = storage.start_collect_run(conn, started_at=T0)
    storage.finish_collect_run(
        conn,
        run_id,
        finished_at=T0,
        status="auth_error",
        error_message="token wygasł",
    )

    run = storage.recent_collect_runs(conn)[0]
    assert run["status"] == "auth_error"
    assert run["error_message"] == "token wygasł"


def test_app_state_roundtrip(conn: sqlite3.Connection) -> None:
    assert storage.get_state(conn, "collect_interval") is None

    storage.set_state(conn, "collect_interval", "3600")
    assert storage.get_state(conn, "collect_interval") == "3600"

    storage.set_state(conn, "collect_interval", "900")
    assert storage.get_state(conn, "collect_interval") == "900"


def test_log_action_stores_row(conn: sqlite3.Connection) -> None:
    action_id = storage.log_action(
        conn,
        ts=T0,
        offer_id="123",
        action="price",
        request_json='{"sellingMode": {}}',
        response_status=200,
        response_summary="OK",
    )
    assert action_id > 0

    row = conn.execute("SELECT * FROM actions_log WHERE id = ?", (action_id,)).fetchone()
    assert row["offer_id"] == "123"
    assert row["action"] == "price"
    assert row["response_status"] == 200
    assert row["ts"] == storage.to_iso(T0)


# --- czas i osobne bazy ------------------------------------------------------
def test_iso_helpers_treat_naive_as_utc() -> None:
    naive = datetime(2026, 10, 27, 10, 0)
    assert storage.to_iso(naive) == "2026-10-27T10:00:00+00:00"
    assert storage.from_iso("2026-10-27T10:00:00+00:00") == T0
    assert storage.from_iso("2026-10-27T12:00:00+02:00") == T0


def test_separate_databases_per_environment(tmp_path) -> None:
    sandbox_path = tmp_path / "sandbox.db"
    prod_path = tmp_path / "prod.db"

    for path in (sandbox_path, prod_path):
        connection = storage.connect(path)
        storage.init_db(connection)
        storage.upsert_offer(connection, make_offer())
        storage.insert_snapshots(connection, [make_snapshot()])
        connection.close()

    assert sandbox_path.exists() and prod_path.exists()
    assert sandbox_path != prod_path

    connection = storage.connect(prod_path)
    connection.execute("DELETE FROM snapshots")
    connection.commit()
    connection.close()

    sandbox_connection = storage.connect(sandbox_path)
    assert storage.count_snapshots(sandbox_connection) == 1
    sandbox_connection.close()
