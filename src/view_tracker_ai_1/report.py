"""Raport HTML: jeden samodzielny plik z wykresami, liczbami i komentarzem AI (SPEC §11).

Zasady:

- **jeden plik** — wykresy są osadzone jako `data:image/png;base64`, zero zasobów
  zewnętrznych, więc raport działa offline i po wysłaniu mailem;
- **autoescape włączony** — nazwa oferty i komentarz modelu to dane nieufne;
- **badge środowiska** — SANDBOX / PROD / DEMO, gdzie DEMO oznacza dane syntetyczne;
- **oznaczenie danych syntetycznych** widoczne w nagłówku i stopce (SPEC §6 FR-8);
- **stopka z ostrzeżeniem** o semantyce licznika (SPEC §4.2).
"""

from __future__ import annotations

import base64
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, select_autoescape

from view_tracker_ai_1 import ai_comment, analytics, charts, storage
from view_tracker_ai_1.models import Metric, Offer, Series, SeriesSummary

COUNTER_WARNING = (
    "Licznik wyświetleń to wartość z okna czasowego (najprawdopodobniej unikatowe "
    "wyświetlenia z 30 dni), więc może maleć. Spadek licznika jest oznaczany jako anomalia, "
    "a nie traktowany jako błąd danych."
)
SYNTHETIC_WARNING = (
    "Raport powstał z DANYCH SYNTETYCZNYCH (source='synthetic') — nie pochodzą z API Allegro "
    "i służą tylko do demonstracji wykresów."
)

DEFAULT_RANGES: tuple[str, ...] = ("7d",)


@dataclass(frozen=True, slots=True)
class ChartCard:
    """Jeden kafelek: wykres + liczby + komentarz dla pary (oferta, przedział)."""

    range_key: str
    range_label: str
    image_data_uri: str
    summary: SeriesSummary
    comment: str


@dataclass(frozen=True, slots=True)
class OfferReport:
    """Sekcja jednej oferty."""

    offer_id: str
    name: str
    cards: tuple[ChartCard, ...]


@dataclass(frozen=True, slots=True)
class Report:
    """Gotowy raport: dane do wyświetlenia i wyrenderowany HTML."""

    env_label: str
    generated_at: datetime
    metric: Metric
    metric_label: str
    offers: tuple[OfferReport, ...]
    is_synthetic: bool
    ai_enabled: bool
    html: str


def build_report(
    conn: sqlite3.Connection | None,
    *,
    series_by_offer: dict[str, tuple[Offer, Series]],
    env: str,
    ranges: tuple[str, ...],
    metric: Metric,
    generator: ai_comment.CommentGenerator,
    now: datetime,
) -> Report:
    """Złóż raport z gotowych serii.

    `series_by_offer` mapuje `offer_id` na parę `(Offer, Series)` — dzięki temu raport nie
    zna warstwy HTTP ani API i da się go zbudować także z danych demo. `conn` służy tylko
    do cache komentarzy (może być `None`).
    """
    if not ranges:
        raise ValueError("Raport wymaga co najmniej jednego przedziału.")

    offer_reports: list[OfferReport] = []
    synthetic = False
    for offer_id, (offer, series) in series_by_offer.items():
        synthetic = synthetic or series.is_synthetic
        cards: list[ChartCard] = []
        for range_key in ranges:
            summary = analytics.summarize(series, range_key=range_key, now=now)
            if summary.n_points == 0:
                continue
            png = charts.render_png(
                series,
                offer_name=offer.name,
                range_key=range_key,
                now=now,
                metric=metric,
            )
            text = ai_comment.generate_comment(
                summary,
                offer_id=offer_id,
                offer_name=offer.name,
                range_key=range_key,
                metric=metric,
                generator=generator,
                conn=conn,
                now=now,
            )
            cards.append(
                ChartCard(
                    range_key=range_key,
                    range_label=charts.RANGE_LABELS.get(range_key, range_key),
                    image_data_uri=_data_uri(png),
                    summary=summary,
                    comment=text,
                )
            )
        if cards:
            offer_reports.append(
                OfferReport(offer_id=offer_id, name=offer.name, cards=tuple(cards))
            )

    report = Report(
        env_label="DEMO" if synthetic else env.upper(),
        generated_at=now,
        metric=metric,
        metric_label=charts.METRIC_LABELS.get(metric, metric),
        offers=tuple(offer_reports),
        is_synthetic=synthetic,
        ai_enabled=not isinstance(generator, ai_comment.FakeCommentGenerator),
        html="",
    )
    return _with_html(report)


def write_report(report: Report, out_path: str | Path) -> Path:
    """Zapisz raport do pliku (UTF-8) i zwróć ścieżkę."""
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.html, encoding="utf-8")
    return target


def series_for_offer(
    conn: sqlite3.Connection, offer_id: str, metric: Metric
) -> tuple[Offer, Series]:
    """Wczytaj ofertę i jej serię z bazy — skrót używany przez CLI."""
    offer = next((item for item in storage.list_offers(conn) if item.offer_id == offer_id), None)
    if offer is None:
        raise LookupError(offer_id)
    snapshots = storage.get_series(conn, offer_id)
    source = snapshots[0].source if snapshots else "api"
    series = analytics.build_series(snapshots, offer_id=offer_id, metric=metric, source=source)
    return offer, series


def _with_html(report: Report) -> Report:
    environment = Environment(autoescape=select_autoescape(default=True, default_for_string=True))
    template = environment.from_string(TEMPLATE)
    html = template.render(
        report=report,
        generated_at=format_local(report.generated_at),
        counter_warning=COUNTER_WARNING,
        synthetic_warning=SYNTHETIC_WARNING,
    )
    return replace(report, html=html)


def format_local(moment: datetime) -> str:
    """Czas w `Europe/Warsaw` do nagłówka raportu."""
    return moment.astimezone(analytics.LOCAL_TZ).strftime("%Y-%m-%d %H:%M")


def _data_uri(png: bytes) -> str:
    encoded = base64.b64encode(png).decode("ascii")
    return f"data:image/png;base64,{encoded}"


TEMPLATE = """<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>view_tracker_ai_1 — raport {{ report.metric_label }}</title>
<style>
  :root { color-scheme: light; }
  body { font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
         margin: 0 auto; max-width: 1040px; padding: 24px; color: #1f2328; background: #fff; }
  header { border-bottom: 2px solid #eaecef; padding-bottom: 12px; margin-bottom: 24px; }
  h1 { font-size: 24px; margin: 0 0 8px; }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 999px;
           font-size: 12px; font-weight: 600; letter-spacing: .04em; color: #fff; }
  .badge-sandbox { background: #0969da; }
  .badge-prod { background: #cf222e; }
  .badge-demo { background: #8250df; }
  .meta { color: #57606a; font-size: 13px; margin-left: 8px; }
  .notice { border: 1px solid #d4a72c; background: #fff8c5; border-radius: 8px;
            padding: 10px 14px; margin: 16px 0; font-size: 14px; }
  section.offer { border: 1px solid #d0d7de; border-radius: 10px; padding: 16px 20px;
                  margin-bottom: 28px; }
  section.offer h2 { font-size: 18px; margin: 0 0 4px; }
  .offer-id { color: #57606a; font-size: 12px; font-family: ui-monospace, monospace; }
  h3 { font-size: 15px; margin: 20px 0 8px; color: #24292f; }
  img.chart { width: 100%; height: auto; border: 1px solid #eaecef; border-radius: 6px; }
  table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 14px; }
  th, td { border: 1px solid #d0d7de; padding: 6px 10px; text-align: right; }
  th:first-child, td:first-child { text-align: left; }
  thead th { background: #f6f8fa; }
  .comment { background: #f6f8fa; border-left: 3px solid #0969da; border-radius: 6px;
             padding: 10px 14px; font-size: 14px; line-height: 1.5; }
  .comment .label { display: block; font-size: 11px; text-transform: uppercase;
                    letter-spacing: .05em; color: #57606a; margin-bottom: 6px; }
  footer { border-top: 1px solid #eaecef; margin-top: 32px; padding-top: 12px;
           color: #57606a; font-size: 12px; line-height: 1.6; }
</style>
</head>
<body>
<header>
  <h1>Raport liczników ofert — {{ report.metric_label }}</h1>
  <div>
    <span class="badge badge-{{ report.env_label|lower }}">{{ report.env_label }}</span>
    <span class="meta">
      wygenerowano {{ generated_at }} (Europe/Warsaw) ·
      ofert: {{ report.offers|length }} ·
      komentarz AI: {{ "tak" if report.ai_enabled else "nie (--no-ai)" }}
    </span>
  </div>
</header>

{% if report.is_synthetic %}
<div class="notice">DANE SYNTETYCZNE — {{ synthetic_warning }}</div>
{% endif %}

{% if not report.offers %}
<div class="notice">
  Brak danych do pokazania — uruchom <code>collect</code> albo wybierz inny przedział.
</div>
{% endif %}

{% for offer in report.offers %}
<section class="offer">
  <h2>{{ offer.name }}</h2>
  <div class="offer-id">oferta {{ offer.offer_id }}</div>

  {% for card in offer.cards %}
  <h3>{{ card.range_label }}</h3>
  <img class="chart" alt="Wykres: {{ offer.name }}, {{ card.range_label }}"
       src="{{ card.image_data_uri }}">

  <table>
    <thead>
      <tr><th>Wskaźnik</th><th>Wartość</th></tr>
    </thead>
    <tbody>
      <tr><td>Liczba punktów</td><td>{{ card.summary.n_points }}</td></tr>
      <tr><td>Minimum</td><td>{{ card.summary.min }}</td></tr>
      <tr><td>Maksimum</td><td>{{ card.summary.max }}</td></tr>
      <tr><td>Średnia</td><td>{{ "%.1f"|format(card.summary.mean) }}</td></tr>
      <tr><td>Suma przyrostów</td><td>{{ card.summary.gained_total }}</td></tr>
      <tr><td>Nachylenie na dzień</td><td>{{ "%.2f"|format(card.summary.slope_per_day) }}</td></tr>
      <tr><td>Trend</td><td>{{ card.summary.trend_label }}</td></tr>
      <tr><td>Pokrycie danych</td><td>{{ (card.summary.coverage * 100)|round(0)|int }}%</td></tr>
      <tr><td>Spadki licznika (anomalie)</td><td>{{ card.summary.anomalies|length }}</td></tr>
    </tbody>
  </table>

  <div class="comment">
    <span class="label">Komentarz{{ "" if report.ai_enabled else " (bez AI)" }}</span>
    {{ card.comment }}
  </div>
  {% endfor %}
</section>
{% endfor %}

<footer>
  <p>{{ counter_warning }}</p>
  {% if report.is_synthetic %}<p>{{ synthetic_warning }}</p>{% endif %}
  <p>view_tracker_ai_1 — dane w UTC, prezentacja w Europe/Warsaw.</p>
</footer>
</body>
</html>
"""
