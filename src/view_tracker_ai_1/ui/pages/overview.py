"""Przegląd „ogółem” (S3): kafle, porównanie okresów, ranking ofert z linkami."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import streamlit as st

from view_tracker_ai_1 import services
from view_tracker_ai_1.models import Metric
from view_tracker_ai_1.text import (
    alert_rule_label,
    format_datetime,
    format_decimal,
    format_number,
    format_percent,
    format_signed_percent,
    metric_label,
    offers_label,
    range_label,
)
from view_tracker_ai_1.ui import components, state


def render() -> None:
    current = state.current_state()
    config = state.config_for(current)
    components.page_header(
        "Przegląd",
        f"Baza: {state.DATABASE_LABELS[current.database]}",
    )

    with components.connection(config) as conn:
        if conn is None:
            return
        offers = services.list_offers(conn)
        if not offers:
            st.info(
                "Baza nie ma jeszcze ofert. Uruchom zbieranie (S4) albo wygeneruj dane demo."
            )
            return

        chosen_range, chosen_metric = components.range_and_metric_controls(
            current, allow_both=False
        )
        metric = cast(Metric, chosen_metric)
        now = datetime.now(UTC)
        summary = services.overview(conn, range_key=chosen_range, metric=metric, now=now)
        comparison = services.compare_periods(
            conn, range_key=chosen_range, metric=metric, now=now
        )

        level_value = summary.levels.visits if metric == "visits" else summary.levels.watchers
        st.caption(
            f"Zakres: {range_label(chosen_range)} · metryka: {metric_label(metric)} · "
            f"dane na: {format_datetime(summary.levels.at)}"
        )

        first, second, third, fourth = st.columns(4)
        first.metric(f"Poziom: {metric_label(metric)}", format_number(level_value))
        second.metric(
            "Przyrost w oknie",
            f"+{format_number(summary.gains.gained)}",
            delta=_change_label(comparison.change_pct),
        )
        third.metric(
            "Mediana przyrostu",
            "—" if summary.median_gain is None else format_decimal(summary.median_gain, 1),
        )
        fourth.metric("Oferty z danymi", format_number(summary.levels.offers))

        fifth, sixth, seventh, eighth = st.columns(4)
        fifth.metric("Oferty ze spadkiem", format_number(summary.offers_with_drops))
        sixth.metric("Spadki licznika", format_number(summary.gains.drops))
        seventh.metric(
            "Poprzedni okres",
            f"+{format_number(comparison.previous.gained)}"
            if comparison.previous.offers
            else "brak danych",
        )
        eighth.metric("Oferty w bazie", format_number(len(offers)))

        st.caption(
            f"{offers_label(len(offers))} · "
            + _comparison_caption(chosen_range, comparison.change_pct)
        )

        hits = services.alert_hits(conn, now=now, metric=metric)
        if hits:
            described = "; ".join(
                f"{hit.offer.name}: {alert_rule_label(hit.rule.kind)} "
                f"{format_percent(hit.drop_pct)} (szczyt {format_number(hit.peak_value)} → "
                f"teraz {format_number(hit.last_value)})"
                for hit in hits[:3]
            )
            more = f" (+{len(hits) - 3} więcej)" if len(hits) > 3 else ""
            st.warning(f"Alerty progowe: {described}{more}")

        st.divider()
        st.subheader("Ranking ofert")
        if not summary.ranking:
            st.info("Brak przyrostów w tym oknie — wybierz szerszy zakres.")
        else:
            st.dataframe(
                [
                    {
                        "Oferta": row.offer.name,
                        "ID": row.offer.offer_id,
                        "Przyrost": f"+{format_number(row.gained)}",
                        "Spadki": format_number(row.drops),
                        "Otwórz": _offer_link(current, row.offer.offer_id, chosen_range, metric),
                    }
                    for row in summary.ranking
                ],
                hide_index=True,
                width="stretch",
                column_config={
                    "Otwórz": st.column_config.LinkColumn("Otwórz", display_text="pokaż"),
                },
            )

        st.caption(
            "Ranking liczy przyrosty per oferta (spadki nie obniżają sumy). "
            "Poziom „ogółem” to suma ostatnich snapshotów w jednej chwili — nie suma w czasie."
        )


def _change_label(change: float | None) -> str | None:
    if change is None:
        return None
    return f"{format_signed_percent(change)} vs poprzedni okres"


def _comparison_caption(range_key: str, change: float | None) -> str:
    if change is None:
        return (
            "brak porównania z poprzednim okresem (zakres „cały okres” albo brak danych)"
            if range_key == "all"
            else "brak danych z poprzedniego okresu"
        )
    return f"zmiana przyrostu: {format_signed_percent(change)} vs poprzedni okres"


def _offer_link(current: state.UiState, offer_id: str, range_key: str, metric: Metric) -> str:
    return f"oferta?db={current.database}&offer={offer_id}&range={range_key}&metric={metric}"
