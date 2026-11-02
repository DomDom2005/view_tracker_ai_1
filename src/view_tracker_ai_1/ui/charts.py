"""Figury Plotly dla UI 2.0 (SPEC-2.0 §11).

Rysujemy z gotowego `OfferView` (punkty, agregaty dobowe, podsumowanie), więc warstwa
prezentacji nie powtarza analityki. Osie czasu w `Europe/Warsaw`, liczby i etykiety PL.
"""

from __future__ import annotations

from datetime import datetime, time

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from view_tracker_ai_1.models import Metric
from view_tracker_ai_1.services import OfferView
from view_tracker_ai_1.text import (
    LOCAL_TZ,
    format_number,
    format_percent,
    metric_label,
    points_label,
    to_local,
)

LINE_COLOR = "#1f77b4"
GAIN_COLOR = "#2ca02c"
ANOMALY_COLOR = "#d62728"
SYNTHETIC_COLOR = "#b35c00"

EMPTY_MESSAGE = "Brak danych w wybranym przedziale — uruchom zbieranie albo wybierz inny zakres."


def build_figure(view: OfferView, *, metric: Metric, range_text: str) -> go.Figure:
    """Wykres dwupanelowy: poziom licznika + dzienne przyrosty (z anomaliami)."""
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.68, 0.32],
        vertical_spacing=0.1,
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
            name=metric_label(metric),
            line={"color": LINE_COLOR, "width": 2},
            marker={"size": 4},
            hovertemplate="%{x|%d.%m.%Y %H:%M}<br>%{y:,.0f}<extra></extra>",
        ),
        row=1,
        col=1,
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

    _apply_layout(figure, view, metric=metric, range_text=range_text)
    return figure


def _apply_layout(figure: go.Figure, view: OfferView, *, metric: Metric, range_text: str) -> None:
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
        template="plotly_white",
        height=560,
        margin={"l": 70, "r": 30, "t": 95, "b": 45},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 1, "xanchor": "right"},
        hovermode="x unified",
        bargap=0.2,
    )
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
