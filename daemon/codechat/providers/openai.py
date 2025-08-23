# codechat/providers/openai.py
import json
from typing import AsyncIterator
from fastapi import HTTPException
from openai import OpenAI, AsyncOpenAI, APIStatusError  # type: ignore[attr-defined] # openai > 1.0 has this
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

    def _async_client(self):
        self.check_key()
        return AsyncOpenAI(api_key=get_config().get("openai.key"))

    def check_key(self):
        if not get_config().get("openai.key"):
            logger.warning("OpenAI API key not found in config")
            raise ValueError("OpenAI API key not found in config, call codechat config set openai.key sk-…")


    # --- required interface --------------------------------------------
    def send(self, req: QueryRequest) -> dict:
        try:            
            messages = self.prompt.make_chat_prompt(req)
            resp = self._client().responses.create(
                model=req.model, 
                input=messages
            )
            return {"text": resp.output_text}
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
        """
        An async generator that streams responses from the OpenAI API.
        It uses the AsyncOpenAI client to make non-blocking API calls.
        """
        client = self._async_client()
        messages_for_stream = self.prompt.make_chat_prompt(req)

        try:
            async_stream = await client.responses.create(model=req.model, 
                                                         input=messages_for_stream, 
                                                         stream=True)

            async for event in async_stream:
                if event.type == 'response.function_call_arguments.delta':
                    logger.debug("Function call chunk received, currently unsupported", chunk=event.delta)
                    continue
                if event.type == 'response.output_text.delta':
                    delta = event.delta
                    yield json.dumps({"token": delta, "finish": False})

            yield json.dumps({"finish": True})
        except APIStatusError as e:
            logger.error(
                "OpenAI API error during stream",
                status_code=e.status_code,
                detail=e.message,
                response=e.response.text if e.response else "N/A",
                exc_info=True
            )
            # The router's error handling will catch this and format an SSE error message.
            raise HTTPException(status_code=e.status_code, detail=f"OpenAI API error: {e.message}")
        except Exception as e:
            logger.error("Unexpected error during OpenAI stream processing", exception=str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="An unexpected error occurred during streaming.")

# register on import
register(OpenAIProvider())
