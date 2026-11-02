"""`python -m view_tracker_ai_1.ui` — uruchamia Streamlita z aplikacją 2.0.

Odpowiednik `streamlit run src/view_tracker_ai_1/ui/app.py`, ale przez moduł Pythona,
żeby użytkownik nie musiał znać ścieżki do pliku (SPEC-2.0 §6 FR-1).
Port: `UI_PORT` (domyślnie 8501), chyba że podano `--server.port` w argumentach.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path

APP_PATH: Path = Path(__file__).with_name("app.py")
DEFAULT_FLAGS: tuple[str, ...] = ("--server.headless=true",)
DEFAULT_PORT = "8501"
PORT_FLAG = "--server.port"


def build_argv(extra: Sequence[str] = ()) -> list[str]:
    """Zbuduj `sys.argv` dla Streamlita (testowalne bez uruchamiania serwera)."""
    arguments = list(extra)
    has_port = any(
        argument == PORT_FLAG or argument.startswith(f"{PORT_FLAG}=")
        for argument in arguments
    )
    if not has_port:
        arguments = [*arguments, f"{PORT_FLAG}={os.environ.get('UI_PORT', DEFAULT_PORT)}"]
    return ["streamlit", "run", str(APP_PATH), *DEFAULT_FLAGS, *arguments]


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    previous = sys.argv
    sys.argv = build_argv(arguments)
    try:
        from streamlit.web import cli as streamlit_cli

        result = streamlit_cli.main()
    finally:
        sys.argv = previous
    return int(result or 0)


if __name__ == "__main__":
    raise SystemExit(main())
