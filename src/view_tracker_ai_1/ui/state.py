"""Stan aplikacji 2.0: URL ↔ wybór bazy, ofert, zakresu i metryki; konfiguracja z env.

Warstwa cienka: parsowanie i budowanie parametrów jest czystymi funkcjami (testy bez
Streamlita), a `current_state`/`update` tylko spinają je z `st.query_params`/`session_state`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st

from view_tracker_ai_1.config import Config, default_db_path
from view_tracker_ai_1.services import RANGE_KEYS

DATABASE_NAMES: tuple[str, ...] = ("sandbox", "prod", "demo")
DATABASE_LABELS: Mapping[str, str] = {
    "sandbox": "Sandbox (API)",
    "prod": "Produkcja (tylko odczyt)",
    "demo": "Dane demo (syntetyczne)",
}

RANGE_CHOICES: tuple[str, ...] = (*RANGE_KEYS, "custom")
METRIC_CHOICES: tuple[str, ...] = ("visits", "watchers", "both")
METRIC_CHOICE_LABELS: Mapping[str, str] = {
    "visits": "wyświetlenia",
    "watchers": "obserwujący",
    "both": "oba",
}

DEFAULT_DATABASE = "sandbox"
DEFAULT_RANGE = "30d"
DEFAULT_METRIC = "visits"

DEMO_DB_PATH = Path("data") / "demo.db"


@dataclass(frozen=True, slots=True)
class UiState:
    """To, co trzymamy w URL: baza, wybrane oferty, zakres i metryka."""

    database: str = DEFAULT_DATABASE
    offers: tuple[str, ...] = ()
    range_key: str = DEFAULT_RANGE
    metric: str = DEFAULT_METRIC
    date_from: str | None = None
    date_to: str | None = None


def parse_params(params: Mapping[str, str]) -> UiState:
    """Zamień parametry URL na stan; nieznane wartości zastępujemy domyślnymi."""
    database = params.get("db", DEFAULT_DATABASE)
    if database not in DATABASE_NAMES:
        database = DEFAULT_DATABASE

    raw_offers = params.get("offer", "")
    offers = tuple(item.strip() for item in raw_offers.split(",") if item.strip())

    range_key = params.get("range", DEFAULT_RANGE)
    if range_key not in RANGE_CHOICES:
        range_key = DEFAULT_RANGE

    metric = params.get("metric", DEFAULT_METRIC)
    if metric not in METRIC_CHOICES:
        metric = DEFAULT_METRIC

    return UiState(
        database=database,
        offers=offers,
        range_key=range_key,
        metric=metric,
        date_from=_parse_date(params.get("from")),
        date_to=_parse_date(params.get("to")),
    )


def params_for(state: UiState) -> dict[str, str]:
    """Parametry URL dla stanu (kanoniczna kolejność, oferty po przecinku)."""
    params = {"db": state.database, "range": state.range_key, "metric": state.metric}
    if state.offers:
        params["offer"] = ",".join(state.offers)
    if state.date_from and state.date_to:
        params["from"] = state.date_from
        params["to"] = state.date_to
    return params


def resolve_db_path(database: str) -> Path:
    """Ścieżka bazy dla wybranej pozycji w UI (`demo` ma własny plik)."""
    if database == "demo":
        return DEMO_DB_PATH
    return default_db_path("prod" if database == "prod" else "sandbox")


def database_env(database: str) -> str:
    """Środowisko API odpowiadające bazie (demo korzysta z konfiguracji sandboxa)."""
    return "prod" if database == "prod" else "sandbox"


def config_for(state: UiState) -> Config:
    """Konfiguracja aplikacji dla wybranej bazy (env + ścieżka nadpisane jawnie)."""
    return Config.from_env().with_overrides(
        env=database_env(state.database),
        db_path=resolve_db_path(state.database),
    )


def current_state() -> UiState:
    """Stan z URL; w testach/kliknięciach może przyjść z `session_state`."""
    params = {key: str(value) for key, value in st.query_params.items()}
    if params:
        return parse_params(params)
    stored: dict[str, Any] = st.session_state
    if not {"db", "offer", "range", "metric"} & set(stored):
        return UiState()
    offers = stored.get("offer") or ()
    if isinstance(offers, str):
        offers = (offers,)
    return parse_params(
        {
            "db": str(stored.get("db", DEFAULT_DATABASE)),
            "offer": ",".join(offers),
            "range": str(stored.get("range", DEFAULT_RANGE)),
            "metric": str(stored.get("metric", DEFAULT_METRIC)),
            "from": str(stored.get("date_from", "") or ""),
            "to": str(stored.get("date_to", "") or ""),
        }
    )


def update(state: UiState) -> None:
    """Zapisz stan w URL i w `session_state` (dla testów AppTest bez query_params)."""
    for key in ("db", "offer", "range", "metric", "from", "to"):
        if key in st.query_params:
            del st.query_params[key]
    for key, value in params_for(state).items():
        st.query_params[key] = value
    st.session_state["db"] = state.database
    st.session_state["offer"] = state.offers
    st.session_state["range"] = state.range_key
    st.session_state["metric"] = state.metric
    st.session_state["date_from"] = state.date_from
    st.session_state["date_to"] = state.date_to


def with_database(state: UiState, database: str) -> UiState:
    """Zmień bazę, zachowując resztę wyboru (adres widoku pozostaje sensowny)."""
    return replace(state, database=database)


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None
