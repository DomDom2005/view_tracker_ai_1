"""Testy zakresu własnego w analityce (FR-10): wybór punktów, pokrycie, podsumowanie."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from view_tracker_ai_1 import analytics
from view_tracker_ai_1.models import Series, SeriesPoint

START = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)


def make_series(values: list[int], *, step_hours: int = 1) -> Series:
    points = tuple(
        SeriesPoint(captured_at=START + timedelta(hours=index * step_hours), value=value)
        for index, value in enumerate(values)
    )
    return Series(offer_id="1", metric="visits", points=points)


def test_select_between_filters_inclusive_bounds() -> None:
    series = make_series([1, 2, 3, 4])
    start = START + timedelta(hours=1)
    end = START + timedelta(hours=2)

    selected = analytics.select_between(series.points, start, end)

    assert [point.value for point in selected] == [2, 3]


def test_summarize_between_uses_custom_window() -> None:
    series = make_series([10, 20, 30, 40, 50])

    summary = analytics.summarize_between(
        series,
        start=START + timedelta(hours=1),
        end=START + timedelta(hours=3),
    )

    assert summary.n_points == 3
    assert summary.min == 20
    assert summary.max == 40
    assert summary.gained_total == 20
    assert summary.start == START + timedelta(hours=1)
    assert summary.end == START + timedelta(hours=3)


def test_coverage_between_uses_window_length() -> None:
    series = make_series([1, 2, 3, 4])  # 4 punkty, 4 godziny

    full = analytics.coverage_between(series.points, start=START, end=START + timedelta(hours=3))
    doubled = analytics.coverage_between(
        series.points, start=START, end=START + timedelta(hours=7)
    )

    assert full == 1.0
    assert doubled == pytest.approx(4 / 7)  # 4 godziny z danymi w oknie 7 godzin


def test_summarize_between_outside_data_gives_empty_summary() -> None:
    series = make_series([1, 2, 3])

    summary = analytics.summarize_between(
        series,
        start=START + timedelta(days=5),
        end=START + timedelta(days=6),
    )

    assert summary.n_points == 0
    assert summary.trend_label == "brak danych"


def test_summarize_between_detects_anomalies() -> None:
    series = make_series([10, 20, 5, 30])

    summary = analytics.summarize_between(series, start=START, end=START + timedelta(hours=3))

    assert len(summary.anomalies) == 1
    assert summary.anomalies[0].delta == -15
    assert summary.gained_total == 35  # 10 + 0 (spadek) + 25
