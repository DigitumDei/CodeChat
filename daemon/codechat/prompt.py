from typing import List, Optional
from google.genai import types

from codechat.models import ChatMessage, ProviderType
import structlog 
logger = structlog.get_logger(__name__)


class PromptManager:
    """Builds and formats chat prompts for LLMs."""
    def __init__(self, system_prompt: Optional[str] = None):
        self.system_prompt = system_prompt or "You are CodeChat, a helpful assistant for working with code."
        self._formatters = {
            p: getattr(self, f"_format_{p.value}")
            for p in ProviderType
        }

    def make_chat_prompt(self, history: List[ChatMessage], instruction: str, provider: ProviderType):
        """Route to the provider‐specific formatter."""
        fmt = self._formatters.get(provider)
        if not fmt:
            logger.error(f"No prompt formatter for provider '{provider}'")            
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
            msgs.append({"role": "developer", "content": self.system_prompt})

        msgs.extend([{"role": msg.role, "content": msg.content} for msg in history])
        msgs.append({"role": "user", "content": instruction})
        return msgs

    def _format_anthropic(
        self,
        history: List[ChatMessage],
        instruction: str
    ) -> list[dict]:
        msgs = []
        msgs.extend([{"role": msg.role, "content": msg.content} for msg in history])
        msgs.append({"role": "user", "content": instruction})
        return msgs

    def _format_google(
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
