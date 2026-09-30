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


if __name__ == "__main__":
    unittest.main()
