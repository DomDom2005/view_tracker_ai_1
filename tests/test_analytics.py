"""Testy analityki: przedziały, delty, anomalie, DST, coverage i trend (SPEC §12)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from view_tracker_ai_1 import analytics
from view_tracker_ai_1.models import Series, SeriesPoint, Snapshot

WARSAW = ZoneInfo("Europe/Warsaw")
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


def point(moment: datetime, value: int) -> SeriesPoint:
    return SeriesPoint(captured_at=moment, value=value)


def hourly(values: list[int], *, end: datetime = NOW) -> tuple[SeriesPoint, ...]:
    """Punkty co godzinę, kończąc na `end` (ostatnia wartość = ostatni punkt)."""
    count = len(values)
    start = end - timedelta(hours=count - 1)
    return tuple(point(start + timedelta(hours=index), value) for index, value in enumerate(values))


def series(
    points: tuple[SeriesPoint, ...], *, metric: str = "visits", source: str = "api"
) -> Series:
    return Series(offer_id="1", metric=metric, points=points, source=source)  # type: ignore[arg-type]


# --- przedziały -------------------------------------------------------------
@pytest.mark.parametrize(
    ("range_key", "hours"),
    [("24h", 24), ("7d", 168), ("30d", 720), ("90d", 2160)],
)
def test_range_duration_of_known_ranges(range_key: str, hours: int) -> None:
    assert analytics.range_duration(range_key) == timedelta(hours=hours)


def test_range_duration_of_all_is_none() -> None:
    assert analytics.range_duration("all") is None


def test_unknown_range_is_rejected_with_the_allowed_keys() -> None:
    with pytest.raises(ValueError, match="Nieznany przedział"):
        analytics.range_duration("14d")


def test_window_start_uses_utc() -> None:
    assert analytics.window_start("24h", NOW) == NOW - timedelta(hours=24)
    assert analytics.window_start("all", NOW) is None


def test_select_points_drops_old_and_future_points() -> None:
    points = (
        point(NOW - timedelta(hours=25), 1),
        point(NOW - timedelta(hours=23), 2),
        point(NOW, 3),
        point(NOW + timedelta(hours=1), 4),
    )

    selected = analytics.select_points(points, "24h", NOW)

    assert [item.value for item in selected] == [2, 3]


def test_select_points_for_all_keeps_everything() -> None:
    points = hourly([1, 2, 3])

    assert analytics.select_points(points, "all", NOW) == points


def test_naive_timestamps_are_treated_as_utc() -> None:
    naive = point(datetime(2026, 10, 28, 11, 0), 5)

    selected = analytics.select_points((naive,), "24h", NOW)

    assert selected == (naive,)


# --- delty i anomalie -------------------------------------------------------
def test_deltas_keep_negative_values() -> None:
    points = hourly([100, 120, 115, 130])

    assert analytics.deltas(points) == (20, -5, 15)


def test_positive_gains_never_go_negative() -> None:
    points = hourly([100, 120, 115, 130])

    assert analytics.positive_gains(points) == (20, 0, 15)
    assert analytics.gained_total(points) == 35


def test_find_anomalies_records_the_decrease_with_its_delta() -> None:
    points = hourly([100, 120, 115, 130])

    anomalies = analytics.find_anomalies(points)

    assert len(anomalies) == 1
    assert anomalies[0].delta == -5
    assert anomalies[0].captured_at == points[2].captured_at


def test_monotonic_series_has_no_anomalies() -> None:
    assert analytics.find_anomalies(hourly([1, 2, 3, 4])) == ()


def test_daily_gains_of_empty_series_is_empty() -> None:
    assert analytics.daily_gains(()) == ()


# --- agregacja dzienna ------------------------------------------------------
def test_daily_gains_sum_positive_deltas_and_keep_last_level() -> None:
    day1 = datetime(2026, 10, 27, 0, 0, tzinfo=WARSAW)  # po zmianie czasu: UTC+1
    day2 = datetime(2026, 10, 28, 0, 0, tzinfo=WARSAW)
    points = (
        point(day1, 10),
        point(day1 + timedelta(hours=1), 12),
        point(day1 + timedelta(hours=2), 11),  # spadek: 0 do przyrostu
        point(day2, 15),
    )

    daily = analytics.daily_gains(points)

    assert [entry.day for entry in daily] == [date(2026, 10, 27), date(2026, 10, 28)]
    assert [entry.gained for entry in daily] == [2, 4]
    assert [entry.level_end for entry in daily] == [11, 15]


def test_daily_gains_handle_the_25_hour_day_when_dst_ends() -> None:
    """2026-10-25 w Europe/Warsaw ma 25 godzin — doba nie może się rozjechać."""
    day_start = datetime(2026, 10, 25, 0, 0, tzinfo=WARSAW)
    day_end = datetime(2026, 10, 26, 0, 0, tzinfo=WARSAW)

    # Pułapka PEP 495: odejmowanie dwóch dat w tej samej strefie liczy czas ścienny
    # (24 h), więc długość doby sprawdzamy po sprowadzeniu obu chwil do UTC.
    assert (day_end - day_start) == timedelta(hours=24)
    assert (day_end.astimezone(UTC) - day_start.astimezone(UTC)) == timedelta(hours=25)

    # 25 snapshotów godzinowych pokrywających całą tę dobę (00:00 CEST → 23:00 CET).
    points = tuple(
        point(day_start.astimezone(UTC) + timedelta(hours=index), index) for index in range(25)
    )

    daily = analytics.daily_gains(points)

    assert len(daily) == 1
    assert daily[0].day == date(2026, 10, 25)
    assert daily[0].gained == 24
    assert daily[0].level_end == 24
    # Ten sam materiał pogrupowany po dacie UTC dałby dwie doby — dlatego liczymy lokalnie.
    assert len({item.captured_at.date() for item in points}) == 2


# --- coverage ---------------------------------------------------------------
def test_coverage_is_capped_at_one() -> None:
    # 25 godzin danych w oknie 24 h — pokrycie nie może przekroczyć 1.
    points = hourly([index for index in range(25)])

    assert analytics.coverage(points, "24h", NOW) == 1.0


def test_coverage_drops_when_hours_are_missing() -> None:
    points = tuple(
        point(NOW - timedelta(hours=offset), offset) for offset in (1, 3, 6, 9, 12, 18)
    )

    assert analytics.coverage(points, "24h", NOW) == pytest.approx(6 / 24)


def test_coverage_of_all_uses_the_data_span() -> None:
    points = hourly([index for index in range(10)])

    assert analytics.coverage(points, "all", NOW) == 1.0


def test_coverage_of_empty_selection_is_zero() -> None:
    old = (point(NOW - timedelta(days=5), 1),)

    assert analytics.coverage(old, "24h", NOW) == 0.0


def test_distinct_hours_counts_unique_hours_only() -> None:
    points = (
        point(NOW.replace(minute=5), 1),
        point(NOW.replace(minute=55), 2),
        point(NOW + timedelta(hours=1), 3),
    )

    assert analytics.distinct_hours(points) == 2


# --- trend ------------------------------------------------------------------
def test_slope_per_day_of_a_straight_line() -> None:
    points = (
        point(NOW, 10),
        point(NOW + timedelta(days=1), 20),
        point(NOW + timedelta(days=2), 30),
    )

    assert analytics.slope_per_day(points) == pytest.approx(10.0)


def test_slope_of_flat_series_is_zero() -> None:
    assert analytics.slope_per_day(hourly([7, 7, 7, 7])) == pytest.approx(0.0)


def test_slope_of_single_point_is_zero() -> None:
    assert analytics.slope_per_day(hourly([5])) == 0.0


def test_slope_is_zero_when_every_point_shares_one_timestamp() -> None:
    points = (point(NOW, 1), point(NOW, 2), point(NOW, 3))

    assert analytics.slope_per_day(points) == 0.0


@pytest.mark.parametrize(
    ("slope", "mean", "expected"),
    [
        (2.5, 100.0, "rosnący"),
        (2.0, 100.0, "stabilny"),  # dokładnie na progu — nie „większy niż”
        (1.0, 100.0, "stabilny"),
        (-2.0, 100.0, "stabilny"),
        (-2.5, 100.0, "malejący"),
    ],
)
def test_trend_labels_respect_the_threshold(slope: float, mean: float, expected: str) -> None:
    assert analytics.label_trend(slope, mean) == expected


# --- podsumowanie -----------------------------------------------------------
def test_summarize_increasing_series() -> None:
    result = analytics.summarize(series(hourly([10, 20, 30, 40, 50, 60])), range_key="24h", now=NOW)

    assert result.n_points == 6
    assert result.start == NOW - timedelta(hours=5)
    assert result.end == NOW
    assert result.min == 10
    assert result.max == 60
    assert result.mean == pytest.approx(35.0)
    assert result.gained_total == 50
    assert result.trend_label == "rosnący"
    assert result.coverage == pytest.approx(6 / 24)
    assert result.anomalies == ()


def test_summarize_treats_a_drop_as_anomaly_not_negative_gain() -> None:
    result = analytics.summarize(series(hourly([100, 120, 90, 130])), range_key="24h", now=NOW)

    assert result.gained_total == 60  # 20 + 0 + 40
    assert len(result.anomalies) == 1
    assert result.anomalies[0].delta == -30
    assert result.has_anomalies is True


def test_summarize_below_three_points_has_no_trend_label() -> None:
    result = analytics.summarize(series(hourly([10, 40])), range_key="24h", now=NOW)

    assert result.n_points == 2
    assert result.trend_label == "brak danych"
    assert result.slope_per_day == 0.0


def test_summarize_all_zeros_is_valid_data() -> None:
    result = analytics.summarize(series(hourly([0, 0, 0, 0])), range_key="24h", now=NOW)

    assert result.n_points == 4
    assert (result.min, result.max, result.gained_total) == (0, 0, 0)
    assert result.mean == 0.0
    assert result.trend_label == "stabilny"
    assert result.anomalies == ()


def test_summarize_empty_series_returns_defaults() -> None:
    result = analytics.summarize(series(()), range_key="7d", now=NOW)

    assert result.n_points == 0
    assert result.start is None
    assert result.end is None
    assert result.coverage == 0.0
    assert result.trend_label == "brak danych"


def test_summarize_only_uses_points_from_the_range() -> None:
    old = (point(NOW - timedelta(days=40), 1), point(NOW - timedelta(days=39), 2))
    recent = hourly([5, 6, 7])

    result = analytics.summarize(series(old + recent), range_key="7d", now=NOW)

    assert result.n_points == 3
    assert result.min == 5


def test_summarize_rejects_unknown_range() -> None:
    with pytest.raises(ValueError, match="Nieznany przedział"):
        analytics.summarize(series(hourly([1, 2, 3])), range_key="1y", now=NOW)


# --- budowa serii -----------------------------------------------------------
def test_build_series_sorts_points_and_picks_the_metric() -> None:
    snapshots = [
        Snapshot("1", NOW, visits_count=30, watchers_count=3),
        Snapshot("1", NOW - timedelta(hours=1), visits_count=20, watchers_count=2),
    ]

    visits = analytics.build_series(snapshots, offer_id="1", metric="visits")
    watchers = analytics.build_series(snapshots, offer_id="1", metric="watchers")

    assert [item.value for item in visits.points] == [20, 30]
    assert [item.value for item in watchers.points] == [2, 3]


def test_build_series_marks_synthetic_source() -> None:
    snapshots = [Snapshot("1", NOW, 1, 0, source="synthetic")]

    result = analytics.build_series(snapshots, offer_id="1", metric="visits", source="synthetic")

    assert result.is_synthetic is True
