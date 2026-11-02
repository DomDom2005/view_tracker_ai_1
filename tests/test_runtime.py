"""Testy trybu ciągłego: start/stop, obsługa błędów, brak wyścigów z odczytem."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from view_tracker_ai_1 import services, storage
from view_tracker_ai_1.client import RemoteOffer
from view_tracker_ai_1.config import Config
from view_tracker_ai_1.errors import ApiError, AuthError
from view_tracker_ai_1.models import Offer, Snapshot
from view_tracker_ai_1.ui.runtime import (
    DEFAULT_INTERVAL_SECONDS,
    MIN_INTERVAL_SECONDS,
    CollectorRuntime,
)

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def make_config(tmp_path: Path) -> Config:
    config = Config.from_env(
        {"ALLEGRO_CLIENT_ID": "test-id", "ALLEGRO_CLIENT_SECRET": "test-secret"},
        load_env_file=False,
    )
    return config.with_overrides(
        db_path=tmp_path / "loop.db",
        token_store_path=tmp_path / "tokens.json",
    )


class FakeClient:
    def __init__(self, *, failures: int = 0, error: Exception | None = None) -> None:
        self.failures = failures
        self.error = error if error is not None else ApiError("awaria")
        self.calls = 0

    def iter_offers(self, *, statuses, limit):  # noqa: ANN001, ANN202 - stub
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        yield RemoteOffer(
            offer_id="1",
            name="Suszarka",
            status="ACTIVE",
            visits_count=10,
            watchers_count=1,
        )


def wait_until(predicate, timeout: float = 5.0) -> bool:  # noqa: ANN001
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def make_runtime(config: Config, **kwargs: object) -> CollectorRuntime:
    options = {"interval": MIN_INTERVAL_SECONDS, "client_factory": FakeClient}
    options.update(kwargs)
    return CollectorRuntime(config, **options)  # type: ignore[arg-type]


def test_runtime_does_not_start_automatically(tmp_path: Path) -> None:
    runtime = make_runtime(make_config(tmp_path))

    status = runtime.status()
    assert status.running is False
    assert status.runs == 0
    assert status.interval == MIN_INTERVAL_SECONDS


def test_start_collects_and_stop_is_quick(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    runtime = make_runtime(config)

    runtime.start()
    assert runtime.status().running is True
    assert wait_until(lambda: runtime.status().runs >= 1)

    began = time.monotonic()
    stopped = runtime.stop()
    elapsed = time.monotonic() - began

    assert stopped.running is False
    assert elapsed <= 5.0
    assert not wait_until(lambda: runtime.status().running, timeout=0.2)

    conn = services.open_database(config)
    assert storage.recent_collect_runs(conn)[0]["status"] == "ok"
    assert storage.count_snapshots(conn) >= 1
    conn.close()


def test_auth_error_stops_the_loop(tmp_path: Path) -> None:
    runtime = make_runtime(
        make_config(tmp_path),
        client_factory=lambda: FakeClient(failures=99, error=AuthError("token wygasł")),
    )

    runtime.start()
    assert wait_until(lambda: runtime.status().last_status == "auth_error")
    assert wait_until(lambda: runtime.status().running is False)
    assert runtime.status().last_error == "token wygasł"


def test_api_error_does_not_stop_the_loop(tmp_path: Path) -> None:
    client = FakeClient(failures=1)  # pierwsze wywołanie pada, drugie się udaje
    runtime = make_runtime(
        make_config(tmp_path),
        client_factory=lambda: client,
        waiter=lambda seconds: False,  # bez czekania: pętla idzie od razu dalej
    )

    runtime.start()
    assert wait_until(lambda: runtime.status().runs >= 2)
    status = runtime.stop()

    assert status.last_status == "ok"
    assert status.inserted_total >= 1


def test_interval_validation(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    with pytest.raises(ValueError, match="Minimalny interwał"):
        CollectorRuntime(config, interval=60)

    runtime = CollectorRuntime(config, interval=DEFAULT_INTERVAL_SECONDS)
    with pytest.raises(ValueError, match="Minimalny interwał"):
        runtime.configure(interval=299)
    assert runtime.configure(interval=900).interval == 900


def test_stop_is_idempotent(tmp_path: Path) -> None:
    runtime = make_runtime(make_config(tmp_path))

    assert runtime.stop().running is False
    runtime.start()
    assert wait_until(lambda: runtime.status().runs >= 1)
    runtime.stop()
    assert runtime.stop().running is False


def test_concurrent_read_and_write_do_not_lock(tmp_path: Path) -> None:
    """Wątek pisze (jak pętla), UI czyta — WAL + busy_timeout mają to udźwignąć."""
    config = make_config(tmp_path)
    conn = services.open_database(config)
    storage.upsert_offer(
        conn,
        Offer(
            offer_id="1",
            name="Suszarka",
            status="ACTIVE",
            first_seen_at=NOW,
            last_seen_at=NOW,
        ),
    )

    errors: list[Exception] = []

    def writer() -> None:
        own = services.open_database(config)
        try:
            for index in range(50):
                storage.insert_snapshots(
                    own,
                    [
                        Snapshot(
                            offer_id="1",
                            captured_at=NOW + timedelta(minutes=index),
                            visits_count=index,
                            watchers_count=1,
                        )
                    ],
                )
        except Exception as exc:  # noqa: BLE001 - zbieramy do asercji
            errors.append(exc)
        finally:
            own.close()

    thread = threading.Thread(target=writer)
    thread.start()
    reads = 0
    while thread.is_alive():
        storage.list_offers(conn)
        storage.count_snapshots(conn)
        reads += 1
    thread.join(timeout=10)

    assert not errors
    assert reads > 0
    conn.close()
