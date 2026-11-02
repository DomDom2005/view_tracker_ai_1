"""Przypadki użycia 2.0 — jedyna warstwa, którą zna UI.

UI (Streamlit) nie importuje `sqlite3`, `storage` ani `client`; woła funkcje stąd.
Dzięki temu logikę da się testować bez przeglądarki, a późniejsza zmiana frameworka
(np. FastAPI) nie rusza analityki.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from statistics import median

from view_tracker_ai_1 import analytics, collector, queries, storage
from view_tracker_ai_1.auth import DeviceAuthorization, DeviceFlowAuth, Tokens, TokenStatus
from view_tracker_ai_1.client import AllegroClient
from view_tracker_ai_1.config import Config
from view_tracker_ai_1.errors import AuthError
from view_tracker_ai_1.models import Metric, Offer, Series, SeriesSummary, Source

RANGE_KEYS: tuple[str, ...] = ("24h", "7d", "30d", "90d", "all")


# --- połączenie -------------------------------------------------------------
def open_database(config: Config) -> sqlite3.Connection:
    """Otwórz bazę i doprowadź schemat do bieżącej wersji (migracja w tle)."""
    conn = storage.connect(config.effective_db_path)
    try:
        storage.init_db(conn)
    except Exception:
        conn.close()
        raise
    return conn


@contextmanager
def database(config: Config) -> Iterator[sqlite3.Connection]:
    """Połączenie na czas jednego widoku UI (Streamlit otwiera je na każdy rerun)."""
    conn = open_database(config)
    try:
        yield conn
    finally:
        conn.close()


# --- oferty -----------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class OfferListItem:
    offer: Offer
    last_captured_at: datetime | None
    visits: int | None
    watchers: int | None
    snapshots: int


def list_offers(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    search: str | None = None,
) -> list[OfferListItem]:
    """Oferty z bazy; `search` filtruje po nazwie i identyfikatorze (bez rozróżniania wielkości)."""
    items = [
        OfferListItem(
            offer=state.offer,
            last_captured_at=state.last_captured_at,
            visits=state.visits_count,
            watchers=state.watchers_count,
            snapshots=state.snapshots,
        )
        for state in queries.offers_with_last_snapshot(conn, status=status)
    ]
    needle = (search or "").strip().casefold()
    if needle:
        items = [
            item
            for item in items
            if needle in item.offer.name.casefold() or needle in item.offer.offer_id.casefold()
        ]
    return items


# --- pojedyncza oferta ------------------------------------------------------
@dataclass(frozen=True, slots=True)
class OfferView:
    offer: Offer
    series: Series
    summary: SeriesSummary
    snapshots: int
    gaps: int
    freshness: queries.Freshness


def offer_view(
    conn: sqlite3.Connection,
    offer_id: str,
    *,
    range_key: str = "30d",
    metric: Metric = "visits",
    now: datetime,
) -> OfferView | None:
    """Seria, podsumowanie i jakość danych jednej oferty (None, gdy oferty nie ma)."""
    state = next(
        (
            item
            for item in queries.offers_with_last_snapshot(conn)
            if item.offer.offer_id == offer_id
        ),
        None,
    )
    if state is None:
        return None

    snapshots = storage.get_series(conn, offer_id)
    source: Source = snapshots[0].source if snapshots else "api"
    series = analytics.build_series(snapshots, offer_id=offer_id, metric=metric, source=source)
    summary = analytics.summarize(series, range_key=range_key, now=now)
    return OfferView(
        offer=state.offer,
        series=series,
        summary=summary,
        snapshots=len(snapshots),
        gaps=queries.gaps(
            conn,
            offer_id,
            since=analytics.window_start(range_key, now),
            max_gap_hours=2.0,
        ),
        freshness=queries.freshness(conn),
    )


# --- przegląd „ogółem” ------------------------------------------------------
@dataclass(frozen=True, slots=True)
class RankRow:
    offer: Offer
    gained: int
    drops: int


@dataclass(frozen=True, slots=True)
class Overview:
    range_key: str
    metric: Metric
    period_start: datetime | None
    period_end: datetime
    levels: queries.LevelTotals
    gains: queries.RangeTotals
    median_gain: float | None
    ranking: tuple[RankRow, ...]
    freshness: queries.Freshness


def overview(
    conn: sqlite3.Connection,
    *,
    offer_ids: Sequence[str] | None = None,
    range_key: str = "30d",
    metric: Metric = "visits",
    now: datetime,
) -> Overview:
    """Kafle „ogółem” + ranking. Poziomy sumujemy dla jednej chwili, przyrosty per oferta."""
    offers_by_id = {
        item.offer.offer_id: item.offer for item in queries.offers_with_last_snapshot(conn)
    }
    selected = [offer_id for offer_id in offers_by_id if not offer_ids or offer_id in offer_ids]

    since = analytics.window_start(range_key, now)
    gains = [
        row
        for row in queries.gains_per_offer(conn, since=since, until=now, metric=metric)
        if not offer_ids or row.offer_id in offer_ids
    ]
    gains_sorted = sorted(gains, key=lambda row: (-row.gained, row.offer_id))
    medians = [row.gained for row in gains]

    return Overview(
        range_key=range_key,
        metric=metric,
        period_start=since,
        period_end=now,
        levels=queries.level_totals(conn, selected or None, at=now),
        gains=queries.RangeTotals(
            offers=len(gains),
            gained=sum(row.gained for row in gains),
            drops=sum(row.drops for row in gains),
        ),
        median_gain=(None if not medians else float(median(medians))),
        ranking=tuple(
            RankRow(offer=offers_by_id[row.offer_id], gained=row.gained, drops=row.drops)
            for row in gains_sorted
            if row.offer_id in offers_by_id
        ),
        freshness=queries.freshness(conn),
    )


# --- porównania -------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PeriodComparison:
    range_key: str
    metric: Metric
    current: queries.RangeTotals
    previous: queries.RangeTotals
    change_pct: float | None


def compare_periods(
    conn: sqlite3.Connection,
    *,
    range_key: str = "7d",
    metric: Metric = "visits",
    now: datetime,
    offer_id: str | None = None,
) -> PeriodComparison:
    """Bieżący okres vs poprzedni tej samej długości. Dla `all` porównanie nie istnieje."""
    duration = analytics.range_duration(range_key)
    current = _range_totals(conn, since=now - duration if duration else None, until=now,
                            metric=metric, offer_id=offer_id)
    if duration is None:
        return PeriodComparison(
            range_key=range_key,
            metric=metric,
            current=current,
            previous=queries.RangeTotals(offers=0, gained=0, drops=0),
            change_pct=None,
        )

    previous_start = now - 2 * duration
    previous = _range_totals(
        conn, since=previous_start, until=now - duration, metric=metric, offer_id=offer_id
    )
    change = None
    if previous.gained > 0:
        change = (current.gained - previous.gained) / previous.gained
    return PeriodComparison(
        range_key=range_key,
        metric=metric,
        current=current,
        previous=previous,
        change_pct=change,
    )


@dataclass(frozen=True, slots=True)
class OfferSeries:
    offer: Offer
    series: Series


def compare_offers(
    conn: sqlite3.Connection,
    offer_ids: Sequence[str],
    *,
    range_key: str = "30d",
    metric: Metric = "visits",
) -> tuple[OfferSeries, ...]:
    """Serie do wykresu porównawczego (UI normalizuje je do indeksu 100)."""
    offers_by_id = {
        item.offer.offer_id: item.offer for item in queries.offers_with_last_snapshot(conn)
    }
    result: list[OfferSeries] = []
    for offer_id in offer_ids:
        offer = offers_by_id.get(offer_id)
        if offer is None:
            continue
        snapshots = storage.get_series(conn, offer_id)
        source: Source = snapshots[0].source if snapshots else "api"
        result.append(
            OfferSeries(
                offer=offer,
                series=analytics.build_series(
                    snapshots, offer_id=offer_id, metric=metric, source=source
                ),
            )
        )
    return tuple(result)


# --- kolektor ---------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class RefreshResult:
    run_id: int
    offers: int
    inserted: int
    started_at: datetime
    finished_at: datetime


def refresh_once(
    config: Config,
    conn: sqlite3.Connection,
    *,
    statuses: Sequence[str] = collector.DEFAULT_STATUSES,
    client: AllegroClient | None = None,
    now: datetime | None = None,
) -> RefreshResult:
    """Jeden przebieg kolektora z wpisem w `collect_runs` (także przy błędzie)."""
    started = now if now is not None else datetime.now(UTC)
    run_id = storage.start_collect_run(conn, started_at=started)
    try:
        inserted = collector.run_once(
            client if client is not None else AllegroClient(config=config),
            conn,
            statuses=statuses,
            captured_at=started,
        )
    except AuthError as exc:
        storage.finish_collect_run(
            conn,
            run_id,
            finished_at=datetime.now(UTC),
            status="auth_error",
            error_message=str(exc),
        )
        raise
    except Exception as exc:  # noqa: BLE001 - każdy błąd przebiegu ma trafić do collect_runs
        storage.finish_collect_run(
            conn,
            run_id,
            finished_at=datetime.now(UTC),
            status="error",
            error_message=str(exc),
        )
        raise

    finished = datetime.now(UTC)
    storage.finish_collect_run(
        conn,
        run_id,
        finished_at=finished,
        status="ok",
        offers_count=queries.offers_at(conn, started),
        inserted=inserted,
    )
    return RefreshResult(
        run_id=run_id,
        offers=queries.offers_at(conn, started),
        inserted=inserted,
        started_at=started,
        finished_at=finished,
    )


@dataclass(frozen=True, slots=True)
class CollectorState:
    freshness: queries.Freshness
    runs: tuple[dict[str, object], ...]


def collector_state(conn: sqlite3.Connection, *, limit: int = 10) -> CollectorState:
    """Stan kolektora dla ekranu „Dane”: świeżość + ostatnie przebiegi."""
    return CollectorState(
        freshness=queries.freshness(conn),
        runs=tuple(storage.recent_collect_runs(conn, limit=limit)),
    )


# --- uwierzytelnianie -------------------------------------------------------
def build_auth(config: Config) -> DeviceFlowAuth:
    return DeviceFlowAuth(config=config)


def token_status(config: Config) -> TokenStatus:
    return build_auth(config).status()


def begin_login(config: Config) -> tuple[DeviceFlowAuth, DeviceAuthorization]:
    """Start device flow; UI pokazuje kod i odpytuje `complete_login` co `interval`."""
    auth = build_auth(config)
    return auth, auth.start()


def complete_login(auth: DeviceFlowAuth, authorization: DeviceAuthorization) -> Tokens:
    return auth.poll(authorization)


def data_version(conn: sqlite3.Connection) -> tuple[str | None, int]:
    """Klucz cache UI — zmienia się po każdym przebiegu kolektora."""
    return queries.data_version(conn)


# --- pomocnicze -------------------------------------------------------------
def _range_totals(
    conn: sqlite3.Connection,
    *,
    since: datetime | None,
    until: datetime,
    metric: Metric,
    offer_id: str | None,
) -> queries.RangeTotals:
    rows = queries.gains_per_offer(
        conn,
        since=since,
        until=until,
        metric=metric,
    )
    if offer_id is not None:
        rows = [row for row in rows if row.offer_id == offer_id]
    return queries.RangeTotals(
        offers=len(rows),
        gained=sum(row.gained for row in rows),
        drops=sum(row.drops for row in rows),
    )


def previous_period(range_key: str, now: datetime) -> tuple[datetime, datetime] | None:
    """Granice poprzedniego okresu (dla UI); `None` dla zakresu `all`."""
    duration = analytics.range_duration(range_key)
    if duration is None:
        return None
    return now - 2 * duration, now - duration


__all__ = [
    "RANGE_KEYS",
    "CollectorState",
    "OfferListItem",
    "OfferSeries",
    "OfferView",
    "Overview",
    "PeriodComparison",
    "RankRow",
    "RefreshResult",
    "begin_login",
    "build_auth",
    "collector_state",
    "compare_offers",
    "compare_periods",
    "complete_login",
    "data_version",
    "database",
    "list_offers",
    "offer_view",
    "open_database",
    "overview",
    "previous_period",
    "refresh_once",
    "token_status",
]
