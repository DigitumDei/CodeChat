import json
import os

from fastapi import HTTPException
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
        self.set_config()

    def set_config(self):
        cfg_path = os.path.expanduser("/config/config.json")
        if os.path.exists(cfg_path):
            self.cfg = json.load(open(cfg_path))
        else:
            print("Warning: No config file found at /config/config.json")


    def route(self, request: QueryRequest) -> dict:
        handler = self._handlers.get(request.provider)
        if handler is None:
            # Should never happen once __init__ guard is in place
            raise HTTPException(status_code=400, detail=f"Unknown provider: {request.provider}")
        try:
            return handler(request)
        except ValueError as ve:
             # Catch specific ValueErrors you expect (like API key missing)
             # and convert them to HTTPExceptions
             print(f"Caught ValueError: {ve}") # Log the original error
             raise HTTPException(status_code=400, detail=str(ve))
        except Exception as e:
            # Catch unexpected errors and return a 500
            print(f"Caught unexpected error: {e}") # Log the full error for debugging
            # Be careful about leaking internal details in the detail message
            raise HTTPException(status_code=500, detail="An internal server error occurred.")

    
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
        if not self.cfg.get("anthropic.key"):
            raise ValueError("Anthropic key not found in config, call codechat config set anthropic.key sk-…")

        client = Anthropic(api_key=self.cfg.get("anthropic.key"))

        prompt = self.prompt_manager.make_chat_prompt(
            history=request.history,
            instruction=request.message,
            provider=request.provider
        )
        response = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            system=self.prompt_manager.get_system_prompt(),
            max_tokens=1024, #we should add this to the base request model
            messages=prompt
        )
        return response

    def _handle_gemini(self, request: QueryRequest) -> dict:
        
        if not self.cfg.get("gemini.key"):
            raise ValueError("Gemini key not found in config, call codechat config set gemini.key sk-…")

        client = genai.Client(api_key=self.cfg.get("gemini.key"))

        history = self.prompt_manager.make_chat_prompt(
            history=request.history,
            instruction=request.message,
            provider=request.provider
        )
        config = types.GenerateContentConfig(system_instruction=self.prompt_manager.get_system_prompt())
        chat = client.chats.create(model="gemini-2.0-flash", history=history, config=config)

        response = chat.send_message(request.message)
        
        return response
    
    def _handle_azure(self, request: QueryRequest) -> dict:
        prompt = self.prompt_manager.make_chat_prompt(
            history=request.history,
            instruction=request.message,
            provider=request.provider
        )
        
        #if cfg.get("openai.key") doesn't exist throw an error
        if not self.cfg.get("azureopenai.key"):
            raise ValueError("Azure OpenAI key not found in config, call codechat config set azureopenai.key sk-…")
        
        client = OpenAI(api_key=self.cfg.get("azureopenai.key"))

        response = client.responses.create(
            model="gpt-4.1",
            input=prompt)
        
        return response