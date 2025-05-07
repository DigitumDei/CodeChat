    # def _handle_google(self, request: QueryRequest) -> dict:
        
    #     if not self.cfg.get("gemini.key"):
    #         logger.warning("Google Gemini API key not found in config")
    #         raise ValueError("Google Gemini API key not found in config, call codechat config set gemini.key sk-…")

    #     client = genai.Client(api_key=self.cfg.get("gemini.key"))

    #     history = self.prompt_manager.make_chat_prompt(
    #         history=request.history,
    #         instruction=request.message,
    #         provider=request.provider
    #     )
    #     config = types.GenerateContentConfig(system_instruction=self.prompt_manager.get_system_prompt())
    #     chat = client.chats.create(
    #         model=request.model, 
    #         history=history, 
    #         config=config)

    #     response = chat.send_message(request.message)
        
    #     return response.model_dump()