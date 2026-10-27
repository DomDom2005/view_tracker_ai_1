"""Interfejs CLI (argparse). Komendy: auth, offers, collect, chart, comment, report, act."""

from __future__ import annotations

import argparse
import sys

from view_tracker_ai_1 import __version__


def build_parser() -> argparse.ArgumentParser:
    """Zbuduj parser CLI. Komendy dochodzą etapami (PLAN.md): auth+collect (4), chart (6), ..."""
    parser = argparse.ArgumentParser(
        prog="view_tracker_ai_1",
        description="Historia i trendy liczników ofert Allegro.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    # TODO(PLAN stage 4): globalne opcje --env/--db/-v oraz komendy auth, collect, offers list.
    # TODO(PLAN stage 6): chart. TODO(stage 7): comment. TODO(stage 8): report. TODO(stage 9): act.
    return parser


def main(argv: list[str] | None = None) -> int:
    """Punkt wejścia CLI. Kody wyjścia: 0 sukces, 1 błąd użytkownika, 2 auth, 3 API (SPEC §8)."""
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
