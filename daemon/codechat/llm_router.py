from pathlib import Path
from fastapi import HTTPException
from codechat.models import QueryRequest, Snippet, SnippetType
import json 
from codechat.providers import get as get_provider
from codechat.indexer import Indexer # Import Indexer

import structlog
logger = structlog.get_logger(__name__)

class LLMRouter:
    def __init__(self, indexer: Indexer):
        self.indexer = indexer
        from codechat import providers  # noqa: F401 auto‑import side‑effects

    def _create_snippet_from_file_path(self, file_path_str: str, source_description: str) -> Snippet | None:
        """
        Reads a file and creates a Snippet object.
        Returns None if the file cannot be read or processed.
        """
        try:
            file_path_obj = Path(file_path_str)
            file_content = file_path_obj.read_text(encoding="utf-8")
            # Using file_path_str for the original path as provided
            content = f"# File: {file_path_obj.name}\n# Path: {file_path_str}\n\n{file_content}"
            return Snippet(type=SnippetType.FILE, content=content)
        except UnicodeDecodeError:
            logger.warning(f"Could not decode {source_description} file as UTF-8. Skipping.", path=file_path_str)
        except FileNotFoundError:
            logger.warning(f"{source_description.capitalize()} file not found. Skipping.", path=file_path_str)
        except Exception as e:
            logger.error(f"Failed to read {source_description} file for context", path=file_path_str, error=e)
        return None

    def _ensure_context(self, req: QueryRequest, top_k: int = 5) -> None:
        # only populate once
        if req.context.snippets:
            return

        snippets: list[Snippet] = []
        processed_snippet_paths: list[str] = [] # Renamed for clarity
        context_source = "unknown"

        if req.files and len(req.files) > 0:
            logger.info("Client provided specific files for context.", client_files=req.files)
            context_source = "client_files"
            for file_path_str in req.files:
                snippet = self._create_snippet_from_file_path(file_path_str, "client-specified")
                if snippet:
                    snippets.append(snippet)
                    processed_snippet_paths.append(file_path_str)
        else:
            logger.info("No client files provided for context, querying VDB.")
            context_source = "vdb_query"
            results = self.indexer.query(req.message, top_k=top_k)
            for item in results:
                snippet = self._create_snippet_from_file_path(item['path'], "VDB")
                if snippet:
                    snippets.append(snippet)
                    processed_snippet_paths.append(item['path'])

        req.context.snippets = snippets
        if processed_snippet_paths:
            logger.info("Context populated with snippets.", paths=processed_snippet_paths, source=context_source)

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