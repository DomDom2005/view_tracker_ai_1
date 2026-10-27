"""Wyjątki aplikacji — wspólna baza i typy błędów z SPEC §9."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

MAX_BODY_LENGTH = 300


class AppError(Exception):
    """Baza dla wszystkich błędów aplikacji."""


class ConfigError(AppError):
    """Błędna lub niekompletna konfiguracja (np. brak wymaganej zmiennej środowiskowej)."""


class StorageError(AppError):
    """Błąd warstwy danych: nieobsługiwany schemat, naruszenie ograniczeń bazy."""


class AuthError(AppError):
    """Autoryzacja nieudana: brak tokena, odrzucone odświeżenie, odmowa użytkownika."""


class RateLimitError(AppError):
    """Limit zapytań wyczerpany po wszystkich ponowieniach (HTTP 429)."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ApiError(AppError):
    """Inny błąd API (4xx/5xx) albo błąd sieci po wyczerpaniu ponowień."""

    def __init__(self, message: str, *, status: int | None = None, body: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = _shorten(body)


class ValidationError(AppError):
    """HTTP 422: niepoprawne wartości pól. Niesie listę błędów z odpowiedzi API."""

    def __init__(
        self,
        message: str,
        errors: Iterable[Mapping[str, Any]] = (),
        *,
        status: int = 422,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.errors: tuple[Mapping[str, Any], ...] = tuple(errors)

    def describe(self) -> list[str]:
        """Czytelne linie do wypisania w CLI: kod, komunikat i ścieżka pola."""
        lines = []
        for error in self.errors:
            code = str(error.get("code") or "?")
            message = str(error.get("userMessage") or error.get("message") or "").strip()
            path = str(error.get("path") or "").strip()
            line = f"{code}: {message}" if message else code
            lines.append(f"{line} (pole: {path})" if path else line)
        return lines


def _shorten(text: str | None, limit: int = MAX_BODY_LENGTH) -> str | None:
    if text is None:
        return None
    stripped = " ".join(text.split())
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1] + "…"
