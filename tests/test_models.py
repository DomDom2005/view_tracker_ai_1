"""Testy modeli: wartości metryk, serie i podsumowanie."""

from __future__ import annotations

from datetime import UTC, datetime

from view_tracker_ai_1.models import (
    Anomaly,
    DailyGain,
    Offer,
    Series,
    SeriesPoint,
    SeriesSummary,
    Snapshot,
)

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


def make_snapshot(visits: int = 10, watchers: int = 3) -> Snapshot:
    return Snapshot(
        offer_id="123",
        captured_at=NOW,
        visits_count=visits,
        watchers_count=watchers,
    )


def test_snapshot_value_by_metric() -> None:
    snapshot = make_snapshot(visits=54, watchers=7)
    assert snapshot.value("visits") == 54
    assert snapshot.value("watchers") == 7
    assert snapshot.source == "api"


def test_series_values_and_flags() -> None:
    series = Series(
        offer_id="123",
        metric="visits",
        points=(SeriesPoint(NOW, 5), SeriesPoint(NOW, 8)),
        source="synthetic",
    )
    assert len(series) == 2
    assert series.values == (5, 8)
    assert series.is_synthetic


def test_series_summary_defaults() -> None:
    summary = SeriesSummary()
    assert summary.n_points == 0
    assert summary.trend_label == "brak danych"
    assert summary.has_anomalies is False

    with_anomaly = SeriesSummary(
        anomalies=(Anomaly(captured_at=NOW, delta=-4),),
        n_points=10,
    )
    assert with_anomaly.has_anomalies is True


def test_offer_and_daily_gain_are_plain_containers() -> None:
    offer = Offer(
        offer_id="1",
        name="Test",
        status="ACTIVE",
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    gain = DailyGain(day=NOW.date(), gained=5, level_end=20)
    assert offer.status == "ACTIVE"
    assert gain.gained == 5
