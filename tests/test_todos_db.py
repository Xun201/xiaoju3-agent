# -*- coding: utf-8 -*-
"""待办独立拆库测试（2026-10-04）：XIAOJU3_TODOS_DB_PATH 指向共享
todos.db——缺省向后兼容（todos_db == memory_db）；分离模式 todos 落
分离库、memories 留原库；首访自动迁移（按列名保 id，幂等标记）；
WAL 生效；双实例共用互见。全离线（tmp 目录，绝不触真实 agent_state）。"""
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from agent_state.state_manager import StateManager


class TodosDbSplitTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name

    def _mgr(self, base_dir, todos_db=None):
        """构造 StateManager；todos_db 传入即注入分离模式环境变量。"""
        if todos_db:
            patcher = mock.patch.dict(
                os.environ, {"XIAOJU3_TODOS_DB_PATH": todos_db})
            patcher.start()
            self.addCleanup(patcher.stop)
        return StateManager(base_dir=base_dir)

    def test_default_todos_db_is_memory_db(self):
        """缺省（未设变量）：todos_db == memory_db，向后兼容零迁移。"""
        sm = self._mgr(os.path.join(self.tmp, "a"))
        self.assertEqual(sm.todos_db, sm.memory_db)
        sm.save_todos([{"content": "缺省行", "priority": "P1"}])
        con = sqlite3.connect(sm.memory_db)
        self.assertEqual(
            con.execute("SELECT COUNT(*) FROM todos").fetchone()[0], 1)
        con.close()

    def test_separated_todos_land_in_todos_db(self):
        """分离模式：todos 落 todos.db；memories 留 memory_db。"""
        base = os.path.join(self.tmp, "base")
        todos_db = os.path.join(self.tmp, "shared", "todos.db")
        sm = self._mgr(base, todos_db=todos_db)
        self.assertEqual(sm.todos_db, todos_db)
        sm.save_todos([{"content": "分离行", "priority": "P0"}])
        sm.save_memory("user", "一条记忆")
        con = sqlite3.connect(todos_db)
        self.assertEqual(
            con.execute("SELECT content FROM todos").fetchall(),
            [("分离行",)])
        con.close()
        con = sqlite3.connect(sm.memory_db)
        self.assertEqual(
            con.execute("SELECT COUNT(*) FROM todos").fetchone()[0], 0)
        self.assertEqual(
            con.execute("SELECT content FROM memories").fetchall(),
            [("一条记忆",)])
        con.close()

    def test_auto_migration_from_memory_db(self):
        """自动迁移：memory_db 已有 todos 行 → 首访分离库整表搬入
        （按列名保 id 保 priority）；源库原样保留（天然备份）。"""
        base = os.path.join(self.tmp, "base")
        old = StateManager(base_dir=base)   # 缺省模式写 2 行进 long_term.db
        old.save_todos([{"content": "行一", "priority": "P0"},
                        {"content": "行二", "priority": "P1"}])
        old.complete_todo(1)
        todos_db = os.path.join(self.tmp, "shared", "todos.db")
        sm = self._mgr(base, todos_db=todos_db)   # 分离模式首访 → 自动迁移
        rows = sm.get_todos()
        self.assertEqual(len(rows), 2)
        by_id = {r["id"]: r for r in rows}
        self.assertEqual(by_id[1]["status"], "done")      # done_at 随行搬入
        self.assertEqual(by_id[2]["priority"], "P1")      # 按列名不错位
        # 源库只读未动（天然备份）
        con = sqlite3.connect(sm.memory_db)
        self.assertEqual(
            con.execute("SELECT COUNT(*) FROM todos").fetchone()[0], 2)
        con.close()

    def test_migration_idempotent(self):
        """迁移幂等（todos_meta 标记）：重复初始化不重复搬入。"""
        base = os.path.join(self.tmp, "base")
        old = StateManager(base_dir=base)
        old.save_todos(["行一", "行二"])
        todos_db = os.path.join(self.tmp, "shared", "todos.db")
        sm1 = self._mgr(base, todos_db=todos_db)
        self.assertEqual(len(sm1.get_todos()), 2)
        sm2 = self._mgr(base, todos_db=todos_db)   # 重复初始化
        self.assertEqual(len(sm2.get_todos()), 2)  # 不翻倍

    def test_two_instances_share_todos_db(self):
        """两版共用场景：两个 StateManager（不同 base_dir、同一
        todos.db）一写另一立即可见（SQLite 短连接跨进程语义）。"""
        todos_db = os.path.join(self.tmp, "shared", "todos.db")
        sm1 = self._mgr(os.path.join(self.tmp, "base1"), todos_db=todos_db)
        sm2 = self._mgr(os.path.join(self.tmp, "base2"), todos_db=todos_db)
        sm1.save_todos([{"content": "共用行", "priority": "P1"}])
        rows = sm2.get_todos()
        self.assertEqual([r["content"] for r in rows], ["共用行"])

    def test_wal_mode_on_separated_todos_db(self):
        """WAL 生效：分离 todos_db journal_mode = wal；memory_db 保持
        delete（不动）。"""
        base = os.path.join(self.tmp, "base")
        todos_db = os.path.join(self.tmp, "shared", "todos.db")
        self._mgr(base, todos_db=todos_db)
        con = sqlite3.connect(todos_db)
        self.assertEqual(
            con.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        con.close()
        memory_db = os.path.join(base, "long_term.db")
        con = sqlite3.connect(memory_db)
        self.assertEqual(
            con.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        con.close()


if __name__ == "__main__":
    unittest.main()
