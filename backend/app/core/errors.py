"""Application errors and the single JSON error format used by every failure."""

import logging
from http import HTTPStatus
from typing import Any, ClassVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for expected failures raised by services."""

    status_code: ClassVar[int] = 400
    code: ClassVar[str] = "bad_request"
    message: ClassVar[str] = "The request could not be processed."
    headers: ClassVar[dict[str, str] | None] = None

    def __init__(self, message: str | None = None, details: Any = None) -> None:
        super().__init__(message or self.message)
        self.detail_message = message or self.message
        self.details = details


class NotAuthenticatedError(AppError):
    status_code = 401
    code = "not_authenticated"
    message = "Authentication is required."
    headers = {"WWW-Authenticate": "Bearer"}


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "invalid_credentials"
    message = "Incorrect email or password."


class InvalidRefreshTokenError(AppError):
    status_code = 401
    code = "invalid_refresh_token"
    message = "Your session has expired. Please sign in again."


class EmailTakenError(AppError):
    status_code = 409
    code = "email_taken"
    message = "An account with this email already exists."


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    message = "The service is temporarily unavailable."


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id_var.get(),
        }
    }


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101  # Guaranteed by handler registration.
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.detail_message, exc.details),
        headers=exc.headers,
    )


def _friendly_message(err: Any) -> str:
    """Translate Pydantic's developer-oriented wording into text fit to show to a student."""
    kind, context = err["type"], err.get("ctx", {})
    if kind == "missing" or (kind == "string_too_short" and context["min_length"] == 1):
        return "This field is required."
    if kind == "string_too_short":
        return f"Must be at least {context['min_length']} characters."
    if kind == "string_too_long":
        return f"Must be at most {context['max_length']} characters."
    message: str = err["msg"]
    return message.removeprefix("Value error, ").removeprefix(
        "value is not a valid email address: "
    )


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    # Only location and message are returned. Pydantic's "input" field is deliberately dropped,
    # because it would echo rejected values, which can include passwords, back into responses.
    details = [
        {
            "field": ".".join(str(part) for part in err["loc"] if part != "body"),
            "message": _friendly_message(err),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=error_body("validation_error", "The submitted data is invalid.", details),
    )


async def _handle_http_exception(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, HTTPStatus(exc.status_code).phrase),
        headers=exc.headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
