"""Kolektor: jedno wywołanie API → snapshoty zapisane w jednej transakcji (SPEC §6 FR-2, FR-3)."""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from view_tracker_ai_1 import storage
from view_tracker_ai_1.client import DEFAULT_PAGE_LIMIT, AllegroClient
from view_tracker_ai_1.errors import AuthError
from view_tracker_ai_1.models import Offer, Snapshot

logger = logging.getLogger(__name__)

DEFAULT_STATUSES: tuple[str, ...] = ("ACTIVE",)
DEFAULT_INTERVAL_SECONDS = 3600
#: Licznik wyświetleń odświeża się co godzinę, więc częstszy polling nie ma sensu (FR-3).
MIN_INTERVAL_SECONDS = 300


def utc_now() -> datetime:
    """Znacznik czasu przebiegu (UTC). Wydzielone, żeby testy mogły go podmienić."""
    return datetime.now(UTC)


def run_once(
    client: AllegroClient,
    conn: sqlite3.Connection,
    *,
    statuses: Sequence[str] = DEFAULT_STATUSES,
    captured_at: datetime | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
) -> int:
    """Pobierz oferty i zapisz cały przebieg. Zwraca liczbę nowych snapshotów."""
    moment = captured_at if captured_at is not None else utc_now()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)

    remote_offers = list(client.iter_offers(statuses=statuses, limit=limit))
    if not remote_offers:
        logger.info("Brak ofert do zebrania (statusy: %s)", ", ".join(statuses))
        return 0

    offers = [
        Offer(
            offer_id=remote.offer_id,
            name=remote.name,
            status=remote.status,
            first_seen_at=moment,
            last_seen_at=moment,
        )
        for remote in remote_offers
    ]
    snapshots = [
        Snapshot(
            offer_id=remote.offer_id,
            captured_at=moment,
            visits_count=remote.visits_count,
            watchers_count=remote.watchers_count,
            source="api",
        )
        for remote in remote_offers
    ]

    inserted = storage.save_collection(conn, offers=offers, snapshots=snapshots)
    logger.info(
        "Przebieg %s: %d ofert, %d nowych snapshotów",
        moment.isoformat(),
        len(offers),
        inserted,
    )
    return inserted


def run_forever(
    client: AllegroClient,
    conn: sqlite3.Connection,
    *,
    statuses: Sequence[str] = DEFAULT_STATUSES,
    interval: int = DEFAULT_INTERVAL_SECONDS,
    runs: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Pętla przebiegów. Błąd jednego przebiegu jest logowany, `AuthError` kończy pętlę.

    `runs` służy testom — w normalnej pracy `None` oznacza „aż do Ctrl+C”.
    """
    if interval < MIN_INTERVAL_SECONDS:
        raise ValueError(
            f"Minimalny interwał to {MIN_INTERVAL_SECONDS} s (jest {interval})."
        )

    total = 0
    completed = 0
    while runs is None or completed < runs:
        try:
            total += run_once(client, conn, statuses=statuses)
        except AuthError:
            logger.error("Autoryzacja wygasła — zatrzymuję pętlę. Uruchom: `auth login`.")
            raise
        except Exception:  # noqa: BLE001 - pojedynczy przebieg nie może zabić pętli (FR-3)
            logger.exception("Przebieg collect nie powiódł się — kontynuuję")
        completed += 1
        if runs is not None and completed >= runs:
            break
        sleep(interval)
    return total
