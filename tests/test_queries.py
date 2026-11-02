"""Testy zapytań agregujących: sumy poziomów, przyrosty per oferta, mediana, luki."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from view_tracker_ai_1 import queries, storage
from view_tracker_ai_1.models import Offer, Snapshot

T0 = datetime(2026, 10, 28, 10, 0, tzinfo=UTC)


def add_offer(conn: sqlite3.Connection, offer_id: str, name: str = "Oferta") -> None:
    storage.upsert_offer(
        conn,
        Offer(
            offer_id=offer_id,
            name=name,
            status="ACTIVE",
            first_seen_at=T0,
            last_seen_at=T0,
        ),
    )


def add_snapshot(
    conn: sqlite3.Connection,
    offer_id: str,
    hours: int,
    visits: int,
    watchers: int = 1,
    source: str = "api",
) -> None:
    storage.insert_snapshots(
        conn,
        [
            Snapshot(
                offer_id=offer_id,
                captured_at=T0 + timedelta(hours=hours),
                visits_count=visits,
                watchers_count=watchers,
                source=source,  # type: ignore[arg-type]
            )
        ],
    )


@pytest.fixture()
def conn() -> sqlite3.Connection:
    connection = storage.connect(storage.MEMORY_DB)
    storage.init_db(connection)
    yield connection
    connection.close()


def test_data_version_changes_with_new_snapshots(conn: sqlite3.Connection) -> None:
    assert queries.data_version(conn) == (None, 0)

    add_offer(conn, "1")
    add_snapshot(conn, "1", 0, visits=10)
    version, count = queries.data_version(conn)
    assert count == 1
    assert version == storage.to_iso(T0)


def test_freshness(conn: sqlite3.Connection) -> None:
    add_offer(conn, "1")
    add_snapshot(conn, "1", 0, visits=10)
    add_snapshot(conn, "1", 1, visits=12)

    fresh = queries.freshness(conn)
    assert fresh.snapshots == 2
    assert fresh.offers == 1
    assert fresh.last_captured_at == T0 + timedelta(hours=1)


def test_offers_with_last_snapshot_includes_empty_offers(conn: sqlite3.Connection) -> None:
    add_offer(conn, "1", "Z danymi")
    add_offer(conn, "2", "Bez danych")
    add_snapshot(conn, "1", 0, visits=10, watchers=3)

    states = {state.offer.offer_id: state for state in queries.offers_with_last_snapshot(conn)}
    assert states["1"].visits_count == 10
    assert states["1"].watchers_count == 3
    assert states["1"].snapshots == 1
    assert states["2"].last_captured_at is None
    assert states["2"].snapshots == 0


def test_offers_with_last_snapshot_filters_by_status(conn: sqlite3.Connection) -> None:
    add_offer(conn, "1")
    add_offer(conn, "2")

    assert len(queries.offers_with_last_snapshot(conn, status="ACTIVE")) == 2
    assert queries.offers_with_last_snapshot(conn, status="ENDED") == []


def test_level_totals_sum_only_latest_snapshot(conn: sqlite3.Connection) -> None:
    add_offer(conn, "1")
    add_offer(conn, "2")
    add_snapshot(conn, "1", 0, visits=10, watchers=2)
    add_snapshot(conn, "1", 2, visits=30, watchers=5)
    add_snapshot(conn, "2", 0, visits=7, watchers=1)

    totals = queries.level_totals(conn)
    assert totals.offers == 2
    assert totals.visits == 37
    assert totals.watchers == 6

    as_of_first_hour = queries.level_totals(conn, at=T0)
    assert as_of_first_hour.visits == 17


def test_level_totals_can_be_limited_to_offers(conn: sqlite3.Connection) -> None:
    add_offer(conn, "1")
    add_offer(conn, "2")
    add_snapshot(conn, "1", 0, visits=10)
    add_snapshot(conn, "2", 0, visits=99)

    assert queries.level_totals(conn, ["1"]).visits == 10


def test_level_totals_of_empty_database(conn: sqlite3.Connection) -> None:
    totals = queries.level_totals(conn)
    assert (totals.offers, totals.visits, totals.watchers, totals.at) == (0, 0, 0, None)


def test_gains_per_offer_ignores_drops_in_sum(conn: sqlite3.Connection) -> None:
    add_offer(conn, "1")
    for hours, visits in enumerate([10, 15, 12, 20]):
        add_snapshot(conn, "1", hours, visits=visits)

    rows = queries.gains_per_offer(conn, since=T0, until=T0 + timedelta(hours=3), metric="visits")
    assert len(rows) == 1
    assert rows[0].gained == 13  # +5 i +8, spadek −3 nie obniża sumy
    assert rows[0].drops == 1


def test_gains_per_offer_respects_until_boundary(conn: sqlite3.Connection) -> None:
    add_offer(conn, "1")
    for hours, visits in enumerate([10, 20, 40]):
        add_snapshot(conn, "1", hours, visits=visits)

    rows = queries.gains_per_offer(conn, since=None, until=T0 + timedelta(hours=1), metric="visits")
    assert rows[0].gained == 10


def test_gains_per_offer_uses_metric(conn: sqlite3.Connection) -> None:
    add_offer(conn, "1")
    add_snapshot(conn, "1", 0, visits=10, watchers=1)
    add_snapshot(conn, "1", 1, visits=20, watchers=4)

    rows = queries.gains_per_offer(
        conn, since=T0, until=T0 + timedelta(hours=1), metric="watchers"
    )
    assert rows[0].gained == 3


def test_totals_and_median(conn: sqlite3.Connection) -> None:
    for offer_id, values in {"1": [0, 0], "2": [0, 10], "3": [0, 20]}.items():
        add_offer(conn, offer_id)
        add_snapshot(conn, offer_id, 0, visits=values[0])
        add_snapshot(conn, offer_id, 1, visits=values[1])

    window = {"since": T0, "until": T0 + timedelta(hours=1), "metric": "visits"}
    totals = queries.totals_for_range(conn, **window)  # type: ignore[arg-type]
    assert (totals.offers, totals.gained, totals.drops) == (3, 30, 0)
    assert queries.median_gain(conn, **window) == 10.0  # type: ignore[arg-type]


def test_median_of_empty_range_is_none(conn: sqlite3.Connection) -> None:
    assert queries.median_gain(conn, since=None, until=T0, metric="visits") is None


def test_gaps_counts_long_breaks(conn: sqlite3.Connection) -> None:
    add_offer(conn, "1")
    for hours in (0, 1, 2, 8):
        add_snapshot(conn, "1", hours, visits=10)

    assert queries.gaps(conn, "1", since=None, max_gap_hours=2.0) == 1
    assert queries.gaps(conn, "1", since=None, max_gap_hours=10.0) == 0


def test_offers_at_counts_single_run(conn: sqlite3.Connection) -> None:
    add_offer(conn, "1")
    add_offer(conn, "2")
    add_snapshot(conn, "1", 0, visits=10)
    add_snapshot(conn, "2", 0, visits=5)

    assert queries.offers_at(conn, T0) == 2
    assert queries.offers_at(conn, T0 + timedelta(hours=1)) == 0


def test_offer_exists(conn: sqlite3.Connection) -> None:
    add_offer(conn, "1")
    assert queries.offer_exists(conn, "1") is True
    assert queries.offer_exists(conn, "404") is False
