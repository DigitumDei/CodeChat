from typing import Protocol, AsyncIterator
from codechat.models import QueryRequest
import structlog
logger = structlog.get_logger(__name__)

class ProviderInterface(Protocol):
    name: str                # "openai", "anthropic",

    def send(self, req: QueryRequest) -> dict:             ...
    async def stream(self, req: QueryRequest) -> AsyncIterator[str]: ...    

_registry: dict[str, ProviderInterface] = {}

def register(provider: ProviderInterface):
    _registry[provider.name] = provider

def get(name: str) -> ProviderInterface:
    return _registry[name]

def all() -> dict[str, ProviderInterface]:
    return _registry

# Import all provider modules to ensure they register themselves.
# These imports are for their side-effects (calling register()).
from . import openai # noqa: F401, E402
from . import anthropic # noqa: F401, E402
from . import google # noqa: F401, E402
from . import azure # noqa: F401, E402
