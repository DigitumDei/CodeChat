from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import structlog

from ..models import ExecutionContext, FunctionDefinition
from ..registry import FunctionRegistry


logger = structlog.get_logger(__name__)


READ_FILE_DEF = FunctionDefinition(
    name="read_file",
    description="Read a UTF-8 text file from the repository root.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to project root"},
            "max_bytes": {"type": "integer", "minimum": 1, "maximum": 1048576},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    required=["path"],
    tags=["fs", "read"],
    permissions=["fs.read"],
)


def _handler(args: Dict[str, Any], ctx: ExecutionContext) -> str:
    rel = Path(args["path"])  # required validated by executor
    # Disallow absolute paths
    if rel.is_absolute():
        raise ValueError("Absolute paths are not allowed")

    # Resolve under root and prevent traversal outside
    abs_path = (ctx.root / rel).resolve()
    try:
        abs_path.relative_to(ctx.root)
    except ValueError:
        raise ValueError("Path escapes project root")

    max_bytes = int(args.get("max_bytes", 64 * 1024))
    if max_bytes < 1:
        max_bytes = 1
    if max_bytes > 1_048_576:
        max_bytes = 1_048_576

    logger.info("Reading file via function", path=str(abs_path), max_bytes=max_bytes)

    data = abs_path.read_bytes()
    data = data[:max_bytes]
    # Decode as UTF-8 with replacement to avoid exceptions on partial/binary
    return data.decode("utf-8", errors="replace")


def register(registry: FunctionRegistry) -> None:
    registry.register_function(READ_FILE_DEF, _handler)

