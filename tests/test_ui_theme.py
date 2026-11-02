"""Testy motywu „warm glass”: lokalny CSS, dekoracje tła, konfiguracja Streamlita."""

from __future__ import annotations

import tomllib
from pathlib import Path

from view_tracker_ai_1.ui import theme

CONFIG = Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml"


def test_theme_uses_glass_and_warm_background() -> None:
    assert "backdrop-filter" in theme.CSS
    assert theme.GLASS in theme.CSS
    assert "linear-gradient(135deg, #e2c6b6" in theme.CSS
    assert "--vt-accent" in theme.CSS


def test_theme_has_decorative_orbs_and_rings() -> None:
    assert theme.DECOR.count("vt-orb ") == 3
    assert theme.DECOR.count("vt-ring ") == 2
    assert 'aria-hidden="true"' in theme.DECOR


def test_theme_css_has_no_external_assets() -> None:
    combined = theme.CSS + theme.DECOR
    assert "http://" not in combined
    assert "https://" not in combined
    assert "url(" not in combined


def test_streamlit_theme_config_is_light_and_warm() -> None:
    with CONFIG.open("rb") as handle:
        config = tomllib.load(handle)

    palette = config["theme"]
    assert palette["base"] == "light"
    assert palette["primaryColor"].lower() == "#f2601d"
    assert palette["textColor"].lower() == "#2f170d"
    assert palette["backgroundColor"].lower() == "#d2a996"


def test_inject_renders_decor_and_style() -> None:
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_string(
        "from view_tracker_ai_1.ui import theme\n"
        "theme.inject()\n"
    )
    at.run()

    assert not at.exception
    values = " ".join(element.value for element in at.markdown)
    assert "vt-decor" in values
    assert "<style>" in values
