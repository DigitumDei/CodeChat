import builtins
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from codechat import config
from codechat.llm_router import LLMRouter
from codechat.models import ProviderType, QueryRequest
from codechat.providers.openai import OpenAIProvider


class DummyIndexer:
    """Minimal Indexer stub for tests."""

    root = Path(".")

    def query(self, message: str, top_k: int = 5):  # pragma: no cover - simple stub
        return []


def write_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, content) -> None:
    """Helper to patch `set_config` to load from temporary content."""
    cfg_file = tmp_path / "config.json"
    if isinstance(content, str):
        cfg_file.write_text(content)
    else:
        cfg_file.write_text(json.dumps(content))
    monkeypatch.setattr(config.os.path, "exists", lambda path: True)
    monkeypatch.setattr(
        config,
        "open",
        lambda path, *args, **kwargs: builtins.open(cfg_file, *args, **kwargs),
        raising=False,
    )
    config.set_config()


def make_request() -> QueryRequest:
    return QueryRequest(provider=ProviderType.OPENAI, model="gpt-4", message="hi")


def test_reload_config_missing_openai_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "_cfg", {})
    write_config(monkeypatch, tmp_path, {})
    router = LLMRouter(DummyIndexer())
    with pytest.raises(HTTPException) as exc:
        router.route(make_request())
    assert exc.value.status_code == 400


def test_reload_config_after_setting_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "_cfg", {})
    write_config(monkeypatch, tmp_path, {})
    router = LLMRouter(DummyIndexer())
    req = make_request()
    with pytest.raises(HTTPException):
        router.route(req)

    def fake_send(self, req):
        self.check_key()
        return {"text": "ok"}

    monkeypatch.setattr(OpenAIProvider, "send", fake_send)
    write_config(monkeypatch, tmp_path, {"openai.key": "sk-test"})
    result = router.route(req)
    assert result["text"] == "ok"


def test_set_config_invalid_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "_cfg", {})
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("{ invalid json }")
    monkeypatch.setattr(config.os.path, "exists", lambda path: True)
    monkeypatch.setattr(
        config,
        "open",
        lambda path, *args, **kwargs: builtins.open(cfg_file, *args, **kwargs),
        raising=False,
    )
    with pytest.raises(json.JSONDecodeError):
        config.set_config()
