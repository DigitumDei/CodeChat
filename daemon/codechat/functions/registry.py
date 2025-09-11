from __future__ import annotations

from typing import Dict, List, Optional
import threading

from .models import FunctionDefinition, FunctionHandler


class FunctionRegistry:
    """In-process registry for available functions and their handlers."""

    def __init__(self) -> None:
        self._defs: Dict[str, FunctionDefinition] = {}
        self._handlers: Dict[str, FunctionHandler] = {}
        self._lock = threading.Lock()

    def register_function(self, func_def: FunctionDefinition, handler: FunctionHandler) -> None:
        name = func_def.name
        with self._lock:
            self._defs[name] = func_def
            self._handlers[name] = handler

    def get_definition(self, name: str) -> Optional[FunctionDefinition]:
        return self._defs.get(name)

    def get_handler(self, name: str) -> Optional[FunctionHandler]:
        return self._handlers.get(name)

    def list_definitions(self) -> List[FunctionDefinition]:
        return list(self._defs.values())

    # Placeholder for future per-user/context filtering
    def get_available_functions(self) -> List[FunctionDefinition]:
        return self.list_definitions()


_GLOBAL_REGISTRY: Optional[FunctionRegistry] = None


def get_global_registry() -> FunctionRegistry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = FunctionRegistry()
    return _GLOBAL_REGISTRY

