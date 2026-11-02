"""Figury Plotly dla UI 2.0 (SPEC-2.0 §11).

Rysujemy z gotowego `OfferView` (punkty, agregaty dobowe, podsumowanie), więc warstwa
prezentacji nie powtarza analityki. Osie czasu w `Europe/Warsaw`, liczby i etykiety PL.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from view_tracker_ai_1.models import Metric
from view_tracker_ai_1.services import IndexedSeries, OfferView
from view_tracker_ai_1.text import (
    LOCAL_TZ,
    format_number,
    format_percent,
    metric_label,
    points_label,
    to_local,
)

LINE_COLOR = "#b23a17"
GAIN_COLOR = "#c98212"
ANOMALY_COLOR = "#b91c1c"
SYNTHETIC_COLOR = "#9a3412"
WATCHERS_COLOR = "#6d4fc4"
EVENT_COLOR = "#8a5a3c"
ANNOTATION_COLOR = "#7c3aed"
THEME_INK = "#3b1b0c"
THEME_INK_SOFT = "rgba(59, 27, 12, 0.7)"
THEME_GRID = "rgba(59, 27, 12, 0.12)"
THEME_AXIS = "rgba(59, 27, 12, 0.35)"
THEME_FONT = "'Segoe UI', 'Inter', system-ui, sans-serif"


@dataclass(frozen=True, slots=True)
class ChartMarker:
    """Pionowy znacznik na wykresie: zdarzenie z API albo adnotacja ręczna."""

    at: datetime
    label: str
    kind: str = "event"

EMPTY_MESSAGE = "Brak danych w wybranym przedziale — uruchom zbieranie albo wybierz inny zakres."


def _theme_layout(figure: go.Figure) -> None:
    """Wspólny styl Plotly: przezroczyste tło, atramentowa typografia, delikatna siatka."""
    figure.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255, 255, 255, 0.16)",
        font={"family": THEME_FONT, "color": THEME_INK, "size": 13},
        title_font={"color": THEME_INK},
        hoverlabel={
            "bgcolor": "rgba(255, 250, 244, 0.96)",
            "bordercolor": "rgba(120, 60, 20, 0.25)",
            "font": {"family": THEME_FONT, "color": THEME_INK},
        },
    )
    figure.update_xaxes(
        gridcolor=THEME_GRID,
        linecolor=THEME_AXIS,
        zeroline=False,
        tickfont={"color": THEME_INK_SOFT},
        title_font={"color": THEME_INK_SOFT},
    )
    figure.update_yaxes(
        gridcolor=THEME_GRID,
        linecolor=THEME_AXIS,
        zeroline=False,
        tickfont={"color": THEME_INK_SOFT},
        title_font={"color": THEME_INK_SOFT},
    )


def build_figure(
    view: OfferView,
    *,
    metric: Metric | str,
    range_text: str,
    markers: Sequence[ChartMarker] = (),
) -> go.Figure:
    """Wykres dwupanelowy: poziom licznika + dzienne przyrosty (z anomaliami).

    Dla `metric="both"` poziom wyświetleń i obserwujących jest na dwóch osiach Y.
    """
    both = view.secondary_series is not None
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.68, 0.32],
        vertical_spacing=0.1,
        specs=[[{"secondary_y": both}], [{"secondary_y": False}]],
    )

    if not view.points:
        figure.add_annotation(
            text=EMPTY_MESSAGE,
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 15},
        )
        _apply_layout(figure, view, metric=metric, range_text=range_text)
        return figure

    moments = [to_local(point.captured_at) for point in view.points]
    values = [point.value for point in view.points]
    figure.add_trace(
        go.Scatter(
            x=moments,
            y=values,
            mode="lines+markers",
            name=metric_label("visits") if both else metric_label(metric),
            line={"color": LINE_COLOR, "width": 2},
            marker={"size": 4},
            hovertemplate="%{x|%d.%m.%Y %H:%M}<br>%{y:,.0f}<extra></extra>",
        ),
        row=1,
        col=1,
        secondary_y=False,
    )

    if both and view.secondary_series is not None:
        secondary_points = {
            to_local(point.captured_at): point.value
            for point in view.secondary_series.points
        }
        figure.add_trace(
            go.Scatter(
                x=list(secondary_points),
                y=list(secondary_points.values()),
                mode="lines+markers",
                name=metric_label("watchers"),
                line={"color": WATCHERS_COLOR, "width": 2, "dash": "dot"},
                marker={"size": 4},
                hovertemplate="%{x|%d.%m.%Y %H:%M}<br>%{y:,.0f}<extra></extra>",
            ),
            row=1,
            col=1,
            secondary_y=True,
        )

    anomalies = view.summary.anomalies
    if anomalies:
        by_moment = {to_local(point.captured_at): point.value for point in view.points}
        anomaly_x = [to_local(anomaly.captured_at) for anomaly in anomalies]
        anomaly_y = [by_moment.get(moment) for moment in anomaly_x]
        figure.add_trace(
            go.Scatter(
                x=anomaly_x,
                y=anomaly_y,
                mode="markers",
                name="spadek licznika",
                marker={"color": ANOMALY_COLOR, "size": 11, "symbol": "x"},
                hovertemplate="spadek o %{customdata}<extra></extra>",
                customdata=[abs(anomaly.delta) for anomaly in anomalies],
            ),
            row=1,
            col=1,
            secondary_y=False,
        )

    if view.daily:
        days = [datetime.combine(gain.day, time.min, tzinfo=LOCAL_TZ) for gain in view.daily]
        figure.add_trace(
            go.Bar(
                x=days,
                y=[gain.gained for gain in view.daily],
                name="dzienny przyrost",
                marker_color=GAIN_COLOR,
                hovertemplate="%{x|%d.%m.%Y}<br>+%{y:,.0f}<extra></extra>",
            ),
            row=2,
            col=1,
        )

    for marker in markers:
        figure.add_vline(
            x=to_local(marker.at),
            line_width=1,
            line_dash="dot",
            line_color=ANNOTATION_COLOR if marker.kind == "annotation" else EVENT_COLOR,
            annotation_text=marker.label[:26],
            annotation_position="top",
            annotation_font_size=10,
        )

    _apply_layout(figure, view, metric=metric, range_text=range_text)
    return figure


def build_comparison_figure(
    indexed: Sequence[IndexedSeries], *, metric: Metric | str, range_text: str
) -> go.Figure:
    """Porównanie ofert: indeks 100 w pierwszym punkcie wspólnego okna (FR-14)."""
    figure = go.Figure()
    for item in indexed:
        moments = [to_local(point.captured_at) for point in item.points]
        values = [point.index for point in item.points]
        figure.add_trace(
            go.Scatter(
                x=moments,
                y=values,
                mode="lines+markers",
                name=f"{item.offer.name} ({item.offer.offer_id})",
                marker={"size": 4},
                hovertemplate="%{x|%d.%m.%Y %H:%M}<br>indeks %{y:.1f}<extra></extra>",
            )
        )

    if not figure.data:
        figure.add_annotation(
            text="Brak ofert do porównania — wybierz oferty z danymi w tym przedziale.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 15},
        )

    figure.update_layout(
        title={
            "text": f"Porównanie ofert — {metric_label(metric)} ({range_text})<br>"
            "<sup>indeks 100 = wartość w pierwszym punkcie okna</sup>",
            "x": 0.01,
            "xanchor": "left",
        },
        height=540,
        margin={"l": 70, "r": 30, "t": 95, "b": 45},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "x": 1,
            "xanchor": "right",
            "font": {"color": THEME_INK},
        },
        hovermode="x unified",
    )
    _theme_layout(figure)
    figure.update_yaxes(title_text="indeks (100 = start okna)")
    figure.update_xaxes(title_text="czas (Europe/Warsaw)")
    return figure


def _apply_layout(
    figure: go.Figure, view: OfferView, *, metric: Metric | str, range_text: str
) -> None:
    summary = view.summary
    subtitle = (
        f"pokrycie: {format_percent(summary.coverage)} · "
        f"{points_label(summary.n_points)} · "
        f"anomalie: {len(summary.anomalies)} · "
        f"snapshoty w bazie: {format_number(view.snapshots)}"
    )
    figure.update_layout(
        title={
            "text": f"{view.offer.name} — {metric_label(metric)} ({range_text})<br>"
            f"<sup>{subtitle}</sup>",
            "x": 0.01,
            "xanchor": "left",
        },
        height=560,
        margin={"l": 70, "r": 30, "t": 95, "b": 45},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "x": 1,
            "xanchor": "right",
            "font": {"color": THEME_INK},
        },
        hovermode="x unified",
        bargap=0.2,
    )
    _theme_layout(figure)
    if view.secondary_series is not None:
        figure.update_yaxes(title_text=metric_label("visits"), row=1, col=1, secondary_y=False)
        figure.update_yaxes(
            title_text=metric_label("watchers"), row=1, col=1, secondary_y=True
        )
        figure.update_yaxes(title_text="przyrost wyświetleń", row=2, col=1, secondary_y=False)
    else:
        figure.update_yaxes(title_text=metric_label(metric), row=1, col=1)
        figure.update_yaxes(title_text="przyrost", row=2, col=1)
    figure.update_xaxes(title_text="czas (Europe/Warsaw)", row=2, col=1)

    if view.series.is_synthetic:
        figure.add_annotation(
            text="DANE SYNTETYCZNE",
            xref="paper",
            yref="paper",
            x=0.99,
            y=0.03,
            showarrow=False,
            font={"size": 13, "color": SYNTHETIC_COLOR},
            bgcolor="rgba(255, 235, 205, 0.85)",
            bordercolor=SYNTHETIC_COLOR,
            borderwidth=1,
        )
