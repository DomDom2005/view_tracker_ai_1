"""Faza 0 SPEC: obserwacja zachowania licznika `visitsCount` przez >= 48 h.

Uruchamia **człowiek**, na koncie z realnym ruchem — agent dostarcza tylko skrypt.
Celem jest sprawdzenie hipotezy z SPEC §4.2: czy licznik bywa oknem kroczącym (maleje).

Przykład (192 pomiary × 15 min ≈ 48 h):

    python scripts/probe_counter.py --offer 1234567890 --interval 900 --runs 192

Wynik trafia do README jako ograniczenie/ustalenie.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Uruchomienie bez `pip install -e .`: dodaj `src/` do ścieżki importu.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from view_tracker_ai_1 import storage  # noqa: E402
from view_tracker_ai_1.client import AllegroClient  # noqa: E402
from view_tracker_ai_1.config import Config, setup_logging  # noqa: E402
from view_tracker_ai_1.errors import AppError  # noqa: E402
from view_tracker_ai_1.models import Offer, Snapshot  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Zapisuj liczniki wybranych ofert i sprawdź, czy visitsCount maleje.",
    )
    parser.add_argument(
        "--offer",
        action="append",
        dest="offers",
        required=True,
        metavar="ID",
        help="identyfikator oferty (można podać wielokrotnie)",
    )
    parser.add_argument("--interval", type=int, default=900, help="sekundy między pomiarami")
    parser.add_argument("--runs", type=int, default=192, help="liczba pomiarów")
    parser.add_argument("--env", choices=("sandbox", "prod"), default=None)
    parser.add_argument("--db", type=Path, default=Path("data") / "probe.db")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    config = Config.from_env()
    if args.env:
        config = config.with_overrides(env=args.env)
    config = config.with_overrides(db_path=args.db)
    setup_logging(config.log_level)

    conn = storage.connect(config.effective_db_path)
    storage.init_db(conn)
    client = AllegroClient(config=config)

    print(
        f"Obserwacja {len(args.offers)} ofert co {args.interval} s, "
        f"{args.runs} pomiarów. Ctrl+C przerywa i pokazuje raport."
    )
    try:
        for index in range(args.runs):
            moment = datetime.now(UTC)
            remote = list(
                client.iter_offers(statuses=("ACTIVE",), limit=100, offer_ids=args.offers)
            )
            added = storage.save_collection(
                conn,
                offers=[
                    Offer(
                        offer_id=item.offer_id,
                        name=item.name,
                        status=item.status,
                        first_seen_at=moment,
                        last_seen_at=moment,
                    )
                    for item in remote
                ],
                snapshots=[
                    Snapshot(
                        offer_id=item.offer_id,
                        captured_at=moment,
                        visits_count=item.visits_count,
                        watchers_count=item.watchers_count,
                        source="api",
                    )
                    for item in remote
                ],
            )
            print(
                f"[{index + 1}/{args.runs}] {moment:%Y-%m-%d %H:%M} UTC — "
                f"{len(remote)} ofert, {added} nowych snapshotów"
            )
            if index + 1 < args.runs:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nPrzerwano — raport z zebranych danych:")
    except AppError as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    finally:
        report(conn, args.offers)
        conn.close()
    return 0


def report(conn, offer_ids: list[str]) -> None:
    print("\nRaport z obserwacji licznika visitsCount:")
    for offer_id in offer_ids:
        values = [snapshot.visits_count for snapshot in storage.get_series(conn, offer_id)]
        if len(values) < 2:
            print(f"  oferta {offer_id}: za mało danych ({len(values)} pomiarów)")
            continue
        drops = sum(1 for before, after in zip(values, values[1:], strict=False) if after < before)
        verdict = (
            "licznik malał — wygląda na okno kroczące"
            if drops
            else "licznik rósł monotonicznie"
        )
        print(
            f"  oferta {offer_id}: {len(values)} pomiarów, min={min(values)}, "
            f"max={max(values)}, spadków={drops} → {verdict}"
        )
    print("Wniosek opisz w README (SPEC §4.2, sekcja „Ograniczenia”).")


if __name__ == "__main__":
    raise SystemExit(main())
