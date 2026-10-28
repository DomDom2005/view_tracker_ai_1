"""Interfejs CLI (argparse).

Kody wyjścia (SPEC §8): 0 sukces, 1 błąd użytkownika/konfiguracji, 2 błąd autoryzacji,
3 błąd API/limit. Komendy: `auth login`, `auth status`, `offers list`, `collect`.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO
from zoneinfo import ZoneInfo

from view_tracker_ai_1 import __version__, collector, storage
from view_tracker_ai_1.auth import DeviceAuthorization, DeviceFlowAuth
from view_tracker_ai_1.client import AllegroClient
from view_tracker_ai_1.config import Config, setup_logging
from view_tracker_ai_1.errors import (
    ApiError,
    AuthError,
    ConfigError,
    RateLimitError,
    StorageError,
)

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_AUTH = 2
EXIT_API = 3

LOCAL_TZ = ZoneInfo("Europe/Warsaw")
TIME_FORMAT = "%Y-%m-%d %H:%M"


@dataclass
class CliContext:
    """Kontekst komendy — strumienie wstrzykiwane, żeby dały się przechwycić w testach."""

    config: Config
    stdout: TextIO
    stderr: TextIO


class CommandParser(argparse.ArgumentParser):
    """Parser, który błędy użycia kończy kodem 1 (SPEC §8), a nie argparse'owym 2."""

    def error(self, message: str) -> None:  # noqa: D102 - zachowanie z argparse
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: błąd: {message}\n")


# --- parser -----------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    """Zbuduj parser CLI wraz z komendami dostępnymi w tym etapie."""
    parser = CommandParser(
        prog="view_tracker_ai_1",
        description="Historia i trendy liczników ofert Allegro.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_global_options(parser)

    commands = parser.add_subparsers(dest="command", required=True, metavar="komenda")

    auth_parser = commands.add_parser("auth", help="logowanie i stan tokenów")
    auth_commands = auth_parser.add_subparsers(dest="auth_command", required=True, metavar="akcja")
    login_parser = auth_commands.add_parser("login", help="zaloguj przez device flow")
    _add_global_options(login_parser, suppress_defaults=True)
    login_parser.set_defaults(handler=_cmd_auth_login)
    status_parser = auth_commands.add_parser("status", help="pokaż, czy token jest ważny")
    _add_global_options(status_parser, suppress_defaults=True)
    status_parser.set_defaults(handler=_cmd_auth_status)

    offers_parser = commands.add_parser("offers", help="oferty zapisane w bazie")
    offers_commands = offers_parser.add_subparsers(
        dest="offers_command", required=True, metavar="akcja"
    )
    list_parser = offers_commands.add_parser("list", help="wypisz oferty z bazy")
    _add_global_options(list_parser, suppress_defaults=True)
    list_parser.add_argument("--status", help="filtr statusu, np. ACTIVE")
    list_parser.set_defaults(handler=_cmd_offers_list)

    collect_parser = commands.add_parser("collect", help="pobierz snapshoty liczników")
    _add_global_options(collect_parser, suppress_defaults=True)
    collect_parser.add_argument(
        "--status",
        action="append",
        dest="statuses",
        metavar="STATUS",
        help="status oferty do pobrania (można podać wielokrotnie; domyślnie ACTIVE)",
    )
    collect_parser.add_argument(
        "--loop",
        action="store_true",
        help="pracuj w pętli (Ctrl+C kończy)",
    )
    collect_parser.add_argument(
        "--interval",
        type=int,
        default=collector.DEFAULT_INTERVAL_SECONDS,
        metavar="SEC",
        help=f"interwał pętli w sekundach (min. {collector.MIN_INTERVAL_SECONDS})",
    )
    collect_parser.set_defaults(handler=_cmd_collect)

    return parser


def _add_global_options(
    parser: argparse.ArgumentParser, *, suppress_defaults: bool = False
) -> None:
    """Opcje globalne. Na podkomendach nie ustawiają domyślnych wartości, żeby nie
    nadpisywały tego, co podano przed komendą."""
    default = argparse.SUPPRESS if suppress_defaults else None
    parser.add_argument(
        "--env",
        choices=("sandbox", "prod"),
        default=default,
        help="środowisko API (domyślnie z ALLEGRO_ENV)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=default,
        metavar="PATH",
        help="ścieżka bazy SQLite (domyślnie data/<env>.db)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=argparse.SUPPRESS if suppress_defaults else False,
        help="logowanie na poziomie DEBUG",
    )


# --- wejście ----------------------------------------------------------------
def main(argv: Sequence[str] | None = None) -> int:
    """Punkt wejścia CLI; mapuje wyjątki na kody wyjścia z SPEC §8."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = Config.from_env().with_overrides(**_config_overrides(args))
    except ConfigError as exc:
        print(f"Błąd konfiguracji: {exc}", file=sys.stderr)
        return EXIT_USAGE

    setup_logging(config.log_level)
    context = CliContext(config=config, stdout=sys.stdout, stderr=sys.stderr)

    try:
        return int(args.handler(args, context))
    except KeyboardInterrupt:
        print("\nPrzerwano (Ctrl+C).", file=sys.stderr)
        return EXIT_OK
    except ConfigError as exc:
        print(f"Błąd konfiguracji: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except AuthError as exc:
        print(f"Błąd autoryzacji: {exc}", file=sys.stderr)
        return EXIT_AUTH
    except (ApiError, RateLimitError) as exc:
        print(f"Błąd API: {exc}", file=sys.stderr)
        return EXIT_API
    except StorageError as exc:
        print(f"Błąd bazy danych: {exc}", file=sys.stderr)
        return EXIT_USAGE


def _config_overrides(args: argparse.Namespace) -> dict[str, object]:
    changes: dict[str, object] = {}
    env = getattr(args, "env", None)
    if env:
        changes["env"] = env
    db_path = getattr(args, "db", None)
    if db_path:
        changes["db_path"] = Path(db_path)
    if getattr(args, "verbose", False):
        changes["log_level"] = "DEBUG"
    return changes


# --- komendy ----------------------------------------------------------------
def _cmd_auth_login(args: argparse.Namespace, context: CliContext) -> int:
    auth = _build_auth(context.config)

    def announce(authorization: DeviceAuthorization) -> None:
        print("Aby zalogować się do Allegro:", file=context.stdout)
        print(f"  1. Otwórz: {authorization.verification_uri}", file=context.stdout)
        print(f"  2. Wpisz kod: {authorization.user_code}", file=context.stdout)
        if authorization.verification_uri_complete:
            print(
                f"  (skrót: {authorization.verification_uri_complete})",
                file=context.stdout,
            )
        print("Czekam na potwierdzenie…", file=context.stdout)
        context.stdout.flush()

    tokens = auth.login(announce=announce)
    print(
        f"Zalogowano. Token ważny do {_format_local(tokens.expires_at)}.",
        file=context.stdout,
    )
    return EXIT_OK


def _cmd_auth_status(args: argparse.Namespace, context: CliContext) -> int:
    status = _build_auth(context.config).status()
    if not status.logged_in:
        print(
            "Brak zalogowania. Uruchom: view_tracker_ai_1 auth login",
            file=context.stdout,
        )
        return EXIT_OK

    state = "wygasł — zaloguj się ponownie" if status.expired else "ważny"
    expires = "—" if status.expires_at is None else _format_local(status.expires_at)
    print(f"Token {state}. Ważny do: {expires}", file=context.stdout)
    if status.scope:
        print(f"Zakres: {status.scope}", file=context.stdout)
    return EXIT_OK


def _cmd_offers_list(args: argparse.Namespace, context: CliContext) -> int:
    conn = _open_db(context.config)
    try:
        offers = storage.list_offers(conn, status=args.status)
        if not offers:
            print(
                "Baza nie ma jeszcze ofert — uruchom: view_tracker_ai_1 collect",
                file=context.stdout,
            )
            return EXIT_OK

        print(f"{'ID':<16} {'STATUS':<10} {'OSTATNI SNAPSHOT':<18} NAZWA", file=context.stdout)
        for offer in offers:
            last = storage.get_last_snapshot(conn, offer.offer_id)
            when = "—" if last is None else _format_local(last.captured_at)
            status = offer.status or "—"
            print(f"{offer.offer_id:<16} {status:<10} {when:<18} {offer.name}", file=context.stdout)
    finally:
        conn.close()
    return EXIT_OK


def _cmd_collect(args: argparse.Namespace, context: CliContext) -> int:
    statuses = tuple(args.statuses) if args.statuses else collector.DEFAULT_STATUSES
    interval = int(args.interval)

    if args.loop and interval < collector.MIN_INTERVAL_SECONDS:
        print(
            f"Minimalny interwał pętli to {collector.MIN_INTERVAL_SECONDS} s "
            f"(licznik odświeża się co godzinę).",
            file=context.stderr,
        )
        return EXIT_USAGE

    conn = _open_db(context.config)
    try:
        client = _build_client(context.config)
        if args.loop:
            print(
                f"Tryb ciągły: co {interval} s, statusy: {', '.join(statuses)}. "
                "Ctrl+C kończy.",
                file=context.stdout,
            )
            context.stdout.flush()
            collector.run_forever(client, conn, statuses=statuses, interval=interval)
        else:
            inserted = collector.run_once(client, conn, statuses=statuses)
            print(f"Zapisano {inserted} nowych snapshotów.", file=context.stdout)
    finally:
        conn.close()
    return EXIT_OK


# --- fabryki (podmieniane w testach) ---------------------------------------
def _build_auth(config: Config) -> DeviceFlowAuth:
    return DeviceFlowAuth(config=config)


def _build_client(config: Config) -> AllegroClient:
    return AllegroClient(config=config)


def _open_db(config: Config) -> sqlite3.Connection:
    conn = storage.connect(config.effective_db_path)
    try:
        storage.init_db(conn)
    except Exception:
        # Bez tego wyjątek z init_db (np. niezgodna wersja schematu) zostawiał
        # otwarte połączenie — `finally` w komendzie już się nie wykonywał.
        conn.close()
        raise
    return conn


def _format_local(moment: datetime) -> str:
    return moment.astimezone(LOCAL_TZ).strftime(TIME_FORMAT)


if __name__ == "__main__":
    sys.exit(main())
