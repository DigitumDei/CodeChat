import json
from typing import AsyncIterator

from fastapi import HTTPException
from codechat.providers import ProviderInterface, register
from codechat.prompt import PromptManager
from codechat.models import QueryRequest
from google import genai
from google.genai import types, errors

import structlog

from codechat.config import get_config
logger = structlog.get_logger(__name__)

class GoogleProvider(ProviderInterface):
    name = "google"

    def __init__(self):
        self.prompt = PromptManager()

    # --- util -----------------------------------------------------------
    def _client(self):
        self.check_key()
        return genai.Client(api_key=get_config().get("gemini.key"))

    def check_key(self):
        if not get_config().get("gemini.key"):
            logger.warning("Google Gemini API key not found in config")
            raise ValueError("Google Gemini API key not found in config, call codechat config set gemini.key sk-…")

    def populate_message(self, req: QueryRequest) -> list[types.Part]:
        context_parts: list[types.Part] = []
        if req.context.snippets:                
            for snippet in req.context.snippets:
                snippet_text = f"{snippet.type}\n{snippet.content}"
                context_parts.append(types.Part(text=snippet_text))
        context_parts.append(types.Part(text=req.message))
        return context_parts

    # --- required interface --------------------------------------------
    def send(self, req: QueryRequest) -> dict:
        try:
            history = self.prompt.make_chat_prompt(req)
            config = types.GenerateContentConfig(system_instruction=self.prompt.get_system_prompt())
            chat = self._client().chats.create(model=req.model, history=history, config=config)
            response = chat.send_message(self.populate_message(req))
            return {"text": response.text}
        except errors.APIError as e:
            # Handle Google specific API errors (includes 4xx/5xx from their API)
            status_code = e.code
            detail = f"Google API error: {e.message}" 
            logger.error(
                "Google API error encountered",
                status_code=status_code,
                detail=detail,
                response=e.response.text if e.response else "N/A", 
                provider=req.provider,
                model=req.model,
                exc_info=True 
            )
            raise HTTPException(status_code=status_code, detail=detail)

    async def stream(self, req: QueryRequest) -> AsyncIterator[str]:

        # This inner function is the actual async generator
        async def _chunk_generator() -> AsyncIterator[str]:
            history = self.prompt.make_chat_prompt(req)
            config = types.GenerateContentConfig(system_instruction=self.prompt.get_system_prompt())
            chat = self._client().aio.chats.create(model=req.model, history=history, config=config)            

            try:
                async for chunk in await chat.send_message_stream(self.populate_message(req)):
                    token_text = chunk.text
                    if token_text: # Ensure we don't send empty updates
                        yield json.dumps({"token": token_text, "finish": False})
                yield json.dumps({"token": "", "finish": True}) # Signal completion
            except Exception as e:
                logger.error("Google GenAI stream error", exc_info=e, model=req.model)
                    

        return _chunk_generator()

# register on import
register(GoogleProvider())
