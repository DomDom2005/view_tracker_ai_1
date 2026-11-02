"""Testy figur Plotly (SPEC-2.0 §11): dwa panele, anomalie, pokrycie, dane syntetyczne."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import plotly.graph_objects as go

from view_tracker_ai_1 import analytics, queries
from view_tracker_ai_1.models import Offer, Series, SeriesPoint
from view_tracker_ai_1.services import IndexedSeries, IndexPoint, OfferView
from view_tracker_ai_1.ui import charts

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
OFFER = Offer(
    offer_id="1",
    name="Suszarka",
    status="ACTIVE",
    first_seen_at=NOW - timedelta(days=120),
    last_seen_at=NOW,
)


def make_view(*, values: list[int], source: str = "api", range_key: str = "24h") -> OfferView:
    """Zbuduj `OfferView` z gotowych wartości (godzinne punkty kończące się na NOW)."""
    points = tuple(
        SeriesPoint(
            captured_at=NOW - timedelta(hours=len(values) - 1 - index),
            value=value,
        )
        for index, value in enumerate(values)
    )
    series = Series(offer_id="1", metric="visits", points=points, source=source)  # type: ignore[arg-type]
    selected = analytics.select_points(series.points, range_key, NOW)
    return OfferView(
        offer=OFFER,
        series=series,
        points=selected,
        daily=analytics.daily_gains(selected),
        summary=analytics.summarize(series, range_key=range_key, now=NOW),
        snapshots=len(points),
        gaps=0,
        freshness=queries.Freshness(last_captured_at=NOW, snapshots=len(points), offers=1),
    )


def test_figure_has_level_anomaly_and_gain_traces() -> None:
    view = make_view(values=[10, 20, 5, 30])

    figure = charts.build_figure(view, metric="visits", range_text="24 godziny")

    names = [trace.name for trace in figure.data]
    assert "wyświetlenia" in names
    assert "spadek licznika" in names
    assert "dzienny przyrost" in names
    level = figure.data[0]
    assert list(level.y) == [10, 20, 5, 30]


def test_figure_has_two_rows() -> None:
    view = make_view(values=[1, 2, 3])

    figure = charts.build_figure(view, metric="visits", range_text="24 godziny")

    assert figure.layout.yaxis.title.text == "wyświetlenia"
    assert figure.layout.yaxis2.title.text == "przyrost"
    assert figure.layout.title.text and "Suszarka" in figure.layout.title.text


def test_figure_marks_synthetic_data() -> None:
    view = make_view(values=[1, 2, 3], source="synthetic")

    figure = charts.build_figure(view, metric="visits", range_text="24 godziny")

    annotations = " ".join(str(item.text) for item in figure.layout.annotations)
    assert "DANE SYNTETYCZNE" in annotations


def test_figure_without_data_shows_message() -> None:
    view = make_view(values=[])

    figure = charts.build_figure(view, metric="visits", range_text="24 godziny")

    assert figure.data == ()
    annotations = " ".join(str(item.text) for item in figure.layout.annotations)
    assert "Brak danych" in annotations


def test_figure_works_for_every_preset() -> None:
    values = [100 + index for index in range(120)]  # 120 godzin
    view = make_view(values=values, range_key="all")

    for range_key in ("24h", "7d", "30d", "90d", "all"):
        figure = charts.build_figure(view, metric="watchers", range_text=range_key)
        assert isinstance(figure, go.Figure)
        assert len(figure.data) >= 2
        assert figure.data[0].x is not None
        assert len(figure.data[0].x) > 0


def test_figure_shows_coverage_and_points_in_subtitle() -> None:
    view = make_view(values=[1, 2, 3])

    figure = charts.build_figure(view, metric="visits", range_text="24 godziny")

    assert "pokrycie" in figure.layout.title.text
    assert "3 punkty" in figure.layout.title.text


def test_comparison_figure_has_line_per_offer() -> None:
    first = make_view(values=[10, 20, 30])
    second = make_view(values=[100, 50, 200])
    indexed = (
        IndexedSeries(
            offer=first.offer,
            points=tuple(
                IndexPoint(captured_at=point.captured_at, index=point.value / 10 * 100)
                for point in first.points
            ),
            base_value=10,
        ),
        IndexedSeries(
            offer=second.offer,
            points=tuple(
                IndexPoint(captured_at=point.captured_at, index=point.value / 100 * 100)
                for point in second.points
            ),
            base_value=100,
        ),
    )

    figure = charts.build_comparison_figure(
        indexed, metric="visits", range_text="24 godziny"
    )

    assert len(figure.data) == 2
    assert list(figure.data[0].y)[0] == 100.0
    assert list(figure.data[1].y)[0] == 100.0


def test_comparison_figure_without_offers_shows_message() -> None:
    figure = charts.build_comparison_figure((), metric="visits", range_text="24 godziny")

    assert figure.data == ()
    annotations = " ".join(str(item.text) for item in figure.layout.annotations)
    assert "Brak ofert do porównania" in annotations


def test_both_metrics_use_secondary_y_axis() -> None:
    view = make_view(values=[10, 20, 30])
    secondary = Series(offer_id="1", metric="watchers", points=view.series.points)
    both = replace(view, secondary_series=secondary)

    figure = charts.build_figure(both, metric="both", range_text="24 godziny")

    names = [trace.name for trace in figure.data]
    assert "wyświetlenia" in names
    assert "obserwujący" in names
    assert figure.layout.yaxis2.title.text == "obserwujący"
    assert figure.layout.yaxis.title.text == "wyświetlenia"
    assert figure.layout.yaxis3.title.text == "przyrost wyświetleń"
