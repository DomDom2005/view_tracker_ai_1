"""Wspólne elementy UI: wybór bazy, belka statusu, obsługa błędów, połączenie z bazą."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace

import streamlit as st

from view_tracker_ai_1 import __version__, queries, services, storage
from view_tracker_ai_1.config import Config
from view_tracker_ai_1.errors import AppError, StorageError
from view_tracker_ai_1.text import format_datetime, range_label
from view_tracker_ai_1.ui.state import (
    DATABASE_LABELS,
    DATABASE_NAMES,
    METRIC_CHOICE_LABELS,
    METRIC_CHOICES,
    RANGE_CHOICES,
    UiState,
    with_database,
)

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
        from view_tracker_ai_1.ui import runtime as runtime_module
        from view_tracker_ai_1.ui import state as state_module

        # Zmiana bazy nie może zostawić pętli zbierającej dane do starej bazy.
        runtime_module.stop_for(state_module.config_for(state))
        state_module.update(with_database(state, chosen))
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


def page_header(title: str, subtitle: str | None = None) -> None:
    """Nagłówek strony: kicker, tytuł, podtytuł i cienka linia jak w motywie."""
    st.markdown(
        '<div class="vt-kicker">panel sprzedawcy · view_tracker_ai_1</div>',
        unsafe_allow_html=True,
    )
    st.title(title)
    if subtitle:
        st.caption(subtitle)
    st.markdown('<div class="vt-rule"></div>', unsafe_allow_html=True)


def sidebar(state: UiState, config: Config) -> None:
    """Belka statusu: środowisko, token, świeżość danych, wersje."""
    with st.sidebar:
        st.markdown(
            '<div class="vt-brand">view<span>·</span>tracker</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"panel ofert · v{__version__}")
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
        st.caption("Zaloguj się na stronie Dane (device flow).")
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


def range_and_metric_controls(
    current: UiState, *, allow_both: bool = True
) -> tuple[str, str]:
    """Wspólne przełączniki zakresu i metryki; zmiana od razu trafia do URL."""
    from view_tracker_ai_1.ui import state as state_module

    chosen_range = st.radio(
        "Zakres",
        RANGE_CHOICES,
        index=RANGE_CHOICES.index(current.range_key),
        format_func=range_label,
        horizontal=True,
        key=f"range-controls-{current.range_key}",
    )
    if chosen_range != current.range_key:
        state_module.update(replace(current, range_key=chosen_range))
        st.rerun()

    metric_options = METRIC_CHOICES if allow_both else METRIC_CHOICES[:2]
    chosen_metric = st.radio(
        "Metryka",
        metric_options,
        index=metric_options.index(current.metric) if current.metric in metric_options else 0,
        format_func=METRIC_CHOICE_LABELS.get,
        horizontal=True,
        key=f"metric-controls-{current.metric}",
    )
    if chosen_metric != current.metric:
        state_module.update(replace(current, metric=chosen_metric))
        st.rerun()
    return chosen_range, chosen_metric


def synthetic_badge() -> None:
    """Plakietka dla danych syntetycznych (FR-18: wykres, tabela, kafel)."""
    st.markdown(":orange-badge[DANE SYNTETYCZNE]")


def placeholder(step: str, description: str) -> None:
    """Czytelny ekran „będzie w etapie X” zamiast pustki."""
    st.info(f"{description} (etap {step}).")
