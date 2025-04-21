class PromptManager:
    """Builds and formats chat prompts for LLMs."""
    def __init__(self, system_prompt: str = None):
        # you can customize this system prompt as you like
        self.system_prompt = system_prompt or "You are CodeChat, a helpful assistant for working with code."

    def make_chat_prompt(self, history: list, instruction: str) -> list[dict]:
        """
        history: list of {"role": "user"|"assistant", "content": "..."}
        instruction: the new user message
        returns: full list of messages ready to send to a chat-LLM
        """
        messages: list[dict] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.extend(history)
        messages.append({"role": "user", "content": instruction})
        return messages