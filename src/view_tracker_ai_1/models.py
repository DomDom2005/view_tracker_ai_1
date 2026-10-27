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
