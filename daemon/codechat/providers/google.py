import json
import asyncio
from typing import AsyncIterator, Iterator
from codechat.providers import ProviderInterface, register
from codechat.prompt import PromptManager
from codechat.models import QueryRequest
from google import genai
from google.genai import types

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


    # --- required interface --------------------------------------------
    def send(self, req: QueryRequest) -> dict:
        history = self.prompt.make_chat_prompt(req.history, req.message, req.provider)
        config = types.GenerateContentConfig(system_instruction=self.prompt.get_system_prompt())
        chat = self._client().chats.create(model=req.model, history=history, config=config)
        response = chat.send_message(req.message)        
        return response.model_dump()


    async def stream(self, req: QueryRequest) -> AsyncIterator[str]:

        # This inner function is the actual async generator
        async def _chunk_generator() -> AsyncIterator[str]:
            loop = asyncio.get_running_loop()

# This is the synchronous generator that interacts with the Google GenAI client
            def _blocking_google_call_sync_generator() -> Iterator[str]:
                history = self.prompt.make_chat_prompt(req.history, req.message, req.provider)
                config = types.GenerateContentConfig(system_instruction=self.prompt.get_system_prompt())
                chat = self._client().aio.chats.create(model=req.model, history=history, config=config)
                

                try:
                    chat.send_message_stream(req.message)
                    
                    for chunk in chat.send_message_stream(req.message):
                        token_text = chunk.text
                        if token_text: # Ensure we don't send empty updates
                            yield json.dumps({"token": token_text, "finish": False})
                    yield json.dumps({"token": "", "finish": True}) # Signal completion
                except Exception as e:
                    logger.error("Google GenAI stream error", exc_info=e, model=req.model)
                    
            
            # This function will be executed in the executor thread.
            # It calls the synchronous generator function and collects its results into a list.
            def _collect_blocking_generator_results() -> list[str]:
                sync_gen_obj = _blocking_google_call_sync_generator()
                return list(sync_gen_obj)

            # Run the collection function in an executor
            # all_response_chunks will be of type list[str]
            all_response_chunks: list[str] = await loop.run_in_executor(
                None, _collect_blocking_generator_results
            )
            
            for chunk_str in all_response_chunks:
                yield chunk_str
        return _chunk_generator()

# register on import
register(GoogleProvider())
