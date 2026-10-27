"""Smoke test szkieletu: moduły się importują, CLI odpowiada, sieć jest zablokowana."""

from __future__ import annotations

import importlib
import socket

import pytest

import view_tracker_ai_1
from view_tracker_ai_1.cli import main

MODULES = (
    "actions",
    "ai_comment",
    "analytics",
    "auth",
    "charts",
    "client",
    "collector",
    "config",
    "errors",
    "models",
    "report",
    "storage",
)


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name: str) -> None:
    assert importlib.import_module(f"view_tracker_ai_1.{name}") is not None


def test_version_is_set() -> None:
    assert view_tracker_ai_1.__version__


def test_cli_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert "view_tracker_ai_1" in capsys.readouterr().out


def test_network_is_blocked() -> None:
    with pytest.raises(RuntimeError):
        socket.create_connection(("example.com", 80), timeout=0.1)
