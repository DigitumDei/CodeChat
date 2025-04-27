from typing import List
from google.genai import types

from codechat.models import ChatMessage, ProviderType


class PromptManager:
    """Builds and formats chat prompts for LLMs."""
    def __init__(self, system_prompt: str = None):
        self.system_prompt = system_prompt or "You are CodeChat, a helpful assistant for working with code."
        self._formatters = {
            p: getattr(self, f"_format_{p.value}")
            for p in ProviderType
        }

    def make_chat_prompt(self, history: List[ChatMessage], instruction: str, provider: ProviderType):
        """Route to the provider‐specific formatter."""
        fmt = self._formatters.get(provider)
        if not fmt:
            # Should never happen thanks to __init__ guard
            raise ValueError(f"No prompt formatter for provider '{provider}'")
        return fmt(history, instruction)
    
    def get_system_prompt(self) -> str:
        return self.system_prompt
    
    def _format_openai(
        self,
        history: List[ChatMessage],
        instruction: str
    ) -> list[dict]:
        # identical to your old make_chat_prompt
        msgs = []
        if self.system_prompt:
            msgs.append({"role": "developer", "content": "openAI" + self.system_prompt})
        msgs.extend(history)
        msgs.append({"role": "user", "content": instruction})
        return msgs

    def _format_anthropic(
        self,
        history: List[ChatMessage],
        instruction: str
    ) -> list[dict]:
        # e.g. Anthropics usually want "user"/"assistant" roles,
        # could tweak system prompt placement, etc.
        msgs = []
        if self.system_prompt:
            # Anthropics often handle system prompts differently
            msgs.append({"role": "system", "content": "anthropic" + self.system_prompt})
        msgs.extend(history)
        msgs.append({"role": "user", "content": instruction})
        return msgs

    def _format_gemini(
        self,
        history: List[ChatMessage],
        instruction: str
    ) -> list[types.Content]:
        # Gemini will only take in chat history and return it. No system prompt included.
        msgs = []
        for message in history:
            if message.role == "user":
                msgs.append(types.Content(parts=[types.Part(text=message.content)], role="user"))
            elif message.role == "assistant":
                msgs.append(types.Content(parts=[types.Part(text=message.content)], role="model"))

        return msgs
    
    def _format_azure(
        self,
        history: List[ChatMessage],
        instruction: str
    ) -> list[dict]:
        return self._format_openai(
            history,
            instruction
        )
