# codechat/providers/openai.py
import json
from typing import AsyncIterator
from fastapi import HTTPException
from openai import OpenAI, AsyncOpenAI, APIStatusError  # type: ignore[attr-defined] # openai > 1.0 has this
from codechat.providers import ProviderInterface, register
from codechat.prompt import PromptManager
from codechat.models import QueryRequest
from codechat.functions.models import FunctionDefinition, FunctionCall

import structlog

from codechat.config import get_config
logger = structlog.get_logger(__name__)

class OpenAIProvider(ProviderInterface):
    name = "openai"

    def __init__(self):
        self.prompt = PromptManager()

    # --- util -----------------------------------------------------------
    def _client(self):
        self.check_key()
        return OpenAI(api_key=get_config().get("openai.key"))

    def _async_client(self):
        self.check_key()
        return AsyncOpenAI(api_key=get_config().get("openai.key"))

    def check_key(self):
        if not get_config().get("openai.key"):
            logger.warning("OpenAI API key not found in config")
            raise ValueError("OpenAI API key not found in config, call codechat config set openai.key sk-…")


    # --- required interface --------------------------------------------
    def send(self, req: QueryRequest) -> dict:
        try:            
            messages = self.prompt.make_chat_prompt(req)
            resp = self._client().responses.create(
                model=req.model, 
                input=messages
            )
            return {"text": resp.output_text}
        except APIStatusError as e:
            # Handle OpenAI specific API errors (includes 4xx/5xx from their API)
            status_code = e.status_code
            detail = f"OpenAI API error: {e.message}" 
            
            logger.error(
                "OpenAI API error encountered",
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
                "type": "function",
                "function": {
                    "name": f.name,
                    "description": f.description,
                    "parameters": f.parameters or {"type": "object", "properties": {}, "additionalProperties": False},
                }
            })
        return tools

    def invoke_with_tools(self, req: QueryRequest, functions: list[FunctionDefinition]) -> dict:
        """Call OpenAI with tool definitions; return text or function_calls.

        Returns one of:
          {"text": str}
          {"function_calls": list[FunctionCall]}
        """
        messages = self.prompt.make_chat_prompt(req)
        tools = self._translate_tools(functions)

        try:
            resp = self._client().responses.create(
                model=req.model,
                input=messages,
                tools=tools,
            )

            # Prefer text if present
            output_text = getattr(resp, "output_text", None)
            if output_text:
                return {"text": output_text}

            # Attempt to extract function calls from structured output
            calls: list[FunctionCall] = []
            # Try common shapes defensively
            output = getattr(resp, "output", None)
            if output:
                for item in output:
                    # Responses SDK often has item.type and .content or .name/.arguments for tool use
                    item_type = getattr(item, "type", None) or (isinstance(item, dict) and item.get("type"))
                    if item_type in ("tool_use", "function_call"):
                        name = getattr(item, "name", None) or (isinstance(item, dict) and item.get("name"))
                        arguments = getattr(item, "arguments", None) or (isinstance(item, dict) and item.get("arguments")) or {}
                        call_id_raw = getattr(item, "id", None) or (isinstance(item, dict) and item.get("id"))
                        call_id: str | None
                        if call_id_raw is None or call_id_raw is False:
                            call_id = None
                        else:
                            call_id = str(call_id_raw)
                        # Some variants embed JSON arguments as string
                        if isinstance(arguments, str):
                            try:
                                arguments = json.loads(arguments)
                            except Exception:
                                arguments = {"_raw": arguments}
                        if name:
                            calls.append(FunctionCall(name=name, arguments=arguments, call_id=call_id))

            # Fallback: some models expose top-level tool_calls
            tool_calls = getattr(resp, "tool_calls", None)
            if tool_calls:
                for tc in tool_calls:
                    fn = getattr(tc, "function", None) or {}
                    name = getattr(fn, "name", None) or (isinstance(fn, dict) and fn.get("name"))
                    args = getattr(fn, "arguments", None) or (isinstance(fn, dict) and fn.get("arguments")) or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {"_raw": args}
                    if name:
                        calls.append(FunctionCall(name=name, arguments=args))

            if calls:
                return {"function_calls": calls}

            # If nothing recognized, return empty text
            return {"text": ""}
        except APIStatusError as e:
            status_code = e.status_code
            detail = f"OpenAI API error: {e.message}"
            logger.error("OpenAI API error (tools)", status_code=status_code, detail=detail, exc_info=True)
            raise HTTPException(status_code=status_code, detail=detail)

    async def stream(self, req: QueryRequest) -> AsyncIterator[str]:
        """
        An async generator that streams responses from the OpenAI API.
        It uses the AsyncOpenAI client to make non-blocking API calls.
        """
        client = self._async_client()
        messages_for_stream = self.prompt.make_chat_prompt(req)

        try:
            async_stream = await client.responses.create(model=req.model, 
                                                         input=messages_for_stream, 
                                                         stream=True)

            async for event in async_stream:
                if event.type == 'response.function_call_arguments.delta':
                    logger.debug("Function call chunk received, currently unsupported", chunk=event.delta)
                    continue
                if event.type == 'response.output_text.delta':
                    delta = event.delta
                    yield json.dumps({"token": delta, "finish": False})

            yield json.dumps({"finish": True})
        except APIStatusError as e:
            logger.error(
                "OpenAI API error during stream",
                status_code=e.status_code,
                detail=e.message,
                response=e.response.text if e.response else "N/A",
                exc_info=True
            )
            # The router's error handling will catch this and format an SSE error message.
            raise HTTPException(status_code=e.status_code, detail=f"OpenAI API error: {e.message}")
        except Exception as e:
            logger.error("Unexpected error during OpenAI stream processing", exception=str(e), exc_info=True)
            raise HTTPException(status_code=500, detail="An unexpected error occurred during streaming.")

# register on import
register(OpenAIProvider())
