# codechat/providers/__init__.py
from typing import Protocol, AsyncIterator
from codechat.models import QueryRequest

class ProviderInterface(Protocol):
    name: str                # "openai", "anthropic", …
    models: list[str]        # cached list or on‑demand call

    def send(self, req: QueryRequest) -> dict:             ...
    async def stream(self, req: QueryRequest) -> AsyncIterator[str]: ...
    def check_key(self) -> None:                           ... 

_registry: dict[str, ProviderInterface] = {}

def register(provider: ProviderInterface):
    _registry[provider.name] = provider

def get(name: str) -> ProviderInterface:
    return _registry[name]

def all() -> dict[str, ProviderInterface]:
    return _registry
