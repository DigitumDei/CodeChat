import threading
from pathlib import Path

from codechat.llm_router import LLMRouter
from codechat.models import QueryRequest, ProviderType, ChatMessage
from codechat.functions.models import FunctionDefinition, FunctionCall
from codechat import providers
from codechat.functions.executor import FunctionExecutor


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
    async def stream(self, req: QueryRequest):
        yield "{}"
    def invoke_with_tools(self, req: QueryRequest, functions: list[FunctionDefinition]) -> dict:
        self._called += 1
        if self._called == 1:
            return {"function_calls": [FunctionCall(name="read_file", arguments={"path": "data.txt"})]}
        return {"text": "done"}


def _count_threads() -> int:
    return len([t for t in threading.enumerate() if t.name.startswith("ThreadPoolExecutor")])


def test_executor_context_manager_closes_threads():
    before = _count_threads()
    with FunctionExecutor() as ex:
        future = ex._pool.submit(lambda: None)
        future.result()
    after = _count_threads()
    assert after == before


def test_llm_router_no_thread_leak(tmp_path: Path):
    f = tmp_path / "data.txt"
    f.write_text("hi", encoding="utf-8")
    router = LLMRouter(_FakeIndexer(tmp_path))
    stub = _StubProvider()
    orig = providers.get("openai")
    providers.register(stub)
    req = QueryRequest(provider=ProviderType.OPENAI, model="gpt-test", history=[ChatMessage(role="user", content="hi")], message="Use tools.")
    before = _count_threads()
    try:
        router.process_request_with_functions(req)
    finally:
        providers.register(orig)
    after = _count_threads()
    assert after == before
