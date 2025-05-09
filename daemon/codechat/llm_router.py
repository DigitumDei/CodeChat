from fastapi import HTTPException
from codechat.models import QueryRequest
import json # Added for yielding error JSONs
from codechat.providers import get as get_provider

import structlog
logger = structlog.get_logger(__name__)

class LLMRouter:
    def __init__(self):
        from codechat import providers  # noqa: F401 auto‑import side‑effects

    def route(self, req: QueryRequest) -> dict:
        try:
            return get_provider(req.provider.value).send(req)
        except ValueError as ve:
             raise HTTPException(status_code=400, detail=str(ve))
        except HTTPException as e:            
            raise e
        except Exception as e:
             # Catch unexpected errors and return a 500
            logger.error("Caught unexpected error", exception=str(e)) # Log the full error for debugging

            # Be careful about leaking internal details in the detail message
            raise HTTPException(status_code=500, detail="An internal server error occurred.")

    async def stream(self, req: QueryRequest):
        try:
            provider_instance = get_provider(req.provider.value)
            # provider_instance.stream(req) returns a coroutine.
            # Awaiting it yields the async generator object.
            async for chunk in await provider_instance.stream(req):
                yield chunk
        except ValueError as ve: # Handles errors like provider not found or initial config errors from provider
            logger.error("ValueError during stream setup in LLMRouter", detail=str(ve), exc_info=True)
            # Yield a JSON error message to be sent over SSE
            yield json.dumps({"error": True, "message": str(ve), "finish": True})
        except HTTPException as he: # Re-raise HTTPExceptions to be handled by FastAPI
            logger.warning("HTTPException occurred during stream processing in LLMRouter", detail=he.detail, status_code=he.status_code, exc_info=True)
            # If we want to ensure SSE clients get a JSON error, we could yield it here too,
            # but FastAPI's default handling for raised HTTPExceptions in StreamingResponse might be sufficient
            # or might just close the connection. For consistency, let's yield a JSON error.
            yield json.dumps({"error": True, "message": he.detail, "status_code": he.status_code, "finish": True})
        except Exception as e:
            logger.error("Unexpected error during stream processing in LLMRouter", exception=str(e), exc_info=True)
            # Yield a generic error message as part of the stream
            yield json.dumps({"error": True, "message": "An internal server error occurred during streaming.", "finish": True})