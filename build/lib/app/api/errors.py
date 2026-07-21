from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import ConflictError, NotFoundError, RegistryError, ValidationError


def registry_error_handler(request: Request, exc: RegistryError) -> JSONResponse:
    status_code = 400
    if isinstance(exc, NotFoundError):
        status_code = 404
    elif isinstance(exc, ConflictError):
        status_code = 409
    elif isinstance(exc, ValidationError):
        status_code = 422
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "type": exc.__class__.__name__,
                "message": str(exc),
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )
