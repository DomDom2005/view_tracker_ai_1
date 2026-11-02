"""Porównanie (S3): indeks 100 dla 2–5 ofert oraz porównanie okresów."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import streamlit as st

from view_tracker_ai_1 import services
from view_tracker_ai_1.models import Metric
from view_tracker_ai_1.text import (
    format_number,
    format_signed_percent,
    metric_label,
    range_label,
)
from view_tracker_ai_1.ui import charts, components, state

ALL_CATALOG = "__all__"


def render() -> None:
    current = state.current_state()
    config = state.config_for(current)
    components.page_header(
        "Porównanie",
        f"Baza: {state.DATABASE_LABELS[current.database]}",
    )

    with components.connection(config) as conn:
        if conn is None:
            return
        offers = services.list_offers(conn)
        if len(offers) < 2:
            st.info(
                "Do porównania potrzebne są co najmniej 2 oferty w bazie — "
                "zbierz dane (S4) albo wygeneruj demo."
            )
            return

        ids = [item.offer.offer_id for item in offers]
        names = {item.offer.offer_id: item.offer.name for item in offers}
        default = [offer_id for offer_id in current.offers if offer_id in ids][
            : services.MAX_COMPARISON_OFFERS
        ]
        if len(default) < 2:
            default = ids[:2]

        selected = st.multiselect(
            "Oferty do porównania (2–5)",
            ids,
            default=default,
            format_func=lambda offer_id: f"{names[offer_id]} ({offer_id})",
            max_selections=services.MAX_COMPARISON_OFFERS,
            key=f"compare-selection-{len(current.offers)}",
        )
        if tuple(selected) != current.offers:
            state.update(replace(current, offers=tuple(selected)))
            st.rerun()
        if len(selected) < 2:
            st.info("Wybierz co najmniej dwie oferty.")
            return

        chosen_range, chosen_metric = components.range_and_metric_controls(current)
        metrics: tuple[Metric, ...] = (
            ("visits", "watchers") if chosen_metric == "both" else (cast(Metric, chosen_metric),)
        )
        now = datetime.now(UTC)

        tabs = (
            st.tabs([metric_label(metric) for metric in metrics])
            if len(metrics) > 1
            else [st.container()]
        )
        for tab, metric in zip(tabs, metrics, strict=True):
            with tab:
                _render_comparison(conn, selected, names, chosen_range, metric, now)

        st.divider()
        st.subheader("Porównanie okresów")
        if chosen_range == "custom":
            st.info("Porównanie okresów dotyczy presetów — wybierz 7d/30d/90d albo cały okres.")
            return
        _render_periods(conn, ids, names, chosen_range, metrics[0], now)


def _render_comparison(
    conn,  # noqa: ANN001 - sqlite3.Connection bez importu w podpisie UI
    selected: list[str],
    names: dict[str, str],
    range_key: str,
    metric: Metric,
    now: datetime,
) -> None:
    indexed = services.compare_offers_indexed(
        conn, selected, range_key=range_key, metric=metric, now=now
    )
    figure = charts.build_comparison_figure(
        indexed, metric=metric, range_text=range_label(range_key)
    )
    st.plotly_chart(figure, width="stretch", key=f"comparison-{metric}")

    rows = services.comparison_rows(
        conn, selected, range_key=range_key, metric=metric, now=now
    )
    if rows:
        st.dataframe(
            [
                {
                    "Oferta": row.offer.name,
                    "ID": row.offer.offer_id,
                    "Start okna": format_number(row.base_value),
                    "Koniec okna": format_number(row.last_value),
                    "Przyrost": f"+{format_number(row.gained)}",
                    "Spadki": format_number(row.drops),
                    "Punkty": row.points,
                }
                for row in rows
            ],
            hide_index=True,
            width="stretch",
        )

    skipped = [
        offer_id
        for offer_id in selected
        if offer_id not in {item.offer.offer_id for item in indexed}
    ]
    if skipped:
        listed = ", ".join(
            f"{names.get(offer_id, offer_id)} ({offer_id})" for offer_id in skipped
        )
        st.caption(f"Pominięte w wykresie (brak danych albo poziom startowy 0): {listed}.")


def _render_periods(
    conn,  # noqa: ANN001
    ids: list[str],
    names: dict[str, str],
    range_key: str,
    metric: Metric,
    now: datetime,
) -> None:
    choice = st.selectbox(
        "Zakres porównania",
        [ALL_CATALOG, *ids],
        format_func=lambda value: "cały katalog" if value == ALL_CATALOG else names[value],
        key="period-scope",
    )
    comparison = services.compare_periods(
        conn,
        range_key=range_key,
        metric=metric,
        now=now,
        offer_id=None if choice == ALL_CATALOG else choice,
    )

    left, right = st.columns(2)
    left.metric(
        "Bieżący okres",
        f"+{format_number(comparison.current.gained)}",
        delta=(
            None
            if comparison.change_pct is None
            else format_signed_percent(comparison.change_pct)
        ),
    )
    right.metric("Poprzedni okres", f"+{format_number(comparison.previous.gained)}")

    st.dataframe(
        [
            {
                "Okres": f"bieżący ({range_label(range_key)})",
                "Oferty": comparison.current.offers,
                "Przyrost": comparison.current.gained,
                "Spadki": comparison.current.drops,
            },
            {
                "Okres": "poprzedni",
                "Oferty": comparison.previous.offers,
                "Przyrost": comparison.previous.gained,
                "Spadki": comparison.previous.drops,
            },
        ],
        hide_index=True,
        width="stretch",
    )
    if comparison.change_pct is None:
        st.caption("Brak danych z poprzedniego okresu — nie ma z czym porównać.")
