"""SQLite: schemat (SPEC-2.0 §7), migracje i zapytania.

Warstwa bez żądań sieciowych. Czasy trzymamy w UTC jako ISO 8601; prezentacja
w `Europe/Warsaw` należy do `text.py` / UI (SPEC §6 NFR-3).

Wersja 2.0 dodaje tabele `collect_runs`, `offer_events`, `annotations`, `alert_rules`
i `app_state` oraz usuwa `ai_comments` (AI wycofane — SPEC-2.0 §10).
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from view_tracker_ai_1.errors import StorageError
from view_tracker_ai_1.models import Offer, Snapshot, Source

SCHEMA_VERSION = 2
MEMORY_DB = ":memory:"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS offers (
  offer_id      TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  status        TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  offer_id       TEXT NOT NULL REFERENCES offers(offer_id),
  captured_at    TEXT NOT NULL,
  visits_count   INTEGER NOT NULL CHECK (visits_count >= 0),
  watchers_count INTEGER NOT NULL CHECK (watchers_count >= 0),
  source         TEXT NOT NULL CHECK (source IN ('api','synthetic')),
  UNIQUE (offer_id, captured_at)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_offer_time ON snapshots (offer_id, captured_at);

CREATE TABLE IF NOT EXISTS actions_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  offer_id TEXT NOT NULL,
  action TEXT NOT NULL,
  request_json TEXT NOT NULL,
  response_status INTEGER,
  response_summary TEXT
);

-- 2.0: przebiegi kolektora (FR-5/FR-6, ekran „Dane”)
CREATE TABLE IF NOT EXISTS collect_runs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at    TEXT NOT NULL,
  finished_at   TEXT,
  status        TEXT NOT NULL CHECK (status IN ('running','ok','error','auth_error')),
  offers_count  INTEGER NOT NULL DEFAULT 0,
  inserted      INTEGER NOT NULL DEFAULT 0,
  error_message TEXT
);

-- 2.0: zdarzenia ofert z API (FR-15); bez FK — event może dotyczyć oferty spoza listy
CREATE TABLE IF NOT EXISTS offer_events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  offer_id     TEXT NOT NULL,
  occurred_at  TEXT NOT NULL,
  type         TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  fetched_at   TEXT NOT NULL,
  UNIQUE (offer_id, occurred_at, type)
);
CREATE INDEX IF NOT EXISTS idx_offer_events_offer_time ON offer_events (offer_id, occurred_at);

-- 2.0: adnotacje ręczne (FR-15)
CREATE TABLE IF NOT EXISTS annotations (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  offer_id    TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  label       TEXT NOT NULL,
  note        TEXT,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_annotations_offer_time ON annotations (offer_id, occurred_at);

-- 2.0: reguły alertów progowych (FR-16)
CREATE TABLE IF NOT EXISTS alert_rules (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  offer_id    TEXT,
  kind        TEXT NOT NULL CHECK (kind IN ('pct_drop','abs_drop')),
  threshold   REAL NOT NULL,
  window_days INTEGER NOT NULL CHECK (window_days > 0),
  created_at  TEXT NOT NULL
);

-- 2.0: trwały stan UI (np. interwał trybu ciągłego, znacznik ostatniej wizyty)
CREATE TABLE IF NOT EXISTS app_state (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

_INSERT_SNAPSHOT_SQL = """
INSERT INTO snapshots (offer_id, captured_at, visits_count, watchers_count, source)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(offer_id, captured_at) DO NOTHING
"""


# --- połączenie i schemat ---------------------------------------------------
def connect(db_path: str | Path) -> sqlite3.Connection:
    """Otwórz połączenie; dla ścieżki plikowej utwórz katalog nadrzędny."""
    target = str(db_path)
    if target != MEMORY_DB:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # 2.0: UI czyta, a wątek kolektora pisze — WAL i ograniczony czas oczekiwania.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(conn: sqlite3.Connection) -> int:
    """Utwórz lub zmigruj schemat do bieżącej wersji (idempotentnie)."""
    version = schema_version(conn)
    if version is None:
        conn.executescript(SCHEMA_SQL)
        with conn:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        return SCHEMA_VERSION

    if version == SCHEMA_VERSION:
        # Dociągnij brakujące tabele (np. gdy plik powstał częściowo) bez ruszania danych.
        conn.executescript(SCHEMA_SQL)
        return SCHEMA_VERSION

    if version == 1:
        return migrate_v1_to_v2(conn)

    raise StorageError(
        f"Nieobsługiwana wersja schematu: {version} (oczekiwana {SCHEMA_VERSION}). "
        "Zaktualizuj aplikację albo użyj nowej bazy."
    )


def migrate_v1_to_v2(conn: sqlite3.Connection) -> int:
    """Migracja schematu 1 → 2: nowe tabele, `DROP ai_comments`, kopia zapasowa pliku.

    Migracja jest jednokierunkowa: po niej baza nie otworzy się w aplikacji 1.0.
    """
    backup = _backup_database(conn)
    try:
        conn.executescript(SCHEMA_SQL)
        with conn:
            conn.execute("DROP TABLE IF EXISTS ai_comments")
            conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
    except sqlite3.Error as exc:
        where = "" if backup is None else f" Kopia sprzed migracji: {backup}."
        raise StorageError(
            f"Migracja bazy do wersji {SCHEMA_VERSION} nie powiodła się.{where}"
        ) from exc
    return SCHEMA_VERSION


def _backup_database(conn: sqlite3.Connection) -> Path | None:
    """Kopia pliku bazy przed migracją; dla bazy w pamięci nic nie robi."""
    path = _database_path(conn)
    if path is None or not path.exists():
        return None
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, target)
    return target


def _database_path(conn: sqlite3.Connection) -> Path | None:
    for row in conn.execute("PRAGMA database_list"):
        if row[1] == "main" and row[2]:
            return Path(row[2])
    return None


def schema_version(conn: sqlite3.Connection) -> int | None:
    """Wersja schematu zapisana w bazie (None dla pustej bazy)."""
    try:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
    except sqlite3.OperationalError:  # brak tabeli = baza jeszcze nie zainicjalizowana
        return None
    return None if row is None else int(row["version"])


# --- zapis ------------------------------------------------------------------
_UPSERT_OFFER_SQL = """
INSERT INTO offers (offer_id, name, status, first_seen_at, last_seen_at)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(offer_id) DO UPDATE SET
    name = excluded.name,
    status = excluded.status,
    last_seen_at = excluded.last_seen_at
"""


def upsert_offer(conn: sqlite3.Connection, offer: Offer) -> None:
    """Dodaj ofertę albo odśwież jej metadane (bez zmiany `first_seen_at`)."""
    try:
        with conn:
            conn.execute(_UPSERT_OFFER_SQL, _offer_params(offer))
    except sqlite3.IntegrityError as exc:
        raise StorageError(f"Nie udało się zapisać oferty {offer.offer_id}: {exc}") from exc


def insert_snapshots(conn: sqlite3.Connection, snapshots: Iterable[Snapshot]) -> int:
    """Zapisz snapshoty w jednej transakcji. Zwraca liczbę faktycznie dodanych wierszy."""
    rows = [_snapshot_params(snapshot) for snapshot in snapshots]
    if not rows:
        return 0

    before = conn.total_changes
    try:
        with conn:
            conn.executemany(_INSERT_SNAPSHOT_SQL, rows)
    except sqlite3.IntegrityError as exc:
        raise StorageError(_integrity_message(exc)) from exc
    return conn.total_changes - before


def save_collection(
    conn: sqlite3.Connection,
    *,
    offers: Iterable[Offer],
    snapshots: Iterable[Snapshot],
) -> int:
    """Zapisz oferty i snapshoty **w jednej transakcji** (przebieg kolektora).

    Zwraca liczbę faktycznie dodanych snapshotów; powtórzony przebieg z tym samym
    `captured_at` doda zero wierszy (UNIQUE + `ON CONFLICT DO NOTHING`).
    """
    offer_params = [_offer_params(offer) for offer in offers]
    snapshot_params = [_snapshot_params(snapshot) for snapshot in snapshots]
    if not offer_params and not snapshot_params:
        return 0

    try:
        with conn:
            if offer_params:
                conn.executemany(_UPSERT_OFFER_SQL, offer_params)
            # Liczymy tylko snapshoty — upserty ofert nie są „nowymi snapshotami”.
            before_snapshots = conn.total_changes
            if snapshot_params:
                conn.executemany(_INSERT_SNAPSHOT_SQL, snapshot_params)
    except sqlite3.IntegrityError as exc:
        raise StorageError(_integrity_message(exc)) from exc
    return conn.total_changes - before_snapshots


def start_collect_run(conn: sqlite3.Connection, *, started_at: datetime) -> int:
    """Zapisz rozpoczęcie przebiegu kolektora (FR-5/FR-6); zwraca `id` przebiegu."""
    with conn:
        cursor = conn.execute(
            "INSERT INTO collect_runs (started_at, status) VALUES (?, 'running')",
            (to_iso(started_at),),
        )
    return int(cursor.lastrowid or 0)


def finish_collect_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    finished_at: datetime,
    status: str,
    offers_count: int = 0,
    inserted: int = 0,
    error_message: str | None = None,
) -> None:
    """Domknij wpis przebiegu (`ok`/`error`/`auth_error`)."""
    with conn:
        conn.execute(
            """
            UPDATE collect_runs
               SET finished_at = ?, status = ?, offers_count = ?, inserted = ?,
                   error_message = ?
             WHERE id = ?
            """,
            (to_iso(finished_at), status, offers_count, inserted, error_message, run_id),
        )


def recent_collect_runs(
    conn: sqlite3.Connection, *, limit: int = 10
) -> list[dict[str, object]]:
    """Ostatnie przebiegi kolektora (najnowsze pierwsze)."""
    rows = conn.execute(
        "SELECT * FROM collect_runs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(row) for row in rows]


def get_state(conn: sqlite3.Connection, key: str) -> str | None:
    """Trwały stan UI (np. interwał trybu ciągłego, znacznik ostatniej wizyty)."""
    row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row["value"])


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO app_state (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def log_action(
    conn: sqlite3.Connection,
    *,
    ts: datetime,
    offer_id: str,
    action: str,
    request_json: str,
    response_status: int | None = None,
    response_summary: str | None = None,
) -> int:
    """Zapisz wykonaną akcję (faza 3) — bez sekretów w `request_json`."""
    sql = """
    INSERT INTO actions_log
        (ts, offer_id, action, request_json, response_status, response_summary)
    VALUES (?, ?, ?, ?, ?, ?)
    """
    with conn:
        cursor = conn.execute(
            sql,
            (to_iso(ts), offer_id, action, request_json, response_status, response_summary),
        )
    return int(cursor.lastrowid or 0)


# --- odczyt -----------------------------------------------------------------
def get_series(
    conn: sqlite3.Connection,
    offer_id: str,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    source: Source | None = None,
) -> list[Snapshot]:
    """Snapshoty oferty w przedziale czasu, posortowane rosnąco."""
    sql = "SELECT * FROM snapshots WHERE offer_id = ?"
    params: list[object] = [offer_id]
    if since is not None:
        sql += " AND captured_at >= ?"
        params.append(to_iso(since))
    if until is not None:
        sql += " AND captured_at <= ?"
        params.append(to_iso(until))
    if source is not None:
        sql += " AND source = ?"
        params.append(source)
    sql += " ORDER BY captured_at"

    return [_row_to_snapshot(row) for row in conn.execute(sql, params)]


def list_offers(conn: sqlite3.Connection, *, status: str | None = None) -> list[Offer]:
    """Oferty z bazy (opcjonalnie filtrowane po statusie)."""
    sql = "SELECT * FROM offers"
    params: list[object] = []
    if status is not None:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY offer_id"
    return [_row_to_offer(row) for row in conn.execute(sql, params)]


def get_last_snapshot(
    conn: sqlite3.Connection,
    offer_id: str,
    *,
    source: Source | None = None,
) -> Snapshot | None:
    """Najnowszy snapshot oferty albo `None`."""
    sql = "SELECT * FROM snapshots WHERE offer_id = ?"
    params: list[object] = [offer_id]
    if source is not None:
        sql += " AND source = ?"
        params.append(source)
    sql += " ORDER BY captured_at DESC LIMIT 1"
    row = conn.execute(sql, params).fetchone()
    return None if row is None else _row_to_snapshot(row)


def count_snapshots(conn: sqlite3.Connection, *, offer_id: str | None = None) -> int:
    """Liczba snapshotów (łącznie albo dla jednej oferty)."""
    if offer_id is None:
        row = conn.execute("SELECT COUNT(*) AS n FROM snapshots").fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM snapshots WHERE offer_id = ?", (offer_id,)
        ).fetchone()
    return int(row["n"])


# --- czas -------------------------------------------------------------------
def to_iso(value: datetime) -> str:
    """Znormalizuj czas do UTC i zapisz jako ISO 8601."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def from_iso(value: str) -> datetime:
    """Odczytaj ISO 8601; brak strefy interpretujemy jako UTC."""
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


# --- pomocnicze -------------------------------------------------------------
def _row_to_offer(row: sqlite3.Row) -> Offer:
    return Offer(
        offer_id=str(row["offer_id"]),
        name=str(row["name"]),
        status=None if row["status"] is None else str(row["status"]),
        first_seen_at=from_iso(str(row["first_seen_at"])),
        last_seen_at=from_iso(str(row["last_seen_at"])),
    )


def _row_to_snapshot(row: sqlite3.Row) -> Snapshot:
    return Snapshot(
        offer_id=str(row["offer_id"]),
        captured_at=from_iso(str(row["captured_at"])),
        visits_count=int(row["visits_count"]),
        watchers_count=int(row["watchers_count"]),
        source=str(row["source"]),  # type: ignore[arg-type]
    )


def _offer_params(offer: Offer) -> tuple[object, ...]:
    return (
        offer.offer_id,
        offer.name,
        offer.status,
        to_iso(offer.first_seen_at),
        to_iso(offer.last_seen_at),
    )


def _snapshot_params(snapshot: Snapshot) -> tuple[object, ...]:
    return (
        snapshot.offer_id,
        to_iso(snapshot.captured_at),
        snapshot.visits_count,
        snapshot.watchers_count,
        snapshot.source,
    )


def _integrity_message(exc: sqlite3.IntegrityError) -> str:
    message = str(exc)
    if "FOREIGN KEY" in message.upper():
        return (
            "Snapshot wskazuje ofertę, której nie ma w bazie — najpierw zapisz ofertę "
            "(upsert_offer) w tej samej transakcji."
        )
    if "CHECK" in message.upper():
        return "Liczniki nie mogą być ujemne, a źródło musi być 'api' albo 'synthetic'."
    return f"Baza odrzuciła zapis: {message}"
