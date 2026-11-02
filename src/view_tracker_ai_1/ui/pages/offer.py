"""Oferta — wybór oferty, zakres (presety + własny), metryka, wykres i podsumowanie (S2)."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from typing import cast

import streamlit as st

from view_tracker_ai_1 import services
from view_tracker_ai_1.errors import AppError, AuthError, EventError
from view_tracker_ai_1.models import Metric
from view_tracker_ai_1.text import (
    LOCAL_TZ,
    alert_rule_label,
    event_label,
    format_datetime,
    format_decimal,
    format_number,
    format_percent,
    metric_label,
    points_label,
    range_label,
)
from view_tracker_ai_1.ui import charts, components, state

__all__ = ["render"]


def render() -> None:
    current = state.current_state()
    config = state.config_for(current)
    components.page_header(
        "Oferta",
        f"Baza: {state.DATABASE_LABELS[current.database]}",
    )

    with components.connection(config) as conn:
        if conn is None:
            return
        offers = services.list_offers(conn)
        if not offers:
            st.info("Brak ofert w bazie — najpierw zbierz dane (S4) albo wygeneruj demo.")
            return

        now = datetime.now(UTC)
        search = st.text_input(
            "Szukaj oferty (nazwa lub ID)",
            value=current.offer_query,
            key=f"offer-query-{current.database}",
        )
        statuses = ["all", *services.offer_statuses(conn)]
        status_index = (
            statuses.index(current.offer_status) if current.offer_status in statuses else 0
        )
        status = st.selectbox(
            "Status",
            statuses,
            index=status_index,
            format_func=lambda value: "wszystkie" if value == "all" else value,
            key=f"offer-status-{current.offer_status}",
        )
        sort = st.selectbox(
            "Sortuj według",
            state.OFFER_SORT_CHOICES,
            index=state.OFFER_SORT_CHOICES.index(current.offer_sort),
            format_func=state.OFFER_SORT_LABELS.get,
            key=f"offer-sort-{current.offer_sort}",
        )
        if (search, status, sort) != (
            current.offer_query,
            current.offer_status,
            current.offer_sort,
        ):
            state.update(
                replace(
                    current,
                    offer_query=search,
                    offer_status=status,
                    offer_sort=sort,
                )
            )
            st.rerun()

        catalog = services.offer_catalog(
            conn,
            search=search,
            status=status,
            sort=sort,
            range_key=current.range_key,
            metric=cast(Metric, "visits" if current.metric == "both" else current.metric),
            now=now,
        )
        if not catalog:
            st.info("Brak ofert spełniających filtry — zmień frazę albo status.")
            return

        ids = [row.item.offer.offer_id for row in catalog]
        names = {
            row.item.offer.offer_id: f"{row.item.offer.name} ({row.item.offer.offer_id})"
            for row in catalog
        }
        with st.expander(f"Lista ofert ({len(catalog)})", expanded=False):
            st.dataframe(
                [
                    {
                        "Oferta": row.item.offer.name,
                        "ID": row.item.offer.offer_id,
                        "Status": row.item.offer.status,
                        "Ostatni snapshot": format_datetime(row.item.last_captured_at),
                        "Przyrost": f"+{format_number(row.gained)}",
                    }
                    for row in catalog
                ],
                hide_index=True,
                width="stretch",
            )

        selected = st.multiselect(
            "Oferty do porównania (2–5)",
            ids,
            default=[offer_id for offer_id in current.offers if offer_id in ids][
                : services.MAX_COMPARISON_OFFERS
            ],
            format_func=names.get,
            max_selections=services.MAX_COMPARISON_OFFERS,
            key=f"compare-pick-{len(current.offers)}",
        )
        if tuple(selected) != tuple(offer_id for offer_id in current.offers if offer_id in ids):
            state.update(replace(current, offers=tuple(selected)))
            st.rerun()

        detail_id = current.detail_offer if current.detail_offer in ids else ids[0]
        chosen_id = st.selectbox(
            "Oferta",
            ids,
            index=ids.index(detail_id),
            format_func=names.get,
            key=f"offer-selector-{detail_id}",
        )
        if chosen_id != current.detail_offer:
            state.update(replace(current, detail_offer=chosen_id))
            st.rerun()

        chosen_range = st.radio(
            "Zakres",
            state.RANGE_CHOICES,
            index=state.RANGE_CHOICES.index(current.range_key),
            format_func=range_label,
            horizontal=True,
            key=f"range-selector-{current.range_key}",
        )
        if chosen_range != current.range_key:
            state.update(replace(current, range_key=chosen_range))
            st.rerun()

        chosen_metric = st.radio(
            "Metryka",
            state.METRIC_CHOICES,
            index=state.METRIC_CHOICES.index(current.metric),
            format_func=state.METRIC_CHOICE_LABELS.get,
            horizontal=True,
            key=f"metric-selector-{current.metric}",
        )
        if chosen_metric != current.metric:
            state.update(replace(current, metric=chosen_metric))
            st.rerun()

        start: datetime | None = None
        end: datetime | None = None
        if chosen_range == "custom":
            start, end = _custom_range(current, now)
            if start is None:
                return

        view = services.offer_view(
            conn,
            chosen_id,
            range_key=chosen_range,
            metric=chosen_metric,
            now=now,
            start=start,
            end=end,
        )
        if view is None:
            st.error("Nie znaleziono oferty w bazie.")
            return
        _render_offer(
            conn,
            view,
            metric=chosen_metric,
            range_text=range_label(chosen_range),
            now=now,
        )
        _whats_new_block(
            conn,
            chosen_id,
            metric=cast(Metric, "visits" if chosen_metric == "both" else chosen_metric),
            now=now,
        )
        _events_and_annotations(
            conn,
            config,
            chosen_id,
            view,
            now=now,
            allow_sync=current.database == "sandbox",
        )
        _alerts_block(conn, chosen_id, now=now)


def _render_offer(
    conn: sqlite3.Connection,
    view: services.OfferView,
    *,
    metric: Metric | str,
    range_text: str,
    now: datetime,
) -> None:
    since = view.points[0].captured_at if view.points else None
    until = view.points[-1].captured_at if view.points else None
    events = services.events_for_offer(conn, view.offer.offer_id, since=since, until=until)
    annotations = services.annotations_for_offer(
        conn, view.offer.offer_id, since=since, until=until
    )
    markers = [
        charts.ChartMarker(at=event.occurred_at, label=event_label(event.type))
        for event in events
    ] + [
        charts.ChartMarker(at=item.occurred_at, label=item.label, kind="annotation")
        for item in annotations
    ]
    figure = charts.build_figure(
        view, metric=metric, range_text=range_text, markers=markers
    )
    st.plotly_chart(figure, width="stretch", key=f"chart-{metric}")

    summary = view.summary
    _summary_card(view, metric=metric)
    source_text = "dane syntetyczne" if view.series.is_synthetic else "dane z API"
    extra = ""
    if view.secondary_series is not None and view.secondary_series.points:
        extra = (
            f" · obserwujący teraz: "
            f"{format_number(view.secondary_series.points[-1].value)}"
        )
    st.caption(
        f"Źródło: {source_text}{extra} · anomalie: {len(summary.anomalies)} · "
        f"luki > 2 h: {view.gaps} · snapshoty w bazie: {format_number(view.snapshots)} · "
        f"aktualizacja danych: {format_datetime(view.freshness.last_captured_at)}"
    )

    if view.series.is_synthetic:
        components.synthetic_badge()
        st.warning("DANE SYNTETYCZNE — to nie są dane z API, nie wyciągaj z nich wniosków o rynku.")
    if summary.n_points == 0:
        st.info(
            "Brak punktów w tym przedziale — uruchom zbieranie (S4) albo wybierz szerszy zakres."
        )
    elif summary.n_points < 6 or summary.coverage < 0.3:
        st.info(
            "Mało danych w przedziale — trend jest niepewny "
            f"({points_label(summary.n_points)}, pokrycie {format_percent(summary.coverage)})."
        )


def _summary_card(view: services.OfferView, *, metric: Metric | str) -> None:
    summary = view.summary
    st.subheader(f"Podsumowanie: {metric_label(metric)}")
    if summary.n_points == 0:
        st.caption("Brak danych do podsumowania.")
        return

    first, second, third, fourth = st.columns(4)
    first.metric("Minimum", format_number(summary.min))
    second.metric("Maksimum", format_number(summary.max))
    third.metric("Średnia", format_decimal(summary.mean, 1))
    fourth.metric("Przyrost", f"+{format_number(summary.gained_total)}")

    fifth, sixth, seventh, eighth = st.columns(4)
    fifth.metric("Trend", summary.trend_label)
    sixth.metric("Nachylenie / dzień", format_decimal(summary.slope_per_day, 2))
    seventh.metric("Pokrycie", format_percent(summary.coverage))
    eighth.metric("Punkty", summary.n_points)

    if summary.start and summary.end:
        st.caption(f"Dane od {format_datetime(summary.start)} do {format_datetime(summary.end)}.")


def _custom_range(
    current: state.UiState, now: datetime
) -> tuple[datetime | None, datetime | None]:
    today = now.astimezone(LOCAL_TZ).date()
    default_from = today - timedelta(days=30)
    parsed_from = _safe_date(current.date_from, default_from)
    parsed_to = _safe_date(current.date_to, today)

    left, right = st.columns(2)
    start_date = left.date_input("Od", value=parsed_from, max_value=today)
    end_date = right.date_input("Do", value=parsed_to, max_value=today)

    if (start_date.isoformat(), end_date.isoformat()) != (current.date_from, current.date_to):
        state.update(
            replace(current, date_from=start_date.isoformat(), date_to=end_date.isoformat())
        )
        st.rerun()

    if start_date > end_date:
        st.error("Data „Od” jest późniejsza niż „Do” — popraw zakres.")
        return None, None

    start = datetime.combine(start_date, time.min, tzinfo=LOCAL_TZ)
    end = datetime.combine(end_date, time(23, 59, 59), tzinfo=LOCAL_TZ)
    return start, end


def _safe_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except ValueError:
        return fallback


# --- S5: co nowego, zdarzenia, adnotacje, alerty ----------------------------
def _whats_new_block(
    conn: sqlite3.Connection, offer_id: str, *, metric: Metric, now: datetime
) -> None:
    news = services.whats_new(conn, offer_id, metric=metric, now=now)
    with st.container(border=True):
        st.markdown("#### Co nowego od ostatniej wizyty")
        if news.first_visit:
            st.caption(
                "Pierwsza wizyta na tej ofercie — od teraz zapamiętujemy punkt odniesienia."
            )
        else:
            delta = "—" if news.level_delta is None else f"{news.level_delta:+d}"
            st.write(
                f"Od {format_datetime(news.since)}: zmiana poziomu **{delta}**, "
                f"nowe snapshoty: {news.new_snapshots}, "
                f"nowe anomalie: {news.new_anomalies}, "
                f"nowe zdarzenia: {news.new_events}."
            )
    services.mark_offer_seen(conn, offer_id, now=now)


def _events_and_annotations(
    conn: sqlite3.Connection,
    config: object,
    offer_id: str,
    view: services.OfferView,
    *,
    now: datetime,
    allow_sync: bool,
) -> None:
    st.divider()
    st.subheader("Zdarzenia i adnotacje")
    since = view.points[0].captured_at if view.points else None
    until = view.points[-1].captured_at if view.points else now
    read_only = bool(getattr(config, "is_prod", False)) or not allow_sync

    left, right = st.columns(2)
    with left:
        st.markdown("**Zdarzenia z API**")
        if st.button("Pobierz zdarzenia", key=f"sync-{offer_id}", disabled=read_only):
            try:
                added = services.sync_offer_events(conn, config)  # type: ignore[arg-type]
            except (AuthError, EventError, AppError) as exc:
                st.error(f"Zdarzenia niedostępne: {exc}")
            else:
                st.session_state["events-message"] = f"Zapisano {added} nowych zdarzeń."
                st.rerun()
        message = st.session_state.pop("events-message", None)
        if message:
            st.success(message)

        events = services.events_for_offer(conn, offer_id, since=since, until=until)
        if events:
            st.dataframe(
                [
                    {
                        "Kiedy": format_datetime(event.occurred_at),
                        "Zdarzenie": event_label(event.type),
                        "Typ API": event.type,
                    }
                    for event in events
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption(
                "Brak zdarzeń w tym przedziale. Endpoint zwraca tylko ostatnie 24 h; "
                "przy braku uprawnień użyj adnotacji ręcznych."
            )

    with right:
        st.markdown("**Adnotacje ręczne**")
        today = now.astimezone(LOCAL_TZ).date()
        with st.form(f"annotation-{offer_id}", clear_on_submit=True):
            when = st.date_input("Data zdarzenia", value=today, max_value=today)
            label = st.text_input("Etykieta", placeholder="np. obniżka ceny")
            note = st.text_area("Notatka (opcjonalnie)")
            submitted = st.form_submit_button("Dodaj adnotację", disabled=read_only)
        if submitted and label.strip():
            services.add_annotation(
                conn,
                offer_id=offer_id,
                occurred_at=datetime.combine(when, time(12, 0), tzinfo=LOCAL_TZ),
                label=label.strip(),
                note=note.strip() or None,
                now=now,
            )
            st.rerun()

        annotations = services.annotations_for_offer(conn, offer_id)
        if annotations:
            st.dataframe(
                [
                    {
                        "Data": format_datetime(item.occurred_at),
                        "Etykieta": item.label,
                        "Notatka": item.note or "—",
                    }
                    for item in annotations
                ],
                hide_index=True,
                width="stretch",
            )
            options = [item.id for item in annotations]
            labels = {
                item.id: f"{item.occurred_at:%d.%m.%Y} — {item.label}"
                for item in annotations
            }
            chosen = st.selectbox(
                "Usuń adnotację",
                options,
                format_func=labels.get,
                key=f"del-annotation-{offer_id}",
            )
            if st.button("Usuń adnotację", key=f"delete-annotation-{offer_id}"):
                services.delete_annotation(conn, int(chosen))
                st.rerun()
        else:
            st.caption("Brak adnotacji — dodaj pierwszą (np. zmiana ceny, kampania).")


def _alerts_block(conn: sqlite3.Connection, offer_id: str, *, now: datetime) -> None:
    st.divider()
    st.subheader("Alerty progowe")
    hits = [hit for hit in services.alert_hits(conn, now=now) if hit.offer.offer_id == offer_id]
    for hit in hits:
        st.warning(
            f"{alert_rule_label(hit.rule.kind)}: szczyt {format_number(hit.peak_value)} → "
            f"teraz {format_number(hit.last_value)} "
            f"(spadek {format_number(hit.drop_abs)}, {format_percent(hit.drop_pct)})."
        )
    if not hits:
        st.caption("Brak aktywnych alertów dla tej oferty.")

    with st.form(f"alert-{offer_id}", clear_on_submit=True):
        kind = st.selectbox(
            "Rodzaj alertu",
            ["pct_drop", "abs_drop"],
            format_func=alert_rule_label,
        )
        threshold = st.number_input(
            "Próg (0,2 = 20% albo liczba sztuk)",
            min_value=0.0,
            value=0.2 if kind == "pct_drop" else 10.0,
            step=0.05 if kind == "pct_drop" else 1.0,
        )
        window_days = st.number_input("Okno (dni)", min_value=1, value=30, step=1)
        added = st.form_submit_button("Dodaj alert")
    if added:
        services.add_alert_rule(
            conn,
            kind=kind,
            threshold=float(threshold),
            window_days=int(window_days),
            offer_id=offer_id,
            now=now,
        )
        st.rerun()

    rules = [
        rule
        for rule in services.alert_rules(conn)
        if rule.offer_id in (None, offer_id)
    ]
    if rules:
        st.caption(
            "Reguły: "
            + "; ".join(
                f"{alert_rule_label(rule.kind)} ≥ {rule.threshold:g} w {rule.window_days} d"
                for rule in rules
            )
        )
        rule_ids = [rule.id for rule in rules]
        chosen_rule = st.selectbox("Usuń regułę", rule_ids, key=f"del-rule-{offer_id}")
        if st.button("Usuń regułę", key=f"delete-rule-{offer_id}"):
            services.delete_alert_rule(conn, int(chosen_rule))
            st.rerun()
