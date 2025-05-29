from typing import List, Optional
from google.genai import types

from codechat.models import ChatMessage, ProviderType, QueryRequest
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

    def make_chat_prompt(self, req: QueryRequest):
        """Route to the provider‐specific formatter."""
        fmt = self._formatters.get(req.provider)
        if not fmt:
            logger.error(f"No prompt formatter for provider '{req.provider}'")
            raise ValueError(f"No prompt formatter for provider '{req.provider}'")
        return fmt(req)
    
    def get_system_prompt(self) -> str:
        return self.system_prompt
    
    def _format_openai(
        self,
        req: QueryRequest
    ) -> list[dict]:
        msgs = []
        if self.system_prompt:
            msgs.append({"role": "developer", "content": self.system_prompt})

        msgs.extend([{"role": msg.role, "content": msg.content} for msg in req.history])
        msgs.extend([{"role": "assistant", "content": f"{snippet.type}\n{snippet.content}"} for snippet in req.context.snippets])

        msgs.append({"role": "user", "content": req.message})
        return msgs

    def _format_anthropic(
        self,
        req: QueryRequest
    ) -> list[dict]:
        msgs = []
        msgs.extend([{"role": msg.role, "content": msg.content} for msg in req.history])
        # msgs.extend([{"role": "assistant", "content": f"{snippet.type}\n{snippet.content}"} for snippet in req.context.snippets])
        msgs.append({"role": "user", "content": req.message})
        return msgs

    def _format_google(
        self,
        req: QueryRequest
    ) -> list[types.Content]:
        # Gemini will only take in chat history and return it. No system prompt included.
        msgs = []
        for message in req.history:
            if message.role == "user":
                msgs.append(types.Content(parts=[types.Part(text=message.content)], role="user"))
            elif message.role == "assistant":
                msgs.append(types.Content(parts=[types.Part(text=message.content)], role="model"))

        # Note: Google's Chat.send_message takes the latest user message and context separately,
        # so we don't append req.message and req.context to msgs here. The `history` for Google
        # is just the prior conversation.
        return msgs
    
    def _format_azure(
        self,
        req: QueryRequest
    ) -> list[dict]:
        return self._format_openai(req)
