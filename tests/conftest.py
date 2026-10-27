"""Konfiguracja testów: twarda blokada sieci (SPEC §12) i wspólne fixtures.

Żaden test nie może otworzyć połączenia sieciowego — HTTP mockujemy (`responses`).
Blokada jest na poziomie gniazd, więc łapie też biblioteki, które nie wiedzą o mockach.
"""

from __future__ import annotations

import socket

import pytest


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
