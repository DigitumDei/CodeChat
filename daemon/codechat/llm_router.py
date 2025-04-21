import json
import os
from codechat.prompt import PromptManager
from codechat.models import ProviderType, QueryRequest
from openai import OpenAI
from anthropic import Anthropic
from google import genai
from google.genai import types

class LLMRouter:
    def __init__(self):
        self.prompt_manager = PromptManager()
        self._handlers = {
            p: getattr(self, f"_handle_{p.value}")
            for p in ProviderType
        }
        self.cfg = {}
        cfg_path = os.path.expanduser("~/config/config.json")
        if os.path.exists(cfg_path):
            self.cfg = json.load(open(cfg_path))


    def route(self, request: QueryRequest) -> dict:
        handler = self._handlers.get(request.provider)
        if handler is None:
            # Should never happen once __init__ guard is in place
            raise ValueError(f"Unknown provider: {request.provider}")
        return handler(request)
    
    def _handle_openai(self, request: QueryRequest) -> dict:
        prompt = self.prompt_manager.make_chat_prompt(
            history=request.history,
            instruction=request.message,
            provider=request.provider
        )
        
        #if cfg.get("openai.key") doesn't exist throw an error
        if not self.cfg.get("openai.key"):
            raise ValueError("OpenAI key not found in config, call codechat config set openai.key sk-…")

        client = OpenAI(api_key=self.cfg.get("openai.key"))

        response = client.responses.create(
            model="gpt-4.1",
            input=prompt)
        
        return response

    def _handle_anthropic(self, request: QueryRequest) -> dict:
        prompt = self.prompt_manager.make_chat_prompt(
            history=request.history,
            instruction=request.message,
            provider=request.provider
        )
        # ⚙️ insert Anthropic-specific dispatch here
        return {
            "provider": "claude",
            "model": request.model,
            "prompt": prompt,
        }

    def _handle_gemini(self, request: QueryRequest) -> dict:
        prompt = self.prompt_manager.make_chat_prompt(
            history=request.history,
            instruction=request.message,
            provider=request.provider
        )
        # ⚙️ insert Gemini-specific dispatch here
        return {
            "provider": "gem",
            "model": request.model,
            "prompt": prompt,
        }