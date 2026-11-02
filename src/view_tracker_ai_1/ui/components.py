"""Wspólne elementy UI: wybór bazy, belka statusu, obsługa błędów, połączenie z bazą."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

import streamlit as st

from view_tracker_ai_1 import __version__, queries, services, storage
from view_tracker_ai_1.config import Config
from view_tracker_ai_1.errors import AppError, StorageError
from view_tracker_ai_1.text import format_datetime
from view_tracker_ai_1.ui.state import DATABASE_LABELS, DATABASE_NAMES, UiState, with_database

ENV_LABELS = {"sandbox": "SANDBOX", "prod": "PROD", "demo": "DEMO"}


def database_selector(state: UiState) -> UiState:
    """Selektor bazy; zmiana natychmiast trafia do URL i przerywa bieżący rerun."""
    options = list(DATABASE_NAMES)
    chosen = st.selectbox(
        "Baza danych",
        options=options,
        index=options.index(state.database),
        format_func=lambda name: DATABASE_LABELS[name],
        key=f"db-selector-{state.database}",
    )
    if chosen != state.database:
        new_state = with_database(state, chosen)
        from view_tracker_ai_1.ui import state as state_module

        state_module.update(new_state)
        st.rerun()
    return state


@contextmanager
def connection(config: Config) -> Iterator[sqlite3.Connection | None]:
    """Połączenie na czas widoku; błąd bazy pokazujemy, nie wywalamy aplikacji."""
    try:
        conn = services.open_database(config)
    except (StorageError, OSError, sqlite3.Error) as exc:
        st.error(f"Nie mogę otworzyć bazy `{config.effective_db_path}`: {exc}")
        yield None
        return
    try:
        yield conn
    finally:
        conn.close()


def sidebar(state: UiState, config: Config) -> None:
    """Belka statusu: środowisko, token, świeżość danych, wersje."""
    with st.sidebar:
        st.caption(f"view_tracker_ai_1 {__version__}")
        database_selector(state)
        label = ENV_LABELS[state.database]
        if state.database == "prod":
            st.error(f"{label} — tylko odczyt")
        elif state.database == "demo":
            st.info(f"{label} — dane syntetyczne")
        else:
            st.info(f"{label}")

        st.divider()
        _token_block(config)
        st.divider()
        _freshness_block(config)
        st.divider()
        st.caption(f"Schemat: v{storage.SCHEMA_VERSION} · baza: `{config.effective_db_path}`")


def _token_block(config: Config) -> None:
    try:
        status = services.token_status(config)
    except AppError as exc:
        st.warning(f"Stan tokena nieznany: {exc}")
        return
    if not status.logged_in:
        st.markdown("**Token:** brak zalogowania")
        st.caption("Logowanie pojawi się w etapie S2.")
        return
    state_text = "wygasł" if status.expired else "ważny"
    st.markdown(f"**Token:** {state_text}")
    st.caption(f"Ważny do: {format_datetime(status.expires_at)}")


def _freshness_block(config: Config) -> None:
    try:
        with connection(config) as conn:
            if conn is None:
                return
            fresh = queries.freshness(conn)
    except AppError as exc:
        st.warning(f"Nie mogę odczytać stanu danych: {exc}")
        return

    if fresh.last_captured_at is None:
        st.markdown("**Dane:** brak snapshotów")
        st.caption("Uruchom zbieranie w etapie S4 albo wygeneruj dane demo.")
        return
    st.markdown(f"**Ostatni snapshot:** {format_datetime(fresh.last_captured_at)}")
    st.caption(f"{fresh.offers} ofert · {fresh.snapshots} snapshotów")


def page_header(title: str, subtitle: str | None = None) -> None:
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def placeholder(step: str, description: str) -> None:
    """Czytelny ekran „będzie w etapie X” zamiast pustki."""
    st.info(f"{description} (etap {step}).")
