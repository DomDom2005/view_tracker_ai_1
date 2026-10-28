"""Testy CLI: `--help`, kody wyjścia i komendy na podmienionych fabrykach (SPEC §8)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from view_tracker_ai_1 import cli, storage
from view_tracker_ai_1 import config as config_module
from view_tracker_ai_1.auth import DeviceAuthorization, Tokens, TokenStatus
from view_tracker_ai_1.client import RemoteOffer
from view_tracker_ai_1.errors import ApiError, AuthError, StorageError
from view_tracker_ai_1.models import Offer, Snapshot

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
ENVIRONMENT = (
    "ALLEGRO_ENV",
    "ALLEGRO_CLIENT_ID",
    "ALLEGRO_CLIENT_SECRET",
    "ALLEGRO_USER_AGENT",
    "DB_PATH",
    "LLM_PROVIDER",
    "LOG_LEVEL",
    "ALLOW_PROD_WRITES",
    "ANTHROPIC_API_KEY",
    "TOKEN_STORE_PATH",
)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Czyste env i brak `.env`, żeby lokalny plik nie wpływał na wyniki testów."""
    for name in ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config_module, "load_dotenv", lambda *args, **kwargs: False)


class FakeAuth:
    def __init__(
        self,
        *,
        status: TokenStatus | None = None,
        login_error: Exception | None = None,
    ) -> None:
        self._status = status if status is not None else TokenStatus(logged_in=False)
        self.login_error = login_error
        self.login_calls = 0

    def status(self) -> TokenStatus:
        return self._status

    def login(self, *, announce=None, scope=None):  # noqa: ANN001, ANN201 - stub
        self.login_calls += 1
        authorization = DeviceAuthorization(
            device_code="device-code-secret",
            user_code="ABC-123",
            verification_uri="https://allegro.pl/skojarz-aplikacje",
            expires_in=600,
            interval=5,
            verification_uri_complete="https://allegro.pl/skojarz-aplikacje?code=ABC-123",
        )
        if announce is not None:
            announce(authorization)
        return Tokens(
            access_token="access-secret",
            refresh_token="refresh-secret",
            expires_at=NOW + timedelta(hours=12),
        )


class FakeClient:
    def __init__(
        self,
        offers: tuple[RemoteOffer, ...] = (),
        *,
        error: Exception | None = None,
        config: object | None = None,
    ) -> None:
        self.offers = offers
        self.error = error
        self.config = config
        self.calls = 0

    def iter_offers(self, *, statuses, limit):  # noqa: ANN001, ANN202 - stub
        self.calls += 1
        if self.error is not None:
            raise self.error
        yield from self.offers


def offer(offer_id: str, name: str, status: str = "ACTIVE") -> Offer:
    return Offer(
        offer_id=offer_id,
        name=name,
        status=status,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )


def snapshot(offer_id: str) -> Snapshot:
    return Snapshot(
        offer_id=offer_id,
        captured_at=NOW,
        visits_count=10,
        watchers_count=1,
    )


def prepare_db(path: Path) -> None:
    conn = storage.connect(path)
    storage.init_db(conn)
    storage.save_collection(
        conn,
        offers=[offer("1", "Suszarka"), offer("2", "Lokówka")],
        snapshots=[snapshot("1"), snapshot("2")],
    )
    conn.close()


# --- parser ------------------------------------------------------------------
@pytest.mark.parametrize(
    "argv",
    [
        ["--help"],
        ["auth", "--help"],
        ["auth", "login", "--help"],
        ["auth", "status", "--help"],
        ["offers", "--help"],
        ["offers", "list", "--help"],
        ["collect", "--help"],
    ],
)
def test_help_exits_zero(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(argv)

    assert exc_info.value.code == 0
    assert "usage" in capsys.readouterr().out


def test_unknown_command_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["nie-ma-takiej-komendy"])

    assert exc_info.value.code == cli.EXIT_USAGE
    assert "błąd" in capsys.readouterr().err


def test_version_prints_name(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--version"])

    assert exc_info.value.code == 0
    assert "view_tracker_ai_1" in capsys.readouterr().out


# --- auth --------------------------------------------------------------------
def test_auth_status_when_logged_out(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "_build_auth", lambda config: FakeAuth())

    assert cli.main(["auth", "status"]) == cli.EXIT_OK
    assert "Brak zalogowania" in capsys.readouterr().out


def test_auth_status_shows_expiry(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    status = TokenStatus(
        logged_in=True, expires_at=NOW + timedelta(hours=3), scope="allegro:api:sale:offers:read"
    )
    monkeypatch.setattr(cli, "_build_auth", lambda config: FakeAuth(status=status))

    assert cli.main(["auth", "status"]) == cli.EXIT_OK
    output = capsys.readouterr().out
    assert "ważny" in output
    assert "2026-10-28" in output
    assert "allegro:api:sale:offers:read" in output


def test_auth_login_prints_code_but_not_tokens(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeAuth()
    monkeypatch.setattr(cli, "_build_auth", lambda config: fake)

    assert cli.main(["auth", "login"]) == cli.EXIT_OK

    output = capsys.readouterr().out
    assert fake.login_calls == 1
    assert "ABC-123" in output
    assert "https://allegro.pl/skojarz-aplikacje" in output
    assert "access-secret" not in output
    assert "refresh-secret" not in output


# --- offers list -------------------------------------------------------------
def test_offers_list_on_empty_database(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "pusta.db"

    assert cli.main(["offers", "list", "--db", str(db_path)]) == cli.EXIT_OK
    assert "collect" in capsys.readouterr().out


def test_offers_list_prints_saved_offers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "dane.db"
    prepare_db(db_path)

    assert cli.main(["offers", "list", "--db", str(db_path)]) == cli.EXIT_OK

    output = capsys.readouterr().out
    assert "Suszarka" in output
    assert "1 " in output or "1" in output
    assert "2026-10-28" in output


def test_offers_list_filters_by_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "statusy.db"
    prepare_db(db_path)
    conn = storage.connect(db_path)
    storage.save_collection(conn, offers=[offer("3", "Zakończona", status="ENDED")], snapshots=[])
    conn.close()

    cli.main(["offers", "list", "--db", str(db_path), "--status", "ENDED"])

    output = capsys.readouterr().out
    assert "Zakończona" in output
    assert "Suszarka" not in output


# --- collect -----------------------------------------------------------------
def test_collect_saves_snapshots_and_list_reads_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "collect.db"
    remote = (
        RemoteOffer(
            offer_id="1", name="Suszarka", status="ACTIVE", visits_count=54, watchers_count=3
        ),
        RemoteOffer(
            offer_id="2", name="Lokówka", status="ACTIVE", visits_count=12, watchers_count=1
        ),
    )
    monkeypatch.setattr(cli, "_build_client", lambda config: FakeClient(remote))

    assert cli.main(["collect", "--db", str(db_path)]) == cli.EXIT_OK
    assert "Zapisano 2 nowych snapshotów" in capsys.readouterr().out

    assert cli.main(["offers", "list", "--db", str(db_path)]) == cli.EXIT_OK
    assert "Suszarka" in capsys.readouterr().out


def test_collect_rejects_short_loop_interval(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "loop.db"

    assert cli.main(["collect", "--loop", "--interval", "60", "--db", str(db_path)]) == (
        cli.EXIT_USAGE
    )
    assert "Minimalny interwał" in capsys.readouterr().err
    assert not db_path.exists()


def test_collect_maps_auth_error_to_exit_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cli, "_build_client", lambda config: FakeClient(error=AuthError("wygasł token"))
    )

    code = cli.main(["collect", "--db", str(tmp_path / "auth.db")])

    assert code == cli.EXIT_AUTH
    assert "Błąd autoryzacji" in capsys.readouterr().err


def test_collect_maps_api_error_to_exit_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cli, "_build_client", lambda config: FakeClient(error=ApiError("awaria", status=500))
    )

    code = cli.main(["collect", "--db", str(tmp_path / "api.db")])

    assert code == cli.EXIT_API
    assert "Błąd API" in capsys.readouterr().err


def test_storage_error_maps_to_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "stara.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(storage.SCHEMA_SQL)
    conn.execute("INSERT INTO schema_version (version) VALUES (99)")
    conn.commit()
    conn.close()

    assert cli.main(["offers", "list", "--db", str(db_path)]) == cli.EXIT_USAGE
    assert "Błąd bazy danych" in capsys.readouterr().err


def test_open_db_closes_the_connection_when_init_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wyjątek z `init_db` nie może zostawić otwartego połączenia (ResourceWarning)."""

    class TrackingConnection:
        closed = False

        def close(self) -> None:
            self.closed = True

    conn = TrackingConnection()
    monkeypatch.setattr(cli.storage, "connect", lambda path: conn)

    def failing_init(_conn: object) -> int:
        raise StorageError("nieobsługiwana wersja schematu")

    monkeypatch.setattr(cli.storage, "init_db", failing_init)

    with pytest.raises(StorageError):
        cli._open_db(config_module.Config.from_env())

    assert conn.closed is True


def test_config_error_maps_to_exit_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ALLEGRO_ENV", "staging")

    assert cli.main(["offers", "list"]) == cli.EXIT_USAGE
    assert "Błąd konfiguracji" in capsys.readouterr().err


def test_env_option_overrides_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[object] = []

    def build(config):  # noqa: ANN001, ANN202 - przechwytuje konfigurację
        captured.append(config)
        return FakeClient(config=config)

    monkeypatch.setattr(cli, "_build_client", build)

    assert cli.main(["collect", "--env", "prod", "--db", str(tmp_path / "prod.db")]) == (
        cli.EXIT_OK
    )
    config = captured[0]
    assert config.env == "prod"  # type: ignore[attr-defined]
    assert config.api_base_url == "https://api.allegro.pl"  # type: ignore[attr-defined]


def test_verbose_switches_logging_to_debug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[object] = []

    def build(config):  # noqa: ANN001, ANN202 - przechwytuje konfigurację
        captured.append(config)
        return FakeClient(config=config)

    monkeypatch.setattr(cli, "_build_client", build)

    cli.main(["-v", "collect", "--db", str(tmp_path / "debug.db")])

    assert captured[0].log_level == "DEBUG"  # type: ignore[attr-defined]


def test_ctrl_c_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def interrupt(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202 - stub
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.collector, "run_forever", interrupt)

    assert cli.main(["collect", "--loop", "--db", str(tmp_path / "ctrl-c.db")]) == cli.EXIT_OK
    assert "Przerwano" in capsys.readouterr().err
