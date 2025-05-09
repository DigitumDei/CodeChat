# codechat/providers/openai.py
import json
import asyncio
from typing import AsyncIterator, Iterator
from openai import AzureOpenAI
from codechat.providers import ProviderInterface, register
from codechat.prompt import PromptManager
from codechat.models import QueryRequest

import structlog

from codechat.config import get_config
logger = structlog.get_logger(__name__)

class AzureOpenAIProvider(ProviderInterface):
    name = "azure"

    def __init__(self):
        self.prompt = PromptManager()

    # --- util -----------------------------------------------------------
    def _client(self):
        self.check_key()
        return AzureOpenAI(api_key=get_config().get("openai.key"))

    def check_key(self):
        if not self.cfg.get("azureopenai.key"):
            logger.warning("Azure OpenAI key not found in config")
            raise ValueError("Azure OpenAI key not found in config, call codechat config set azureopenai.key sk-…")


    # --- required interface --------------------------------------------
    def send(self, req: QueryRequest) -> dict:
        messages = self.prompt.make_chat_prompt(
            req.history, req.message, req.provider
        )
        resp = self._client().chat.completions.create(
            model=req.model, messages=messages
        )
        return resp.to_dict()

    async def stream(self, req: QueryRequest) -> AsyncIterator[str]:
        messages = self.prompt.make_chat_prompt(
            req.history, req.message, req.provider
        )
        # This inner function is the actual async generator
        async def _chunk_generator() -> AsyncIterator[str]:
            loop = asyncio.get_running_loop()

            # This is the original synchronous generator that interacts with the OpenAI client
            def _blocking_openai_call_sync_generator() -> Iterator[str]:
                client = self._client() 
                for ev in client.chat.completions.create(
                        model=req.model, messages=messages, stream=True):
                    delta = ev.choices[0].delta.content or ""
                    yield json.dumps({"token": delta, "finish": False})
                yield json.dumps({"finish": True})
            
            # This function will be executed in the executor thread.
            # It calls the synchronous generator function and collects its results into a list.
            def _collect_blocking_generator_results() -> list[str]:
                sync_gen_obj = _blocking_openai_call_sync_generator()
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
register(AzureOpenAIProvider())

    # def _handle_azure(self, request: QueryRequest) -> dict:
    #     prompt = self.prompt_manager.make_chat_prompt(
    #         history=request.history,
    #         instruction=request.message,
    #         provider=request.provider
    #     )
        
    #     #if cfg.get("openai.key") doesn't exist throw an error
    #     if not self.cfg.get("azureopenai.key"):
    #         logger.warning("Azure OpenAI key not found in config")
    #         raise ValueError("Azure OpenAI key not found in config, call codechat config set azureopenai.key sk-…")
        
    #     client = OpenAI(api_key=self.cfg.get("azureopenai.key"))

    #     response = client.responses.create(
    #         model="gpt-4.1",
    #         input=prompt)
        
    #     return response.to_dict()