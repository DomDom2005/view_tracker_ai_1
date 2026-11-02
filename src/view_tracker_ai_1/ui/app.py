"""Punkt wejścia aplikacji Streamlit 2.0 (SPEC-2.0 §8).

Uruchomienie: `python -m view_tracker_ai_1.ui` albo `streamlit run src/view_tracker_ai_1/ui/app.py`.
"""

from __future__ import annotations

import streamlit as st

from view_tracker_ai_1.errors import ConfigError
from view_tracker_ai_1.ui import components, state
from view_tracker_ai_1.ui.pages import comparison, data, offer, overview, settings

st.set_page_config(
    page_title="view_tracker_ai_1",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


def build_pages() -> list[st.Page]:
    """Strony aplikacji; domyślnie otwiera się Przegląd."""
    return [
        st.Page(overview.render, title="Przegląd", icon="📊", url_path="przeglad", default=True),
        st.Page(offer.render, title="Oferta", icon="📈", url_path="oferta"),
        st.Page(comparison.render, title="Porównanie", icon="⚖️", url_path="porownanie"),
        st.Page(data.render, title="Dane", icon="🔄", url_path="dane"),
        st.Page(settings.render, title="Ustawienia", icon="⚙️", url_path="ustawienia"),
    ]


def main() -> None:
    current = state.current_state()
    try:
        config = state.config_for(current)
    except ConfigError as exc:
        st.error(f"Błąd konfiguracji: {exc}")
        st.caption("Popraw `.env` (wzór w `.env.example`) albo wybierz inną bazę.")
        st.stop()

    components.sidebar(current, config)
    st.navigation(build_pages()).run()


main()
