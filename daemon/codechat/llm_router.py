from codechat.prompt import PromptManager
from codechat.models import ProviderType, QueryRequest

class LLMRouter:
    def __init__(self):
        self.prompt_manager = PromptManager()
        self._handlers = {
            p: getattr(self, f"_handle_{p.value}")
            for p in ProviderType
        }

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
        # ⚙️ insert OpenAI-specific dispatch here
        return {
            "provider": "open ai was here",
            "model": request.model,
            "prompt": prompt,
        }

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