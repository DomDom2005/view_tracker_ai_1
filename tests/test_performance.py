"""Test wydajności bramki S3: typowy widok przeglądu na dużej bazie < 2 s."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from view_tracker_ai_1 import services, storage
from view_tracker_ai_1.models import Offer, Snapshot

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
OFFERS = 20
HOURS = 720


def test_overview_is_fast_on_large_dataset(tmp_path) -> None:  # noqa: ANN001 - fixture
    conn = storage.connect(tmp_path / "perf.db")
    storage.init_db(conn)

    start = NOW - timedelta(hours=HOURS - 1)
    offers = [
        Offer(
            offer_id=str(index),
            name=f"Oferta {index}",
            status="ACTIVE",
            first_seen_at=start,
            last_seen_at=NOW,
        )
        for index in range(OFFERS)
    ]
    snapshots = [
        Snapshot(
            offer_id=str(offer_index),
            captured_at=start + timedelta(hours=hour),
            visits_count=100 + hour + offer_index,
            watchers_count=5 + offer_index,
        )
        for offer_index in range(OFFERS)
        for hour in range(HOURS)
    ]
    storage.save_collection(conn, offers=offers, snapshots=snapshots)

    began = time.perf_counter()
    overview = services.overview(conn, range_key="30d", metric="visits", now=NOW)
    elapsed = time.perf_counter() - began

    assert overview.ranking
    assert overview.levels.offers == OFFERS
    assert elapsed < 2.0, f"przegląd trwał {elapsed:.2f} s"
    conn.close()
