from pathlib import Path
from typing import AsyncIterator

import pytest

from codechat.llm_router import LLMRouter
from codechat.models import QueryRequest, ProviderType, ChatMessage
from codechat.functions.models import FunctionDefinition, FunctionCall
from codechat import providers


class _FakeIndexer:
    def __init__(self, root: Path):
        self.root = root
        class _DG:
            def get_direct_dependencies(self, p):
                return set()
            def get_direct_dependents(self, p):
                return set()
            def get_all_dependencies(self, p):
                return set()
            def get_all_dependents(self, p):
                return set()
        self.dgraph = _DG()
    def query(self, text: str, top_k: int = 5):
        return []


class _StubProvider:
    name = "openai"
    def __init__(self):
        self._called = 0
    def send(self, req: QueryRequest) -> dict:
        return {"text": "stub"}
    async def stream(self, req: QueryRequest) -> AsyncIterator[str]:
        yield "{}"  # not used in this test
    def invoke_with_tools(self, req: QueryRequest, functions: list[FunctionDefinition]) -> dict:
        self._called += 1
        if self._called == 1:
            return {"function_calls": [FunctionCall(name="read_file", arguments={"path": "hello.txt"})]}
        return {"text": "Done after tools."}


@pytest.mark.asyncio
async def test_stream_with_tools_reads_file(tmp_path: Path, monkeypatch):
    # Prepare file
    f = tmp_path / "hello.txt"
    f.write_text("hi there", encoding="utf-8")

    # Router with fake indexer rooted at tmp_path
    router = LLMRouter(_FakeIndexer(tmp_path))

    # Swap in a stub provider for OPENAI and restore after
    stub = _StubProvider()
    original = providers.get("openai")
    providers.register(stub)

    req = QueryRequest(
        provider=ProviderType.OPENAI,
        model="gpt-test",
        history=[ChatMessage(role="user", content="Please read the file." )],
        message="Use tools.",
    )

    try:
        chunks = []
        async for ch in router.stream_with_functions(req):
            chunks.append(ch)
        text = "".join([__import__("json").loads(c).get("token", "") for c in chunks])
        assert "Done after tools." in text
    finally:
        providers.register(original)
