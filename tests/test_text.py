"""Testy formatowania i odmiany po polsku (SPEC-2.0 §11)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from view_tracker_ai_1 import text


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, "punktów"),
        (1, "punkt"),
        (2, "punkty"),
        (4, "punkty"),
        (5, "punktów"),
        (11, "punktów"),
        (12, "punktów"),
        (14, "punktów"),
        (21, "punktów"),
        (22, "punkty"),
        (25, "punktów"),
        (102, "punkty"),
        (112, "punktów"),
    ],
)
def test_plural(count: int, expected: str) -> None:
    assert text.plural(count, "punkt", "punkty", "punktów") == expected


def test_labelled_counts() -> None:
    assert text.points_label(1) == "1 punkt"
    assert text.points_label(3) == "3 punkty"
    assert text.points_label(8) == "8 punktów"
    assert text.offers_label(2) == "2 oferty"
    assert text.offers_label(5) == "5 ofert"
    assert text.snapshots_label(1) == "1 snapshot"


def test_number_formatting_uses_polish_conventions() -> None:
    assert text.format_number(1234567) == "1\u00a0234\u00a0567"
    assert text.format_number(0) == "0"
    assert text.format_decimal(12.5, 2) == "12,50"
    assert text.format_percent(0.62) == "62%"


def test_signed_percent() -> None:
    assert text.format_signed_percent(0.12) == "+12%"
    assert text.format_signed_percent(0.0) == "+0%"
    assert text.format_signed_percent(-0.04) == "−4%"


def test_metric_labels() -> None:
    assert text.metric_label("visits") == "wyświetlenia"
    assert text.metric_label("watchers") == "obserwujący"


def test_datetime_is_rendered_in_warsaw_time_winter() -> None:
    moment = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    assert text.format_datetime(moment) == "15.01.2026 13:00"
    assert text.format_date(moment) == "15.01.2026"


def test_datetime_is_rendered_in_warsaw_time_summer() -> None:
    moment = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
    assert text.format_datetime(moment) == "01.07.2026 14:00"


def test_missing_datetime() -> None:
    assert text.format_datetime(None) == "—"
    assert text.format_date(None) == "—"


def test_to_local_changes_zone_not_instant() -> None:
    moment = datetime(2026, 10, 28, 10, 0, tzinfo=UTC)
    local = text.to_local(moment)
    assert local.tzinfo is not None
    assert local.utcoffset() is not None
    assert local.timestamp() == moment.timestamp()
