# -*- coding: utf-8 -*-
"""agent_state/state_manager 单元测试：建库 / 存取 / 截断 / 并发。

全部离线可跑，数据库与会话文件均写入 tempfile 临时目录。
"""
import contextlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest

from agent_state.state_manager import StateManager


@contextlib.contextmanager
def _quiet_stdout():
    """吞掉模块内的 print（含 emoji），保持测试输出干净且编码安全。"""
    with contextlib.redirect_stdout(io.StringIO()):
        yield


class StateManagerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_state_")
        with _quiet_stdout():
            self.sm = StateManager(base_dir=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- 建库 ----

    def test_init_creates_db_and_memories_table(self):
        db_path = os.path.join(self.tmp, "long_term.db")
        self.assertTrue(os.path.isfile(db_path))
        conn = sqlite3.connect(db_path)
        try:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(memories)")]
            self.assertEqual(cols, ["id", "category", "content", "timestamp"])
        finally:
            conn.close()

    def test_explicit_base_dir_layout(self):
        # 显式传参时库与身份文件都落在指定目录，不触碰默认 AGENT_STATE_DIR
        self.assertEqual(self.sm.memory_db, os.path.join(self.tmp, "long_term.db"))
        self.assertEqual(self.sm.identity_file, os.path.join(self.tmp, "identity.json"))

    def test_init_on_empty_base_dir(self):
        # 目录不存在时也能惰性创建并建库
        fresh = os.path.join(self.tmp, "nested", "state")
        sm = StateManager(base_dir=fresh)
        self.assertTrue(os.path.isfile(os.path.join(fresh, "long_term.db")))

    # ---- 存取 ----

    def test_save_and_get_recent_memories(self):
        with _quiet_stdout():
            self.sm.save_memory("事实", "用户喜欢橙色")
            self.sm.save_memory("偏好", "回答要简短")
        rows = self.sm.get_recent_memories(limit=5)
        self.assertEqual(len(rows), 2)
        self.assertEqual({r[0] for r in rows}, {"事实", "偏好"})
        self.assertEqual({r[1] for r in rows}, {"用户喜欢橙色", "回答要简短"})

    def test_get_recent_memories_returns_newest_first(self):
        with _quiet_stdout():
            self.sm.save_memory("早期", "第一条")
            time.sleep(1.1)  # CURRENT_TIMESTAMP 为秒级精度，错开时间戳保证顺序确定
            self.sm.save_memory("最近", "第二条")
        self.assertEqual(self.sm.get_recent_memories(limit=1), [("最近", "第二条")])

    def test_default_limit_is_five(self):
        with _quiet_stdout():
            for i in range(7):
                self.sm.save_memory("t", f"m{i}")
        self.assertEqual(len(self.sm.get_recent_memories()), 5)

    def test_get_recent_memories_on_empty_db(self):
        self.assertEqual(self.sm.get_recent_memories(limit=3), [])

    # ---- 截断 ----

    def test_save_conversation_keeps_recent_max_messages(self):
        from xiaoju3 import MAX_MESSAGES
        total = MAX_MESSAGES + 10
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(total)]

        self.sm.save_conversation("test", messages)

        path = os.path.join(self.tmp, "conversations", "test_history.json")
        self.assertTrue(os.path.isfile(path))
        with open(path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(len(saved), MAX_MESSAGES)
        self.assertEqual(saved[0]["content"], f"msg{total - MAX_MESSAGES}")
        self.assertEqual(saved[-1]["content"], f"msg{total - 1}")

    def test_save_conversation_short_history_untouched(self):
        messages = [{"role": "assistant", "content": "你好呀"}]
        self.sm.save_conversation("web", messages)
        path = os.path.join(self.tmp, "conversations", "web_history.json")
        with open(path, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), messages)

    def test_save_conversation_overwrites_previous(self):
        self.sm.save_conversation("qq", [{"role": "user", "content": "旧"}])
        self.sm.save_conversation("qq", [{"role": "user", "content": "新"}])
        path = os.path.join(self.tmp, "conversations", "qq_history.json")
        with open(path, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), [{"role": "user", "content": "新"}])

    # ---- 并发 ----

    def test_concurrent_save_memory(self):
        errors = []
        barrier = threading.Barrier(4)

        def worker(tid):
            try:
                barrier.wait()
                for i in range(10):
                    self.sm.save_memory("并发", f"线程{tid}-{i}")
            except Exception as e:  # pragma: no cover - 仅在异常时记录
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
        with _quiet_stdout():
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(self.sm.get_recent_memories(limit=1000)), 40)


class TodoStoreTests(unittest.TestCase):
    """todos 表（2026-10-04 待办提取，docs/TODO_EXTRACT_DESIGN.md §2）：
    写入幂等 / 过滤排序 / 完成语义 / CHECK 约束。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_todos_")
        with _quiet_stdout():
            self.sm = StateManager(base_dir=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_returns_inserted_and_skipped_counts(self):
        inserted, skipped = self.sm.save_todos(["买牛奶", " 写周报 ", "", None],
                                               source_url="u1")
        self.assertEqual((inserted, skipped), (2, 0))   # 空串/None 直接丢弃
        rows = self.sm.get_todos(status="pending")
        self.assertEqual([r["content"] for r in rows], ["买牛奶", "写周报"])
        self.assertTrue(all(r["source_url"] == "u1" for r in rows))
        self.assertTrue(all(r["done_at"] is None for r in rows))

    def test_dedup_same_source_normalized(self):
        self.sm.save_todos(["买牛奶"], source_url="u1")
        inserted, skipped = self.sm.save_todos(["买 牛 奶"], source_url="u1")
        self.assertEqual((inserted, skipped), (0, 1))   # 规范化去空白后同文跳过

    def test_same_content_diff_source_not_deduped(self):
        self.sm.save_todos(["买牛奶"], source_url="u1")
        inserted, _ = self.sm.save_todos(["买牛奶"], source_url="u2")
        self.assertEqual(inserted, 1)

    def test_empty_source_url_groups_together(self):
        self.sm.save_todos(["A"])
        inserted, skipped = self.sm.save_todos(["A"])
        self.assertEqual((inserted, skipped), (0, 1))   # 缺省 source_url 同组幂等

    def test_get_filter_and_order(self):
        self.sm.save_todos(["A", "B", "C"])
        self.sm.complete_todo(2)
        pending = self.sm.get_todos(status="pending")
        done = self.sm.get_todos(status="done")
        self.assertEqual([r["id"] for r in pending], [1, 3])          # pending 按 id ASC
        self.assertEqual([r["id"] for r in done], [2])                # done
        self.assertIsNotNone(done[0]["done_at"])
        all_rows = self.sm.get_todos()                                # 全部按 id DESC
        self.assertEqual([r["id"] for r in all_rows], [3, 2, 1])

    def test_complete_returns_row_and_is_idempotent(self):
        self.sm.save_todos(["A"])
        done = self.sm.complete_todo(1)
        self.assertEqual(done["id"], 1)
        self.assertEqual(done["status"], "done")
        self.assertIsNotNone(done["done_at"])
        self.assertIsNone(self.sm.complete_todo(1))     # 重复完成 → None（幂等）
        self.assertIsNone(self.sm.complete_todo(999))   # 不存在 id → None

    def test_reopen_restores_pending_and_is_idempotent(self):
        # 尾巴 1：复选框取消钩——done 翻回 pending、done_at 清空、幂等
        self.sm.save_todos(["A"], source_url="u1")
        self.sm.complete_todo(1)
        reopened = self.sm.reopen_todo(1)
        self.assertEqual(reopened["id"], 1)
        self.assertEqual(reopened["status"], "pending")
        self.assertIsNone(reopened["done_at"])
        self.assertIsNone(self.sm.reopen_todo(1))       # 已是 pending → None（幂等）
        self.assertIsNone(self.sm.reopen_todo(999))     # 不存在 id → None
        # 翻回后可再次完成（双向闭环）
        self.assertEqual(self.sm.complete_todo(1)["status"], "done")

    def test_save_accepts_dict_items_with_priority(self):
        # 尾巴 C：dict 条目（content+priority）入库；非法优先级归一 P1
        inserted, _ = self.sm.save_todos(
            [{"content": "A", "priority": "P0"}, {"content": "B", "priority": "urgent"}],
            source_url="u1")
        self.assertEqual(inserted, 2)
        rows = {r["content"]: r["priority"] for r in self.sm.get_todos(status="pending")}
        self.assertEqual(rows, {"A": "P0", "B": "P1"})

    def test_set_todo_priority(self):
        self.sm.save_todos(["A"], source_url="u1")
        row = self.sm.set_todo_priority(1, "P2")
        self.assertEqual(row["priority"], "P2")
        self.assertEqual(self.sm.set_todo_priority(1, "urgent")["priority"], "P1")  # 归一
        self.assertIsNone(self.sm.set_todo_priority(999, "P0"))  # 不存在 → None

    def test_last_extracted_at_cross_process(self):
        # 尾巴 B：持久查重层——有记录返回 unix 秒、无记录 None
        import calendar
        import time as _time
        self.assertIsNone(self.sm.last_extracted_at("u1"))
        self.sm.save_todos(["A"], source_url="u1")
        last = self.sm.last_extracted_at("u1")
        self.assertIsNotNone(last)
        self.assertLess(abs(last - _time.time()), 86400)   # CURRENT_TIMESTAMP 为 UTC
        self.assertIsNone(self.sm.last_extracted_at("u2"))

    def test_priority_column_added_to_legacy_db(self):
        # 尾巴 C 迁移路径：手工建旧 schema 库 → StateManager 接管补列，
        # 既有行自动落默认 P1
        import os
        import sqlite3
        legacy_dir = os.path.join(self.tmp, "legacy")
        os.makedirs(legacy_dir, exist_ok=True)
        conn = sqlite3.connect(os.path.join(legacy_dir, "long_term.db"))
        conn.execute(
            "CREATE TABLE todos ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " content TEXT NOT NULL,"
            " source_url TEXT DEFAULT '',"
            " status TEXT NOT NULL DEFAULT 'pending',"
            " created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
            " done_at DATETIME)")
        conn.execute("INSERT INTO todos (content, source_url) VALUES ('旧', 'old')")
        conn.commit()
        conn.close()
        with _quiet_stdout():
            sm2 = StateManager(base_dir=legacy_dir)
        conn = sqlite3.connect(sm2.memory_db)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(todos)")]
        legacy_row = conn.execute("SELECT content, priority FROM todos").fetchone()
        conn.close()
        self.assertIn("priority", cols)
        self.assertEqual(legacy_row, ("旧", "P1"))

    def test_check_constraint_rejects_bad_status(self):
        conn = sqlite3.connect(self.sm.memory_db)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO todos (content, status) VALUES ('x', 'bad')")
        conn.close()


if __name__ == "__main__":
    unittest.main()
