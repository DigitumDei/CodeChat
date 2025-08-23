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

    def populate_message(self, req: QueryRequest) -> list[types.PartUnionDict]:
        context_parts: list[types.PartUnionDict] = []
        if req.context.snippets:                
            for snippet in req.context.snippets:
                snippet_text = f"{snippet.type.value}\n{snippet.content}"
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
        history = self.prompt.make_chat_prompt(req)
        config = types.GenerateContentConfig(system_instruction=self.prompt.get_system_prompt())
        chat = self._client().aio.chats.create(model=req.model, history=history, config=config)

        try:                                               
            # The google-genai library's type hints are incorrect, suggesting a "double await"
            # is needed. At runtime, a single await returns the async iterator directly.
            # To fix the type hint for Pylance and get autocomplete on the `chunk` variable,
            # we assign the result to a variable that is explicitly typed.
            stream: AsyncIterator[types.GenerateContentResponse]
            stream = await chat.send_message_stream(self.populate_message(req))  # type: ignore

            async for chunk in stream:    
                if (chunk.function_calls and len(chunk.function_calls) > 0):
                    logger.debug("Function call chunk received, currently unsupported", chunk=chunk)
                    continue          
                token_text = chunk.text
                if token_text:  # Ensure we don't send empty updates
                    yield json.dumps({"token": token_text, "finish": False})
            yield json.dumps({"token": "", "finish": True})  # Signal completion
        except errors.APIError as e:
            status_code = getattr(e, 'code', 500)
            detail = f"Google API error: {e.message}"
            logger.error(
                "Google API error during stream",
                status_code=status_code,
                detail=detail,
                response=getattr(e, 'response', "N/A"),
                exc_info=True
            )
            raise HTTPException(status_code=status_code, detail=detail)
        except Exception as e:
            logger.error("Unexpected error during Google stream processing", exception=str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="An unexpected error occurred during streaming.")

# register on import
register(GoogleProvider())
