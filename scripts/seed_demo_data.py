"""Generator danych syntetycznych do bazy demo (SPEC-2.0 FR-18).

Logika generatora mieszka w pakiecie (`view_tracker_ai_1.demo`); ten skrypt to tylko
cienkie wejście z terminala dla człowieka.

Użycie:
    python scripts/seed_demo_data.py --db data/demo.db --seed 42
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from view_tracker_ai_1 import demo, storage

DEFAULT_DB = Path("data") / "demo.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seed_demo_data.py",
        description="Generuj syntetyczne snapshoty do bazy demo (source='synthetic').",
    )
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB, help=f"baza docelowa (dom. {DEFAULT_DB})"
    )
    parser.add_argument("--seed", type=int, default=demo.DEFAULT_SEED, help="ziarno generatora")
    parser.add_argument("--days", type=int, default=demo.DEFAULT_DAYS, help="ile dni historii")
    parser.add_argument(
        "--end",
        help="koniec zakresu w ISO 8601 (dom. bieżąca godzina UTC) — dla powtarzalnych danych",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    end = _parse_end(args.end)

    try:
        conn = storage.connect(args.db)
    except (OSError, sqlite3.Error) as exc:
        print(f"Nie mogę otworzyć bazy {args.db}: {exc}", file=sys.stderr)
        return 1

    try:
        result = demo.seed_demo_database(conn, seed=args.seed, days=args.days, end=end)
    except demo.DemoDataError as exc:
        print(f"Odmowa: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print(
        f"Zapisano {result.snapshots} snapshotów dla {result.offers} ofert "
        f"do {args.db} (source='synthetic', seed={result.seed}, dni={result.days})."
    )
    print("To dane syntetyczne — w aplikacji będą oznaczone plakietką „DANE SYNTETYCZNE”.")
    return 0


def _parse_end(value: str | None) -> datetime:
    if value is None:
        return demo.default_end()
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


if __name__ == "__main__":
    sys.exit(main())
