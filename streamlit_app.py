#!/usr/bin/env python
"""Punkt wejścia dla Streamlit Community Cloud.

Cloud uruchamia dokładnie jeden plik (`streamlit run <main file path>`) i nie
instaluje pakietu z `src/`, więc tutaj dodajemy `src/` do `sys.path` i wykonujemy
właściwą aplikację (`view_tracker_ai_1/ui/app.py`) w trybie skryptu.

Lokalnie nic się nie zmienia: nadal `python run.py` albo
`python -m view_tracker_ai_1.ui`.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

runpy.run_path(str(SRC / "view_tracker_ai_1" / "ui" / "app.py"), run_name="__main__")
