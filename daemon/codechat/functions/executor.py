from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

import structlog

from .models import ExecutionContext, FunctionCall, FunctionResult
from .registry import get_global_registry


logger = structlog.get_logger(__name__)


class FunctionExecutor:
    """Executes registered functions with basic safety controls."""

    def __init__(self, max_workers: int = 4, max_output_bytes: int = 256 * 1024) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        self._max_output_bytes = max_output_bytes

    def close(self) -> None:
        """Shut down the underlying thread pool."""
        self._pool.shutdown(wait=True)

    def __enter__(self) -> "FunctionExecutor":  # noqa: D401 - part of context manager
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401 - part of context manager
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _truncate_output(self, value: Any) -> Any:
        try:
            data = value if isinstance(value, (bytes, bytearray)) else str(value).encode("utf-8", errors="replace")
            if len(data) <= self._max_output_bytes:
                return value
            truncated = data[: self._max_output_bytes]
            # Return text to keep results readable
            return truncated.decode("utf-8", errors="replace") + "\n…[truncated]"
        except Exception:
            return value

    def execute_function(self, call: FunctionCall, context: ExecutionContext) -> FunctionResult:
        registry = get_global_registry()
        handler = registry.get_handler(call.name)
        if handler is None:
            err = f"Unknown function: {call.name}"
            logger.warning("Function not found", name=call.name)
            return FunctionResult(name=call.name, success=False, error=err, call_id=call.call_id)

        # Minimal required-args validation if schema exists
        func_def = registry.get_definition(call.name)
        if func_def and func_def.required:
            missing = [key for key in func_def.required if key not in call.arguments]
            if missing:
                err = f"Missing required arguments: {', '.join(missing)}"
                logger.warning("Function call missing args", name=call.name, missing=missing)
                return FunctionResult(name=call.name, success=False, error=err, call_id=call.call_id)

        def _invoke():
            return handler(call.arguments, context)

        future = self._pool.submit(_invoke)
        try:
            result = future.result(timeout=context.timeout_secs)
            return FunctionResult(
                name=call.name,
                success=True,
                output=self._truncate_output(result),
                call_id=call.call_id,
            )
        except TimeoutError:
            logger.warning("Function execution timed out", name=call.name, timeout=context.timeout_secs)
            return FunctionResult(name=call.name, success=False, error="timeout", call_id=call.call_id)
        except Exception as e:
            logger.error("Function execution error", name=call.name, error=str(e), exc_info=True)
            return FunctionResult(name=call.name, success=False, error=str(e), call_id=call.call_id)

