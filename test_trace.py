# -*- coding: utf-8 -*-
"""Turn/Step 可观测性测试锚（#282 M1，+10 锚）。

隔离：每例 monkeypatch XIAOJU3_TRACE_DB_PATH 到临时库；brain 侧挂钩
用源码锚锁（不真跑对话链——那是既有 1937 锚的事）。
"""
import os
import sqlite3

import pytest

import turn_trace


@pytest.fixture(autouse=True)
def _iso_db(tmp_path, monkeypatch):
    db = str(tmp_path / "trace.db")
    monkeypatch.setenv("XIAOJU3_TRACE_DB_PATH", db)
    monkeypatch.delenv("XIAOJU3_TRACE_ENABLED", raising=False)
    _DB["path"] = db
    yield db


_DB = {"path": None}


def _rows(table, order="id"):
    c = sqlite3.connect(_DB["path"])
    rows = c.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
    c.close()
    return rows


# 1/2 turn 包装：sync 路径 ok 落库（duration/status/steps 联动）
def test_turn_ok_roundtrip():
    with turn_trace.TurnTimer("sync"):
        turn_trace.record_step("local", "m1", 120, eval_count=42)
        turn_trace.record_tool("get_ha_devices")
    turns = _rows("turns")
    steps = _rows("steps")
    assert len(turns) == 1 and turns[0][4] == "ok"          # status
    assert turns[0][3] >= 0 and turns[0][6] == 1            # steps=1
    assert turns[0][7] == "get_ha_devices"                  # tool_names
    assert turns[0][5] == "local"                           # brain_source
    assert len(steps) == 1 and steps[0][6] == 42            # eval_count
    assert steps[0][1] == turns[0][0]                       # turn_id 关联


# 3 turn 异常路径：status=error 且异常照常抛出（不吞）
def test_turn_error_reraise():
    with pytest.raises(ValueError):
        with turn_trace.TurnTimer("sync"):
            raise ValueError("boom")
    turns = _rows("turns")
    assert turns[0][4] == "error" and "boom" in turns[0][8]


# 4 stream 入口同名包装（entry 区分）
def test_stream_entry():
    with turn_trace.TurnTimer("stream"):
        pass
    assert _rows("turns")[0][2] == "stream"


# 5 无活跃 turn 时 record_step 落行（turn_id=NULL，后台链路语义）
def test_step_without_turn():
    turn_trace.record_step("cloud", "deepseek", 300)
    steps = _rows("steps")
    assert len(steps) == 1 and steps[0][1] is None


# 6 工具名单聚合：两次 record_tool → 逗号连
def test_tool_names_joined():
    with turn_trace.TurnTimer("sync"):
        turn_trace.record_tool("tool_a")
        turn_trace.record_tool("tool_b")
    assert _rows("turns")[0][7] == "tool_a,tool_b"


# 7 混合来源：local+cloud → brain_source=mixed
def test_mixed_source():
    with turn_trace.TurnTimer("sync"):
        turn_trace.record_step("local", "m1", 50)
        turn_trace.record_step("cloud", "deepseek", 500)
    assert _rows("turns")[0][5] == "mixed"


# 8 开关关：零读写（db 文件都不建）
def test_enabled_off(tmp_path, monkeypatch):
    db = tmp_path / "off.db"
    monkeypatch.setenv("XIAOJU3_TRACE_DB_PATH", str(db))
    monkeypatch.setenv("XIAOJU3_TRACE_ENABLED", "0")
    assert turn_trace.turn_start("sync") is None
    turn_trace.record_step("local", "m", 1)
    turn_trace.record_tool("t")
    assert not os.path.exists(str(db))


# 9 故障兜底：路径不可建 → 全 API 静默不抛
def test_db_failure_silent(monkeypatch, tmp_path):
    bad = tmp_path / "file.txt"
    bad.write_text("x")
    monkeypatch.setenv("XIAOJU3_TRACE_DB_PATH", str(bad / "trace.db"))
    assert turn_trace.turn_start("sync") is None
    turn_trace.record_step("local", "m", 1)   # 不抛
    turn_trace.record_tool("t")               # 不抛
    turn_trace.turn_end(999)                  # 不抛


# 10 brain 源码锚：双入口改名包装 + step/tool 挂钩在位
def test_brain_hook_anchor():
    import inspect
    import brain
    src = inspect.getsource(brain)
    assert "def _smart_ask_impl(" in src
    assert "def _smart_ask_stream_impl(" in src
    assert src.count("turn_trace.TurnTimer(") == 2
    assert src.count("turn_trace.record_tool(") == 2
    assert "turn_trace.record_step(\"local\"" in src
    assert "turn_trace.record_step(\"cloud\"" in src
    # 静默纪律：模块缺席时 turn_trace=None 旁路
    assert "except ImportError:\n    turn_trace = None" in src


# 11 frozen 路径优先级：xiaoju3.AGENT_STATE_DIR 优先（同 mood 修复）
def test_db_path_prefers_xiaoju3(monkeypatch, tmp_path):
    import xiaoju3
    monkeypatch.delenv("XIAOJU3_TRACE_DB_PATH", raising=False)
    monkeypatch.setattr(xiaoju3, "AGENT_STATE_DIR", str(tmp_path))
    assert turn_trace._db_path() == os.path.join(str(tmp_path), "trace.db")
