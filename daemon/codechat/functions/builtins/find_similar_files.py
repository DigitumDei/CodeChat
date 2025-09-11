from __future__ import annotations

from typing import Any, Dict

from ..models import ExecutionContext, FunctionDefinition
from ..registry import FunctionRegistry


FIND_SIMILAR_DEF = FunctionDefinition(
    name="find_similar_files",
    description="Search repository for files similar to a query using embeddings.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural language or code query"},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    required=["query"],
    tags=["search", "embeddings"],
    permissions=["index.search"],
)


def _handler(args: Dict[str, Any], ctx: ExecutionContext):
    if ctx.indexer is None:
        raise RuntimeError("Indexer not available for similarity search")
    query: str = args["query"]
    top_k: int = int(args.get("top_k", 5))
    results = ctx.indexer.query(query, top_k=top_k)
    # Return a simple structured list
    return [{"path": r.get("path"), "score": r.get("score")} for r in results]


def register(registry: FunctionRegistry) -> None:
    registry.register_function(FIND_SIMILAR_DEF, _handler)

