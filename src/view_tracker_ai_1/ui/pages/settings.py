"""Ustawienia — w S1: konfiguracja, ścieżki, wersje, informacje o bazach."""

from __future__ import annotations

import streamlit as st

from view_tracker_ai_1 import __version__, storage
from view_tracker_ai_1.config import DEFAULT_ENV, DEFAULT_LOG_LEVEL
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
    st.info(
        "Generator danych syntetycznych (`scripts/seed_demo_data.py`) ma wejście w UI "
        "w etapie S6. Do tego czasu uruchamia się go z terminala."
    )
