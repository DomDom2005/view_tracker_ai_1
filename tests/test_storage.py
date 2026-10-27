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
    assert storage.schema_version(conn) == 1
    assert storage.init_db(conn) == 1
    assert storage.schema_version(conn) == 1


def test_init_db_creates_expected_tables(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    names = {row["name"] for row in rows}
    assert {"schema_version", "offers", "snapshots", "ai_comments", "actions_log"} <= names


def test_unsupported_schema_version_is_rejected() -> None:
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


# --- cache komentarzy i log akcji -------------------------------------------
def test_comment_cache_roundtrip(conn: sqlite3.Connection) -> None:
    key = {
        "offer_id": "123",
        "range_key": "7d",
        "metric": "visits",
        "input_hash": "abc",
    }
    assert storage.get_cached_comment(conn, **key) is None

    storage.put_cached_comment(conn, **key, text="Pierwszy komentarz", created_at=T0)
    assert storage.get_cached_comment(conn, **key) == "Pierwszy komentarz"

    storage.put_cached_comment(conn, **key, text="Zaktualizowany", created_at=T0)
    assert storage.get_cached_comment(conn, **key) == "Zaktualizowany"


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
