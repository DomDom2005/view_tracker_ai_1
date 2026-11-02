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

from view_tracker_ai_1 import analytics, collector, demo, events, queries, storage
from view_tracker_ai_1.auth import DeviceAuthorization, DeviceFlowAuth, Tokens, TokenStatus
from view_tracker_ai_1.client import AllegroClient
from view_tracker_ai_1.config import Config
from view_tracker_ai_1.errors import AuthError
from view_tracker_ai_1.models import (
    AlertRule,
    Annotation,
    DailyGain,
    Metric,
    Offer,
    OfferEvent,
    Series,
    SeriesPoint,
    SeriesSummary,
    Source,
)

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
OFFER_SORT_CHOICES: tuple[str, ...] = ("recent", "gain", "name")


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


@dataclass(frozen=True, slots=True)
class OfferCatalogRow:
    """Wiersz listy ofert: dane oferty + przyrost w bieżącym zakresie."""

    item: OfferListItem
    gained: int


def offer_catalog(
    conn: sqlite3.Connection,
    *,
    search: str = "",
    status: str = "all",
    sort: str = "recent",
    range_key: str = "30d",
    metric: Metric = "visits",
    now: datetime,
) -> tuple[OfferCatalogRow, ...]:
    """Lista ofert z filtrami i sortowaniem (FR-7).

    `status="all"` oznacza brak filtra; sortowanie: `recent` (ostatni snapshot),
    `gain` (przyrost w bieżącym oknie) albo `name`.
    """
    chosen_status = None if status in ("", "all") else status
    items = list_offers(conn, status=chosen_status, search=search)
    effective_range = range_key if range_key in analytics.RANGE_KEYS else "30d"
    since = analytics.window_start(effective_range, now)
    gains = {
        row.offer_id: row.gained
        for row in queries.gains_per_offer(conn, since=since, until=now, metric=metric)
    }
    rows = [OfferCatalogRow(item=item, gained=gains.get(item.offer.offer_id, 0)) for item in items]

    if sort == "gain":
        rows.sort(key=lambda row: (-row.gained, row.item.offer.name.casefold()))
    elif sort == "name":
        rows.sort(key=lambda row: row.item.offer.name.casefold())
    else:
        rows.sort(
            key=lambda row: (
                row.item.last_captured_at is None,
                -(row.item.last_captured_at.timestamp() if row.item.last_captured_at else 0),
                row.item.offer.name.casefold(),
            )
        )
    return tuple(rows)


def offer_statuses(conn: sqlite3.Connection) -> tuple[str, ...]:
    return queries.offer_statuses(conn)


# --- pojedyncza oferta ------------------------------------------------------
@dataclass(frozen=True, slots=True)
class OfferView:
    offer: Offer
    series: Series
    points: tuple[SeriesPoint, ...]
    daily: tuple[DailyGain, ...]
    summary: SeriesSummary
    snapshots: int
    gaps: int
    freshness: queries.Freshness
    custom_range: bool = False
    secondary_series: Series | None = None


def offer_view(
    conn: sqlite3.Connection,
    offer_id: str,
    *,
    range_key: str = "30d",
    metric: Metric | str = "visits",
    now: datetime,
    start: datetime | None = None,
    end: datetime | None = None,
) -> OfferView | None:
    """Seria, podsumowanie i jakość danych jednej oferty (None, gdy oferty nie ma).

    Gdy podano `start` i `end`, używamy zakresu własnego (FR-10), inaczej presetu
    z `range_key`.
    """
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
    chosen: Metric = "visits" if metric not in ("visits", "watchers") else metric
    series = analytics.build_series(snapshots, offer_id=offer_id, metric=chosen, source=source)
    secondary = (
        analytics.build_series(snapshots, offer_id=offer_id, metric="watchers", source=source)
        if metric not in ("visits", "watchers")
        else None
    )

    custom = start is not None and end is not None
    if custom:
        points = analytics.select_between(series.points, start, end)
        summary = analytics.summarize_between(series, start=start, end=end)
        since = start
    else:
        points = analytics.select_points(series.points, range_key, now)
        summary = analytics.summarize(series, range_key=range_key, now=now)
        since = analytics.window_start(range_key, now)

    return OfferView(
        offer=state.offer,
        series=series,
        points=points,
        daily=analytics.daily_gains(points),
        summary=summary,
        snapshots=len(snapshots),
        gaps=queries.gaps(
            conn,
            offer_id,
            since=since,
            max_gap_hours=2.0,
        ),
        freshness=queries.freshness(conn),
        custom_range=custom,
        secondary_series=secondary,
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
    offers_with_drops: int = 0


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
        offers_with_drops=sum(1 for row in gains if row.drops > 0),
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


MAX_COMPARISON_OFFERS = 5


@dataclass(frozen=True, slots=True)
class IndexPoint:
    captured_at: datetime
    index: float


@dataclass(frozen=True, slots=True)
class IndexedSeries:
    offer: Offer
    points: tuple[IndexPoint, ...]
    base_value: int
    source: Source = "api"


def compare_offers_indexed(
    conn: sqlite3.Connection,
    offer_ids: Sequence[str],
    *,
    range_key: str = "30d",
    metric: Metric = "visits",
    now: datetime,
) -> tuple[IndexedSeries, ...]:
    """Serie znormalizowane do indeksu 100 w pierwszym punkcie okna (FR-14).

    Oferty bez danych albo z bazą 0 są pomijane — indeksu nie da się zdefiniować.
    """
    if len(offer_ids) > MAX_COMPARISON_OFFERS:
        raise ValueError(
            f"Do porównania można wybrać najwyżej {MAX_COMPARISON_OFFERS} ofert."
        )

    offers_by_id = {
        item.offer.offer_id: item.offer for item in queries.offers_with_last_snapshot(conn)
    }
    result: list[IndexedSeries] = []
    for offer_id in offer_ids:
        offer = offers_by_id.get(offer_id)
        if offer is None:
            continue
        snapshots = storage.get_series(conn, offer_id)
        source: Source = snapshots[0].source if snapshots else "api"
        series = analytics.build_series(snapshots, offer_id=offer_id, metric=metric, source=source)
        points = analytics.select_points(series.points, range_key, now)
        if not points:
            continue
        base = points[0].value
        if base <= 0:
            continue
        result.append(
            IndexedSeries(
                offer=offer,
                points=tuple(
                    IndexPoint(captured_at=point.captured_at, index=point.value / base * 100.0)
                    for point in points
                ),
                base_value=base,
                source=source,
            )
        )
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ComparisonRow:
    offer: Offer
    base_value: int
    last_value: int
    gained: int
    drops: int
    points: int


def comparison_rows(
    conn: sqlite3.Connection,
    offer_ids: Sequence[str],
    *,
    range_key: str = "30d",
    metric: Metric = "visits",
    now: datetime,
) -> tuple[ComparisonRow, ...]:
    """Tabela porównawcza: poziom na starcie i końcu okna, przyrost, spadki, punkty."""
    offers_by_id = {
        item.offer.offer_id: item.offer for item in queries.offers_with_last_snapshot(conn)
    }
    rows: list[ComparisonRow] = []
    for offer_id in offer_ids:
        offer = offers_by_id.get(offer_id)
        if offer is None:
            continue
        snapshots = storage.get_series(conn, offer_id)
        source: Source = snapshots[0].source if snapshots else "api"
        series = analytics.build_series(snapshots, offer_id=offer_id, metric=metric, source=source)
        points = analytics.select_points(series.points, range_key, now)
        if not points:
            continue
        deltas = analytics.deltas(points)
        rows.append(
            ComparisonRow(
                offer=offer,
                base_value=points[0].value,
                last_value=points[-1].value,
                gained=sum(analytics.positive_gains(points)),
                drops=sum(1 for delta in deltas if delta < 0),
                points=len(points),
            )
        )
    return tuple(rows)


# --- zdarzenia, adnotacje, alerty (S5) -------------------------------------
def sync_offer_events(
    conn: sqlite3.Connection,
    config: Config,
    *,
    client: AllegroClient | None = None,
    limit: int = events.DEFAULT_EVENT_LIMIT,
    now: datetime | None = None,
) -> int:
    """Pobierz zdarzenia z API i zapisz nowe (deduplikacja po kluczu naturalnym)."""
    return events.sync_events(
        conn,
        client if client is not None else AllegroClient(config=config),
        limit=limit,
        now=now,
    )


def events_for_offer(
    conn: sqlite3.Connection,
    offer_id: str,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> tuple[OfferEvent, ...]:
    return tuple(storage.list_events(conn, offer_id=offer_id, since=since, until=until))


def annotations_for_offer(
    conn: sqlite3.Connection,
    offer_id: str,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> tuple[Annotation, ...]:
    return tuple(storage.list_annotations(conn, offer_id=offer_id, since=since, until=until))


def add_annotation(
    conn: sqlite3.Connection,
    *,
    offer_id: str,
    occurred_at: datetime,
    label: str,
    note: str | None = None,
    now: datetime | None = None,
) -> int:
    return storage.add_annotation(
        conn,
        offer_id=offer_id,
        occurred_at=occurred_at,
        label=label,
        note=note,
        created_at=now,
    )


def delete_annotation(conn: sqlite3.Connection, annotation_id: int) -> int:
    return storage.delete_annotation(conn, annotation_id)


def whats_new(
    conn: sqlite3.Connection,
    offer_id: str,
    *,
    metric: Metric = "visits",
    now: datetime,
) -> events.WhatsNew:
    return events.whats_new(conn, offer_id, metric=metric, now=now)


def mark_offer_seen(
    conn: sqlite3.Connection, offer_id: str, *, now: datetime | None = None
) -> None:
    events.mark_seen(conn, offer_id, now=now)


def alert_rules(conn: sqlite3.Connection) -> tuple[AlertRule, ...]:
    return tuple(storage.list_alert_rules(conn))


def add_alert_rule(
    conn: sqlite3.Connection,
    *,
    kind: str,
    threshold: float,
    window_days: int,
    offer_id: str | None = None,
    now: datetime | None = None,
) -> int:
    return storage.add_alert_rule(
        conn,
        kind=kind,
        threshold=threshold,
        window_days=window_days,
        offer_id=offer_id,
        created_at=now,
    )


def delete_alert_rule(conn: sqlite3.Connection, rule_id: int) -> int:
    return storage.delete_alert_rule(conn, rule_id)


def alert_hits(
    conn: sqlite3.Connection, *, now: datetime, metric: Metric = "visits"
) -> tuple[events.AlertHit, ...]:
    return events.evaluate_alerts(conn, now=now, metric=metric)


# --- dane demo --------------------------------------------------------------
def seed_demo(
    conn: sqlite3.Connection,
    *,
    seed: int = demo.DEFAULT_SEED,
    days: int = demo.DEFAULT_DAYS,
    end: datetime | None = None,
    now: datetime | None = None,
) -> demo.SeedResult:
    """Wygeneruj dane syntetyczne do bazy demo (FR-18); odmawia mieszania z API."""
    moment = end if end is not None else demo.default_end(now)
    return demo.seed_demo_database(conn, seed=seed, days=days, end=moment)


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
    "ComparisonRow",
    "IndexPoint",
    "IndexedSeries",
    "MAX_COMPARISON_OFFERS",
    "OFFER_SORT_CHOICES",
    "OfferCatalogRow",
    "OfferListItem",
    "OfferSeries",
    "OfferView",
    "Overview",
    "PeriodComparison",
    "RankRow",
    "RefreshResult",
    "add_alert_rule",
    "add_annotation",
    "alert_hits",
    "alert_rules",
    "annotations_for_offer",
    "begin_login",
    "build_auth",
    "collector_state",
    "compare_offers",
    "compare_offers_indexed",
    "compare_periods",
    "comparison_rows",
    "complete_login",
    "data_version",
    "database",
    "delete_alert_rule",
    "delete_annotation",
    "events_for_offer",
    "list_offers",
    "mark_offer_seen",
    "offer_view",
    "offer_catalog",
    "offer_statuses",
    "open_database",
    "overview",
    "previous_period",
    "refresh_once",
    "seed_demo",
    "sync_offer_events",
    "token_status",
    "whats_new",
]
