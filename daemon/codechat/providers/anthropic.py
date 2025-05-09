import json
from typing import AsyncIterator

from anthropic import APIStatusError, Anthropic, AsyncAnthropic
from fastapi import HTTPException

from codechat.providers import ProviderInterface, register
from codechat.prompt import PromptManager
from codechat.models import QueryRequest

import structlog

from codechat.config import get_config
logger = structlog.get_logger(__name__)

class AnthropicProvider(ProviderInterface):
    name = "anthropic"

    def __init__(self):
        self.prompt = PromptManager()

    # --- util -----------------------------------------------------------
    def _client(self):
        self.check_key()
        return Anthropic(api_key=get_config().get("anthropic.key"))
    
    def _async_client(self):
        self.check_key()
        return AsyncAnthropic(api_key=get_config().get("anthropic.key"))

    def check_key(self):
        if not get_config().get("anthropic.key"):
            logger.warning("Anthropic API key not found in config")
            raise ValueError("Anthropic API key not found in config, call codechat config set anthropic.key sk-…")


    # --- required interface --------------------------------------------
    def send(self, req: QueryRequest) -> dict:
        try:
            messages = self.prompt.make_chat_prompt(req.history, req.message, req.provider)

            response = self._client().messages.create(
                model=req.model,
                system=self.prompt.get_system_prompt(),
                max_tokens=1024,
                messages=messages
            )
            return json.dumps({"text": response.content[0].text})
        except APIStatusError as e:
            # Handle Anthropic specific API errors (includes 4xx/5xx from their API)
            status_code = e.status_code
            detail = f"Anthropic API error: {e.message}" 
            logger.error(
                "Anthropic API error encountered",
                status_code=status_code,
                detail=detail,
                response=e.response.text if e.response else "N/A", 
                provider=req.provider,
                model=req.model,
                exc_info=True 
            )
            raise HTTPException(status_code=status_code, detail=detail)

    async def stream(self, req: QueryRequest) -> AsyncIterator[str]:
        messages = self.prompt.make_chat_prompt(
            req.history, req.message, req.provider
        )
        system_prompt_content = self.prompt.get_system_prompt()

        # This inner function is the actual async generator
        async def _chunk_generator() -> AsyncIterator[str]:           
            async with self._async_client().messages.stream(
                    model=req.model,
                    system=system_prompt_content,
                    messages=messages,
                    max_tokens=1024  # Consider making this configurable
                ) as stream:
                    async for text_chunk in stream.text_stream:
                        yield json.dumps({"token": text_chunk, "finish": False})

                    yield json.dumps({"token": "", "finish": True})

        return _chunk_generator()

# register on import
register(AnthropicProvider())
