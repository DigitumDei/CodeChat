import json
import asyncio
from typing import AsyncIterator, Iterator

from anthropic import Anthropic

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

    def check_key(self):
        if not get_config().get("anthropic.key"):
            logger.warning("Anthropic API key not found in config")
            raise ValueError("Anthropic API key not found in config, call codechat config set anthropic.key sk-…")


    # --- required interface --------------------------------------------
    def send(self, req: QueryRequest) -> dict:
        messages = self.prompt.make_chat_prompt(req.history, req.message, req.provider)

        response = self._client().messages.create(
            model=req.model,
            system=self.prompt.get_system_prompt(),
            max_tokens=1024,
            messages=messages
        )
        return response.to_dict()

    async def stream(self, req: QueryRequest) -> AsyncIterator[str]:
        messages = self.prompt.make_chat_prompt(
            req.history, req.message, req.provider
        )
        system_prompt_content = self.prompt.get_system_prompt()

        # This inner function is the actual async generator
        async def _chunk_generator() -> AsyncIterator[str]:
            loop = asyncio.get_running_loop()

            # This is the synchronous generator that interacts with the Anthropic client
            def _blocking_anthropic_call_sync_generator() -> Iterator[str]:
                client = self._client() 
                try:
                    with client.messages.stream(
                        model=req.model,
                        system=system_prompt_content,
                        messages=messages,
                        max_tokens=1024  # Consider making this configurable
                    ) as stream:
                        for text_delta in stream.text_stream:
                            yield json.dumps({"token": text_delta, "finish": False})
                    # Signal completion after the stream has finished
                    yield json.dumps({"token": "", "finish": True})
                except Exception as e:
                    logger.error("Anthropic stream error", exc_info=e, model=req.model)
                    # Yield an error message to the client
                    yield json.dumps({"error": f"Anthropic API error: {str(e)}", "token": "", "finish": True})
            
            # This function will be executed in the executor thread.
            # It calls the synchronous generator function and collects its results into a list.
            def _collect_blocking_generator_results() -> list[str]:
                sync_gen_obj = _blocking_anthropic_call_sync_generator()
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
register(AnthropicProvider())

# def _handle_anthropic(self, request: QueryRequest) -> dict:        
    #     if not self.cfg.get("anthropic.key"):
    #         logger.warning("Anthropic API key not found in config")
    #         raise ValueError("Anthropic API key not found in config, call codechat config set anthropic.key sk-…")

    #     client = Anthropic(api_key=self.cfg.get("anthropic.key"))

    #     prompt = self.prompt_manager.make_chat_prompt(
    #         history=request.history,
    #         instruction=request.message,
    #         provider=request.provider
    #     )
    #     response = client.messages.create(
    #         model=request.model,
    #         system=self.prompt_manager.get_system_prompt(),
    #         max_tokens=1024, #we should add this to the base request model
    #         messages=prompt
    #     )
    #     return response.to_dict()