"""Global FastAPI exception handler producing RFC 7807 Problem Details.

Authority: WP-002-05 | LLD v2.0 §2.2. The handler logs at ``warning`` using
the exact call pattern from the LLD example::

    log.warning('request.error', code=..., status=..., path=..., detail=...)

``error``/``critical`` levels are reserved for unhandled, non-REOSException
failures (see README).
"""

from __future__ import annotations

from reos_exceptions.exceptions import REOSException
from reos_logging import get_logger

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

__all__ = ["register_exception_handlers"]

log = get_logger(__name__)


def _to_problem_details(exc: REOSException, instance: str) -> dict[str, object]:
    """Shape an ``REOSException`` as an RFC 7807 Problem Details object.

    Response contract (WP-002-05 §21)::

        {"type": ..., "title": ..., "status": ..., "detail": ..., "instance": ..., **metadata}
    """
    return {
        "type": f"https://errors.re-os.dev/{exc.code.lower()}",
        "title": exc.message,
        "status": exc.http_status,
        "detail": exc.detail,
        "instance": instance,
        "code": exc.code,
        **exc.metadata,
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Register the global REOSException handler on ``app``.

    Call once in ``create_app()``. Every raised ``REOSException`` (or
    subclass) anywhere in the service becomes a correctly shaped RFC 7807
    JSON response with the exception's documented HTTP status.
    """

    @app.exception_handler(REOSException)
    async def _handle_reos_exception(req: Request, exc: REOSException) -> JSONResponse:
        log.warning(
            "request.error",
            code=exc.code,
            status=exc.http_status,
            path=str(req.url),
            detail=exc.detail,
        )
        return JSONResponse(
            status_code=exc.http_status,
            content=_to_problem_details(exc, instance=str(req.url.path)),
            media_type="application/problem+json",
        )
