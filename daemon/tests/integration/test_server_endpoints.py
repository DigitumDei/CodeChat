# tests/integration/test_server_endpoints.py
import pytest
from fastapi.testclient import TestClient
from codechat.server import app

@pytest.fixture(scope="module")
def client():
    return TestClient(app)

def test_health_ok(client):
    assert client.get("/health").json() == {"status": "ok"}

def test_validation_error(client):
    res = client.post("/query", json={"foo": "bar"})
    assert res.status_code == 422
    payload = res.json()
    assert payload["error"]["code"] == "VALIDATION_ERR"
