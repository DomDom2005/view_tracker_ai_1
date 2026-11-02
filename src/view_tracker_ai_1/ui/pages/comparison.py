"""Porównanie ofert i okresów — S1: placeholder, implementacja w S3."""

from __future__ import annotations

import streamlit as st

from view_tracker_ai_1.ui import components, state


def render() -> None:
    current = state.current_state()
    components.page_header(
        "Porównanie",
        f"Baza: {state.DATABASE_LABELS[current.database]} · zakres: {current.range_key}",
    )
    st.warning("Ta strona jest jeszcze pusta — powstanie w etapie S3.")
    st.markdown(
        "- porównanie 2–5 ofert na jednym wykresie (indeks 100 w pierwszym punkcie),\n"
        "- porównanie bieżącego okresu z poprzednim (przyrosty i zmiana procentowa),\n"
        "- tabela przyrostów per oferta."
    )
