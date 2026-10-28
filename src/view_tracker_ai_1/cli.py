"""Interfejs CLI (argparse).

Kody wyjścia (SPEC §8): 0 sukces, 1 błąd użytkownika/konfiguracji, 2 błąd autoryzacji,
3 błąd API/limit. Komendy: `auth login`, `auth status`, `offers list`, `collect`, `chart`.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO
from zoneinfo import ZoneInfo

from view_tracker_ai_1 import __version__, ai_comment, analytics, collector, storage
from view_tracker_ai_1.auth import DeviceAuthorization, DeviceFlowAuth
from view_tracker_ai_1.client import AllegroClient
from view_tracker_ai_1.config import Config, setup_logging
from view_tracker_ai_1.errors import (
    ApiError,
    AuthError,
    ChartError,
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

    chart_parser = commands.add_parser("chart", help="wykres PNG dla oferty")
    _add_global_options(chart_parser, suppress_defaults=True)
    chart_parser.add_argument("--offer", required=True, metavar="ID", help="identyfikator oferty")
    chart_parser.add_argument(
        "--range",
        dest="range_key",
        required=True,
        choices=analytics.RANGE_KEYS,
        help="przedział czasu",
    )
    chart_parser.add_argument(
        "--metric",
        choices=("visits", "watchers"),
        default="visits",
        help="metryka (domyślnie visits)",
    )
    chart_parser.add_argument(
        "--out", required=True, type=Path, metavar="FILE.png", help="plik PNG"
    )
    chart_parser.set_defaults(handler=_cmd_chart)

    comment_parser = commands.add_parser("comment", help="komentarz AI do wyników oferty")
    _add_global_options(comment_parser, suppress_defaults=True)
    comment_parser.add_argument("--offer", required=True, metavar="ID", help="identyfikator oferty")
    comment_parser.add_argument(
        "--range",
        dest="range_key",
        required=True,
        choices=analytics.RANGE_KEYS,
        help="przedział czasu",
    )
    comment_parser.add_argument(
        "--metric",
        choices=("visits", "watchers"),
        default="visits",
        help="metryka (domyślnie visits)",
    )
    comment_parser.add_argument(
        "--no-ai",
        action="store_true",
        dest="no_ai",
        help="nie wołaj modelu — użyj deterministycznej atrapy",
    )
    comment_parser.set_defaults(handler=_cmd_comment)

    report_parser = commands.add_parser("report", help="raport HTML z wykresami")
    _add_global_options(report_parser, suppress_defaults=True)
    report_parser.add_argument(
        "--range",
        dest="ranges",
        action="append",
        choices=analytics.RANGE_KEYS,
        help="przedział (można podać wielokrotnie; domyślnie 7d)",
    )
    report_parser.add_argument(
        "--offer",
        dest="offers",
        action="append",
        metavar="ID",
        help="ogranicz raport do oferty (można podać wielokrotnie)",
    )
    report_parser.add_argument(
        "--metric",
        choices=("visits", "watchers"),
        default="visits",
        help="metryka (domyślnie visits)",
    )
    report_parser.add_argument(
        "--no-ai",
        action="store_true",
        dest="no_ai",
        help="nie wołaj modelu — użyj deterministycznej atrapy",
    )
    report_parser.add_argument(
        "--out", required=True, type=Path, metavar="FILE.html", help="plik HTML"
    )
    report_parser.set_defaults(handler=_cmd_report)

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
    except ChartError as exc:
        print(f"Błąd wykresu: {exc}", file=sys.stderr)
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
                f"Tryb ciągły: co {interval} s, statusy: {', '.join(statuses)}. Ctrl+C kończy.",
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


def _cmd_chart(args: argparse.Namespace, context: CliContext) -> int:
    # Import lokalny: matplotlib jest ciężki i niepotrzebny w `auth`, `collect` czy
    # `comment`; poza tym przy pierwszym imporcie tworzy katalog cache.
    from view_tracker_ai_1 import charts

    conn = _open_db(context.config)
    try:
        offer = next(
            (item for item in storage.list_offers(conn) if item.offer_id == args.offer), None
        )
        if offer is None:
            print(
                f"Nie ma oferty {args.offer} w bazie — uruchom najpierw `collect`.",
                file=context.stderr,
            )
            return EXIT_USAGE

        snapshots = storage.get_series(conn, offer.offer_id)
        source = snapshots[0].source if snapshots else "api"
        series = analytics.build_series(
            snapshots, offer_id=offer.offer_id, metric=args.metric, source=source
        )
        result = charts.render_chart(
            series,
            offer_name=offer.name,
            range_key=args.range_key,
            now=_now(),
            out_path=args.out,
            metric=args.metric,
        )
    finally:
        conn.close()

    print(f"Zapisano wykres: {result.path}", file=context.stdout)
    print(
        f"  punktów: {result.n_points}, pokrycie: {result.coverage:.0%}, "
        f"anomalie: {result.anomalies}",
        file=context.stdout,
    )
    if result.is_synthetic:
        print("  DANE SYNTETYCZNE — to nie są dane z API.", file=context.stdout)
    return EXIT_OK


def _cmd_comment(args: argparse.Namespace, context: CliContext) -> int:
    conn = _open_db(context.config)
    try:
        offer = next(
            (item for item in storage.list_offers(conn) if item.offer_id == args.offer), None
        )
        if offer is None:
            print(
                f"Nie ma oferty {args.offer} w bazie — uruchom najpierw `collect`.",
                file=context.stderr,
            )
            return EXIT_USAGE

        snapshots = storage.get_series(conn, offer.offer_id)
        source = snapshots[0].source if snapshots else "api"
        series = analytics.build_series(
            snapshots, offer_id=offer.offer_id, metric=args.metric, source=source
        )
        now = _now()
        summary = analytics.summarize(series, range_key=args.range_key, now=now)
        if summary.n_points == 0:
            print(
                f"Brak danych w przedziale {args.range_key} — uruchom `collect` "
                "albo wybierz inny zakres.",
                file=context.stderr,
            )
            return EXIT_USAGE

        generator = _build_generator(context.config, no_ai=args.no_ai)
        text = ai_comment.generate_comment(
            summary,
            offer_id=offer.offer_id,
            offer_name=offer.name,
            range_key=args.range_key,
            metric=args.metric,
            generator=generator,
            conn=conn,
            now=now,
        )
    finally:
        conn.close()

    print(text, file=context.stdout)
    return EXIT_OK


def _cmd_report(args: argparse.Namespace, context: CliContext) -> int:
    # Import lokalny (jak `charts`): raport ciągnie matplotlib, a inne komendy nie muszą.
    from view_tracker_ai_1 import report

    conn = _open_db(context.config)
    try:
        available = storage.list_offers(conn)
        wanted = args.offers or []
        selected = [item for item in available if not wanted or item.offer_id in wanted]
        missing = sorted(set(wanted) - {item.offer_id for item in selected})
        if missing:
            print(f"Nie ma ofert: {', '.join(missing)}.", file=context.stderr)
            return EXIT_USAGE
        if not selected:
            print(
                "Baza nie ma ofert — uruchom najpierw `collect`.",
                file=context.stderr,
            )
            return EXIT_USAGE

        series_by_offer = {}
        for offer in selected:
            snapshots = storage.get_series(conn, offer.offer_id)
            source = snapshots[0].source if snapshots else "api"
            series = analytics.build_series(
                snapshots, offer_id=offer.offer_id, metric=args.metric, source=source
            )
            series_by_offer[offer.offer_id] = (offer, series)

        now = _now()
        built = report.build_report(
            conn,
            series_by_offer=series_by_offer,
            env=context.config.env,
            ranges=tuple(args.ranges) if args.ranges else report.DEFAULT_RANGES,
            metric=args.metric,
            generator=_build_generator(context.config, no_ai=args.no_ai),
            now=now,
        )
        target = report.write_report(built, args.out)
    finally:
        conn.close()

    cards = sum(len(offer.cards) for offer in built.offers)
    print(f"Zapisano raport: {target}", file=context.stdout)
    print(
        f"  ofert: {len(built.offers)}, sekcji: {cards}, "
        f"badge: {built.env_label}, dane syntetyczne: {'tak' if built.is_synthetic else 'nie'}",
        file=context.stdout,
    )
    return EXIT_OK


# --- fabryki (podmieniane w testach) ---------------------------------------
def _build_auth(config: Config) -> DeviceFlowAuth:
    return DeviceFlowAuth(config=config)


def _build_client(config: Config) -> AllegroClient:
    return AllegroClient(config=config)


def _build_generator(config: Config, *, no_ai: bool) -> ai_comment.CommentGenerator:
    """Wybierz generator: atrapa przy `--no-ai` albo gdy LLM jest wyłączony w env."""
    if no_ai or config.llm_provider != "anthropic":
        return ai_comment.FakeCommentGenerator()
    api_key, model = config.require_llm()
    return ai_comment.AnthropicCommentGenerator(api_key=api_key, model=model)


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


def _now() -> datetime:
    """Bieżąca chwila — osobna funkcja, żeby testy mogły ją podmienić."""
    return datetime.now(UTC)


if __name__ == "__main__":
    sys.exit(main())
