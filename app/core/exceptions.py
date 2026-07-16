from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code = 500
    code = "internal_error"
    message = "An unexpected error occurred."

    def __init__(self, message: str | None = None, details: dict[str, object] | None = None) -> None:
        self.message = message or self.message
        self.details = details or {}


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class StaleReviewRevisionError(ConflictError):
    code = "STALE_REVIEW_REVISION"

    def __init__(self, current_revision_number: int) -> None:
        super().__init__("A newer review revision exists.", {"current_revision_number": current_revision_number})


class UpstreamServiceError(AppError):
    status_code = 503
    code = "upstream_unavailable"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def known(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {"code": "validation_error", "message": "Request validation failed.", "details": exc.errors()}
            },
        )
