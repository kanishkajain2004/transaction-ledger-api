"""Application errors and the handlers that turn them into one consistent JSON shape:

    {"error": {"code": "ACCOUNT_NOT_FOUND", "message": "...", "details": {...}}}
"""
import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "BAD_REQUEST"

    def __init__(self, message: str, details: Any = None):
        super().__init__(message)
        self.message = message
        self.details = details


class ValidationAppError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "VALIDATION_ERROR"


class AccountNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "ACCOUNT_NOT_FOUND"

    def __init__(self, account_id: Any):
        super().__init__(f"Account '{account_id}' not found", {"account_id": str(account_id)})


class DuplicateTransactionError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "DUPLICATE_TRANSACTION"


class InsufficientBalanceError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "INSUFFICIENT_BALANCE"


def error_response(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content=jsonable_encoder({"error": body}))


HTTP_STATUS_CODES = {
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for err in exc.errors():
            location = err["loc"][0]
            # e.g. ("body", "amount") -> "amount"; ("query", "page") -> "page".
            # For malformed JSON the loc holds a character position, so name the body instead.
            if err["type"] == "json_invalid":
                field = "body"
            else:
                field = ".".join(str(p) for p in err["loc"][1:]) or str(location)
            errors.append({"field": field, "location": location, "message": err["msg"]})
        return error_response(
            status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "Invalid request data", errors
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = HTTP_STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=exc)
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "An unexpected error occurred"
        )
