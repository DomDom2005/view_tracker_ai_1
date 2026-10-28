"""Testy wykresów (SPEC §12): plik powstaje, metadane, znak wodny, brak danych."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from view_tracker_ai_1 import analytics, charts
from view_tracker_ai_1.errors import ChartError
from view_tracker_ai_1.models import Series, SeriesPoint

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


def points(values: list[int], *, end: datetime = NOW) -> tuple[SeriesPoint, ...]:
    start = end - timedelta(hours=len(values) - 1)
    return tuple(
        SeriesPoint(captured_at=start + timedelta(hours=index), value=value)
        for index, value in enumerate(values)
    )


def make_series(values: list[int], *, source: str = "api", metric: str = "visits") -> Series:
    return Series("1001", metric, points(values), source)  # type: ignore[arg-type]


def test_render_writes_png_and_returns_metadata(tmp_path: Path) -> None:
    target = tmp_path / "wykres.png"

    result = charts.render_chart(
        make_series([100 + index for index in range(48)]),
        offer_name="Suszarka",
        range_key="24h",
        now=NOW,
        out_path=target,
    )

    assert target.exists()
    assert target.stat().st_size > 0
    assert result.path == target
    assert result.n_points == 25
    assert result.coverage == 1.0
    assert result.anomalies == 0
    assert result.is_synthetic is False
    assert result.metric == "visits"


def test_render_marks_synthetic_data_with_watermark(tmp_path: Path) -> None:
    result = charts.render_chart(
        make_series([10, 20, 30], source="synthetic"),
        offer_name="Demo",
        range_key="24h",
        now=NOW,
        out_path=tmp_path / "demo.png",
    )

    assert result.is_synthetic is True
    assert charts.watermark_text(make_series([1], source="synthetic")) == "DANE SYNTETYCZNE"


def test_watermark_is_absent_for_api_data() -> None:
    assert charts.watermark_text(make_series([1], source="api")) is None


def test_render_creates_missing_parent_directory(tmp_path: Path) -> None:
    target = tmp_path / "reports" / "podkatalog" / "wykres.png"

    charts.render_chart(
        make_series([1, 2, 3]),
        offer_name="Suszarka",
        range_key="24h",
        now=NOW,
        out_path=target,
    )

    assert target.exists()


def test_render_counts_anomalies(tmp_path: Path) -> None:
    result = charts.render_chart(
        make_series([100, 120, 90, 130]),
        offer_name="Spadek",
        range_key="24h",
        now=NOW,
        out_path=tmp_path / "anomalia.png",
    )

    assert result.anomalies == 1


def test_render_of_empty_series_raises(tmp_path: Path) -> None:
    with pytest.raises(ChartError, match="Brak danych"):
        charts.render_chart(
            make_series([]),
            offer_name="Pusta",
            range_key="24h",
            now=NOW,
            out_path=tmp_path / "puste.png",
        )


def test_render_without_points_in_range_raises(tmp_path: Path) -> None:
    old = Series(
        "1001",
        "visits",
        (SeriesPoint(captured_at=NOW - timedelta(days=30), value=5),),
        "api",
    )

    with pytest.raises(ChartError, match="Brak danych"):
        charts.render_chart(
            old,
            offer_name="Stara",
            range_key="24h",
            now=NOW,
            out_path=tmp_path / "stara.png",
        )


def test_render_accepts_metric_override(tmp_path: Path) -> None:
    result = charts.render_chart(
        make_series([1, 2, 3], metric="visits"),
        offer_name="Suszarka",
        range_key="24h",
        now=NOW,
        out_path=tmp_path / "watchers.png",
        metric="watchers",
    )

    assert result.metric == "watchers"


def test_render_of_flat_series_has_no_gains(tmp_path: Path) -> None:
    """Stały licznik = same zera w przyrostach; panel ma pokazać komunikat, nie pustą oś."""
    result = charts.render_chart(
        make_series([300, 300, 300, 300]),
        offer_name="Plateau",
        range_key="24h",
        now=NOW,
        out_path=tmp_path / "plateau.png",
    )

    assert result.path.exists()
    assert result.n_points == 4
    assert result.anomalies == 0


def test_labels_cover_every_range_and_metric() -> None:
    assert set(charts.RANGE_LABELS) == set(analytics.RANGE_KEYS)
    assert set(charts.METRIC_LABELS) == {"visits", "watchers"}
