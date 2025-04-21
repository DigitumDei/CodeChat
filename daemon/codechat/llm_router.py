from codechat.prompt import PromptManager
from codechat.models import QueryRequest

class LLMRouter:
    def __init__(self):
        self.prompt_manager = PromptManager()

    def route(self, request: QueryRequest) -> dict:
        """
        request.provider -> e.g. "openai"
        request.model    -> e.g. "gpt-4"
        request.history  -> List[ChatMessage]
        request.message  -> str
        """
        # you can now branch on provider/model if you want:
        # if request.provider == "openai": ...

        # build the chat prompt
        prompt = self.prompt_manager.make_chat_prompt(
            history=[m.dict() for m in request.history],
            instruction=request.message
        )

        # TODO: dispatch to real LLM based on provider & model
        return {
            "provider": request.provider,
            "model": request.model,
            "prompt": prompt
        }