"""Generator danych syntetycznych (SPEC-2.0 FR-18, wcześniej SPEC §6 FR-8).

Dane są **deterministyczne** dla danego `seed` i `end`: ten sam seed daje te same
liczniki. Wszystko zapisujemy z `source='synthetic'`, a generator **odmawia** zapisu
do bazy, w której są rekordy z API — mieszanie źródeł jest zabronione.

Wejście z UI: `services.seed_demo`; z terminala: `scripts/seed_demo_data.py`.
"""

from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from view_tracker_ai_1 import storage
from view_tracker_ai_1.errors import AppError
from view_tracker_ai_1.models import Offer, Snapshot

DEFAULT_SEED = 42
DEFAULT_DAYS = 90
GAP_RATE = 0.35
"""Udział brakujących godzin w ofercie z lukami (do pokazania niepełnego `coverage`)."""

ANOMALY_START_RATIO = 0.62
"""Kiedy (jako część zakresu) wypada zamierzony spadek licznika w ofercie 1004."""

ANOMALY_DROP = 35


class DemoDataError(AppError):
    """Nie można wygenerować danych demo w tej bazie."""


@dataclass(frozen=True, slots=True)
class DemoOffer:
    """Przepis na jedną ofertę demo: wzorzec i punkt startowy."""

    offer_id: str
    name: str
    pattern: str
    base_visits: int
    step_visits: float
    base_watchers: int
    step_watchers: float
    noise: int


DEMO_OFFERS: tuple[DemoOffer, ...] = (
    DemoOffer("1001", "Suszarka do włosów Premium", "growth", 120, 1.6, 4, 0.05, 2),
    DemoOffer("1002", "Lokówka ceramiczna 25 mm", "decline", 900, -0.1, 40, -0.008, 0),
    DemoOffer("1003", "Szczotka jonizująca", "plateau", 300, 0.0, 15, 0.0, 0),
    DemoOffer("1004", "Prostownica z anomalią", "anomaly", 150, 1.1, 8, 0.02, 1),
    DemoOffer("1005", "Odkurzacz pionowy (luki w danych)", "gaps", 500, 0.5, 25, 0.01, 1),
)
"""Pięć ofert: wzrost, spadek, plateau, anomalia i luki — każdy wzorzec do pokazania.

`noise` trafia na **przyrosty**, nie na poziom: dzięki temu szum nie tworzy fałszywych
spadków licznika (każdy spadek w danych demo jest zamierzony).
"""


@dataclass(frozen=True, slots=True)
class SeedResult:
    """Co zostało zapisane — do pokazania w UI/CLI i do asercji w testach."""

    offers: int
    snapshots: int
    days: int
    seed: int
    end: datetime


def seed_demo_database(
    conn: sqlite3.Connection,
    *,
    seed: int = DEFAULT_SEED,
    days: int = DEFAULT_DAYS,
    end: datetime,
    offers: tuple[DemoOffer, ...] = DEMO_OFFERS,
) -> SeedResult:
    """Wygeneruj i zapisz dane syntetyczne. Zwraca liczbę ofert i snapshotów."""
    if days < 1:
        raise DemoDataError("Liczba dni musi być dodatnia.")
    if end.tzinfo is None:
        raise DemoDataError("Czas `end` musi mieć strefę (najlepiej UTC).")

    storage.init_db(conn)
    _refuse_api_data(conn)

    collections = []
    for spec in offers:
        rng = random.Random(f"{seed}:{spec.offer_id}")
        snapshots = _build_snapshots(spec, end=end, days=days, rng=rng)
        collections.append((spec, snapshots))

    total = 0
    _delete_demo_rows(conn, [spec.offer_id for spec in offers])
    for spec, snapshots in collections:
        first = snapshots[0].captured_at if snapshots else end
        inserted = storage.save_collection(
            conn,
            offers=[
                Offer(
                    offer_id=spec.offer_id,
                    name=spec.name,
                    status="ACTIVE",
                    first_seen_at=first,
                    last_seen_at=end,
                )
            ],
            snapshots=snapshots,
        )
        total += inserted

    return SeedResult(
        offers=len(offers),
        snapshots=total,
        days=days,
        seed=seed,
        end=end,
    )


def _build_snapshots(
    spec: DemoOffer, *, end: datetime, days: int, rng: random.Random
) -> list[Snapshot]:
    """Snapshoty godzinowe dla jednego wzorca, od `end - days` do `end`.

    Poziom licznika narasta od przyrostów (jak prawdziwy licznik wyświetleń), więc
    seria rośnie monotonicznie i szum nie produkuje fałszywych „spadków licznika”.
    Jedyne spadki to te zamierzone we wzorcu „decline” i „anomaly”.
    """
    moments = [end - timedelta(hours=back) for back in range(days * 24 - 1, -1, -1)]
    anomaly_at = int(len(moments) * ANOMALY_START_RATIO)
    gap_day = (end - timedelta(days=days // 3)).date()

    level = float(spec.base_visits)
    snapshots: list[Snapshot] = []
    for index, moment in enumerate(moments):
        if spec.pattern == "gaps" and _is_missing_hour(moment, gap_day, rng):
            continue

        level += _increment(spec, rng)
        if spec.pattern == "anomaly" and index == anomaly_at:
            # Jeden zamierzony spadek: tak wygląda okno kroczące (SPEC v1 §4.2).
            level = max(level - ANOMALY_DROP, 0.0)
        visits = max(int(round(level)), 0)

        watchers = max(spec.base_watchers + spec.step_watchers * index, 0)
        snapshots.append(
            Snapshot(
                offer_id=spec.offer_id,
                captured_at=moment,
                visits_count=visits,
                watchers_count=int(round(watchers)),
                source="synthetic",
            )
        )
    return snapshots


def _is_missing_hour(moment: datetime, gap_day: date, rng: random.Random) -> bool:
    """Czy pominąć snapshot: cały wybrany dzień plus losowe godziny (wzorzec „gaps”)."""
    return moment.date() == gap_day or rng.random() < GAP_RATE


def _increment(spec: DemoOffer, rng: random.Random) -> float:
    """Godzinowy przyrost licznika; nigdy ujemny poza wzorcem „decline”."""
    if spec.pattern == "decline":
        return spec.step_visits
    noise = rng.randint(-spec.noise, spec.noise) if spec.noise else 0
    return max(spec.step_visits + noise, 0.0)


def _refuse_api_data(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(*) AS n FROM snapshots WHERE source = 'api'").fetchone()
    if row is not None and int(row["n"]) > 0:
        raise DemoDataError(
            "Ta baza zawiera snapshoty z API — danych syntetycznych nie wolno z nimi mieszać "
            "(SPEC-2.0 FR-18). Wskaż bazę demo (`data/demo.db`)."
        )


def _delete_demo_rows(conn: sqlite3.Connection, offer_ids: list[str]) -> None:
    placeholders = ",".join("?" * len(offer_ids))
    conn.execute(
        f"DELETE FROM snapshots WHERE source = 'synthetic' AND offer_id IN ({placeholders})",
        offer_ids,
    )


def default_end(now: datetime | None = None) -> datetime:
    """Koniec zakresu: bieżąca godzina UTC (bez minut/sekund) — powtarzalne dane."""
    moment = now if now is not None else datetime.now(UTC)
    return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
