"""Dane i kolektor — S1: diagnostyka danych; „Odśwież” i tryb ciągły w S4."""

from __future__ import annotations

import streamlit as st

from view_tracker_ai_1 import __version__, services, storage
from view_tracker_ai_1.text import format_datetime, format_number
from view_tracker_ai_1.ui import components, state


def render() -> None:
    current = state.current_state()
    config = state.config_for(current)
    components.page_header(
        "Dane i kolektor",
        f"Baza: {config.effective_db_path} · środowisko API: {config.env}",
    )

    with components.connection(config) as conn:
        if conn is None:
            return
        collector = services.collector_state(conn)
        fresh = collector.freshness

        left, middle, right = st.columns(3)
        left.metric("Ostatni snapshot", format_datetime(fresh.last_captured_at))
        middle.metric("Snapshoty", format_number(fresh.snapshots))
        right.metric("Oferty z danymi", format_number(fresh.offers))

        st.caption(f"Wersja aplikacji: {__version__} · wersja schematu: v{storage.SCHEMA_VERSION}")

        if collector.runs:
            st.subheader("Ostatnie przebiegi kolektora")
            st.dataframe(
                [
                    {
                        "Start": format_datetime(
                            storage.from_iso(str(run["started_at"])) if run["started_at"] else None
                        ),
                        "Status": run["status"],
                        "Oferty": run["offers_count"],
                        "Nowe snapshoty": run["inserted"],
                        "Błąd": run["error_message"] or "—",
                    }
                    for run in collector.runs
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info(
                "Brak zapisanych przebiegów — kolektor nie był jeszcze uruchamiany z aplikacji."
            )

    st.divider()
    st.subheader("Zbieranie danych")
    st.markdown(
        "W etapie **S4** pojawi się przycisk **„Odśwież”** (jednorazowy przebieg) oraz "
        "opcjonalny **tryb ciągły** z interwałem ≥ 300 s, działający w tle procesu aplikacji."
    )
    if current.database == "prod":
        st.error("Na bazie produkcyjnej zbieranie jest zablokowane (tylko odczyt).")
