from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers
        super().__init__(message)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    body: dict[str, Any] = {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "request_id": getattr(request.state, "request_id", None),
        }
    }
    if exc.details is not None:
        body["error"]["details"] = exc.details
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)
