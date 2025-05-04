# daemon/codechat/logging.py

import logging
import os
import structlog
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, reset_contextvars, merge_contextvars

def setup_logging(cfg: dict):
    """
    Configure both stdlib logging (for uvicorn, starlette, etc.)
    and structlog for JSON output.
    """
    # determine level: config overrides ENV
    lvl = cfg.get("log.level") or os.getenv("CODECHAT_LOG_LEVEL", "info")
    if isinstance(lvl, str):
        level = lvl.upper()
    else:
        level = "INFO" 

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, level, logging.INFO),
    )

    structlog.configure(
        processors=[
            merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # 1) reset any leftover context
        reset_contextvars()
        # 2) generate or read an incoming X-Request-ID header
        req_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        # 3) bind it (and any other top-level fields) for this request
        bind_contextvars(request_id=req_id, path=request.url.path, method=request.method)
        # 4) call the endpoint
        response = await call_next(request)
        # 5) echo the ID back in the response
        response.headers["X-Request-ID"] = req_id
        return response