"""Dane i kolektor (S4): „Odśwież”, stan przebiegów i tryb ciągły w aplikacji."""

from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from view_tracker_ai_1 import __version__, services, storage
from view_tracker_ai_1.errors import AppError, AuthError
from view_tracker_ai_1.text import format_datetime, format_number
from view_tracker_ai_1.ui import components, state
from view_tracker_ai_1.ui import runtime as runtime_module

REFRESH_MESSAGE_KEY = "refresh-message"
LOGIN_POLL_SECONDS = 5


def render() -> None:
    current = state.current_state()
    config = state.config_for(current)
    read_only = current.database in ("prod", "demo")
    components.page_header(
        "Dane i kolektor",
        f"Baza: {config.effective_db_path} · środowisko API: {config.env}",
    )

    with components.connection(config) as conn:
        if conn is None:
            return

        _flash_message()
        collector = services.collector_state(conn)
        fresh = collector.freshness

        _login_section(config)
        if current.database == "demo":
            components.synthetic_badge()

        left, middle, right = st.columns(3)
        left.metric("Ostatni snapshot", format_datetime(fresh.last_captured_at))
        middle.metric("Snapshoty", format_number(fresh.snapshots))
        right.metric("Oferty z danymi", format_number(fresh.offers))
        st.caption(
            f"Wersja aplikacji: {__version__} · wersja schematu: v{storage.SCHEMA_VERSION}"
        )

        st.divider()
        st.subheader("Odświeżanie jednorazowe")
        if current.database == "prod":
            st.error("Baza produkcyjna jest tylko do odczytu — zbieranie jest zablokowane.")
        elif current.database == "demo":
            st.info(
                "Baza demo zawiera dane syntetyczne — zbieranie z API jest zablokowane, "
                "żeby nie mieszać źródeł. Przełącz bazę na Sandbox, żeby zbierać."
            )
        pressed = st.button(
            "Odśwież teraz",
            type="primary",
            disabled=read_only,
            help="Pobiera listę ofert z API i zapisuje snapshoty (jeden przebieg).",
        )
        if pressed:
            _refresh(conn, config)

        st.divider()
        _loop_controls(conn, config, read_only=read_only)

        st.divider()
        st.subheader("Ostatnie przebiegi kolektora")
        if collector.runs:
            st.dataframe(
                [
                    {
                        "Start": format_datetime(
                            storage.from_iso(str(run["started_at"]))
                            if run["started_at"]
                            else None
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
            st.info("Brak zapisanych przebiegów — użyj „Odśwież teraz”.")


def _login_section(config) -> None:  # noqa: ANN001 - Config bez importu w podpisie UI
    st.subheader("Logowanie Allegro")
    try:
        status = services.token_status(config)
    except AppError as exc:
        st.warning(f"Nie mogę sprawdzić tokena: {exc}")
        return

    if status.logged_in and not status.expired:
        st.success(f"Token ważny do {format_datetime(status.expires_at)}.")
        return
    if status.logged_in and status.expired:
        st.warning("Token wygasł — zaloguj się ponownie.")

    pending = st.session_state.get("auth-pending")
    if not pending:
        if st.button("Rozpocznij logowanie", key="begin-login"):
            try:
                pair = services.begin_login(config)
            except AppError as exc:
                st.error(f"Nie mogę rozpocząć logowania: {exc}")
            else:
                st.session_state["auth-pending"] = pair
                st.rerun()
        st.caption("Device flow: aplikacja poprosi o kod, który wpiszesz na stronie Allegro.")
        return

    auth, authorization = pending
    st.info(
        f"Otwórz {authorization.verification_uri} i wpisz kod **{authorization.user_code}**."
    )
    _poll_login(auth, authorization)


@st.fragment(run_every=LOGIN_POLL_SECONDS)
def _poll_login(auth, authorization) -> None:  # noqa: ANN001 - obiekty auth.py
    try:
        services.complete_login(auth, authorization)
    except AuthError:
        st.caption(
            f"Czekam na zatwierdzenie — sprawdzam co {LOGIN_POLL_SECONDS} s. "
            "Możesz też anulować i spróbować ponownie."
        )
    except AppError as exc:
        st.error(f"Błąd logowania: {exc}")
        st.session_state.pop("auth-pending", None)
        return
    else:
        st.session_state.pop("auth-pending", None)
        st.success("Zalogowano — token zapisany.")
        st.rerun(scope="app")
    if st.button("Anuluj logowanie", key="cancel-login"):
        st.session_state.pop("auth-pending", None)
        st.rerun(scope="app")


def _refresh(conn, config) -> None:  # noqa: ANN001 - sqlite3.Connection w warstwie UI
    try:
        result = services.refresh_once(config, conn)
    except AuthError as exc:
        st.session_state[REFRESH_MESSAGE_KEY] = (
            "error",
            f"Autoryzacja: {exc} Zaloguj się ponownie.",
        )
    except AppError as exc:
        st.session_state[REFRESH_MESSAGE_KEY] = ("error", f"Błąd zbierania: {exc}")
    else:
        st.session_state[REFRESH_MESSAGE_KEY] = (
            "success",
            f"Zapisano {format_number(result.inserted)} nowych snapshotów "
            f"dla {format_number(result.offers)} ofert.",
        )
    st.rerun()


def _flash_message() -> None:
    message = st.session_state.pop(REFRESH_MESSAGE_KEY, None)
    if not message:
        return
    kind, text = message
    if kind == "success":
        st.success(text)
    else:
        st.error(text)


def _loop_controls(conn, config, *, read_only: bool) -> None:  # noqa: ANN001
    st.subheader("Tryb ciągły")
    runtime = runtime_module.shared_runtime(config)
    status = runtime.status()

    stored = storage.get_state(conn, "collect_interval")
    default_interval = int(stored) if stored else runtime_module.DEFAULT_INTERVAL_SECONDS
    interval = st.number_input(
        "Interwał (sekundy; minimum 300)",
        min_value=runtime_module.MIN_INTERVAL_SECONDS,
        value=max(default_interval, runtime_module.MIN_INTERVAL_SECONDS),
        step=60,
        disabled=read_only,
        key=f"interval-{config.effective_db_path}",
    )
    if int(interval) != status.interval:
        runtime.configure(interval=int(interval))
    if str(int(interval)) != stored:
        storage.set_state(conn, "collect_interval", str(int(interval)))

    enabled = st.toggle(
        "Zbieraj cyklicznie, gdy aplikacja działa",
        value=status.running,
        disabled=read_only,
        key="loop-toggle",
    )
    if not read_only and enabled != status.running:
        if enabled:
            runtime.start()
        else:
            runtime.stop()
        st.rerun()

    status = runtime.status()
    if status.running:
        st.success("Tryb ciągły działa.")
    else:
        st.info("Tryb ciągły jest wyłączony.")
    st.caption(
        f"Przebiegi: {status.runs} · zapisane snapshoty: {format_number(status.inserted_total)} · "
        f"ostatni start: {format_datetime(status.last_started_at)} · "
        f"następny: {format_datetime(status.next_run_at)}"
    )
    if status.last_error:
        st.warning(f"Ostatni błąd ({status.last_status}): {status.last_error}")
    st.caption(
        "Tryb ciągły działa tylko, gdy proces aplikacji jest uruchomiony — "
        f"uśpienie komputera oznacza lukę w danych. Teraz: {format_datetime(datetime.now(UTC))}."
    )
