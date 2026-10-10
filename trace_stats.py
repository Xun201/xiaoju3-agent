# -*- coding: utf-8 -*-
"""trace.db CLI 摘要（#282 M1 消费端）：python trace_stats.py [天数]

零依赖（标准库）；默认最近 1 天。只读打开。
"""
import os
import sqlite3
import sys

BASE = os.environ.get("AGENT_STATE_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "agent_state")


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    db = os.environ.get("XIAOJU3_TRACE_DB_PATH") or os.path.join(
        BASE, "trace.db")
    if not os.path.exists(db):
        print(f"（无观测数据：{db} 不存在——trace 未产生记录或开关关闭）")
        return
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    turns, avg_ms, errors = conn.execute(
        "SELECT COUNT(*), COALESCE(AVG(duration_ms),0),"
        " SUM(CASE WHEN status='error' THEN 1 ELSE 0 END)"
        " FROM turns WHERE ts >= datetime('now','localtime', ?)",
        (f"-{days} days",)).fetchone()
    local = conn.execute(
        "SELECT COUNT(*) FROM turns WHERE brain_source='local'"
        " AND ts >= datetime('now','localtime', ?)",
        (f"-{days} days",)).fetchone()[0]
    cloud = conn.execute(
        "SELECT COUNT(*) FROM turns WHERE brain_source='cloud'"
        " AND ts >= datetime('now','localtime', ?)",
        (f"-{days} days",)).fetchone()[0]
    top_tools = conn.execute(
        "SELECT tool_names, COUNT(*) FROM turns"
        " WHERE tool_names IS NOT NULL AND tool_names != ''"
        " AND ts >= datetime('now','localtime', ?)"
        " GROUP BY tool_names ORDER BY COUNT(*) DESC LIMIT 5",
        (f"-{days} days",)).fetchall()
    avg_step = conn.execute(
        "SELECT brain, COUNT(*), COALESCE(AVG(duration_ms),0),"
        " COALESCE(AVG(eval_count),0) FROM steps"
        " WHERE ts >= datetime('now','localtime', ?)"
        " GROUP BY brain", (f"-{days} days",)).fetchall()
    conn.close()

    print(f"=== Turn/Step 观测摘要（最近 {days} 天，{db}） ===")
    print(f"Turns: {turns}  | 平均耗时 {avg_ms:.0f}ms  | 错误 {errors or 0}"
          f"  | local {local} / cloud {cloud}")
    for brain, n, ms, tok in avg_step:
        print(f"Step[{brain}]: {n} 次 | 平均 {ms:.0f}ms | 平均 eval_count"
              f" {tok:.0f}")
    if top_tools:
        print("工具调用 TOP:")
        for names, n in top_tools:
            print(f"  {n:>4}  {names[:60]}")


if __name__ == "__main__":
    main()
