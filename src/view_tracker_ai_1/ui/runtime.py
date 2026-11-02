"""Tryb ciągły kolektora w procesie aplikacji (SPEC-2.0 §9, decyzja D3).

Zasady:
- jeden wątek daemon na proces (`shared_runtime` z `st.cache_resource`),
- wątek ma **własne** połączenie SQLite (WAL + `busy_timeout` z `storage.connect`),
- status czytany przez UI tylko przez `status()` (lock), bez dotykania `st.session_state`,
- stan „włączony” nie jest odtwarzany po restarcie procesu,
- `AuthError` zatrzymuje pętlę; inne błędy są logowane i pętla leci dalej.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import streamlit as st

from view_tracker_ai_1 import collector, services
from view_tracker_ai_1.client import AllegroClient
from view_tracker_ai_1.config import Config
from view_tracker_ai_1.errors import AppError, AuthError

MIN_INTERVAL_SECONDS = collector.MIN_INTERVAL_SECONDS
DEFAULT_INTERVAL_SECONDS = collector.DEFAULT_INTERVAL_SECONDS
STOP_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class RuntimeStatus:
    """Migawka stanu pętli do wyświetlenia w UI (bez uchwytów wątków)."""

    running: bool = False
    interval: int = DEFAULT_INTERVAL_SECONDS
    runs: int = 0
    inserted_total: int = 0
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    next_run_at: datetime | None = None
    last_status: str | None = None
    last_error: str | None = None


class CollectorRuntime:
    """Pętla zbierania w wątku; start/stop jawny, bez automatycznego startu."""

    def __init__(
        self,
        config: Config,
        *,
        interval: int = DEFAULT_INTERVAL_SECONDS,
        client_factory: Callable[[], AllegroClient] | None = None,
        now: Callable[[], datetime] | None = None,
        waiter: Callable[[float], bool] | None = None,
    ) -> None:
        if interval < MIN_INTERVAL_SECONDS:
            raise ValueError(
                f"Minimalny interwał trybu ciągłego to {MIN_INTERVAL_SECONDS} s."
            )
        self._config = config
        self._interval = interval
        self._client_factory = client_factory or (lambda: AllegroClient(config=config))
        self._now = now or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        # `waiter` zwraca True, gdy pętla ma się zatrzymać; domyślnie czeka na stop.
        self._waiter = waiter or self._stop.wait
        self._thread: threading.Thread | None = None
        self._status = RuntimeStatus(interval=interval)

    @property
    def config(self) -> Config:
        return self._config

    def status(self) -> RuntimeStatus:
        with self._lock:
            return self._status

    def configure(self, *, interval: int | None = None) -> RuntimeStatus:
        if interval is not None:
            if interval < MIN_INTERVAL_SECONDS:
                raise ValueError(
                    f"Minimalny interwał trybu ciągłego to {MIN_INTERVAL_SECONDS} s."
                )
            with self._lock:
                self._interval = interval
                self._status = replace(self._status, interval=interval)
        return self.status()

    def start(self) -> RuntimeStatus:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self._status
            self._stop.clear()
            self._status = replace(
                self._status,
                running=True,
                last_error=None,
                last_status=None,
                next_run_at=None,
            )
            self._thread = threading.Thread(
                target=self._loop,
                name="view-tracker-collector",
                daemon=True,
            )
            self._thread.start()
        return self.status()

    def stop(self, *, timeout: float = STOP_TIMEOUT_SECONDS) -> RuntimeStatus:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout)
        with self._lock:
            self._status = replace(self._status, running=False, next_run_at=None)
        return self.status()

    # --- wnętrze wątku ------------------------------------------------------
    def _loop(self) -> None:
        conn = None
        try:
            conn = services.open_database(self._config)
            while not self._stop.is_set():
                moment = self._now()
                with self._lock:
                    self._status = replace(
                        self._status,
                        last_started_at=moment,
                        next_run_at=None,
                    )
                try:
                    result = services.refresh_once(
                        self._config,
                        conn,
                        client=self._client_factory(),
                        now=moment,
                    )
                except AuthError as exc:
                    self._finish("auth_error", 0, str(exc))
                    break
                except AppError as exc:
                    self._finish("error", 0, str(exc))
                except Exception as exc:  # noqa: BLE001 - pętla nie może umrzeć po cichu
                    self._finish("error", 0, f"{exc.__class__.__name__}: {exc}")
                else:
                    self._finish("ok", result.inserted, None)

                with self._lock:
                    next_run = self._now() + timedelta(seconds=self._interval)
                    self._status = replace(self._status, next_run_at=next_run)
                if self._stop.is_set() or self._waiter(self._interval):
                    break
        finally:
            if conn is not None:
                conn.close()
            with self._lock:
                self._status = replace(self._status, running=False, next_run_at=None)

    def _finish(self, status: str, inserted: int, error: str | None) -> None:
        with self._lock:
            self._status = replace(
                self._status,
                runs=self._status.runs + 1,
                inserted_total=self._status.inserted_total + inserted,
                last_finished_at=self._now(),
                last_status=status,
                last_error=error,
            )


@st.cache_resource(show_spinner=False)
def shared_runtime(config: Config) -> CollectorRuntime:
    """Jedna pętla na proces i konfigurację (Streamlit tworzy ją raz)."""
    return CollectorRuntime(config=config)


def stop_for(config: Config) -> None:
    """Zatrzymaj pętlę dla konfiguracji, jeśli istnieje (np. przy zmianie bazy).

    Utworzenie nieuruchomionego runtime'u jest tanie i bezpieczne — `stop()` na nim
    nic nie robi, a dla działającej pętli zatrzymuje wątek.
    """
    try:
        shared_runtime(config).stop()
    except Exception:  # noqa: BLE001 - brak runtime'u nie jest błędem UI
        return
