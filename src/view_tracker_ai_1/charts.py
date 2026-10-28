"""Wykresy PNG: poziom licznika i dzienny przyrost (SPEC §6 FR-5, §11).

Backend `Agg` — rysujemy bez okna i bez sieci, więc działa na serwerze i w testach.
Czas na osiach w `Europe/Warsaw` (NFR-3), opisy po polsku, dane syntetyczne zawsze
oznaczone napisem „DANE SYNTETYCZNE”.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=True)

from matplotlib import dates as mdates  # noqa: E402
from matplotlib import pyplot as plt  # noqa: E402

from view_tracker_ai_1 import analytics  # noqa: E402
from view_tracker_ai_1.errors import ChartError  # noqa: E402
from view_tracker_ai_1.models import DailyGain, Metric, Series, SeriesPoint, SeriesSummary  # noqa: E402

METRIC_LABELS: dict[str, str] = {"visits": "wyświetlenia", "watchers": "obserwujący"}
"""Nazwy metryk w opisach osi i tytule."""

RANGE_LABELS: dict[str, str] = {
    "24h": "ostatnie 24 godziny",
    "7d": "ostatnie 7 dni",
    "30d": "ostatnie 30 dni",
    "90d": "ostatnie 90 dni",
    "all": "cała historia",
}

SYNTHETIC_WATERMARK = "DANE SYNTETYCZNE"
MAX_TITLE_LENGTH = 60

FIGURE_SIZE = (10.0, 7.0)
DPI = 110


@dataclass(frozen=True, slots=True)
class ChartResult:
    """Co powstało — metadane zamiast analizy pikseli (SPEC §11, „łatwe testy”)."""

    path: Path
    is_synthetic: bool
    n_points: int
    range_key: str
    metric: str
    coverage: float
    anomalies: int


def watermark_text(series: Series) -> str | None:
    """Napis-znak wodny dla danych syntetycznych; `None` dla danych z API (FR-8)."""
    return SYNTHETIC_WATERMARK if series.is_synthetic else None


def render_chart(
    series: Series,
    *,
    offer_name: str,
    range_key: str,
    now: datetime,
    out_path: str | Path,
    metric: Metric | None = None,
) -> ChartResult:
    """Narysuj dwupanelowy wykres i zapisz PNG. Zwraca metadane pliku.

    Górny panel: poziom licznika z markerami anomalii (spadek licznika nie jest
    błędem — SPEC §4.2). Dolny panel: dzienny przyrost po dobie `Europe/Warsaw`.
    """
    metric_key: Metric = metric or series.metric
    points, summary = _prepare(series, range_key=range_key, now=now)

    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    figure = _build_figure(
        series, points, summary, offer_name=offer_name, range_key=range_key, metric=metric_key
    )
    try:
        figure.savefig(target, dpi=DPI, bbox_inches="tight", facecolor="white")
    finally:
        plt.close(figure)

    return ChartResult(
        path=target,
        is_synthetic=series.is_synthetic,
        n_points=summary.n_points,
        range_key=range_key,
        metric=metric_key,
        coverage=summary.coverage,
        anomalies=len(summary.anomalies),
    )


def render_png(
    series: Series,
    *,
    offer_name: str,
    range_key: str,
    now: datetime,
    metric: Metric | None = None,
) -> bytes:
    """Ten sam wykres, ale do pamięci — raport osadza go jako base64 (SPEC §11)."""
    metric_key: Metric = metric or series.metric
    points, summary = _prepare(series, range_key=range_key, now=now)

    figure = _build_figure(
        series, points, summary, offer_name=offer_name, range_key=range_key, metric=metric_key
    )
    buffer = BytesIO()
    try:
        figure.savefig(buffer, format="png", dpi=DPI, bbox_inches="tight", facecolor="white")
    finally:
        plt.close(figure)
    return buffer.getvalue()


def _prepare(
    series: Series, *, range_key: str, now: datetime
) -> tuple[tuple[SeriesPoint, ...], SeriesSummary]:
    summary = analytics.summarize(series, range_key=range_key, now=now)
    points = analytics.select_points(series.points, range_key, now)
    if not points or summary.n_points == 0:
        raise ChartError(
            f"Brak danych w przedziale {range_key!r} dla oferty {series.offer_id} — "
            "uruchom `collect` albo wybierz inny zakres."
        )
    return points, summary


def _build_figure(
    series: Series,
    points: tuple[SeriesPoint, ...],
    summary: SeriesSummary,
    *,
    offer_name: str,
    range_key: str,
    metric: Metric,
) -> plt.Figure:
    moments = [analytics.to_local(point.captured_at) for point in points]
    figure, (top, bottom) = plt.subplots(
        2, 1, figsize=FIGURE_SIZE, sharex=True, gridspec_kw={"height_ratios": [2, 1]}
    )
    _draw_level(top, moments, points, summary)
    _draw_gains(bottom, analytics.daily_gains(points))
    _decorate(figure, top, bottom, series, summary, offer_name, range_key, metric)
    return figure


# --- panele -----------------------------------------------------------------
def _draw_level(
    axes: plt.Axes,
    moments: list[datetime],
    points: tuple[SeriesPoint, ...],
    summary: SeriesSummary,
) -> None:
    axes.plot(
        moments,
        [point.value for point in points],
        color="#1f77b4",
        linewidth=1.8,
        zorder=2,
        label="poziom licznika",
    )

    marks = _anomaly_positions(points, summary)
    if marks:
        # Markery pod linią (zorder=1): przy serii systematycznie malejącej jest ich
        # ponad 200 i rysowane na wierzchu zasłaniały cały przebieg poziomu.
        axes.scatter(
            [moment for moment, _ in marks],
            [value for _, value in marks],
            color="#d62728",
            marker="v",
            s=26,
            alpha=0.75,
            zorder=1,
            label=f"spadek licznika ({len(marks)})",
        )

    axes.grid(True, color="#e6e6e6", linewidth=0.8)
    axes.set_ylabel("Poziom licznika")
    axes.legend(loc="upper left", fontsize=9, frameon=False)


def _anomaly_positions(
    points: tuple[SeriesPoint, ...], summary: SeriesSummary
) -> list[tuple[datetime, int]]:
    """Współrzędne markerów anomalii: czas lokalny i wartość licznika w tym punkcie."""
    if not summary.anomalies:
        return []
    by_moment = {analytics.to_local(point.captured_at): point.value for point in points}
    positions = []
    for anomaly in summary.anomalies:
        moment = analytics.to_local(anomaly.captured_at)
        if moment in by_moment:
            positions.append((moment, by_moment[moment]))
    return positions


def _draw_gains(axes: plt.Axes, gains: tuple[DailyGain, ...]) -> None:
    if not gains or all(entry.gained == 0 for entry in gains):
        # Same zera to poprawny wynik (licznik maleje lub stoi), ale pusta os z
        # zakresem -0,05…0,05 wyglądała jak błąd — dlatego komunikat zamiast słupków.
        axes.text(
            0.5,
            0.5,
            "brak dodatnich przyrostów w tym przedziale",
            transform=axes.transAxes,
            ha="center",
            va="center",
            fontsize=10,
            color="#666666",
        )
        axes.set_yticks([])
        return

    centres = [datetime.combine(entry.day, time(hour=12)) for entry in gains]
    # Szerokość 1 dzień: przy 90 słupkach cieńsze słupki rozpadają się na białe prążki.
    axes.bar(
        centres,
        [entry.gained for entry in gains],
        width=1.0,
        color="#2ca02c",
        edgecolor="none",
        linewidth=0,
    )
    axes.grid(True, axis="y", color="#e6e6e6", linewidth=0.8)
    axes.set_ylabel("Dzienny przyrost")
    axes.set_xlabel("Data (Europe/Warsaw)")


def _decorate(
    figure: plt.Figure,
    top: plt.Axes,
    bottom: plt.Axes,
    series: Series,
    summary: SeriesSummary,
    offer_name: str,
    range_key: str,
    metric: Metric,
) -> None:
    metric_label = METRIC_LABELS.get(metric, metric)
    range_label = RANGE_LABELS.get(range_key, range_key)
    figure.suptitle(
        f"{_shorten(offer_name)} — {range_label} — {metric_label}",
        fontsize=13,
        fontweight="bold",
    )
    # Podtytuł w marginesie: w polu wykresu kolidował z legendą i z linią danych.
    figure.text(
        0.5,
        0.935,
        f"pokrycie danych: {summary.coverage:.0%} · punktów: {summary.n_points}",
        ha="center",
        fontsize=9,
        color="#555555",
    )

    locator = mdates.AutoDateLocator()
    bottom.xaxis.set_major_locator(locator)
    bottom.xaxis.set_major_formatter(
        mdates.DateFormatter("%H:%M" if range_key == "24h" else "%d.%m")
    )
    bottom.tick_params(axis="x", labelsize=9)
    top.tick_params(axis="x", labelsize=9)

    watermark = watermark_text(series)
    if watermark is not None:
        # Znak wodny wyłącznie w górnym panelu — na dole zasłaniał słupki przyrostu.
        top.text(
            0.5,
            0.45,
            watermark,
            transform=top.transAxes,
            fontsize=40,
            color="#d62728",
            alpha=0.14,
            ha="center",
            va="center",
            rotation=25,
            fontweight="bold",
            zorder=0,
        )

    figure.text(0.99, 0.01, f"oferta {series.offer_id}", ha="right", fontsize=8, color="#888888")


def _shorten(text: str, limit: int = MAX_TITLE_LENGTH) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + "…"


__all__ = [
    "METRIC_LABELS",
    "RANGE_LABELS",
    "SYNTHETIC_WATERMARK",
    "ChartResult",
    "render_chart",
    "render_png",
    "watermark_text",
]
