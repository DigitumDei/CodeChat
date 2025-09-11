# tests/integration/test_server_endpoints.py
import json
import importlib
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def server_module(monkeypatch):
    import codechat.indexer as indexer_module
    monkeypatch.setattr(indexer_module.Indexer, "build_index", lambda self: None)
    server = importlib.import_module("codechat.server")
    monkeypatch.setattr(server.watcher, "start", lambda: None)
    return server


@pytest.fixture()
def client(server_module):
    return TestClient(server_module.app)

def test_health_ok(client):
    assert client.get("/health").json() == {"status": "ok"}

def test_validation_error(client):
    res = client.post("/query", json={"foo": "bar"})
    assert res.status_code == 422
    payload = res.json()
    assert payload["error"]["code"] == "VALIDATION_ERR"


def test_stream_sse(client, server_module, monkeypatch):
    async def fake_stream(_: server_module.QueryRequest):
        for chunk in [
            json.dumps({"token": "hello", "finish": False}),
            json.dumps({"token": " world", "finish": False}),
            json.dumps({"token": "", "finish": True}),
        ]:
            yield chunk

    monkeypatch.setattr(server_module.router, "stream", fake_stream)

    payload = {
        "provider": "openai",
        "model": "gpt-test",
        "history": [],
        "message": "hi",
    }

    with client.stream("POST", "/query?stream=true", json=payload) as res:
        events = []
        for line in res.iter_lines():
            if line:
                assert line.startswith("data: ")
                events.append(json.loads(line[6:]))

    text = "".join(e.get("token", "") for e in events)
    assert text == "hello world"
    assert events[-1]["finish"] is True


def test_stream_sse_error(client, server_module, monkeypatch):
    async def fake_stream(_: server_module.QueryRequest):
        if False:
            yield ""  # pragma: no cover
        raise RuntimeError("boom")

    monkeypatch.setattr(server_module.router, "stream", fake_stream)

    payload = {
        "provider": "openai",
        "model": "gpt-test",
        "history": [],
        "message": "hi",
    }

    with client.stream("POST", "/query?stream=true", json=payload) as res:
        events = []
        for line in res.iter_lines():
            if line:
                assert line.startswith("data: ")
                events.append(json.loads(line[6:]))

    assert events[-1]["error"] == "boom"
    assert events[-1]["finish"] is True
