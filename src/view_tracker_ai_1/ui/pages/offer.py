"""Oferta — S1: rozpoznanie wyboru z URL; wykres i podsumowanie w S2."""

from __future__ import annotations

import streamlit as st

from view_tracker_ai_1 import services
from view_tracker_ai_1.ui import components, state


def render() -> None:
    current = state.current_state()
    config = state.config_for(current)
    components.page_header(
        "Oferta",
        f"Zakres: {current.range_key} · metryka: {current.metric}",
    )

    with components.connection(config) as conn:
        if conn is None:
            return
        offers = services.list_offers(conn)
        if not offers:
            st.info("Brak ofert w bazie — najpierw zbierz dane (S4) albo wygeneruj demo.")
            return

        if not current.offers:
            st.info(
                "Wybierz ofertę z listy (adres widoku przyjmuje parametr `offer`, "
                "np. `/?db=sandbox&offer=123&range=30d`)."
            )
        else:
            st.success(
                "Wybrana oferta z adresu: " + ", ".join(current.offers)
            )

        st.dataframe(
            [
                {
                    "ID": item.offer.offer_id,
                    "Nazwa": item.offer.name,
                    "Status": item.offer.status or "—",
                    "Snapshoty": item.snapshots,
                }
                for item in offers
            ],
            hide_index=True,
            width="stretch",
        )

    st.divider()
    st.subheader("Wykres i podsumowanie")
    st.markdown(
        "W etapie **S2** pojawi się interaktywny wykres Plotly (poziom licznika + dzienne "
        "przyrosty), przełącznik metryki i karta podsumowania z analityki v1."
    )
