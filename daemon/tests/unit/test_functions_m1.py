from pathlib import Path

from codechat.functions import (
    get_global_registry,
    FunctionExecutor,
)
from codechat.functions.models import ExecutionContext, FunctionCall


def test_registry_contains_read_file():
    reg = get_global_registry()
    names = {d.name for d in reg.list_definitions()}
    assert "read_file" in names


def test_read_file_success(tmp_path: Path):
    p = tmp_path / "hello.txt"
    p.write_text("hello world", encoding="utf-8")

    ctx = ExecutionContext(root=tmp_path)
    with FunctionExecutor() as executor:
        call = FunctionCall(name="read_file", arguments={"path": "hello.txt"})
        res = executor.execute_function(call, ctx)
    assert res.success
    assert "hello world" in str(res.output)


def test_read_file_prevents_escape(tmp_path: Path):
    ctx = ExecutionContext(root=tmp_path)
    with FunctionExecutor() as executor:
        call = FunctionCall(name="read_file", arguments={"path": "../outside.txt"})
        res = executor.execute_function(call, ctx)
    assert not res.success
    assert "escape" in (res.error or "") or "Absolute" in (res.error or "")


def test_read_file_max_bytes(tmp_path: Path):
    p = tmp_path / "data.txt"
    p.write_text("abcdefghij", encoding="utf-8")  # 10 bytes ASCII

    ctx = ExecutionContext(root=tmp_path)
    with FunctionExecutor() as executor:
        call = FunctionCall(name="read_file", arguments={"path": "data.txt", "max_bytes": 5})
        res = executor.execute_function(call, ctx)
    assert res.success
    assert str(res.output) == "abcde"

