"""Testy zdarzeń ofert, adnotacji, „co nowego” i alertów progowych (S5)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from view_tracker_ai_1 import events, services, storage
from view_tracker_ai_1.errors import EventError
from view_tracker_ai_1.models import Offer, Snapshot

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


@pytest.fixture()
def conn() -> sqlite3.Connection:
    connection = storage.connect(storage.MEMORY_DB)
    storage.init_db(connection)
    yield connection
    connection.close()


def add_offer(conn: sqlite3.Connection, offer_id: str = "1") -> None:
    storage.upsert_offer(
        conn,
        Offer(
            offer_id=offer_id,
            name=f"Oferta {offer_id}",
            status="ACTIVE",
            first_seen_at=NOW - timedelta(days=60),
            last_seen_at=NOW,
        ),
    )


def add_point(conn: sqlite3.Connection, visits: int, *, days_ago: int, offer_id: str = "1") -> None:
    storage.insert_snapshots(
        conn,
        [
            Snapshot(
                offer_id=offer_id,
                captured_at=NOW - timedelta(days=days_ago),
                visits_count=visits,
                watchers_count=1,
            )
        ],
    )


# --- parser -----------------------------------------------------------------
def test_parse_events_accepts_camel_case_payload() -> None:
    payload = {
        "events": [
            {
                "id": "abc",
                "type": "OFFER_PRICE_CHANGED",
                "occurredAt": "2026-11-01T10:00:00Z",
                "offer": {"id": "123"},
            }
        ]
    }

    parsed = events.parse_events(payload)

    assert len(parsed) == 1
    assert parsed[0].offer_id == "123"
    assert parsed[0].type == "OFFER_PRICE_CHANGED"
    assert parsed[0].occurred_at == datetime(2026, 11, 1, 10, 0, tzinfo=UTC)


def test_parse_events_accepts_flat_variants() -> None:
    payload = {
        "events": [
            {"offerId": "1", "type": "OFFER_ENDED", "occurred_at": "2026-11-01T10:00:00+00:00"},
            {"offerId": "2", "type": "OFFER_CHANGED", "time": "2026-11-01T11:00:00Z"},
        ]
    }

    parsed = events.parse_events(payload)

    assert [item.offer_id for item in parsed] == ["1", "2"]


def test_parse_events_skips_broken_items_but_keeps_good_ones() -> None:
    payload = {
        "events": [
            {"type": "OFFER_ENDED"},  # brak offer.id
            {"offer": {"id": "1"}, "type": "OFFER_ENDED"},  # brak czasu
            {"offer": {"id": "1"}, "type": "OFFER_ENDED", "occurredAt": "2026-11-01T10:00:00Z"},
        ]
    }

    assert len(events.parse_events(payload)) == 1


def test_parse_events_raises_on_unknown_shape() -> None:
    with pytest.raises(EventError, match="Nieznany kształt"):
        events.parse_events({"events": [{"foo": "bar"}]})


def test_parse_events_raises_when_events_missing() -> None:
    with pytest.raises(EventError, match="events"):
        events.parse_events({"items": []})


def test_parse_events_empty_list_is_ok() -> None:
    assert events.parse_events({"events": []}) == ()


# --- deduplikacja -----------------------------------------------------------
def test_insert_events_deduplicates(conn: sqlite3.Connection) -> None:
    event = events.parse_events(
        {
            "events": [
                {
                    "offer": {"id": "1"},
                    "type": "OFFER_PRICE_CHANGED",
                    "occurredAt": "2026-11-01T10:00:00Z",
                }
            ]
        }
    )[0]

    assert storage.insert_events(conn, [event]) == 1
    assert storage.insert_events(conn, [event]) == 0
    assert len(storage.list_events(conn, offer_id="1")) == 1


def test_sync_events_uses_client_and_stores(conn: sqlite3.Connection) -> None:
    class FakeClient:
        def get(self, path, *, params=None):  # noqa: ANN001, ANN202 - stub
            assert path == events.EVENTS_PATH
            assert params == {"limit": 500}
            return {
                "events": [
                    {
                        "offer": {"id": "1"},
                        "type": "OFFER_PRICE_CHANGED",
                        "occurredAt": "2026-11-01T10:00:00Z",
                    }
                ]
            }

    added = events.sync_events(conn, FakeClient(), limit=500, now=NOW)

    assert added == 1
    stored = storage.list_events(conn, offer_id="1")
    assert stored[0].fetched_at == NOW


# --- adnotacje --------------------------------------------------------------
def test_annotations_roundtrip_and_delete(conn: sqlite3.Connection) -> None:
    add_offer(conn)
    annotation_id = storage.add_annotation(
        conn,
        offer_id="1",
        occurred_at=NOW - timedelta(days=1),
        label="obniżka ceny",
        note="49 → 45",
        created_at=NOW,
    )

    stored = storage.list_annotations(conn, offer_id="1")
    assert [item.label for item in stored] == ["obniżka ceny"]
    assert stored[0].note == "49 → 45"

    assert storage.delete_annotation(conn, annotation_id) == 1
    assert storage.list_annotations(conn, offer_id="1") == []


# --- co nowego --------------------------------------------------------------
def test_whats_new_first_visit(conn: sqlite3.Connection) -> None:
    add_offer(conn)
    news = services.whats_new(conn, "1", now=NOW)

    assert news.first_visit is True
    assert news.since is None


def test_whats_new_reports_changes_since_last_visit(conn: sqlite3.Connection) -> None:
    add_offer(conn)
    add_point(conn, 100, days_ago=3)
    add_point(conn, 150, days_ago=1)
    add_point(conn, 140, days_ago=0)  # spadek po ostatniej wizycie

    seen_at = NOW - timedelta(days=2)
    storage.set_state(conn, events.seen_key("1"), storage.to_iso(seen_at))

    news = services.whats_new(conn, "1", now=NOW)

    assert news.first_visit is False
    assert news.since == seen_at
    assert news.level_delta == 40  # 150 → 140 względem poziomu 100 z 3 dni
    assert news.new_anomalies == 1
    assert news.new_snapshots == 2


def test_mark_seen_sets_state(conn: sqlite3.Connection) -> None:
    add_offer(conn)
    services.mark_offer_seen(conn, "1", now=NOW)

    assert storage.get_state(conn, events.seen_key("1")) == storage.to_iso(NOW)


# --- alerty -----------------------------------------------------------------
def test_alert_pct_drop_triggers(conn: sqlite3.Connection) -> None:
    add_offer(conn)
    add_point(conn, 100, days_ago=10)
    add_point(conn, 200, days_ago=5)
    add_point(conn, 120, days_ago=0)  # spadek 40% od szczytu
    storage.add_alert_rule(
        conn, kind="pct_drop", threshold=0.3, window_days=14, offer_id="1", created_at=NOW
    )

    hits = services.alert_hits(conn, now=NOW)

    assert len(hits) == 1
    assert hits[0].offer.offer_id == "1"
    assert hits[0].peak_value == 200
    assert hits[0].last_value == 120
    assert hits[0].drop_pct == pytest.approx(0.4)


def test_alert_below_threshold_does_not_trigger(conn: sqlite3.Connection) -> None:
    add_offer(conn)
    add_point(conn, 200, days_ago=5)
    add_point(conn, 190, days_ago=0)
    storage.add_alert_rule(
        conn, kind="pct_drop", threshold=0.3, window_days=14, offer_id="1", created_at=NOW
    )

    assert services.alert_hits(conn, now=NOW) == ()


def test_alert_abs_drop_and_global_rule(conn: sqlite3.Connection) -> None:
    add_offer(conn, "1")
    add_point(conn, 50, days_ago=10, offer_id="1")
    add_point(conn, 30, days_ago=0, offer_id="1")
    storage.add_alert_rule(
        conn, kind="abs_drop", threshold=15, window_days=30, offer_id=None, created_at=NOW
    )

    hits = services.alert_hits(conn, now=NOW)

    assert len(hits) == 1
    assert hits[0].drop_abs == 20


def test_alert_rules_crud(conn: sqlite3.Connection) -> None:
    rule_id = storage.add_alert_rule(
        conn, kind="pct_drop", threshold=0.2, window_days=7, created_at=NOW
    )
    assert [rule.id for rule in storage.list_alert_rules(conn)] == [rule_id]

    assert storage.delete_alert_rule(conn, rule_id) == 1
    assert storage.list_alert_rules(conn) == []
