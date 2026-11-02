"""Konfiguracja testów: blokada sieci zewnętrznej i wspólne fixtures.

Testy nie mogą otwierać połączeń do świata — HTTP mockujemy (`responses`). Wyjątkiem jest
**loopback**: asyncio i runtime Streamlita (AppTest) tworzą wewnętrzne gniazda na
`127.0.0.1`, więc blokujemy wszystko poza `127.0.0.1`/`::1`/`localhost`.
"""

from __future__ import annotations

import os
import socket
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRATCH = _REPO_ROOT / ".tmp"
_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})

_ORIGINAL_GETADDRINFO = socket.getaddrinfo
_ORIGINAL_CREATE_CONNECTION = socket.create_connection
_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_CONNECT_EX = socket.socket.connect_ex


def _keep_caches_in_scratch() -> None:
    """Nie pozwól testom tworzyć katalogów-śmieci w katalogu repo.

    Na tej maszynie katalog tymczasowy systemu bywa niezapisywalny (sandbox blokuje
    tworzenie katalogów przez procesy potomne), więc `tempfile.gettempdir()` zwraca
    katalog repo — i tam lądują `pytest-of-*`.
    """
    system_tmp = Path(tempfile.gettempdir()).resolve()
    if not system_tmp.is_relative_to(_REPO_ROOT):
        return

    _SCRATCH.mkdir(parents=True, exist_ok=True)
    for name in ("TMPDIR", "TMP", "TEMP"):
        os.environ[name] = str(_SCRATCH)
    tempfile.tempdir = None  # porzuć zapamiętaną wartość, żeby nowy TMP zadziałał


_keep_caches_in_scratch()


class NetworkAccessBlocked(RuntimeError):
    """Podniesione, gdy test próbuje otworzyć połączenie poza loopbackiem."""


def _raise_network_blocked() -> None:
    raise NetworkAccessBlocked(
        "Testy działają offline (SPEC §12) — zamockuj HTTP, np. przez `responses`."
    )


def _is_loopback(address: Any) -> bool:
    return isinstance(address, tuple) and bool(address) and str(address[0]) in _LOOPBACK


def _guarded_connect(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapper(sock: socket.socket, address: Any, *args: Any, **kwargs: Any) -> Any:
        if _is_loopback(address):
            return original(sock, address, *args, **kwargs)
        _raise_network_blocked()

    return wrapper


def _guarded_create_connection(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapper(address: Any, *args: Any, **kwargs: Any) -> Any:
        if _is_loopback(address):
            return original(address, *args, **kwargs)
        _raise_network_blocked()

    return wrapper


def _guarded_getaddrinfo(original: Callable[..., Any]) -> Callable[..., Any]:
    def wrapper(host: Any, *args: Any, **kwargs: Any) -> Any:
        if str(host) in _LOOPBACK:
            return original(host, *args, **kwargs)
        _raise_network_blocked()

    return wrapper


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zablokuj DNS i połączenia wychodzące; loopback zostaje dozwolony (asyncio, AppTest)."""
    monkeypatch.setattr(socket, "getaddrinfo", _guarded_getaddrinfo(_ORIGINAL_GETADDRINFO))
    monkeypatch.setattr(
        socket, "create_connection", _guarded_create_connection(_ORIGINAL_CREATE_CONNECTION)
    )
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect(_ORIGINAL_CONNECT))
    monkeypatch.setattr(socket.socket, "connect_ex", _guarded_connect(_ORIGINAL_CONNECT_EX))
