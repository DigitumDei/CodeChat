# codechat/providers/openai.py
import json
import asyncio
from typing import AsyncIterator # Iterator removed as it's implicitly used
from fastapi import HTTPException
from openai import OpenAI,APIStatusError  # type: ignore[attr-defined] # openai > 1.0 has this
from codechat.providers import ProviderInterface, register
from codechat.prompt import PromptManager
from codechat.models import QueryRequest

import structlog

from codechat.config import get_config
logger = structlog.get_logger(__name__)

class OpenAIProvider(ProviderInterface):
    name = "openai"

    def __init__(self):
        self.prompt = PromptManager()

    # --- util -----------------------------------------------------------
    def _client(self):
        self.check_key()
        return OpenAI(api_key=get_config().get("openai.key"))

    def check_key(self):
        if not get_config().get("openai.key"):
            logger.warning("OpenAI API key not found in config")
            raise ValueError("OpenAI API key not found in config, call codechat config set openai.key sk-…")


    # --- required interface --------------------------------------------
    def send(self, req: QueryRequest) -> dict:
        try:            
            messages = self.prompt.make_chat_prompt(
                req.history, req.message, req.provider
            )
            resp = self._client().chat.completions.create(
                model=req.model, messages=messages
            )
            return {"text": resp.choices[0].message.content}
        except APIStatusError as e:
            # Handle OpenAI specific API errors (includes 4xx/5xx from their API)
            status_code = e.status_code
            detail = f"OpenAI API error: {e.message}" 
            
            logger.error(
                "OpenAI API error encountered",
                status_code=status_code,
                detail=detail,
                response=e.response.text if e.response else "N/A", 
                provider=req.provider,
                model=req.model,
                exc_info=True 
            )
            raise HTTPException(status_code=status_code, detail=detail)

    async def stream(self, req: QueryRequest) -> AsyncIterator[str]:
        # This inner function is the actual async generator that will handle
        # calling the blocking OpenAI SDK in an executor and yielding results.
        async def _chunk_generator_impl() -> AsyncIterator[str]:
            loop = asyncio.get_running_loop()
            client = self._client()
            messages_for_stream = self.prompt.make_chat_prompt(
                req.history, req.message, req.provider
            )

            # This function will run in the executor and get the next item
            # from the synchronous OpenAI stream.
            sync_stream = None
            try:
                sync_stream = client.chat.completions.create(
                    model=req.model, messages=messages_for_stream, stream=True
                )

                while True:
                    # Define a helper to get the next item, to be run in executor
                    def get_next_item_from_sync_stream():
                        try:
                            return next(sync_stream)
                        except StopIteration:
                            return None # Sentinel for end of stream

                    ev = await loop.run_in_executor(None, get_next_item_from_sync_stream)

                    if ev is None: # End of stream
                        break

                    delta = ev.choices[0].delta.content or ""
                    yield json.dumps({"token": delta, "finish": False})

                yield json.dumps({"finish": True})

            except APIStatusError as e:
                logger.error(
                    "OpenAI API error during stream",
                    status_code=e.status_code,
                    detail=e.message,
                    response=e.response.text if e.response else "N/A",
                    provider=req.provider,
                    model=req.model,
                    provider_name=self.name,
                    exc_info=True
                )
                error_payload = {
                    "error": True,
                    "message": f"OpenAI API error: {e.message}",
                    "status_code": e.status_code,
                    "finish": True # Indicate stream is finished due to error
                }
                yield json.dumps(error_payload)
            except Exception as e: # Catch-all for unexpected errors during the streaming loop
                logger.error("Unexpected error during OpenAI stream processing:", exception=str(e), provider_name=self.name, exc_info=True)
                error_payload = {"error": True, "message": "An unexpected error occurred while streaming.", "finish": True}
                yield json.dumps(error_payload)

        return _chunk_generator_impl()

# register on import
register(OpenAIProvider())
