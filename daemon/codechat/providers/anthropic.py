    # def _handle_anthropic(self, request: QueryRequest) -> dict:        
    #     if not self.cfg.get("anthropic.key"):
    #         logger.warning("Anthropic API key not found in config")
    #         raise ValueError("Anthropic API key not found in config, call codechat config set anthropic.key sk-…")

    #     client = Anthropic(api_key=self.cfg.get("anthropic.key"))

    #     prompt = self.prompt_manager.make_chat_prompt(
    #         history=request.history,
    #         instruction=request.message,
    #         provider=request.provider
    #     )
    #     response = client.messages.create(
    #         model=request.model,
    #         system=self.prompt_manager.get_system_prompt(),
    #         max_tokens=1024, #we should add this to the base request model
    #         messages=prompt
    #     )
    #     return response.to_dict()