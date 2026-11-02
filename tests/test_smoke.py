"""Smoke test szkieletu 2.0: moduły się importują, AI/CLI/eksport usunięte, sieć zamknięta."""

from __future__ import annotations

import importlib
import socket

import pytest

import view_tracker_ai_1

MODULES = (
    "actions",
    "analytics",
    "auth",
    "client",
    "collector",
    "config",
    "errors",
    "models",
    "queries",
    "services",
    "storage",
    "text",
)

REMOVED_MODULES = ("ai_comment", "charts", "report", "cli")


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name: str) -> None:
    assert importlib.import_module(f"view_tracker_ai_1.{name}") is not None


@pytest.mark.parametrize("name", REMOVED_MODULES)
def test_removed_modules_are_gone(name: str) -> None:
    """2.0 usuwa AI, eksport i CLI — moduły nie mogą wrócić przypadkiem (SPEC-2.0 §10)."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"view_tracker_ai_1.{name}")


def test_version_is_set() -> None:
    assert view_tracker_ai_1.__version__


def test_network_is_blocked() -> None:
    with pytest.raises(RuntimeError):
        socket.create_connection(("example.com", 80), timeout=0.1)
