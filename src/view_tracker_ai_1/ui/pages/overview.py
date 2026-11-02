"""Przegląd „ogółem” — S1: stan danych; kafle, ranking i porównania w S3."""

from __future__ import annotations

import streamlit as st

from view_tracker_ai_1 import queries, services
from view_tracker_ai_1.text import format_datetime, offers_label, snapshots_label
from view_tracker_ai_1.ui import components, state


def render() -> None:
    current = state.current_state()
    config = state.config_for(current)
    components.page_header(
        "Przegląd",
        f"Baza: {state.DATABASE_LABELS[current.database]} · zakres: {current.range_key}",
    )

    with components.connection(config) as conn:
        if conn is None:
            return
        fresh = queries.freshness(conn)
        offers = services.list_offers(conn)

        if not offers:
            st.info(
                "Baza nie ma jeszcze ofert. W etapie S4 dojdzie przycisk „Odśwież”, "
                "a dane demo wygenerujesz w Ustawieniach."
            )
            return

        first, second, third = st.columns(3)
        first.metric("Oferty w bazie", len(offers))
        second.metric("Snapshoty", fresh.snapshots)
        third.metric(
            "Ostatni snapshot",
            "—" if fresh.last_captured_at is None else format_datetime(fresh.last_captured_at),
        )

        st.caption(f"{offers_label(len(offers))} · {snapshots_label(fresh.snapshots)}")
        st.divider()

        st.subheader("Co będzie tutaj w kolejnych etapach")
        st.markdown(
            "- **S2** — wybór oferty, zakresu i metryki oraz interaktywny wykres.\n"
            "- **S3** — kafle ogółem (poziomy jednej chwili, suma przyrostów), ranking ofert, "
            "mediana katalogu, porównanie okresów i ofert."
        )

        if offers:
            st.subheader("Oferty w bazie")
            st.dataframe(
                [
                    {
                        "ID": item.offer.offer_id,
                        "Nazwa": item.offer.name,
                        "Status": item.offer.status or "—",
                        "Ostatni snapshot": format_datetime(item.last_captured_at),
                        "Wyświetlenia": item.visits,
                        "Obserwujący": item.watchers,
                        "Snapshoty": item.snapshots,
                    }
                    for item in offers
                ],
                hide_index=True,
                width="stretch",
            )
