# codechat/providers/openai.py
import json, asyncio
from openai import OpenAI
from codechat.providers import ProviderInterface, register
from codechat.prompt import PromptManager
from codechat.models import QueryRequest

import structlog
logger = structlog.get_logger(__name__)

class OpenAIProvider(ProviderInterface):
    name = "openai"

    def __init__(self):
        self.cfg = {}           # load in __init__ or via DI
        self.prompt = PromptManager()

    # --- util -----------------------------------------------------------
    def _client(self):
        self.check_key()
        return OpenAI(api_key=self.cfg["openai.key"])

    def check_key(self):
        if "openai.key" not in self.cfg:
            logger.warning("OpenAI API key not found in config")
            raise ValueError("OpenAI API key not found in config, call codechat config set openai.key sk-…")


    # --- required interface --------------------------------------------
    def send(self, req: QueryRequest) -> dict:
        messages = self.prompt.make_chat_prompt(
            req.history, req.message, req.provider
        )
        resp = self._client().chat.completions.create(
            model=req.model, messages=messages
        )
        return resp.to_dict()

    async def stream(self, req: QueryRequest):
        messages = self.prompt.make_chat_prompt(
            req.history, req.message, req.provider
        )
        loop = asyncio.get_running_loop()

        def _blocking():
            for ev in self._client().chat.completions.create(
                    model=req.model, messages=messages, stream=True):
                delta = ev.choices[0].delta.content or ""
                yield json.dumps({"token": delta, "finish": False})
            yield json.dumps({"finish": True})

        for chunk in await loop.run_in_executor(None, list, _blocking()):
            yield chunk

    # optional: lazy cache of available models
    @property
    def models(self) -> list[str]:
        return ["gpt-4o", "gpt-4o-mini"]

# register on import
register(OpenAIProvider())


#def _handle_openai(self, request: QueryRequest) -> dict:
        # prompt = self.prompt_manager.make_chat_prompt(
        #     history=request.history,
        #     instruction=request.message,
        #     provider=request.provider
        # )
        
        # #if cfg.get("openai.key") doesn't exist throw an error
        # if not self.cfg.get("openai.key"):
        #     logger.warning("OpenAI API key not found in config")
        #     raise ValueError("OpenAI API key not found in config, call codechat config set openai.key sk-…")

        # client = OpenAI(api_key=self.cfg.get("openai.key"))

        # response = client.responses.create(
        #     model=request.model,
        #     input=prompt)
        
        # return response.to_dict()