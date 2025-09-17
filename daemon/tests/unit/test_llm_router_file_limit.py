from pathlib import Path

from codechat.llm_router import LLMRouter
from codechat.config import get_config


class _FakeIndexer:
    def __init__(self, root: Path):
        self.root = root

    def query(self, text: str, top_k: int = 5):
        return []


def test_create_snippet_truncates_large_file(tmp_path: Path):
    big = tmp_path / "big.txt"
    big.write_text("a" * 2000, encoding="utf-8")

    cfg = get_config()
    prev = cfg.get("router.max_snippet_bytes")
    cfg["router.max_snippet_bytes"] = 100
    try:
        router = LLMRouter(_FakeIndexer(tmp_path))
        snippet = router._create_snippet_from_file_path(str(big), "test")
    finally:
        if prev is None:
            cfg.pop("router.max_snippet_bytes", None)
        else:
            cfg["router.max_snippet_bytes"] = prev

    assert snippet is not None
    assert "a" * 100 in snippet.content
    assert "a" * 101 not in snippet.content
    assert "[truncated]" in snippet.content
