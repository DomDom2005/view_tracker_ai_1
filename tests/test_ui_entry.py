"""Testy wejścia `python -m view_tracker_ai_1.ui` bez uruchamiania serwera."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import streamlit.web.cli as streamlit_cli

from view_tracker_ai_1.ui import __main__ as ui_entry


def test_build_argv_points_to_app_script(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UI_PORT", raising=False)
    argv = ui_entry.build_argv()

    assert argv[0] == "streamlit"
    assert argv[1] == "run"
    assert Path(argv[2]).name == "app.py"
    assert Path(argv[2]).exists()
    assert "--server.headless=true" in argv
    assert "--server.port=8501" in argv


def test_build_argv_passes_extra_flags() -> None:
    argv = ui_entry.build_argv(["--server.port", "8599"])
    assert argv[-2:] == ["--server.port", "8599"]


def test_build_argv_honours_ui_port_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UI_PORT", "8602")
    argv = ui_entry.build_argv()

    assert "--server.port=8602" in argv


def test_main_delegates_to_streamlit_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []
    monkeypatch.delenv("UI_PORT", raising=False)

    def fake_main() -> int:
        seen.append(list(sys.argv))
        return 0

    monkeypatch.setattr(streamlit_cli, "main", fake_main)
    original = list(sys.argv)
    try:
        exit_code = ui_entry.main(["--server.port", "8600"])
    finally:
        assert sys.argv == original  # przywracamy argv procesu

    assert exit_code == 0
    assert seen and seen[0][:3] == ["streamlit", "run", str(ui_entry.APP_PATH)]
    assert seen[0][-2:] == ["--server.port", "8600"]
