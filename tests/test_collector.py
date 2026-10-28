"""Testy kolektora: przebieg, wspólny `captured_at`, transakcja i pętla (SPEC FR-2, FR-3)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from view_tracker_ai_1 import collector, storage
from view_tracker_ai_1.client import RemoteOffer
from view_tracker_ai_1.errors import ApiError, AuthError

CAPTURED = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
OFFERS = (
    RemoteOffer(
        offer_id="1", name="Suszarka", status="ACTIVE", visits_count=54, watchers_count=3
    ),
    RemoteOffer(
        offer_id="2", name="Lokówka", status="ACTIVE", visits_count=12, watchers_count=1
    ),
)


class FakeClient:
    """Klient-zabawka: oddaje zadane oferty albo przez `failures` pierwszych wywołań rzuca błąd."""

    def __init__(
        self,
        offers: tuple[RemoteOffer, ...] = OFFERS,
        *,
        failures: int = 0,
        error: Exception | None = None,
    ) -> None:
        self.offers = offers
        self.failures = failures
        self.error = error if error is not None else ApiError("awaria")
        self.calls = 0

    def iter_offers(self, *, statuses, limit):  # noqa: ANN001, ANN202 - prosty stub
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        yield from self.offers


@pytest.fixture()
def conn() -> sqlite3.Connection:
    connection = storage.connect(storage.MEMORY_DB)
    storage.init_db(connection)
    yield connection
    connection.close()


# --- pojedynczy przebieg -----------------------------------------------------
def test_run_once_saves_offers_and_snapshots(conn: sqlite3.Connection) -> None:
    inserted = collector.run_once(FakeClient(), conn, captured_at=CAPTURED)

    assert inserted == 2
    offers = storage.list_offers(conn)
    assert [offer.offer_id for offer in offers] == ["1", "2"]
    assert offers[0].name == "Suszarka"
    assert offers[0].status == "ACTIVE"
    assert storage.count_snapshots(conn) == 2

    snapshot = storage.get_last_snapshot(conn, "1")
    assert snapshot is not None
    assert snapshot.captured_at == CAPTURED
    assert snapshot.visits_count == 54
    assert snapshot.watchers_count == 3
    assert snapshot.source == "api"


def test_all_snapshots_share_one_captured_at(conn: sqlite3.Connection) -> None:
    collector.run_once(FakeClient(), conn, captured_at=CAPTURED)

    moments = {snapshot.captured_at for snapshot in storage.get_series(conn, "1")}
    moments |= {snapshot.captured_at for snapshot in storage.get_series(conn, "2")}
    assert moments == {CAPTURED}


def test_second_run_with_same_timestamp_adds_nothing(conn: sqlite3.Connection) -> None:
    assert collector.run_once(FakeClient(), conn, captured_at=CAPTURED) == 2
    assert collector.run_once(FakeClient(), conn, captured_at=CAPTURED) == 0
    assert storage.count_snapshots(conn) == 2


def test_new_timestamp_adds_new_snapshots(conn: sqlite3.Connection) -> None:
    collector.run_once(FakeClient(), conn, captured_at=CAPTURED)
    later = CAPTURED + timedelta(hours=1)

    assert collector.run_once(FakeClient(), conn, captured_at=later) == 2
    assert storage.count_snapshots(conn) == 4


def test_empty_result_stores_nothing(conn: sqlite3.Connection) -> None:
    assert collector.run_once(FakeClient(offers=()), conn, captured_at=CAPTURED) == 0
    assert storage.list_offers(conn) == []
    assert storage.count_snapshots(conn) == 0


def test_naive_timestamp_is_treated_as_utc(conn: sqlite3.Connection) -> None:
    naive = datetime(2026, 10, 28, 12, 0)
    collector.run_once(FakeClient(), conn, captured_at=naive)

    snapshot = storage.get_last_snapshot(conn, "1")
    assert snapshot is not None
    assert snapshot.captured_at == CAPTURED


def test_error_during_fetch_leaves_database_untouched(conn: sqlite3.Connection) -> None:
    client = FakeClient(failures=1)

    with pytest.raises(ApiError):
        collector.run_once(client, conn, captured_at=CAPTURED)

    assert storage.list_offers(conn) == []
    assert storage.count_snapshots(conn) == 0


# --- pętla -------------------------------------------------------------------
def test_run_forever_rejects_short_interval(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="Minimalny interwał"):
        collector.run_forever(FakeClient(), conn, interval=60)


def test_run_forever_continues_after_failed_run(conn: sqlite3.Connection) -> None:
    sleeps: list[float] = []
    client = FakeClient(failures=1)

    total = collector.run_forever(
        client, conn, interval=3600, runs=2, sleep=sleeps.append
    )

    assert total == 2
    assert client.calls == 2
    assert sleeps == [3600]
    assert storage.count_snapshots(conn) == 2


def test_run_forever_stops_on_auth_error(conn: sqlite3.Connection) -> None:
    client = FakeClient(failures=1, error=AuthError("wygasł token"))

    with pytest.raises(AuthError):
        collector.run_forever(client, conn, interval=3600, runs=3, sleep=lambda seconds: None)

    assert client.calls == 1


def test_run_forever_propagates_keyboard_interrupt(conn: sqlite3.Connection) -> None:
    def interrupt(seconds: float) -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        collector.run_forever(FakeClient(), conn, interval=3600, sleep=interrupt)
