"""Oferta — wybór oferty, zakres (presety + własny), metryka, wykres i podsumowanie (S2)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from typing import cast

import streamlit as st

from view_tracker_ai_1 import services
from view_tracker_ai_1.models import Metric
from view_tracker_ai_1.text import (
    LOCAL_TZ,
    format_datetime,
    format_decimal,
    format_number,
    format_percent,
    metric_label,
    points_label,
    range_label,
)
from view_tracker_ai_1.ui import charts, components, state

PLOT_METRICS: tuple[Metric, ...] = ("visits", "watchers")


def render() -> None:
    current = state.current_state()
    config = state.config_for(current)
    components.page_header(
        "Oferta",
        f"Baza: {state.DATABASE_LABELS[current.database]}",
    )

    with components.connection(config) as conn:
        if conn is None:
            return
        offers = services.list_offers(conn)
        if not offers:
            st.info("Brak ofert w bazie — najpierw zbierz dane (S4) albo wygeneruj demo.")
            return

        ids = [item.offer.offer_id for item in offers]
        names = {
            item.offer.offer_id: f"{item.offer.name} ({item.offer.offer_id})" for item in offers
        }

        current_id = current.offers[0] if current.offers and current.offers[0] in ids else ids[0]
        chosen_id = st.selectbox(
            "Oferta",
            ids,
            index=ids.index(current_id),
            format_func=names.get,
            key=f"offer-selector-{current_id}",
        )
        if (chosen_id,) != current.offers:
            state.update(replace(current, offers=(chosen_id,)))
            st.rerun()

        chosen_range = st.radio(
            "Zakres",
            state.RANGE_CHOICES,
            index=state.RANGE_CHOICES.index(current.range_key),
            format_func=range_label,
            horizontal=True,
            key=f"range-selector-{current.range_key}",
        )
        if chosen_range != current.range_key:
            state.update(replace(current, range_key=chosen_range))
            st.rerun()

        chosen_metric = st.radio(
            "Metryka",
            state.METRIC_CHOICES,
            index=state.METRIC_CHOICES.index(current.metric),
            format_func=state.METRIC_CHOICE_LABELS.get,
            horizontal=True,
            key=f"metric-selector-{current.metric}",
        )
        if chosen_metric != current.metric:
            state.update(replace(current, metric=chosen_metric))
            st.rerun()

        now = datetime.now(UTC)
        start: datetime | None = None
        end: datetime | None = None
        if chosen_range == "custom":
            start, end = _custom_range(current, now)
            if start is None:
                return

        metrics: tuple[Metric, ...] = (
            PLOT_METRICS
            if chosen_metric == "both"
            else (cast(Metric, chosen_metric),)
        )

        tabs = (
            st.tabs([metric_label(metric) for metric in metrics])
            if len(metrics) > 1
            else [st.container()]
        )
        for tab, metric in zip(tabs, metrics, strict=True):
            with tab:
                view = services.offer_view(
                    conn,
                    chosen_id,
                    range_key=chosen_range,
                    metric=metric,
                    now=now,
                    start=start,
                    end=end,
                )
                if view is None:
                    st.error("Nie znaleziono oferty w bazie.")
                    return
                _render_offer(view, metric=metric, range_text=range_label(chosen_range))


def _render_offer(view: services.OfferView, *, metric: Metric, range_text: str) -> None:
    figure = charts.build_figure(view, metric=metric, range_text=range_text)
    st.plotly_chart(figure, width="stretch", key=f"chart-{metric}")

    summary = view.summary
    _summary_card(view, metric=metric)
    st.caption(
        f"Anomalie: {len(summary.anomalies)} · luki > 2 h: {view.gaps} · "
        f"snapshoty w bazie: {format_number(view.snapshots)} · "
        f"aktualizacja danych: {format_datetime(view.freshness.last_captured_at)}"
    )

    if view.series.is_synthetic:
        st.warning("DANE SYNTETYCZNE — to nie są dane z API, nie wyciągaj z nich wniosków o rynku.")
    if summary.n_points == 0:
        st.info(
            "Brak punktów w tym przedziale — uruchom zbieranie (S4) albo wybierz szerszy zakres."
        )
    elif summary.n_points < 6 or summary.coverage < 0.3:
        st.info(
            "Mało danych w przedziale — trend jest niepewny "
            f"({points_label(summary.n_points)}, pokrycie {format_percent(summary.coverage)})."
        )


def _summary_card(view: services.OfferView, *, metric: Metric) -> None:
    summary = view.summary
    st.subheader(f"Podsumowanie: {metric_label(metric)}")
    if summary.n_points == 0:
        st.caption("Brak danych do podsumowania.")
        return

    first, second, third, fourth = st.columns(4)
    first.metric("Minimum", format_number(summary.min))
    second.metric("Maksimum", format_number(summary.max))
    third.metric("Średnia", format_decimal(summary.mean, 1))
    fourth.metric("Przyrost", f"+{format_number(summary.gained_total)}")

    fifth, sixth, seventh, eighth = st.columns(4)
    fifth.metric("Trend", summary.trend_label)
    sixth.metric("Nachylenie / dzień", format_decimal(summary.slope_per_day, 2))
    seventh.metric("Pokrycie", format_percent(summary.coverage))
    eighth.metric("Punkty", summary.n_points)

    if summary.start and summary.end:
        st.caption(f"Dane od {format_datetime(summary.start)} do {format_datetime(summary.end)}.")


def _custom_range(
    current: state.UiState, now: datetime
) -> tuple[datetime | None, datetime | None]:
    today = now.astimezone(LOCAL_TZ).date()
    default_from = today - timedelta(days=30)
    parsed_from = _safe_date(current.date_from, default_from)
    parsed_to = _safe_date(current.date_to, today)

    left, right = st.columns(2)
    start_date = left.date_input("Od", value=parsed_from, max_value=today)
    end_date = right.date_input("Do", value=parsed_to, max_value=today)

    if (start_date.isoformat(), end_date.isoformat()) != (current.date_from, current.date_to):
        state.update(
            replace(current, date_from=start_date.isoformat(), date_to=end_date.isoformat())
        )
        st.rerun()

    if start_date > end_date:
        st.error("Data „Od” jest późniejsza niż „Do” — popraw zakres.")
        return None, None

    start = datetime.combine(start_date, time.min, tzinfo=LOCAL_TZ)
    end = datetime.combine(end_date, time(23, 59, 59), tzinfo=LOCAL_TZ)
    return start, end


def _safe_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except ValueError:
        return fallback
