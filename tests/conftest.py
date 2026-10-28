"""Konfiguracja testów: twarda blokada sieci (SPEC §12) i wspólne fixtures.

Żaden test nie może otworzyć połączenia sieciowego — HTTP mockujemy (`responses`).
Blokada jest na poziomie gniazd, więc łapie też biblioteki, które nie wiedzą o mockach.
"""

from __future__ import annotations

import os
import socket
import tempfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRATCH = _REPO_ROOT / ".tmp"


def _keep_caches_in_scratch() -> None:
    """Nie pozwól testom tworzyć katalogów-śmieci w katalogu repo.

    Na tej maszynie katalog tymczasowy systemu bywa niezapisywalny (sandbox blokuje
    tworzenie katalogów przez procesy potomne), więc `tempfile.gettempdir()` zwraca
    katalog repo — i tam lądują `pytest-of-*` oraz katalog cache matplotliba.
    """
    system_tmp = Path(tempfile.gettempdir()).resolve()
    if not system_tmp.is_relative_to(_REPO_ROOT):
        os.environ.setdefault("MPLCONFIGDIR", str(system_tmp / "view_tracker_ai_1-mpl"))
        return

    _SCRATCH.mkdir(parents=True, exist_ok=True)
    for name in ("TMPDIR", "TMP", "TEMP"):
        os.environ[name] = str(_SCRATCH)
    tempfile.tempdir = None  # porzuć zapamiętaną wartość, żeby nowy TMP zadziałał
    os.environ.setdefault("MPLCONFIGDIR", str(_SCRATCH / "mplconfig"))


_keep_caches_in_scratch()


class NetworkAccessBlocked(RuntimeError):
    """Podniesione, gdy test próbuje otworzyć połączenie sieciowe."""


def _raise_network_blocked(*args: object, **kwargs: object) -> None:
    raise NetworkAccessBlocked(
        "Testy działają offline (SPEC §12) — zamockuj HTTP, np. przez `responses`."
    )


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zablokuj DNS i połączenia wychodzące w każdym teście."""
    monkeypatch.setattr(socket, "getaddrinfo", _raise_network_blocked)
    monkeypatch.setattr(socket, "create_connection", _raise_network_blocked)
    monkeypatch.setattr(socket.socket, "connect", _raise_network_blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _raise_network_blocked)
