"""Testy generatora danych demo (SPEC §12): determinizm, izolacja od API, wzorce."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

from view_tracker_ai_1 import storage
from view_tracker_ai_1.models import Offer, Snapshot

END = datetime(2026, 10, 28, 0, 0, tzinfo=UTC)
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "seed_demo_data.py"


@pytest.fixture(scope="module")
def seed_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_demo_data", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Rejestracja w `sys.modules` jest konieczna: dataclasses ze `slots=True` szukają
    # tam modułu, żeby rozwiązać adnotacje (inaczej AttributeError: 'NoneType').
    sys.modules["seed_demo_data"] = module
    spec.loader.exec_module(module)
    return module


def fresh_db(tmp_path: Path, name: str = "demo.db") -> sqlite3.Connection:
    conn = storage.connect(tmp_path / name)
    storage.init_db(conn)
    return conn


def rows(conn: sqlite3.Connection) -> list[tuple[str, str, int]]:
    return [
        (str(row["offer_id"]), str(row["captured_at"]), int(row["visits_count"]))
        for row in conn.execute("SELECT * FROM snapshots ORDER BY offer_id, captured_at")
    ]


def test_seed_is_deterministic(seed_module: ModuleType, tmp_path: Path) -> None:
    first = fresh_db(tmp_path, "a.db")
    second = fresh_db(tmp_path, "b.db")

    seed_module.seed_demo_database(first, seed=42, days=3, end=END)
    seed_module.seed_demo_database(second, seed=42, days=3, end=END)

    assert rows(first) == rows(second)
    first.close()
    second.close()


def test_seed_differs_for_another_seed(seed_module: ModuleType, tmp_path: Path) -> None:
    first = fresh_db(tmp_path, "c.db")
    second = fresh_db(tmp_path, "d.db")

    seed_module.seed_demo_database(first, seed=42, days=3, end=END)
    seed_module.seed_demo_database(second, seed=7, days=3, end=END)

    assert rows(first) != rows(second)
    first.close()
    second.close()


def test_seed_refuses_database_with_api_snapshots(seed_module: ModuleType, tmp_path: Path) -> None:
    conn = fresh_db(tmp_path, "api.db")
    storage.save_collection(
        conn,
        offers=[Offer("1", "Prawdziwa", "ACTIVE", END, END)],
        snapshots=[Snapshot("1", END, 10, 1, source="api")],
    )

    with pytest.raises(seed_module.DemoDataError, match="zawiera snapshoty z API"):
        seed_module.seed_demo_database(conn, seed=42, days=2, end=END)

    assert storage.count_snapshots(conn) == 1  # nic nie dopisano
    conn.close()


def test_seed_writes_only_synthetic_rows(seed_module: ModuleType, tmp_path: Path) -> None:
    conn = fresh_db(tmp_path)
    result = seed_module.seed_demo_database(conn, seed=42, days=2, end=END)

    sources = {str(row["source"]) for row in conn.execute("SELECT source FROM snapshots")}
    assert sources == {"synthetic"}
    assert result.offers == len(seed_module.DEMO_OFFERS)
    assert result.snapshots == storage.count_snapshots(conn)
    conn.close()


def test_gap_offer_has_missing_hours(seed_module: ModuleType, tmp_path: Path) -> None:
    conn = fresh_db(tmp_path)
    seed_module.seed_demo_database(conn, seed=42, days=10, end=END)

    total = storage.count_snapshots(conn, offer_id="1005")
    conn.close()

    assert 10 * 24 * 0.5 < total < 10 * 24


def test_plateau_offer_is_flat(seed_module: ModuleType, tmp_path: Path) -> None:
    conn = fresh_db(tmp_path)
    seed_module.seed_demo_database(conn, seed=42, days=2, end=END)

    values = {
        int(row["visits_count"])
        for row in conn.execute("SELECT visits_count FROM snapshots WHERE offer_id = '1003'")
    }
    conn.close()

    assert values == {300}


def test_anomaly_offer_has_exactly_one_drop(seed_module: ModuleType, tmp_path: Path) -> None:
    conn = fresh_db(tmp_path)
    seed_module.seed_demo_database(conn, seed=42, days=10, end=END)

    values = [
        int(row["visits_count"])
        for row in conn.execute(
            "SELECT visits_count FROM snapshots WHERE offer_id = '1004' ORDER BY captured_at"
        )
    ]
    conn.close()

    drops = [
        later - earlier
        for earlier, later in zip(values, values[1:], strict=False)
        if later < earlier
    ]
    assert len(drops) == 1
    assert drops[0] < 0


def test_reseeding_replaces_previous_demo_rows(seed_module: ModuleType, tmp_path: Path) -> None:
    conn = fresh_db(tmp_path)
    seed_module.seed_demo_database(conn, seed=42, days=2, end=END)
    first_count = storage.count_snapshots(conn)

    seed_module.seed_demo_database(conn, seed=42, days=2, end=END + timedelta(days=1))
    second_count = storage.count_snapshots(conn)
    conn.close()

    assert first_count == second_count  # stara seria zastąpiona, nie dublowana


def test_naive_end_is_rejected(seed_module: ModuleType, tmp_path: Path) -> None:
    conn = fresh_db(tmp_path)

    with pytest.raises(seed_module.DemoDataError, match="strefę"):
        seed_module.seed_demo_database(conn, seed=42, days=1, end=datetime(2026, 10, 28))

    conn.close()


def test_non_positive_days_are_rejected(seed_module: ModuleType, tmp_path: Path) -> None:
    conn = fresh_db(tmp_path)

    with pytest.raises(seed_module.DemoDataError, match="dodatnia"):
        seed_module.seed_demo_database(conn, seed=42, days=0, end=END)

    conn.close()
