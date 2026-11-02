"""Modele danych aplikacji (SPEC §6 FR-4, §7): oferty, snapshoty, serie i podsumowania."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

Metric = Literal["visits", "watchers"]
Source = Literal["api", "synthetic"]
TrendLabel = Literal["rosnący", "malejący", "stabilny", "brak danych"]

METRICS: tuple[Metric, ...] = ("visits", "watchers")
SOURCES: tuple[Source, ...] = ("api", "synthetic")


@dataclass(frozen=True, slots=True)
class Offer:
    """Oferta sprzedawcy widziana w API (metadane, bez liczników)."""

    offer_id: str
    name: str
    status: str | None
    first_seen_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Odczyt liczników oferty w jednej chwili (UTC)."""

    offer_id: str
    captured_at: datetime
    visits_count: int
    watchers_count: int
    source: Source = "api"

    def value(self, metric: Metric) -> int:
        """Wartość wybranej metryki."""
        return self.visits_count if metric == "visits" else self.watchers_count


@dataclass(frozen=True, slots=True)
class SeriesPoint:
    """Punkt serii: chwila i wartość licznika."""

    captured_at: datetime
    value: int


@dataclass(frozen=True, slots=True)
class DailyGain:
    """Agregat dobowy w strefie Europe/Warsaw."""

    day: date
    gained: int
    level_end: int


@dataclass(frozen=True, slots=True)
class Anomaly:
    """Punkt, w którym licznik spadł (counter_decrease, SPEC §6 FR-4)."""

    captured_at: datetime
    delta: int


@dataclass(frozen=True, slots=True)
class Series:
    """Seria czasowa jednej metryki dla oferty."""

    offer_id: str
    metric: Metric
    points: tuple[SeriesPoint, ...] = ()
    source: Source = "api"

    def __len__(self) -> int:
        return len(self.points)

    @property
    def values(self) -> tuple[int, ...]:
        return tuple(point.value for point in self.points)

    @property
    def is_synthetic(self) -> bool:
        return self.source == "synthetic"


@dataclass(frozen=True, slots=True)
class SeriesSummary:
    """Podsumowanie serii — dokładnie pola z SPEC §6 FR-4."""

    start: datetime | None = None
    end: datetime | None = None
    min: int = 0
    max: int = 0
    mean: float = 0.0
    gained_total: int = 0
    slope_per_day: float = 0.0
    trend_label: TrendLabel = "brak danych"
    coverage: float = 0.0
    anomalies: tuple[Anomaly, ...] = field(default_factory=tuple)
    n_points: int = 0

    @property
    def has_anomalies(self) -> bool:
        return bool(self.anomalies)


# --- 2.0: zdarzenia, adnotacje, alerty --------------------------------------
@dataclass(frozen=True, slots=True)
class OfferEvent:
    """Zdarzenie oferty z API (`GET /sale/offer-events`) albo zsynchronizowane wcześniej."""

    offer_id: str
    occurred_at: datetime
    type: str
    payload_json: str = "{}"
    fetched_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Annotation:
    """Ręczna adnotacja nanoszona na wykres (np. „obniżka ceny”)."""

    id: int
    offer_id: str
    occurred_at: datetime
    label: str
    note: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AlertRule:
    """Reguła alertu progowego (FR-16); `offer_id=None` oznacza cały katalog."""

    id: int
    offer_id: str | None
    kind: str
    threshold: float
    window_days: int
    created_at: datetime
