from fastapi import HTTPException
from codechat.models import QueryRequest
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
        async for chunk in await get_provider(req.provider.value).stream(req):
            yield chunk
    
    