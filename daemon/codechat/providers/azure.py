    # def _handle_azure(self, request: QueryRequest) -> dict:
    #     prompt = self.prompt_manager.make_chat_prompt(
    #         history=request.history,
    #         instruction=request.message,
    #         provider=request.provider
    #     )
        
    #     #if cfg.get("openai.key") doesn't exist throw an error
    #     if not self.cfg.get("azureopenai.key"):
    #         logger.warning("Azure OpenAI key not found in config")
    #         raise ValueError("Azure OpenAI key not found in config, call codechat config set azureopenai.key sk-…")
        
    #     client = OpenAI(api_key=self.cfg.get("azureopenai.key"))

    #     response = client.responses.create(
    #         model="gpt-4.1",
    #         input=prompt)
        
    #     return response.to_dict()