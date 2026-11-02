"""Zdarzenia ofert, „co nowego” i alerty progowe (SPEC-2.0 FR-15/FR-16).

Kształt odpowiedzi `GET /sale/offer-events` jest **niezweryfikowany** (patrz
`docs/api-notes.md` §9) — parser jest tolerancyjny i zgłasza `EventError`, gdy nie
rozpozna żadnego zdarzenia. Adnotacje ręczne działają niezależnie od API.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from view_tracker_ai_1 import analytics, storage
from view_tracker_ai_1.client import AllegroClient
from view_tracker_ai_1.errors import EventError
from view_tracker_ai_1.models import AlertRule, Offer, OfferEvent
from view_tracker_ai_1.text import event_label  # noqa: F401 - re-export dla wygody

EVENTS_PATH = "/sale/offer-events"
DEFAULT_EVENT_LIMIT = 1000
MAX_EVENT_LIMIT = 1000

SEEN_KEY_TEMPLATE = "last_seen:{offer_id}"


def parse_events(payload: Mapping[str, Any]) -> tuple[OfferEvent, ...]:
    """Zamień odpowiedź API na zdarzenia; tolerancyjnie wobec nazw pól.

    Akceptujemy `offer.id`/`offerId` oraz `occurredAt`/`occurred_at`/`time`.
    Gdy lista istnieje, ale żadnego elementu nie da się rozpoznać — `EventError`
    z informacją o niezweryfikowanym kształcie (TODO(verify)).
    """
    if "events" not in payload:
        raise EventError(
            "Odpowiedź `/sale/offer-events` nie zawiera pola `events` "
            "(kształt niezweryfikowany — docs/api-notes.md §9)."
        )
    items = payload["events"]
    if not isinstance(items, list):
        raise EventError(
            "Odpowiedź `/sale/offer-events` nie zawiera listy `events` "
            "(kształt niezweryfikowany — docs/api-notes.md §9)."
        )

    parsed: list[OfferEvent] = []
    for item in items:
        event = _event_from_item(item)
        if event is not None:
            parsed.append(event)

    if items and not parsed:
        raise EventError(
            "Nieznany kształt zdarzeń ofert — zaktualizuj parser i `docs/api-notes.md` §9."
        )
    return tuple(parsed)


def _event_from_item(item: Any) -> OfferEvent | None:
    if not isinstance(item, Mapping):
        return None
    offer = item.get("offer")
    offer_id = item.get("offerId") or (offer.get("id") if isinstance(offer, Mapping) else None)
    event_type = item.get("type")
    occurred = item.get("occurredAt") or item.get("occurred_at") or item.get("time")
    if not offer_id or not event_type or not occurred:
        return None
    try:
        moment = _parse_iso(str(occurred))
    except ValueError:
        return None
    return OfferEvent(
        offer_id=str(offer_id),
        occurred_at=moment,
        type=str(event_type),
        payload_json=json.dumps(item, ensure_ascii=False, sort_keys=True, default=str),
    )


def fetch_events(
    client: AllegroClient, *, limit: int = DEFAULT_EVENT_LIMIT
) -> tuple[OfferEvent, ...]:
    """Pobierz zdarzenia z API (endpoint zwraca zdarzenia z ostatnich 24 h)."""
    bounded = max(1, min(int(limit), MAX_EVENT_LIMIT))
    payload = client.get(EVENTS_PATH, params={"limit": bounded})
    return parse_events(payload)


def sync_events(
    conn: sqlite3.Connection,
    client: AllegroClient,
    *,
    limit: int = DEFAULT_EVENT_LIMIT,
    now: datetime | None = None,
) -> int:
    """Pobierz i zapisz zdarzenia (deduplikacja po `(offer_id, occurred_at, type)`)."""
    fetched_at = now if now is not None else datetime.now(UTC)
    events = fetch_events(client, limit=limit)
    stamped = tuple(
        OfferEvent(
            offer_id=event.offer_id,
            occurred_at=event.occurred_at,
            type=event.type,
            payload_json=event.payload_json,
            fetched_at=fetched_at,
        )
        for event in events
    )
    return storage.insert_events(conn, stamped)


# --- „co nowego od ostatniej wizyty” ----------------------------------------
@dataclass(frozen=True, slots=True)
class WhatsNew:
    since: datetime | None
    first_visit: bool
    level_delta: int | None
    new_anomalies: int
    new_events: int
    new_snapshots: int


def seen_key(offer_id: str) -> str:
    return SEEN_KEY_TEMPLATE.format(offer_id=offer_id)


def whats_new(
    conn: sqlite3.Connection,
    offer_id: str,
    *,
    metric: str = "visits",
    now: datetime,
) -> WhatsNew:
    """Różnice od poprzedniej wizyty na stronie oferty (FR-16)."""
    raw = storage.get_state(conn, seen_key(offer_id))
    if not raw:
        return WhatsNew(None, True, None, 0, 0, 0)

    since = _parse_iso(raw)
    snapshots = storage.get_series(conn, offer_id)
    source = snapshots[0].source if snapshots else "api"
    series = analytics.build_series(
        snapshots, offer_id=offer_id, metric=metric, source=source  # type: ignore[arg-type]
    )
    points = analytics.select_between(series.points, since, now)

    level_delta: int | None = None
    if points:
        before = [point for point in series.points if point.captured_at <= since]
        base = before[-1].value if before else points[0].value
        level_delta = points[-1].value - base

    anomalies = analytics.find_anomalies(points)
    events = storage.list_events(conn, offer_id=offer_id, since=since, until=now)
    return WhatsNew(
        since=since,
        first_visit=False,
        level_delta=level_delta,
        new_anomalies=len(anomalies),
        new_events=len(events),
        new_snapshots=len(points),
    )


def mark_seen(
    conn: sqlite3.Connection, offer_id: str, *, now: datetime | None = None
) -> None:
    moment = now if now is not None else datetime.now(UTC)
    storage.set_state(conn, seen_key(offer_id), storage.to_iso(moment))


# --- alerty progowe ---------------------------------------------------------
@dataclass(frozen=True, slots=True)
class AlertHit:
    rule: AlertRule
    offer: Offer
    last_value: int
    peak_value: int
    drop_abs: int
    drop_pct: float


def evaluate_alerts(
    conn: sqlite3.Connection, *, now: datetime, metric: str = "visits"
) -> tuple[AlertHit, ...]:
    """Oceń reguły: spadek względem szczytu w oknie `window_days` (FR-16)."""
    rules = storage.list_alert_rules(conn)
    if not rules:
        return ()

    offers = {offer.offer_id: offer for offer in storage.list_offers(conn)}
    hits: list[AlertHit] = []
    for rule in rules:
        targets: Sequence[str] = (
            [rule.offer_id] if rule.offer_id is not None else list(offers)
        )
        for offer_id in targets:
            offer = offers.get(offer_id)
            if offer is None:
                continue
            snapshots = storage.get_series(conn, offer_id)
            source = snapshots[0].source if snapshots else "api"
            series = analytics.build_series(
                snapshots, offer_id=offer_id, metric=metric, source=source  # type: ignore[arg-type]
            )
            since = now - timedelta(days=rule.window_days)
            points = analytics.select_between(series.points, since, now)
            if len(points) < 2:
                continue
            peak = max(point.value for point in points)
            last = points[-1].value
            drop_abs = max(0, peak - last)
            drop_pct = (drop_abs / peak) if peak > 0 else 0.0
            triggered = (
                drop_abs >= rule.threshold
                if rule.kind == "abs_drop"
                else drop_pct >= rule.threshold
            )
            if triggered:
                hits.append(
                    AlertHit(
                        rule=rule,
                        offer=offer,
                        last_value=last,
                        peak_value=peak,
                        drop_abs=drop_abs,
                        drop_pct=drop_pct,
                    )
                )
    return tuple(hits)


def _parse_iso(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
