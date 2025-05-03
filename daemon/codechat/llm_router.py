import json
import os

from fastapi import HTTPException
from codechat.prompt import PromptManager
from codechat.models import ProviderType, QueryRequest
from openai import OpenAI, APIStatusError as OpenAIAPIStatusError
from anthropic import Anthropic
from google import genai
from google.genai import types

import structlog
logger = structlog.get_logger(__name__)

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
            logger.warning("No config file found at /config/config.json")


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
             logger.error("Caught ValueError", exception=str(ve)) # Log the original error
             raise HTTPException(status_code=400, detail=str(ve))
        except OpenAIAPIStatusError as e:
            # Handle OpenAI specific API errors (includes 4xx/5xx from their API)
            status_code = e.status_code
            detail = f"OpenAI API error: {e.message}" # Use message from OpenAI error
            logger.error(
                "OpenAI API error encountered",
                status_code=status_code,
                detail=detail,
                response=e.response.text if e.response else "N/A", # Log raw response if available
                provider=request.provider,
                model=request.model,
                exc_info=True # Add traceback info to log
            )
            # Re-raise with the original status code if it's client-side (4xx)
            # or keep it as 500 if it was a server error on OpenAI's side
            raise HTTPException(status_code=status_code, detail=detail)
        except Exception as e:
            # Catch unexpected errors and return a 500
            logger.error("Caught unexpected error", exception=str(e)) # Log the full error for debugging
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
            logger.warning("OpenAI API key not found in config")
            raise ValueError("OpenAI API key not found in config, call codechat config set openai.key sk-…")

        client = OpenAI(api_key=self.cfg.get("openai.key"))

        response = client.responses.create(
            model=request.model,
            input=prompt)
        
        return response.to_dict()

    def _handle_anthropic(self, request: QueryRequest) -> dict:        
        if not self.cfg.get("anthropic.key"):
            logger.warning("Anthropic API key not found in config")
            raise ValueError("Anthropic API key not found in config, call codechat config set anthropic.key sk-…")

        client = Anthropic(api_key=self.cfg.get("anthropic.key"))

        prompt = self.prompt_manager.make_chat_prompt(
            history=request.history,
            instruction=request.message,
            provider=request.provider
        )
        response = client.messages.create(
            model=request.model,
            system=self.prompt_manager.get_system_prompt(),
            max_tokens=1024, #we should add this to the base request model
            messages=prompt
        )
        return response.to_dict()

    def _handle_google(self, request: QueryRequest) -> dict:
        
        if not self.cfg.get("gemini.key"):
            logger.warning("Google Gemini API key not found in config")
            raise ValueError("Google Gemini API key not found in config, call codechat config set gemini.key sk-…")

        client = genai.Client(api_key=self.cfg.get("gemini.key"))

        history = self.prompt_manager.make_chat_prompt(
            history=request.history,
            instruction=request.message,
            provider=request.provider
        )
        config = types.GenerateContentConfig(system_instruction=self.prompt_manager.get_system_prompt())
        chat = client.chats.create(
            model=request.model, 
            history=history, 
            config=config)

        response = chat.send_message(request.message)
        
        return response.model_dump()
    
    def _handle_azure(self, request: QueryRequest) -> dict:
        prompt = self.prompt_manager.make_chat_prompt(
            history=request.history,
            instruction=request.message,
            provider=request.provider
        )
        
        #if cfg.get("openai.key") doesn't exist throw an error
        if not self.cfg.get("azureopenai.key"):
            logger.warning("Azure OpenAI key not found in config")
            raise ValueError("Azure OpenAI key not found in config, call codechat config set azureopenai.key sk-…")
        
        client = OpenAI(api_key=self.cfg.get("azureopenai.key"))

        response = client.responses.create(
            model="gpt-4.1",
            input=prompt)
        
        return response.to_dict()