import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    FeatureDisabledError,
    NotFoundError,
    PermissionDeniedError,
    RegistryError,
    ValidationError,
)

logger = logging.getLogger(__name__)


def _payload(request: Request, error_type: str, message: str) -> dict[str, object]:
    return {
        "error": {
            "type": error_type,
            "message": message,
            "request_id": getattr(request.state, "request_id", None),
        }
    }


def registry_error_handler(request: Request, exc: RegistryError) -> JSONResponse:
    status_code = 400
    if isinstance(exc, NotFoundError):
        status_code = 404
    elif isinstance(exc, ConflictError):
        status_code = 409
    elif isinstance(exc, ValidationError):
        status_code = 422
    elif isinstance(exc, FeatureDisabledError):
        status_code = 503
    elif isinstance(exc, PermissionDeniedError):
        status_code = 403
    elif isinstance(exc, AuthorizationError):
        status_code = 401
    headers = (
        {"WWW-Authenticate": "Bearer"}
        if isinstance(exc, AuthorizationError) and not isinstance(exc, PermissionDeniedError)
        else None
    )
    return JSONResponse(
        status_code=status_code,
        content=_payload(request, exc.__class__.__name__, str(exc)),
        headers=headers,
    )


def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled request failure request_id=%s path=%s",
        getattr(request.state, "request_id", None),
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content=_payload(
            request,
            "InternalServerError",
            "The request failed unexpectedly. Use the request ID to inspect server logs.",
        ),
    )
