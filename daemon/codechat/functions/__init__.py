from .models import FunctionDefinition, FunctionCall, FunctionResult, ExecutionContext
from .registry import FunctionRegistry, get_global_registry
from .executor import FunctionExecutor

# Register built-in functions on import
from .builtins.read_file import register as register_read_file
from .builtins.find_similar_files import register as register_find_similar
from .builtins.dependencies import register as register_dependencies

__all__ = [
    "FunctionDefinition",
    "FunctionCall",
    "FunctionResult",
    "ExecutionContext",
    "FunctionRegistry",
    "get_global_registry",
    "FunctionExecutor",
]

# Ensure built-ins are registered once per process
register_read_file(get_global_registry())
register_find_similar(get_global_registry())
register_dependencies(get_global_registry())
