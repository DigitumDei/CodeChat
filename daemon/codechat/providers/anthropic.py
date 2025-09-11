import json
from typing import AsyncIterator

from anthropic import APIStatusError, Anthropic, AsyncAnthropic
from fastapi import HTTPException

from codechat.providers import ProviderInterface, register
from codechat.prompt import PromptManager
from codechat.models import QueryRequest
from codechat.functions.models import FunctionDefinition, FunctionCall

import structlog

from codechat.config import get_config
logger = structlog.get_logger(__name__)

class AnthropicProvider(ProviderInterface):
    name = "anthropic"

    def __init__(self):
        self.prompt = PromptManager()

    # --- util -----------------------------------------------------------
    def _client(self):
        self.check_key()
        return Anthropic(api_key=get_config().get("anthropic.key"))
    
    def _async_client(self):
        self.check_key()
        return AsyncAnthropic(api_key=get_config().get("anthropic.key"))

    def check_key(self):
        if not get_config().get("anthropic.key"):
            logger.warning("Anthropic API key not found in config")
            raise ValueError("Anthropic API key not found in config, call codechat config set anthropic.key sk-…")


    # --- required interface --------------------------------------------
    def send(self, req: QueryRequest) -> dict:
        try:
            messages = self.prompt.make_chat_prompt(req)

            response = self._client().messages.create(
                model=req.model,
                system=self.prompt.get_system_prompt(),
                max_tokens=1024,
                messages=messages
            )
            return {"text": getattr(response.content[0],"text", "")}
 
        except APIStatusError as e:
            # Handle Anthropic specific API errors (includes 4xx/5xx from their API)
            status_code = e.status_code
            detail = f"Anthropic API error: {e.message}" 
            logger.error(
                "Anthropic API error encountered",
                status_code=status_code,
                detail=detail,
                response=e.response.text if e.response else "N/A", 
                provider=req.provider,
                model=req.model,
                exc_info=True 
            )
            raise HTTPException(status_code=status_code, detail=detail)

    # --- function calling (non-stream) ---------------------------------
    def _translate_tools(self, functions: list[FunctionDefinition]) -> list[dict]:
        tools: list[dict] = []
        for f in functions:
            tools.append({
                "name": f.name,
                "description": f.description,
                "input_schema": f.parameters or {"type": "object", "properties": {}, "additionalProperties": False},
            })
        return tools

    def invoke_with_tools(self, req: QueryRequest, functions: list[FunctionDefinition]) -> dict:
        """Call Anthropic with tool definitions; return text or function_calls."""
        messages = self.prompt.make_chat_prompt(req)
        tools = self._translate_tools(functions)

        try:
            response = self._client().messages.create(
                model=req.model,
                system=self.prompt.get_system_prompt(),
                max_tokens=1024,
                messages=messages,
                tools=tools,
            )
            # Parse content blocks
            calls: list[FunctionCall] = []
            for block in getattr(response, "content", []) or []:
                btype = getattr(block, "type", None)
                if btype in ("tool_use", "input_json"):
                    name = getattr(block, "name", None)
                    args = getattr(block, "input", None) or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {"_raw": args}
                    if name:
                        calls.append(FunctionCall(name=name, arguments=args))
            if calls:
                return {"function_calls": calls}

            # Otherwise return text
            text = ""
            content0 = (getattr(response, "content", []) or [])
            if content0:
                text = getattr(content0[0], "text", "") or ""
            return {"text": text}
        except APIStatusError as e:
            status_code = e.status_code
            detail = f"Anthropic API error: {e.message}"
            logger.error("Anthropic API error (tools)", status_code=status_code, detail=detail, exc_info=True)
            raise HTTPException(status_code=status_code, detail=detail)

    async def stream(self, req: QueryRequest) -> AsyncIterator[str]:
        messages = self.prompt.make_chat_prompt(req)
        system_prompt_content = self.prompt.get_system_prompt()

        try:
            async with self._async_client().messages.stream(
                    model=req.model,
                    system=system_prompt_content,
                    messages=messages,
                    max_tokens=1024  # Consider making this configurable
                ) as stream:
                async for chunk in stream:
                    if chunk.type == "input_json":
                        logger.debug("Function call chunk received, currently unsupported", chunk=chunk)
                        continue
                    if chunk.type == "text":
                        yield json.dumps({"token": chunk.text, "finish": False})

                yield json.dumps({"token": "", "finish": True})
        except APIStatusError as e:
            logger.error(
                "Anthropic API error during stream",
                status_code=e.status_code,
                detail=e.message,
                response=e.response.text if e.response else "N/A",
                exc_info=True
            )
            raise HTTPException(status_code=e.status_code, detail=f"Anthropic API error: {e.message}")
        except Exception as e:
            logger.error("Unexpected error during Anthropic stream processing", exception=str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="An unexpected error occurred during streaming.")

# register on import
register(AnthropicProvider())
