"""Testy launchera `run.py` i `start.bat`: import bez uruchamiania serwera, ścieżki, argumenty."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "run.py"


def load_run_module():
    spec = importlib.util.spec_from_file_location("vt_run", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["vt_run"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("vt_run", None)
    return module


def test_run_script_exists_and_exposes_main() -> None:
    module = load_run_module()

    assert callable(module.main)
    assert module.ROOT == ROOT
    assert module.SRC == ROOT / "src"


def test_run_script_delegates_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_run_module()
    seen: list[list[str]] = []
    monkeypatch.setattr(module, "main", lambda argv: seen.append(argv) or 0)

    exit_code = module.main(["--server.port", "8600"])

    assert exit_code == 0
    assert seen == [["--server.port", "8600"]]


def test_start_bat_prefers_venv_and_calls_run_script() -> None:
    batch = (ROOT / "start.bat").read_text(encoding="ascii")

    assert "%~dp0" in batch
    assert ".venv\\Scripts\\python.exe" in batch
    assert "%PY% run.py %*" in batch
    assert "pause" in batch
    assert "\r\n" in batch  # cmd.exe lubi CRLF
