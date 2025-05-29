from pathlib import Path
from fastapi import HTTPException
from codechat.models import QueryRequest, Snippet, SnippetType
import json # Added for yielding error JSONs
from codechat.providers import get as get_provider
from codechat.indexer import Indexer # Import Indexer

import structlog
logger = structlog.get_logger(__name__)

class LLMRouter:
    def __init__(self, indexer: Indexer):
        self.indexer = indexer
        from codechat import providers  # noqa: F401 auto‑import side‑effects

    def _ensure_context(self, req: QueryRequest, top_k: int = 5) -> None:
        # only populate once
        if req.context.snippets:
            return

        results = self.indexer.query(req.message, top_k=top_k)
        snippets: list[Snippet] = []
        added_snippet_paths: list[str] = []
        for item in results:
            #get the file content from the path here
            try:
                file_content = Path(item['path']).read_text(encoding="utf-8")
            except UnicodeDecodeError:
                logger.warning("Could not decode file as UTF-8 during context retrieval. Skipping.", path=item['path'])
                continue
            except FileNotFoundError:
                 logger.warning("File not found during context retrieval. Skipping.", path=item['path'])
                 continue
            except Exception as e:
                 logger.error("Failed to read file for context", path=item['path'], error=e)
                 continue
                 
            content = f"# {item['path']}\n{file_content}"
            snippets.append(
                Snippet(
                    type=SnippetType.FILE,
                    content=content
                )
            )
            added_snippet_paths.append(item['path'])

        req.context.snippets = snippets
        if added_snippet_paths:
            logger.info("Context populated with snippets from paths.", paths=added_snippet_paths)

    def route(self, req: QueryRequest) -> dict:
        try:
            self._ensure_context(req)
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
            self._ensure_context(req)
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