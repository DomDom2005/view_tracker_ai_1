"""Zapytania agregujące SQL (read-only) — bez logiki UI i bez żądań sieciowych.

Zasada: **nigdy nie sumujemy poziomów liczników w czasie** (licznik to okno kroczące).
Poziomy sumujemy tylko dla jednej chwili; w przedziale sumujemy przyrosty per oferta,
pomijając spadki (SPEC-2.0 §6 FR-12).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from statistics import median

from view_tracker_ai_1.models import Metric, Offer
from view_tracker_ai_1.storage import from_iso, to_iso

METRIC_COLUMNS: dict[Metric, str] = {
    "visits": "visits_count",
    "watchers": "watchers_count",
}


@dataclass(frozen=True, slots=True)
class OfferState:
    """Oferta + stan z bazy (ostatni snapshot, liczba snapshotów)."""

    offer: Offer
    last_captured_at: datetime | None
    visits_count: int | None
    watchers_count: int | None
    snapshots: int


@dataclass(frozen=True, slots=True)
class LevelTotals:
    """Suma poziomów liczników w jednej chwili (nie w czasie!)."""

    at: datetime | None
    offers: int
    visits: int
    watchers: int


@dataclass(frozen=True, slots=True)
class RangeTotals:
    """Sumy przyrostów w przedziale + liczba ofert i spadków."""

    offers: int
    gained: int
    drops: int


@dataclass(frozen=True, slots=True)
class GainRow:
    offer_id: str
    gained: int
    drops: int


@dataclass(frozen=True, slots=True)
class Freshness:
    last_captured_at: datetime | None
    snapshots: int
    offers: int


def data_version(conn: sqlite3.Connection) -> tuple[str | None, int]:
    """Klucz do cache UI: `(max(captured_at), count)` — zmienia się po każdym collect."""
    row = conn.execute("SELECT MAX(captured_at) AS at, COUNT(*) AS n FROM snapshots").fetchone()
    return (None if row["at"] is None else str(row["at"])), int(row["n"])


def freshness(conn: sqlite3.Connection) -> Freshness:
    row = conn.execute(
        "SELECT MAX(captured_at) AS at, COUNT(*) AS n, COUNT(DISTINCT offer_id) AS offers "
        "FROM snapshots"
    ).fetchone()
    at = row["at"]
    return Freshness(
        last_captured_at=None if at is None else from_iso(str(at)),
        snapshots=int(row["n"]),
        offers=int(row["offers"]),
    )


def offers_with_last_snapshot(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
) -> list[OfferState]:
    """Oferty z ostatnim snapshotem (LEFT JOIN — oferta bez danych też ma wiersz)."""
    sql = """
    SELECT o.offer_id, o.name, o.status, o.first_seen_at, o.last_seen_at,
           s.captured_at AS last_captured_at,
           s.visits_count, s.watchers_count,
           (SELECT COUNT(*) FROM snapshots WHERE offer_id = o.offer_id) AS snapshots
    FROM offers o
    LEFT JOIN snapshots s
      ON s.offer_id = o.offer_id
     AND s.captured_at = (SELECT MAX(captured_at) FROM snapshots WHERE offer_id = o.offer_id)
    WHERE (? IS NULL OR o.status = ?)
    ORDER BY o.offer_id
    """
    rows = conn.execute(sql, (status, status)).fetchall()
    return [
        OfferState(
            offer=Offer(
                offer_id=str(row["offer_id"]),
                name=str(row["name"]),
                status=None if row["status"] is None else str(row["status"]),
                first_seen_at=from_iso(str(row["first_seen_at"])),
                last_seen_at=from_iso(str(row["last_seen_at"])),
            ),
            last_captured_at=(
                None if row["last_captured_at"] is None else from_iso(str(row["last_captured_at"]))
            ),
            visits_count=None if row["visits_count"] is None else int(row["visits_count"]),
            watchers_count=(
                None if row["watchers_count"] is None else int(row["watchers_count"])
            ),
            snapshots=int(row["snapshots"]),
        )
        for row in rows
    ]


def level_totals(
    conn: sqlite3.Connection,
    offer_ids: list[str] | None = None,
    *,
    at: datetime | None = None,
) -> LevelTotals:
    """Suma poziomów w jednej chwili: ostatni snapshot każdej oferty (≤ `at`)."""
    where, params = _offer_filter(offer_ids)
    sql = f"""
    WITH ranked AS (
        SELECT offer_id, captured_at, visits_count, watchers_count,
               ROW_NUMBER() OVER (PARTITION BY offer_id ORDER BY captured_at DESC) AS rn
        FROM snapshots
        WHERE (? IS NULL OR captured_at <= ?)
          {where}
    )
    SELECT COUNT(*) AS offers,
           COALESCE(SUM(visits_count), 0) AS visits,
           COALESCE(SUM(watchers_count), 0) AS watchers,
           MAX(captured_at) AS at
    FROM ranked WHERE rn = 1
    """
    boundary = None if at is None else to_iso(at)
    row = conn.execute(sql, (boundary, boundary, *params)).fetchone()
    return LevelTotals(
        at=None if row["at"] is None else from_iso(str(row["at"])),
        offers=int(row["offers"]),
        visits=int(row["visits"]),
        watchers=int(row["watchers"]),
    )


def gains_per_offer(
    conn: sqlite3.Connection,
    *,
    since: datetime | None,
    until: datetime,
    metric: Metric,
) -> list[GainRow]:
    """Przyrosty w przedziale liczone per oferta; spadki nie obniżają sumy."""
    column = METRIC_COLUMNS[metric]
    sql = f"""
    WITH ordered AS (
        SELECT offer_id, captured_at,
               {column} - LAG({column}) OVER (
                   PARTITION BY offer_id ORDER BY captured_at
               ) AS delta
        FROM snapshots
        WHERE captured_at <= ?
    )
    SELECT offer_id,
           COALESCE(SUM(CASE WHEN delta > 0 THEN delta ELSE 0 END), 0) AS gained,
           COALESCE(SUM(CASE WHEN delta < 0 THEN 1 ELSE 0 END), 0) AS drops
    FROM ordered
    WHERE captured_at > ?
    GROUP BY offer_id
    ORDER BY gained DESC, offer_id
    """
    boundary = "" if since is None else to_iso(since)
    rows = conn.execute(sql, (to_iso(until), boundary)).fetchall()
    return [
        GainRow(offer_id=str(row["offer_id"]), gained=int(row["gained"]), drops=int(row["drops"]))
        for row in rows
    ]


def totals_for_range(
    conn: sqlite3.Connection,
    *,
    since: datetime | None,
    until: datetime,
    metric: Metric,
) -> RangeTotals:
    rows = gains_per_offer(conn, since=since, until=until, metric=metric)
    return RangeTotals(
        offers=len(rows),
        gained=sum(row.gained for row in rows),
        drops=sum(row.drops for row in rows),
    )


def median_gain(
    conn: sqlite3.Connection,
    *,
    since: datetime | None,
    until: datetime,
    metric: Metric,
) -> float | None:
    """Mediana przyrostów per oferta — punkt odniesienia dla pojedynczej oferty."""
    rows = gains_per_offer(conn, since=since, until=until, metric=metric)
    if not rows:
        return None
    return float(median(row.gained for row in rows))


def gaps(
    conn: sqlite3.Connection,
    offer_id: str,
    *,
    since: datetime | None,
    max_gap_hours: float = 2.0,
) -> int:
    """Liczba przerw dłuższych niż `max_gap_hours` w szeregu oferty."""
    sql = """
    WITH ordered AS (
        SELECT captured_at,
               LAG(captured_at) OVER (ORDER BY captured_at) AS previous
        FROM snapshots
        WHERE offer_id = ? AND (? IS NULL OR captured_at >= ?)
    )
    SELECT COUNT(*) AS n
    FROM ordered
    WHERE previous IS NOT NULL
      AND (julianday(captured_at) - julianday(previous)) * 24 > ?
    """
    boundary = None if since is None else to_iso(since)
    row = conn.execute(sql, (offer_id, boundary, boundary, max_gap_hours)).fetchone()
    return int(row["n"])


def offer_exists(conn: sqlite3.Connection, offer_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM offers WHERE offer_id = ?", (offer_id,)).fetchone()
    return row is not None


def offers_at(conn: sqlite3.Connection, at: datetime) -> int:
    """Liczba ofert, które mają snapshot dokładnie w chwili `at` (np. jeden przebieg)."""
    row = conn.execute(
        "SELECT COUNT(DISTINCT offer_id) AS n FROM snapshots WHERE captured_at = ?",
        (to_iso(at),),
    ).fetchone()
    return int(row["n"])


def _offer_filter(offer_ids: list[str] | None) -> tuple[str, tuple[object, ...]]:
    if not offer_ids:
        return "", ()
    placeholders = ", ".join("?" for _ in offer_ids)
    return f"AND offer_id IN ({placeholders})", tuple(offer_ids)
