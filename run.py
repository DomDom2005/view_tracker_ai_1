#!/usr/bin/env python
"""Uruchamia aplikację view_tracker_ai_1 (Streamlit) jednym poleceniem.

    python run.py
    python run.py --server.port 8600

Skrypt nie wymaga wcześniejszego `pip install -e .`: jeśli pakiet nie jest
zainstalowany, dodaje lokalne `src/` do `sys.path`. Wymaga tylko zależności
z `requirements.txt`. Port można też ustawić zmienną `UI_PORT`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from view_tracker_ai_1.ui.__main__ import main  # noqa: E402 - ścieżka dodana wyżej

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
