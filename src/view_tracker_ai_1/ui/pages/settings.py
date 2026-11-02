"""Ustawienia — w S1: konfiguracja, ścieżki, wersje, informacje o bazach."""

from __future__ import annotations

import streamlit as st

from view_tracker_ai_1 import __version__, services, storage
from view_tracker_ai_1.config import DEFAULT_ENV, DEFAULT_LOG_LEVEL
from view_tracker_ai_1.errors import AppError
from view_tracker_ai_1.ui import components, state


def render() -> None:
    current = state.current_state()
    config = state.config_for(current)
    components.page_header("Ustawienia", "Konfiguracja aplikacji i wybór bazy")

    st.subheader("Baza danych")
    st.write(f"Wybrana baza: **{state.DATABASE_LABELS[current.database]}**")
    st.code(str(config.effective_db_path), language="text")
    st.caption(
        "Zmiana bazy jest w panelu bocznym i od razu trafia do adresu widoku "
        "(parametr `db`), więc można wysłać link do konkretnej bazy."
    )

    st.subheader("Środowisko API")
    st.write(f"Environment: **{config.env}**")
    st.write(f"API: `{config.api_base_url}`")
    st.write(f"Autoryzacja: `{config.auth_base_url}`")
    if current.database == "prod":
        st.error(
            "Baza produkcyjna jest tylko do odczytu: zbieranie i tryb ciągły będą zablokowane."
        )

    st.subheader("Tokeny i logi")
    st.write(f"Plik tokenów: `{config.token_store_path}`")
    st.caption("Tokeny są poza repozytorium; aplikacja nie pokazuje ich wartości.")
    st.write(f"Poziom logów: **{config.log_level or DEFAULT_LOG_LEVEL}**")
    st.write(f"Domyślne środowisko z `.env`: **{DEFAULT_ENV}**")

    st.subheader("Wersje")
    st.write(f"Aplikacja: **{__version__}**")
    st.write(f"Schemat bazy: **v{storage.SCHEMA_VERSION}**")
    st.caption("Migracja ze schematu v1 wykonuje się automatycznie z kopią pliku `.bak-…`.")

    st.subheader("Dane demo")
    demo_path = state.resolve_db_path("demo")
    st.write(f"Baza demo: `{demo_path}`")
    st.caption(
        "Pięć ofert z wzorcami: wzrost, spadek, plateau, anomalia licznika i luki w danych. "
        "Wszystko z `source='synthetic'`; generator odmawia dopisania do bazy z danymi z API."
    )
    if st.button("Wygeneruj dane demo (90 dni)", disabled=current.database == "prod"):
        demo_config = config.with_overrides(db_path=demo_path)
        try:
            demo_conn = services.open_database(demo_config)
        except AppError as exc:
            st.error(f"Nie mogę otworzyć bazy demo: {exc}")
        else:
            try:
                result = services.seed_demo(demo_conn)
            except AppError as exc:
                st.error(f"Nie mogę wygenerować danych demo: {exc}")
            else:
                st.success(
                    f"Zapisano {result.snapshots} snapshotów dla {result.offers} ofert "
                    f"do `{demo_path}`. Wybierz bazę „Dane demo (syntetyczne)” w panelu bocznym."
                )
            finally:
                demo_conn.close()
    st.caption(
        "Ten sam generator z terminala: `python scripts/seed_demo_data.py --db data/demo.db`."
    )
