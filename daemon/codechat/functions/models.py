from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


JsonDict = Dict[str, Any]


@dataclass(frozen=True)
class FunctionDefinition:
    name: str
    description: str
    parameters: JsonDict  # JSON Schema fragment for parameters (object)
    required: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    permissions: Optional[List[str]] = None


@dataclass(frozen=True)
class FunctionCall:
    name: str
    arguments: JsonDict
    call_id: Optional[str] = None  # Provider/tool-call identifier if present


@dataclass(frozen=True)
class FunctionResult:
    name: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    call_id: Optional[str] = None


@dataclass(frozen=True)
class ExecutionContext:
    root: Path
    timeout_secs: int = 10
    allow_network: bool = False
    request_id: Optional[str] = None
    # Optional references for advanced functions (set by router)
    indexer: Any = None


# Type alias for function handlers
FunctionHandler = Callable[[JsonDict, ExecutionContext], Any]
