# -*- coding: utf-8 -*-
"""待办单向同步测试（2026-10-04 方案 A，测试版为主）：dashboard.
_sync_todos_from_source 整表覆盖式同步——源不存在跳过 / 空目标全量
搬 / 列序差异按列名映射（测试库 priority 为旧版 ALTER 追加在末尾）/
环境变量未设不触发 / 源行违约目标回滚 / mtime 水位防重复。全离线
（tmp 目录双库，绝不触碰真实 agent_state）。"""
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agent_state.state_manager import StateManager
import xiaoju3_dashboard as dashboard

# 源库旧版列序 DDL（2026-10-04 实测：测试库 priority 为旧版 ALTER 追加
# 在末尾，与新版建表中置不同——同步必须按列名，本文件③专门验证）
_OLD_ORDER_DDL = """
    CREATE TABLE todos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        source_url TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        done_at DATETIME,
        priority TEXT NOT NULL DEFAULT 'P1'
    )
"""
# 新版列序 DDL（正式库同款；测试里目标库用 StateManager 建表即为此序）


def _create_source(path, ddl=_OLD_ORDER_DDL):
    con = sqlite3.connect(path)
    con.execute(ddl)
    con.commit()
    con.close()


def _seed(path, rows, ddl=None):
    """按列名插种子行。rows = [(id, content, status, priority), ...]"""
    con = sqlite3.connect(path)
    if ddl is not None:
        con.execute(ddl)
    con.executemany(
        "INSERT INTO todos (id, content, source_url, status, priority)"
        " VALUES (?, ?, '', ?, ?)", rows)
    con.commit()
    con.close()


def _rows_of(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    out = [tuple(r) for r in con.execute(
        "SELECT id, content, status, priority FROM todos ORDER BY id")]
    con.close()
    return out


class TodoSyncTests(unittest.TestCase):
    """待办单向同步（方案 A）：六条锚覆盖任务书 ①-⑤ + mtime 水位。
    每条用例独立 tmp 双库，XIAOJU3_TODO_SYNC_SOURCE 经 patch.dict 注入。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.source = os.path.join(self.tmp, "source_long_term.db")
        self.target_dir = os.path.join(self.tmp, "target_agent_state")
        self.target = os.path.join(self.target_dir, "long_term.db")
        self.watermark = os.path.join(self.target_dir,
                                      ".todo_sync_watermark")

    def _with_env(self, path):
        return mock.patch.dict(os.environ,
                               {"XIAOJU3_TODO_SYNC_SOURCE": path})

    def test_missing_source_skips_and_target_untouched(self):
        """① 源库不存在：返回 skip、不报错、目标原有行原样保留。"""
        target = StateManager(base_dir=self.target_dir)
        target.save_todos([{"content": "正式版本地行", "priority": "P0"}])
        before = _rows_of(self.target)
        with self._with_env(os.path.join(self.tmp, "none.db")):
            result = dashboard._sync_todos_from_source(
                target_db=self.target)
        self.assertTrue(result.startswith("skip"))
        self.assertIn("源库不存在", result)
        self.assertEqual(_rows_of(self.target), before)

    def test_sync_fills_empty_target_and_writes_watermark(self):
        """② 源库存在、目标空：同步后行数与内容一致，水位文件落盘。"""
        _create_source(self.source)
        _seed(self.source, [
            (1, "写周报", "pending", "P1"),
            (2, "交房租", "pending", "P0"),
            (3, "复查代码", "done", "P2"),
        ])
        StateManager(base_dir=self.target_dir)   # 目标空库（新版列序）
        with self._with_env(self.source):
            result = dashboard._sync_todos_from_source(
                target_db=self.target)
        self.assertTrue(result.startswith("ok"))
        self.assertIn("3 条", result)
        self.assertEqual(_rows_of(self.target), _rows_of(self.source))
        self.assertTrue(os.path.exists(self.watermark))

    def test_column_order_mismatch_maps_by_name(self):
        """③ 列序不同（源=旧版 priority 在末尾，目标=新版中置）：按列名
        映射，priority/status/content 不错位。"""
        _create_source(self.source, ddl=_OLD_ORDER_DDL)
        _seed(self.source, [
            (7, "P0 行", "pending", "P0"),
            (9, "P2 行", "done", "P2"),
        ])
        StateManager(base_dir=self.target_dir)
        with self._with_env(self.source):
            dashboard._sync_todos_from_source(target_db=self.target)
        self.assertEqual(
            _rows_of(self.target),
            [(7, "P0 行", "pending", "P0"), (9, "P2 行", "done", "P2")])

    def test_env_unset_skips_sync(self):
        """④ 环境变量未设：不触发同步（目标预置行原样）——测试版实例
        不设此变量即天然不同步。"""
        target = StateManager(base_dir=self.target_dir)
        target.save_todos([{"content": "目标预置", "priority": "P1"}])
        before = _rows_of(self.target)
        _create_source(self.source)
        _seed(self.source, [(1, "源行", "pending", "P1")])
        with mock.patch.dict(os.environ):
            os.environ.pop("XIAOJU3_TODO_SYNC_SOURCE", None)
            result = dashboard._sync_todos_from_source(
                target_db=self.target)
        self.assertTrue(result.startswith("skip"))
        self.assertIn("未设置", result)
        self.assertEqual(_rows_of(self.target), before)

    def test_rollback_keeps_target_on_source_violation(self):
        """⑤ 同步中抛异常（源行 content=None 违反目标 NOT NULL）→
        单事务回滚，目标保持原状、不出现半截数据。"""
        broken_ddl = """
            CREATE TABLE todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT,
                source_url TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                done_at DATETIME,
                priority TEXT NOT NULL DEFAULT 'P1'
            )
        """
        _create_source(self.source, ddl=broken_ddl)   # content 允许 NULL
        con = sqlite3.connect(self.source)
        con.executemany(
            "INSERT INTO todos (id, content, status, priority)"
            " VALUES (?, ?, ?, ?)",
            [(1, "好行", "pending", "P1"), (2, None, "pending", "P1"),
             (3, "另一行", "pending", "P1")])
        con.commit()
        con.close()
        target = StateManager(base_dir=self.target_dir)
        target.save_todos([{"content": "原行A", "priority": "P1"},
                           {"content": "原行B", "priority": "P0"}])
        before = _rows_of(self.target)
        with self._with_env(self.source):
            result = dashboard._sync_todos_from_source(
                target_db=self.target)
        self.assertTrue(result.startswith("❌"))
        self.assertIn("保持原状", result)
        self.assertEqual(_rows_of(self.target), before)   # 无半截数据
        self.assertFalse(os.path.exists(self.watermark))  # 水位不推进

    def test_watermark_skips_unchanged_source(self):
        """⑥ mtime 水位：同步成功后源库未变 → 再次调用跳过；源库 mtime
        变化（os.utime 拨针模拟新写入）→ 再次同步生效。"""
        _create_source(self.source)
        _seed(self.source, [(1, "第一轮", "pending", "P1")])
        StateManager(base_dir=self.target_dir)
        with self._with_env(self.source):
            first = dashboard._sync_todos_from_source(
                target_db=self.target)
            self.assertTrue(first.startswith("ok"))
            second = dashboard._sync_todos_from_source(
                target_db=self.target)
            self.assertTrue(second.startswith("skip"))
            self.assertIn("水位一致", second)
            st = os.stat(self.source)
            os.utime(self.source, (st.st_atime + 100, st.st_mtime + 100))
            third = dashboard._sync_todos_from_source(
                target_db=self.target)
            self.assertTrue(third.startswith("ok"))


if __name__ == "__main__":
    unittest.main()
