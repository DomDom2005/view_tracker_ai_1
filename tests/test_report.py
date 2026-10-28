"""Testy raportu HTML (SPEC §12): autoescape, badge, samodzielność, komentarz."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from view_tracker_ai_1 import ai_comment, report
from view_tracker_ai_1.models import Offer, Series, SeriesPoint

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


def make_offer(name: str = "Suszarka", offer_id: str = "1001") -> Offer:
    return Offer(offer_id=offer_id, name=name, status="ACTIVE", first_seen_at=NOW, last_seen_at=NOW)


def make_series(*, source: str = "api", hours: int = 48, start_value: int = 100) -> Series:
    points = tuple(
        SeriesPoint(
            captured_at=NOW - timedelta(hours=hours - 1 - index),
            value=start_value + index * 3,
        )
        for index in range(hours)
    )
    return Series("1001", "visits", points, source)  # type: ignore[arg-type]


def build(
    *,
    name: str = "Suszarka",
    source: str = "api",
    ranges: tuple[str, ...] = ("24h",),
    hours: int = 48,
    generator: ai_comment.CommentGenerator | None = None,
    env: str = "sandbox",
) -> report.Report:
    """Domyślnie 48 h danych i przedział 24 h — pokrycie 100%, więc bramka AI przepuszcza."""
    offer = make_offer(name=name)
    series = make_series(source=source, hours=hours)
    return report.build_report(
        None,
        series_by_offer={offer.offer_id: (offer, series)},
        env=env,
        ranges=ranges,
        metric="visits",
        generator=generator or ai_comment.FakeCommentGenerator(),
        now=NOW,
    )


def test_report_contains_offer_chart_and_table() -> None:
    built = build()

    assert "<!doctype html>" in built.html
    assert "Suszarka" in built.html
    assert 'src="data:image/png;base64,' in built.html
    assert "Suma przyrostów" in built.html
    assert "Pokrycie danych" in built.html
    assert len(built.offers) == 1
    assert len(built.offers[0].cards) == 1


def test_report_escapes_offer_name() -> None:
    built = build(name="<script>alert('x')</script> Robot")

    assert "<script>alert" not in built.html
    assert "&lt;script&gt;" in built.html


def test_report_marks_synthetic_data() -> None:
    built = build(source="synthetic")

    assert built.is_synthetic is True
    assert built.env_label == "DEMO"
    assert "DANE SYNTETYCZNE" in built.html
    assert 'class="badge badge-demo"' in built.html


def test_report_badge_uses_environment_for_api_data() -> None:
    built = build(source="api", env="prod")

    assert built.env_label == "PROD"
    assert 'class="badge badge-prod"' in built.html


def test_report_is_self_contained() -> None:
    html = build().html

    assert "http://" not in html
    assert "https://" not in html
    assert "<link" not in html
    assert "<script" not in html
    assert html.count("data:image/png;base64,") == 1


def test_report_includes_comment_and_ai_flag() -> None:
    built = build()

    assert built.ai_enabled is False  # atrapa
    assert "komentarz bez AI" in built.html
    assert "Komentarz (bez AI)" in built.html


def test_report_marks_ai_as_enabled_for_a_real_generator() -> None:
    class FakeModel:
        def generate(self, summary, *, offer_name, range_key, metric):  # noqa: ANN001, ANN202
            return "Komentarz z modelu."

    built = build(generator=FakeModel())

    assert built.ai_enabled is True
    assert "Komentarz z modelu." in built.html


def test_report_prints_gate_message_for_thin_data() -> None:
    built = build(hours=3)

    assert "Za mało danych" in built.html


def test_report_skips_ranges_without_data() -> None:
    offer = make_offer()
    old = Series(
        "1001",
        "visits",
        (SeriesPoint(captured_at=NOW - timedelta(days=30), value=5),),
        "api",
    )

    built = report.build_report(
        None,
        series_by_offer={offer.offer_id: (offer, old)},
        env="sandbox",
        ranges=("24h",),
        metric="visits",
        generator=ai_comment.FakeCommentGenerator(),
        now=NOW,
    )

    assert built.offers == ()
    assert "Brak danych do pokazania" in built.html


def test_report_without_ranges_is_rejected() -> None:
    with pytest.raises(ValueError, match="co najmniej jednego"):
        build(ranges=())


def test_write_report_creates_parent_directories(tmp_path: Path) -> None:
    built = build()
    target = tmp_path / "raporty" / "podkatalog" / "raport.html"

    written = report.write_report(built, target)

    assert written == target
    assert target.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_report_formats_generation_time_in_local_zone() -> None:
    built = build()

    assert report.format_local(NOW) == "2026-10-28 13:00"
    assert "2026-10-28 13:00" in built.html


def test_series_for_offer_reads_offer_and_series() -> None:
    from view_tracker_ai_1 import storage
    from view_tracker_ai_1.models import Snapshot

    conn = storage.connect(":memory:")
    storage.init_db(conn)
    storage.save_collection(
        conn,
        offers=[make_offer(name="Lokówka")],
        snapshots=[
            Snapshot("1001", NOW - timedelta(hours=1), 10, 1, source="synthetic"),
            Snapshot("1001", NOW, 12, 1, source="synthetic"),
        ],
    )

    offer, series = report.series_for_offer(conn, "1001", "visits")

    assert offer.name == "Lokówka"
    assert [point.value for point in series.points] == [10, 12]
    assert series.is_synthetic is True
    conn.close()


def test_series_for_offer_rejects_unknown_offer() -> None:
    from view_tracker_ai_1 import storage

    conn = storage.connect(":memory:")
    storage.init_db(conn)

    with pytest.raises(LookupError):
        report.series_for_offer(conn, "404", "visits")

    conn.close()
