from __future__ import annotations

from typing import Any, Dict, Literal

from ..models import ExecutionContext, FunctionDefinition
from ..registry import FunctionRegistry


DEPENDENCIES_DEF = FunctionDefinition(
    name="get_dependencies",
    description="Query the dependency graph for a file's dependencies or dependents.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to file within repo"},
            "relation": {
                "type": "string",
                "enum": [
                    "direct_dependencies",
                    "direct_dependents",
                    "all_dependencies",
                    "all_dependents",
                ],
                "description": "Which relationship to return",
            },
        },
        "required": ["file_path", "relation"],
        "additionalProperties": False,
    },
    required=["file_path", "relation"],
    tags=["depgraph"],
    permissions=["graph.read"],
)


def _handler(args: Dict[str, Any], ctx: ExecutionContext):
    if ctx.indexer is None:
        raise RuntimeError("Indexer not available for dependency queries")
    from pathlib import Path

    file_path = Path(args["file_path"])  # raw
    if file_path.is_absolute():
        try:
            file_path = file_path.relative_to(ctx.root)
        except ValueError:
            raise ValueError("File path must be within project root")

    full_path = (ctx.root / file_path).resolve()
    # The dep_graph expects a Path; it primarily uses .stem for matching
    relation: Literal[
        "direct_dependencies",
        "direct_dependents",
        "all_dependencies",
        "all_dependents",
    ] = args["relation"]

    dgraph = ctx.indexer.dgraph
    if relation == "direct_dependencies":
        res = dgraph.get_direct_dependencies(full_path)
    elif relation == "direct_dependents":
        res = dgraph.get_direct_dependents(full_path)
    elif relation == "all_dependencies":
        res = dgraph.get_all_dependencies(full_path)
    elif relation == "all_dependents":
        res = dgraph.get_all_dependents(full_path)
    else:
        raise ValueError("Invalid relation")
    return sorted(list(res))


def register(registry: FunctionRegistry) -> None:
    registry.register_function(DEPENDENCIES_DEF, _handler)

