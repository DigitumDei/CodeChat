from pathlib import Path
from fastapi import HTTPException
from codechat.models import QueryRequest, Snippet, SnippetType
import json
from codechat.providers import get as get_provider
from codechat.indexer import Indexer  # Import Indexer
from codechat.functions import get_global_registry, FunctionExecutor
from codechat.functions.models import ExecutionContext, FunctionCall
from codechat.config import get_config

import structlog
logger = structlog.get_logger(__name__)

class LLMRouter:
    def __init__(self, indexer: Indexer):
        self.indexer = indexer
        self.reload_config()
        from codechat import providers  # noqa: F401 auto‑import side‑effects

    def reload_config(self) -> None:
        cfg = get_config()
        self.max_snippet_bytes = int(cfg.get("router.max_snippet_bytes", 1_000_000))

    def _create_snippet_from_file_path(self, file_path_str: str, source_description: str) -> Snippet | None:
        """
        Reads a file and creates a Snippet object.
        Returns None if the file cannot be read or processed.
        """
        try:
            file_path_obj = Path(file_path_str)
            size = file_path_obj.stat().st_size
            truncated = size > self.max_snippet_bytes
            with file_path_obj.open("rb") as f:
                if truncated:
                    logger.warning(
                        "File exceeds size limit; truncating for snippet.",
                        path=file_path_str,
                        size=size,
                        limit=self.max_snippet_bytes,
                    )
                    file_bytes = f.read(self.max_snippet_bytes)
                else:
                    file_bytes = f.read()
            file_content = file_bytes.decode("utf-8", errors="ignore")
            content = f"# File: {file_path_obj.name}\n# Path: {file_path_str}\n\n{file_content}"
            if truncated:
                content += "\n\n# [truncated]"
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
        # else:
        #     logger.info("No client files provided for context, querying VDB.")
        #     context_source = "vdb_query"
        #     results = self.indexer.query(req.message, top_k=top_k)
        #     for item in results:
        #         snippet = self._create_snippet_from_file_path(item['path'], "VDB")
        #         if snippet:
        #             snippets.append(snippet)
        #             processed_snippet_paths.append(item['path'])

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
            async for chunk in provider_instance.stream(req):
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

    async def stream_with_functions(self, req: QueryRequest):
        """
        Streaming facade that executes function calls iteratively using non-stream
        rounds, then streams the final assistant text as chunks.

        This avoids relying on provider-specific streaming tool events while still
        giving the user streaming output for the final response.
        """
        try:
            from copy import deepcopy
            self._ensure_context(req)
            provider_instance = get_provider(req.provider.value)
            registry = get_global_registry()
            functions = registry.get_available_functions()

            # If provider lacks tool support, fall back to normal streaming
            if not hasattr(provider_instance, "invoke_with_tools"):
                async for chunk in provider_instance.stream(req):
                    yield chunk
                return

            with FunctionExecutor() as executor:
                ctx = ExecutionContext(root=self.indexer.root, indexer=self.indexer)
                work_req = deepcopy(req)

                max_steps = 3
                steps = 0
                final_text = ""

                while steps < max_steps:
                    steps += 1
                    result = provider_instance.invoke_with_tools(work_req, functions)  # type: ignore[attr-defined]
                    if "function_calls" not in result:
                        final_text = result.get("text", "")
                        break

                    calls: list[FunctionCall] = result["function_calls"]
                    if not calls:
                        final_text = ""
                        break

                    # Execute and append results
                    lines: list[str] = []
                    for call in calls:
                        res = executor.execute_function(call, ctx)
                        if res.success:
                            out_text = f"[{res.name}]\n{res.output}"
                            lines.append(out_text)
                            # Stream tool output to client as we go
                            for i in range(0, len(out_text), 200):
                                yield json.dumps({"token": out_text[i:i+200], "finish": False})
                        else:
                            err_text = f"[{res.name}] ERROR: {res.error}"
                            lines.append(err_text)
                            for i in range(0, len(err_text), 200):
                                yield json.dumps({"token": err_text[i:i+200], "finish": False})
                    tool_msg = "\n\n".join(lines)

                    from codechat.models import ChatMessage
                    work_req.history.append(ChatMessage(role="assistant", content=tool_msg))
                    work_req.message = "Continue."

                # Stream out final_text in small chunks
                if not final_text:
                    yield json.dumps({"token": "", "finish": True})
                    return
                chunk_size = 200
                for i in range(0, len(final_text), chunk_size):
                    yield json.dumps({"token": final_text[i:i+chunk_size], "finish": False})
                yield json.dumps({"token": "", "finish": True})
        except Exception as e:
            logger.error("Unexpected error during stream_with_functions", exception=str(e), exc_info=True)
            yield json.dumps({"error": True, "message": "An internal server error occurred during streaming.", "finish": True})

    # --- Function-call enhanced flow (non-stream, iterative) ---------
    def process_request_with_functions(self, req: QueryRequest) -> dict:
        """
        Non-streaming, iterative function-call loop:
          - Include available functions in provider request
          - If provider requests function calls, execute them safely
          - Append a brief assistant message with tool results and continue
          - Stop when the provider returns text or the step limit is reached
        """
        try:
            self._ensure_context(req)
            provider_instance = get_provider(req.provider.value)

            # Get functions
            registry = get_global_registry()
            functions = registry.get_available_functions()

            # Provider must implement invoke_with_tools; otherwise fallback
            if not hasattr(provider_instance, "invoke_with_tools"):
                logger.info("Provider has no function-call support; falling back to normal route.", provider=req.provider.value)
                return provider_instance.send(req)

            # Iterative loop
            max_steps = 3
            steps = 0
            with FunctionExecutor() as executor:
                ctx = ExecutionContext(root=self.indexer.root)

                # Prepare a working copy we can mutate
                from copy import deepcopy
                work_req = deepcopy(req)

                while steps < max_steps:
                    steps += 1
                    result = provider_instance.invoke_with_tools(work_req, functions)  # type: ignore[attr-defined]

                    # If provider returned normal text, finish
                    if "function_calls" not in result:
                        return result

                    calls: list[FunctionCall] = result["function_calls"]
                    if not calls:
                        return {"text": ""}

                    # Execute calls and append a concise assistant message with outputs
                    lines: list[str] = []
                    for call in calls:
                        res = executor.execute_function(call, ctx)
                        if res.success:
                            lines.append(f"[{res.name}]\n{res.output}")
                        else:
                            lines.append(f"[{res.name}] ERROR: {res.error}")
                    tool_msg = "\n\n".join(lines)

                    # Append tool results as assistant message and prompt the model to continue
                    from codechat.models import ChatMessage
                    work_req.history.append(ChatMessage(role="assistant", content=tool_msg))
                    work_req.message = "Continue."

                # Exceeded max steps; return what we have
                logger.info("Max function-call steps reached", steps=steps)
                return {"text": "Stopped after maximum tool-use steps."}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error in process_request_with_functions", error=str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="An internal server error occurred.")
