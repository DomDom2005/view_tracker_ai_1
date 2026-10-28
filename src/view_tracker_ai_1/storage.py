"""SQLite: schemat (SPEC §7), idempotentna inicjalizacja i zapytania.

Warstwa bez żądań sieciowych (SPEC §5). Czasy trzymamy w UTC jako ISO 8601;
prezentacja w `Europe/Warsaw` należy do analityki i raportu (SPEC §6 NFR-3).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from view_tracker_ai_1.errors import StorageError
from view_tracker_ai_1.models import Metric, Offer, Snapshot, Source

SCHEMA_VERSION = 1
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

CREATE TABLE IF NOT EXISTS ai_comments (
  offer_id   TEXT NOT NULL,
  range_key  TEXT NOT NULL,
  metric     TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  text       TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (offer_id, range_key, metric, input_hash)
);

CREATE TABLE IF NOT EXISTS actions_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  offer_id TEXT NOT NULL,
  action TEXT NOT NULL,
  request_json TEXT NOT NULL,
  response_status INTEGER,
  response_summary TEXT
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
    return conn


def init_db(conn: sqlite3.Connection) -> int:
    """Utwórz schemat (idempotentnie) i ustaw wersję. Zwraca wersję schematu."""
    conn.executescript(SCHEMA_SQL)
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None:
        with conn:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        return SCHEMA_VERSION

    version = int(row["version"])
    if version != SCHEMA_VERSION:
        raise StorageError(
            f"Nieobsługiwana wersja schematu: {version} (oczekiwana {SCHEMA_VERSION}). "
            "Zaktualizuj aplikację albo użyj nowej bazy."
        )
    return version


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


def put_cached_comment(
    conn: sqlite3.Connection,
    *,
    offer_id: str,
    range_key: str,
    metric: Metric,
    input_hash: str,
    text: str,
    created_at: datetime,
) -> None:
    """Zapisz komentarz AI w cache (klucz: hash wejścia do modelu)."""
    sql = """
    INSERT INTO ai_comments (offer_id, range_key, metric, input_hash, text, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(offer_id, range_key, metric, input_hash) DO UPDATE SET
        text = excluded.text,
        created_at = excluded.created_at
    """
    with conn:
        conn.execute(sql, (offer_id, range_key, metric, input_hash, text, to_iso(created_at)))


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


def get_cached_comment(
    conn: sqlite3.Connection,
    *,
    offer_id: str,
    range_key: str,
    metric: Metric,
    input_hash: str,
) -> str | None:
    """Komentarz AI z cache albo `None` przy pudle."""
    row = conn.execute(
        """
        SELECT text FROM ai_comments
        WHERE offer_id = ? AND range_key = ? AND metric = ? AND input_hash = ?
        """,
        (offer_id, range_key, metric, input_hash),
    ).fetchone()
    return None if row is None else str(row["text"])


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
