# -*- coding: utf-8 -*-
"""Turn/Step 可观测性（#282 M1）——三条链的行车记录仪。

设计稿：_dev/design_282_turn_step_observability.md。
- Turn = 一次用户输入到回答结束（smart_ask / smart_ask_stream 一次
  完整调用）；Step = 一次 LLM 调用（ask_local / ask_cloud 单次进出）。
- 落盘 agent_state/trace.db 两表（turns/steps），contextvars 关联
  （QQ/心跳/控制台多线程各自独立上下文）；
- **只记元数据**（时长/来源/状态/工具名），零消息内容零参数值；
- 安全边界与 mood 同款纪律：XIAOJU3_TRACE_ENABLED 开关缺省开、任何
  异常静默、trace.db 不可建即全程旁路、本模块可整体删除（brain 挂
  钩处 ImportError 即 no-op）。
"""
import contextvars
import os
import sqlite3
import time
from datetime import datetime

TURNS_KEEP = 2000
STEPS_KEEP = 10000

_turn_id = contextvars.ContextVar("trace_turn_id", default=None)
_turn_meta = contextvars.ContextVar("trace_turn_meta", default=None)

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    entry TEXT NOT NULL,
    duration_ms INTEGER,
    status TEXT NOT NULL,
    brain_source TEXT,
    steps INTEGER NOT NULL DEFAULT 0,
    tool_names TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id INTEGER,
    ts TEXT NOT NULL,
    brain TEXT NOT NULL,
    model TEXT,
    duration_ms INTEGER,
    eval_count INTEGER,
    status TEXT NOT NULL
);
"""


def enabled():
    return str(os.environ.get("XIAOJU3_TRACE_ENABLED", "1")).strip().lower() \
        not in ("0", "false", "off")


def _db_path():
    p = os.environ.get("XIAOJU3_TRACE_DB_PATH")
    if p:
        return p
    base = os.environ.get("AGENT_STATE_DIR") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "agent_state")
    return os.path.join(base, "trace.db")


def _connect():
    conn = sqlite3.connect(_db_path())
    conn.executescript(SCHEMA)
    return conn


def _now():
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def turn_start(entry):
    """Turn 开始：返回 turn_id（旁路/故障返回 None，调用方无需判断）。"""
    if not enabled():
        return None
    try:
        conn = _connect()
        cur = conn.execute(
            "INSERT INTO turns (ts, entry, status) VALUES (?, ?, 'running')",
            (_now(), entry))
        conn.commit()
        tid = cur.lastrowid
        conn.close()
        _turn_id.set(tid)
        _turn_meta.set({"steps": 0, "tools": [], "sources": []})
        return tid
    except Exception:
        return None


def turn_end(tid, status="ok", error=None):
    """Turn 结束：汇总 steps/tool/source 写回 turns 行（静默）。"""
    if not tid or not enabled():
        return
    try:
        meta = _turn_meta.get() or {}
        sources = [s for s in meta.get("sources", []) if s]
        source = ("mixed" if len(set(sources)) > 1
                  else (sources[0] if sources else None))
        duration = None  # 由包装层传 start 检测的 perf_counter 更准——此处留空
        conn = _connect()
        with conn:
            conn.execute(
                "UPDATE turns SET status=?, brain_source=?, steps=?,"
                " tool_names=?, error=? WHERE id=?",
                (status, source, meta.get("steps", 0),
                 ",".join(meta.get("tools", [])), error, tid))
            conn.execute(
                "DELETE FROM turns WHERE id NOT IN"
                " (SELECT id FROM turns ORDER BY id DESC LIMIT ?)",
                (TURNS_KEEP,))
        conn.close()
    except Exception:
        pass
    finally:
        _turn_id.set(None)
        _turn_meta.set(None)


class TurnTimer:
    """turn 包装助手：turn_start + perf_counter，with 语法自动 end。

    用法：
        with TurnTimer("sync") as t:
            result = impl(...)
        # 异常自动记 error 并 re-raise
    """

    def __init__(self, entry):
        self.entry = entry
        self.tid = None
        self._t0 = None

    def __enter__(self):
        self.tid = turn_start(self.entry)
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.tid and enabled():
            duration = int((time.perf_counter() - self._t0) * 1000)
            try:
                conn = _connect()
                conn.execute("UPDATE turns SET duration_ms=? WHERE id=?",
                             (duration, self.tid))
                conn.commit()
                conn.close()
            except Exception:
                pass
            turn_end(self.tid,
                     status="error" if exc_type else "ok",
                     error=str(exc) if exc else None)
        return False  # 不吞异常


def record_step(brain_source, model=None, duration_ms=None, eval_count=None,
                status="ok"):
    """Step 记录（ask_local/ask_cloud 单次调用）；无活跃 turn 时
    turn_id=NULL 仍落行（如心跳/后台链路）。全程静默。"""
    if not enabled():
        return
    try:
        meta = _turn_meta.get()
        if meta is not None:
            meta["steps"] += 1
            meta["sources"].append(brain_source)
        conn = _connect()
        with conn:
            conn.execute(
                "INSERT INTO steps (turn_id, ts, brain, model,"
                " duration_ms, eval_count, status) VALUES (?,?,?,?,?,?,?)",
                (_turn_id.get(), _now(), brain_source, model,
                 duration_ms, eval_count, status))
            conn.execute(
                "DELETE FROM steps WHERE id NOT IN"
                " (SELECT id FROM steps ORDER BY id DESC LIMIT ?)",
                (STEPS_KEEP,))
        conn.close()
    except Exception:
        pass


def record_tool(name):
    """工具调用名单记录（M1 名字级；result 细分留 M2）。"""
    if not enabled() or not name:
        return
    try:
        meta = _turn_meta.get()
        if meta is not None:
            meta["tools"].append(str(name))
    except Exception:
        pass


def stats(days=1):
    """CLI 摘要数据：最近 N 天 (turns, avg_ms, local_pct, errors)。"""
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT COUNT(*), AVG(duration_ms),"
            " SUM(CASE WHEN brain_source='local' THEN 1 ELSE 0 END),"
            " SUM(CASE WHEN status='error' THEN 1 ELSE 0 END)"
            " FROM turns WHERE ts >= datetime('now','localtime',?)",
            (f"-{int(days)} days",)).fetchone()
        conn.close()
        return {"turns": row[0] or 0, "avg_ms": round(row[1] or 0),
                "local_turns": row[2] or 0, "errors": row[3] or 0}
    except Exception:
        return {"turns": 0, "avg_ms": 0, "local_turns": 0, "errors": 0}
