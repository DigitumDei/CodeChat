# codechat/errors.py
from fastapi import Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import traceback
import structlog

logger = structlog.get_logger(__name__)

class ErrorDetail(BaseModel):
    code: str
    msg: str

class ErrorEnvelope(BaseModel):
    error: ErrorDetail

def add_global_error_handlers(app):
    @app.exception_handler(HTTPException)
    async def http_exc_handler(request: Request, exc: HTTPException):
        logger.error("HTTP error", exc_info=exc)
        envelope = ErrorEnvelope(
            error=ErrorDetail(code=getattr(exc, "code", "HTTP_ERROR"), msg=str(exc.detail))
        )
        return JSONResponse(status_code=exc.status_code, content=envelope.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exc_handler(request: Request, exc: RequestValidationError):
        raw_errors = exc.errors()
        logger.warning("Validation error", errors=raw_errors)
        formatted_errors = []
        for error in raw_errors:
            field = ".".join(map(str, error.get('loc', []))) # Join location path
            message = error.get('msg', 'Unknown error')
            formatted_errors.append(f"Field '{field}': {message}")
        error_message = "; ".join(formatted_errors)
        envelope = ErrorEnvelope(
            error=ErrorDetail(code="VALIDATION_ERR", msg=error_message)
        )
        return JSONResponse(status_code=422, content=envelope.model_dump())

    @app.exception_handler(Exception)
    async def generic_exc_handler(request: Request, exc: Exception):
        # Log full stack for ops
        logger.error("Unhandled exception", stack=traceback.format_exc())
        envelope = ErrorEnvelope(
            error=ErrorDetail(code="UNEXPECTED_ERR", msg="An internal server error occurred")
        )
        return JSONResponse(status_code=500, content=envelope.model_dump())
