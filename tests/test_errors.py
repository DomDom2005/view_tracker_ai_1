"""Testy wyjątków: hierarchia, dane niesione przez błędy, czytelny opis 422."""

from __future__ import annotations

import pytest

from view_tracker_ai_1 import errors


def test_exceptions_share_common_base() -> None:
    for exception_type in (
        errors.ConfigError,
        errors.StorageError,
        errors.AuthError,
        errors.RateLimitError,
        errors.ApiError,
        errors.ValidationError,
    ):
        assert issubclass(exception_type, errors.AppError)


def test_api_error_keeps_status_and_shortens_body() -> None:
    error = errors.ApiError("boom", status=500, body="x" * 1000)
    assert error.status == 500
    assert error.body is not None
    assert len(error.body) <= errors.MAX_BODY_LENGTH
    assert error.body.endswith("…")


def test_api_error_without_body() -> None:
    assert errors.ApiError("boom").body is None


def test_validation_error_describe_includes_path_and_message() -> None:
    error = errors.ValidationError(
        "Niepoprawne dane",
        [
            {
                "code": "PARAMETER_MISMATCH",
                "userMessage": "Zła wartość",
                "path": "sellingMode.price.amount",
            },
            {"code": "MISSING", "message": "Brak pola"},
        ],
    )
    assert error.status == 422
    assert len(error.errors) == 2
    described = error.describe()
    assert described[0] == "PARAMETER_MISMATCH: Zła wartość (pole: sellingMode.price.amount)"
    assert described[1] == "MISSING: Brak pola"


def test_validation_error_without_details_is_readable() -> None:
    error = errors.ValidationError("Błąd", [{"code": "X"}])
    assert error.describe() == ["X"]


def test_rate_limit_error_carries_retry_after() -> None:
    error = errors.RateLimitError("limit", retry_after=60.0)
    assert error.retry_after == 60.0
    assert str(error) == "limit"


@pytest.mark.parametrize("message", ["", "krótki komunikat", "a" * 300])
def test_short_text_is_not_truncated(message: str) -> None:
    error = errors.ApiError("x", body=message)
    assert error.body == " ".join(message.split())
