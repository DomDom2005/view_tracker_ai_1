"""Formatowanie i odmiana tekstów po polsku — wspólne dla całego UI 2.0.

Wyciągnięte z usuniętego modułu AI, bo te same zasady (odmiana, liczby, daty) dotyczą
wykresów, kafli i tabel. Wszystkie funkcje są czyste i testowalne bez UI.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from view_tracker_ai_1.models import Metric

LOCAL_TZ = ZoneInfo("Europe/Warsaw")
DATETIME_FORMAT = "%d.%m.%Y %H:%M"
DATE_FORMAT = "%d.%m.%Y"

METRIC_LABELS: dict[Metric, str] = {
    "visits": "wyświetlenia",
    "watchers": "obserwujący",
}
METRIC_UNITS: dict[Metric, str] = {
    "visits": "wyświetlenia",
    "watchers": "obserwujący",
}

RANGE_LABELS: dict[str, str] = {
    "24h": "24 godziny",
    "7d": "7 dni",
    "30d": "30 dni",
    "90d": "90 dni",
    "all": "cały okres",
    "custom": "zakres własny",
}


def range_label(range_key: str) -> str:
    """Czytelna nazwa zakresu do tytułów wykresów i kart."""
    return RANGE_LABELS.get(range_key, range_key)


def plural(count: int, one: str, few: str, many: str) -> str:
    """Odmiana rzeczownika: 1 punkt / 2 punkty / 5 punktów (z wyjątkiem 12–14)."""
    absolute = abs(int(count))
    if absolute == 1:
        return one
    if absolute % 10 in (2, 3, 4) and absolute % 100 not in (12, 13, 14):
        return few
    return many


def points_label(count: int) -> str:
    return f"{count} {plural(count, 'punkt', 'punkty', 'punktów')}"


def offers_label(count: int) -> str:
    return f"{count} {plural(count, 'oferta', 'oferty', 'ofert')}"


def snapshots_label(count: int) -> str:
    return f"{count} {plural(count, 'snapshot', 'snapshoty', 'snapshotów')}"


def format_number(value: int | float) -> str:
    """Liczba całkowita z separatorem tysięcy (spacja nierozdzielająca)."""
    return f"{int(round(value)):,}".replace(",", "\u00a0")


def format_decimal(value: float, digits: int = 2) -> str:
    text = f"{value:.{digits}f}"
    return text.replace(".", ",")


def format_percent(fraction: float) -> str:
    return f"{fraction * 100:.0f}%"


def format_signed_percent(fraction: float) -> str:
    """Zmiana procentowa ze znakiem, np. `+12%` / `-4%`."""
    sign = "+" if fraction >= 0 else "−"
    return f"{sign}{abs(fraction) * 100:.0f}%"


def to_local(moment: datetime) -> datetime:
    return moment.astimezone(LOCAL_TZ)


def format_datetime(moment: datetime | None) -> str:
    if moment is None:
        return "—"
    return to_local(moment).strftime(DATETIME_FORMAT)


def format_date(moment: datetime | None) -> str:
    if moment is None:
        return "—"
    return to_local(moment).strftime(DATE_FORMAT)


def metric_label(metric: Metric) -> str:
    return METRIC_LABELS[metric]
