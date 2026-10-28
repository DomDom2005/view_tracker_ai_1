"""Analityka: przedziały, delty, anomalie, agregacja dzienna, coverage, trend (SPEC §6 FR-4).

Funkcje czyste: bez I/O, bez sieci i bez `datetime.now()` w środku — czas „teraz”
podaje wywołujący (`now`), dzięki czemu wyniki są deterministyczne i testowalne.

Semantyka licznika (SPEC §4.2): `visitsCount` to hipotetycznie okno kroczące, więc
poziom **może maleć**. Spadek nie jest błędem danych, tylko anomalią: zapisujemy go,
ale nie wliczamy ujemnych przyrostów do „zyskanych” wyświetleń.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

from view_tracker_ai_1.models import (
    Anomaly,
    DailyGain,
    Metric,
    Series,
    SeriesPoint,
    SeriesSummary,
    Snapshot,
    Source,
    TrendLabel,
)

LOCAL_TZ = ZoneInfo("Europe/Warsaw")

RANGE_KEYS: tuple[str, ...] = ("24h", "7d", "30d", "90d", "all")
"""Przedziały obsługiwane przez CLI (SPEC §6 FR-4)."""

RANGE_HOURS: dict[str, int] = {"24h": 24, "7d": 7 * 24, "30d": 30 * 24, "90d": 90 * 24}
"""Nominalna długość przedziału w godzinach; `all` nie ma długości (cała historia)."""

TREND_THRESHOLD = 0.02
"""Próg etykiety trendu: `rel = slope / max(mean, 1)` (SPEC §6 FR-4)."""

MIN_POINTS_FOR_TREND = 3
"""Poniżej tylu punktów trend jest `brak danych`, a nie „stabilny”."""

SECONDS_PER_HOUR = 3600.0
SECONDS_PER_DAY = 86400.0

COUNTER_DECREASE = "counter_decrease"
"""Rodzaj anomalii: licznik zmalał (SPEC §4.2)."""


# --- przedziały -------------------------------------------------------------
def range_duration(range_key: str) -> timedelta | None:
    """Długość przedziału; `None` dla `all` (cała dostępna historia)."""
    if range_key == "all":
        return None
    try:
        hours = RANGE_HOURS[range_key]
    except KeyError:
        raise ValueError(
            f"Nieznany przedział: {range_key!r}. Dozwolone: {', '.join(RANGE_KEYS)}."
        ) from None
    return timedelta(hours=hours)


def window_start(range_key: str, now: datetime) -> datetime | None:
    """Początek okna (UTC) albo `None` dla `all`."""
    duration = range_duration(range_key)
    return None if duration is None else _as_utc(now) - duration


def select_points(
    points: Iterable[SeriesPoint], range_key: str, now: datetime
) -> tuple[SeriesPoint, ...]:
    """Punkty z przedziału `range_key`, kończące się na `now` (włącznie).

    Przyszłe snapshoty (zegar bazy vs zegar aplikacji) są odrzucane — inaczej
    `coverage` i trend liczyłyby dane, których jeszcze nie ma.
    """
    duration = range_duration(range_key)
    if duration is None:
        return tuple(points)

    moment = _as_utc(now)
    start = moment - duration
    return tuple(point for point in points if start <= _as_utc(point.captured_at) <= moment)


# --- delty i anomalie -------------------------------------------------------
def deltas(points: Sequence[SeriesPoint]) -> tuple[int, ...]:
    """Różnice między kolejnymi punktami (`v_i − v_{i−1}`); ujemne są dozwolone."""
    return tuple(current.value - previous.value for previous, current in pairwise(points))


def positive_gains(points: Sequence[SeriesPoint]) -> tuple[int, ...]:
    """Przyrosty bez ujemnych wartości — spadek wnosi 0, nie liczbę ujemną."""
    return tuple(max(delta, 0) for delta in deltas(points))


def gained_total(points: Sequence[SeriesPoint]) -> int:
    """Suma dodatnich przyrostów; nigdy nie jest ujemna (SPEC §6 FR-4)."""
    return sum(positive_gains(points))


def find_anomalies(points: Sequence[SeriesPoint]) -> tuple[Anomaly, ...]:
    """Punkty, w których licznik zmalał (`counter_decrease`).

    To nie błąd: poziom bywa oknem kroczącym, więc spadek jest poprawną obserwacją.
    Zapisujemy go w całości (z ujemną deltą), żeby wykres i komentarz AI mogły go
    pokazać, ale nie trafia do przyrostów.
    """
    return tuple(
        Anomaly(captured_at=current.captured_at, delta=delta)
        for current, delta in zip(points[1:], deltas(points), strict=True)
        if delta < 0
    )


# --- agregacja dzienna ------------------------------------------------------
def daily_gains(points: Sequence[SeriesPoint]) -> tuple[DailyGain, ...]:
    """Agregacja po dobie w `Europe/Warsaw` (DST: doba bywa 23- lub 25-godzinna).

    Przyrost przypisujemy do dnia, w którym go zaobserwowano (dzień późniejszego
    punktu pary). `level_end` to ostatnia wartość licznika w tym dniu.
    """
    if not points:
        return ()

    gained: dict[date, int] = {}
    level_end: dict[date, int] = {}
    for point in points:
        day = _local_date(point.captured_at)
        gained.setdefault(day, 0)
        level_end[day] = point.value  # punkty są posortowane rosnąco — ostatni wygrywa

    for current, delta in zip(points[1:], deltas(points), strict=True):
        if delta > 0:
            day = _local_date(current.captured_at)
            gained[day] = gained.get(day, 0) + delta

    return tuple(
        DailyGain(day=day, gained=gained[day], level_end=level_end[day]) for day in sorted(gained)
    )


# --- pokrycie ---------------------------------------------------------------
def distinct_hours(points: Sequence[SeriesPoint]) -> int:
    """Liczba różnych godzin (UTC) z co najmniej jednym snapshotem."""
    return len(
        {_as_utc(point.captured_at).replace(minute=0, second=0, microsecond=0) for point in points}
    )


def coverage(points: Sequence[SeriesPoint], range_key: str, now: datetime) -> float:
    """Udział godzin z danymi w nominalnej długości przedziału, ograniczony do 1.

    Punkty spoza przedziału są odrzucane, więc funkcję można wołać niezależnie od
    `select_points`. Dla `all` mianownikiem jest rozpiętość dostępnych danych, więc
    seria bez luk daje 1.0, a seria z dziurami — wartość mniejszą.
    """
    points = select_points(points, range_key, now)
    if not points:
        return 0.0

    duration = range_duration(range_key)
    if duration is None:
        first, last = _as_utc(points[0].captured_at), _as_utc(points[-1].captured_at)
        hours = (last - first).total_seconds() / SECONDS_PER_HOUR + 1.0
    else:
        hours = duration.total_seconds() / SECONDS_PER_HOUR

    if hours <= 0:  # pragma: no cover - nienaturalne: przedział zawsze ma długość
        return 1.0
    return min(1.0, distinct_hours(points) / hours)


# --- trend ------------------------------------------------------------------
def slope_per_day(points: Sequence[SeriesPoint]) -> float:
    """Nachylenie regresji liniowej (OLS) poziomu licznika względem czasu w dniach."""
    if len(points) < 2:
        return 0.0

    origin = _as_utc(points[0].captured_at)
    xs = [
        (_as_utc(point.captured_at) - origin).total_seconds() / SECONDS_PER_DAY for point in points
    ]
    ys = [float(point.value) for point in points]

    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return 0.0
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    return sxy / sxx


def label_trend(slope: float, mean: float) -> TrendLabel:
    """Etykieta trendu z progu `TREND_THRESHOLD` (SPEC §6 FR-4)."""
    relative = slope / max(mean, 1.0)
    if relative > TREND_THRESHOLD:
        return "rosnący"
    if relative < -TREND_THRESHOLD:
        return "malejący"
    return "stabilny"


# --- podsumowanie -----------------------------------------------------------
def summarize(series: Series, *, range_key: str, now: datetime) -> SeriesSummary:
    """Podsumowanie serii w przedziale — dokładnie pola z SPEC §6 FR-4.

    `start`/`end` to granice **danych** (pierwszy i ostatni punkt w przedziale),
    a nie nominalne granice okna — dzięki temu widać, jak daleko dane sięgają.
    """
    points = select_points(series.points, range_key, now)
    if not points:
        return SeriesSummary(trend_label="brak danych")

    values = [point.value for point in points]
    mean = sum(values) / len(values)

    # Poniżej progu nie ogłaszamy trendu — ani etykiety, ani nachylenia, bo regresja
    # z dwóch punktów zawsze „coś” pokaże i sugerowałaby pewność, której nie ma.
    if len(points) < MIN_POINTS_FOR_TREND:
        slope = 0.0
        label: TrendLabel = "brak danych"
    else:
        slope = slope_per_day(points)
        label = label_trend(slope, mean)

    return SeriesSummary(
        start=points[0].captured_at,
        end=points[-1].captured_at,
        min=min(values),
        max=max(values),
        mean=mean,
        gained_total=gained_total(points),
        slope_per_day=slope,
        trend_label=label,
        coverage=coverage(points, range_key, now),
        anomalies=find_anomalies(points),
        n_points=len(points),
    )


def build_series(
    snapshots: Iterable[Snapshot],
    *,
    offer_id: str,
    metric: Metric,
    source: Source = "api",
) -> Series:
    """Zamień snapshoty z bazy na serię jednej metryki (posortowaną rosnąco)."""
    points = tuple(
        SeriesPoint(captured_at=_as_utc(snapshot.captured_at), value=snapshot.value(metric))
        for snapshot in sorted(snapshots, key=lambda item: item.captured_at)
    )
    return Series(offer_id=offer_id, metric=metric, points=points, source=source)


# --- pomocnicze -------------------------------------------------------------
def _as_utc(moment: datetime) -> datetime:
    """Naive traktujemy jako UTC (tak samo jak `storage.from_iso`)."""
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def _local_date(moment: datetime) -> date:
    return _as_utc(moment).astimezone(LOCAL_TZ).date()
