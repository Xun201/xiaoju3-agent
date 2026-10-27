# -*- coding: utf-8 -*-
"""qq_lifemate 切片 a 测试（2026-10-27）——契约+三闸纯逻辑+工具行为+落账。

覆盖：
- plugin_loader 目录包装载：rejected=0、tools 3 个 ext_ 前缀、setup 建表；
- 唤醒三闸纯逻辑（静默/quiet 跨午夜/日限帽/首次见面）；
- record_fact / scene_report / recall_fact 真库行为（UNIQUE 更新/场景最新）；
- wake_once 落账（chat_log+meta 计数+跨日重置，mock 生成与发送）。

mock 注意：知识库一律临时目录（patch external_dir/data_dir）；唤醒线程在
装载 setup 时真实启动（daemon，600s 间隔不打扰）——用例结束 teardown 冬眠。
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import plugin_loader  # noqa: E402

PLUGIN_SRC = os.path.join(PROJECT_ROOT, "agent_state", "plugins",
                          "qq_lifemate")


# waker 与插件内部 import 的是同一 sys.modules 实例（sys.path 先插插件
# 目录）——否则两个模块对象并存，set_data_dir 作用不到插件用的那一份
if PLUGIN_SRC not in sys.path:
    sys.path.insert(0, PLUGIN_SRC)
import waker  # noqa: E402


class WakeGateTests(unittest.TestCase):
    """唤醒三闸纯逻辑（W1/W2/硬帽——队长拍板契约）。"""

    def setUp(self):
        self.now = datetime(2026, 10, 27, 14, 0, 0)   # 周二 14:00 非 quiet

    def test_not_silent_blocks(self):
        """距上次发声 <4h：不唤醒。"""
        last = "2026-10-27 12:00:00"   # 2h 前
        wake, reason = waker.should_wake(last, self.now, 0)
        self.assertFalse(wake)
        self.assertEqual(reason, "not_silent")

    def test_silence_passed_wakes(self):
        """≥4h：唤醒（原因带静默时长）。"""
        last = "2026-10-27 09:00:00"   # 5h 前
        wake, reason = waker.should_wake(last, self.now, 0)
        self.assertTrue(wake)
        self.assertTrue(reason.startswith("silence_"))

    def test_quiet_hours_block(self):
        """W2：23:00-08:00 绝不唤醒（跨午夜两端+午夜本体）。"""
        for h in (23, 0, 3, 7):
            now = self.now.replace(hour=h)
            wake, reason = waker.should_wake(None, now, 0)
            self.assertFalse(wake, f"hour={h} 应被 quiet 挡住")
            self.assertEqual(reason, "quiet")

    def test_quight_ends_at_8(self):
        """08:00 整起不再 quiet（白天可唤醒）。"""
        wake, _ = waker.should_wake(None, self.now.replace(hour=8), 0)
        self.assertTrue(wake)

    def test_daily_cap_blocks_even_if_silent(self):
        """硬帽：当日已 5 次即使静默足够也不唤醒（封号纪律）。"""
        last = "2026-10-26 08:00:00"   # 30h 前
        wake, reason = waker.should_wake(last, self.now, waker.DAILY_CAP)
        self.assertFalse(wake)
        self.assertEqual(reason, "daily_cap")

    def test_first_meet_wakes(self):
        """从未发声（库空）：first_meet 唤醒。"""
        wake, reason = waker.should_wake(None, self.now, 0)
        self.assertTrue(wake)
        self.assertEqual(reason, "first_meet")

    def test_bad_ts_treated_as_first_meet(self):
        """ts 损坏：保守按首次处理。"""
        wake, reason = waker.should_wake("垃圾数据", self.now, 0)
        self.assertTrue(wake)
        self.assertEqual(reason, "first_meet")


class PluginLoadContractTests(unittest.TestCase):
    """目录包装载契约（plugin_loader 六步生命周期）。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="xj3_lifemate_")
        self._enter = patch.object(plugin_loader, "external_dir",
                                   lambda: self._tmp)
        self._enter.start()
        plugin_loader._loaded.clear()
        plugin_loader._rejected.clear()
        shutil.copytree(PLUGIN_SRC, os.path.join(self._tmp, "qq_lifemate"))
        plugin_loader.load_all()
        self.plugin = plugin_loader.loaded_plugins().get("qq_lifemate")
        self.mod = self.plugin["module"] if self.plugin else None

    def tearDown(self):
        plugin_loader.unload_all()
        plugin_loader._loaded.clear()
        plugin_loader._rejected.clear()
        self._enter.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_loaded_not_rejected(self):
        """目录包装载成功（rejected=0）——契约 v1.1 兼容目录包首例。"""
        self.assertIsNotNone(self.plugin, "qq_lifemate 应装载成功")
        self.assertEqual(plugin_loader.rejected_plugins(), [])

    def test_tools_three_with_ext_prefix(self):
        names = [t["name"] for t in self.plugin["plugin"]["tools"]]
        self.assertEqual(sorted(names),
                         ["ext_recall_fact", "ext_record_fact",
                          "ext_scene_report"])

    def test_setup_creates_four_tables(self):
        import sqlite3
        dbp = os.path.join(self.plugin["module"].waker.data_dir(),
                           "memory.db")
        self.assertTrue(os.path.isfile(dbp))
        db = sqlite3.connect(dbp)
        tabs = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        db.close()
        self.assertTrue({"chat_log", "facts", "scene", "rel", "meta"
                         } <= tabs)


class ToolBehaviorTests(unittest.TestCase):
    """record_fact / scene_report / recall_fact 真库行为。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="xj3_lifemate_tool_")
        waker.set_data_dir(self._tmp)
        self.spec = importlib.util.spec_from_file_location(
            "agent_state_plugins_qq_lifemate",
            os.path.join(PLUGIN_SRC, "__init__.py"),
            submodule_search_locations=[PLUGIN_SRC])
        self.mod = importlib.util.module_from_spec(self.spec)
        sys.modules[self.spec.name] = self.mod
        self.spec.loader.exec_module(self.mod)

    def tearDown(self):
        waker.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_record_fact_and_recall(self):
        out = self.mod.record_fact(key="喜欢的饮料", value="冰可乐")
        self.assertIn("记住啦", out)
        back = self.mod.record_fact(key="喜欢的饮料", value="热可可")
        self.assertIn("热可可", back)   # UNIQUE(key) 更新语义
        got = self.mod.recall_fact(key="喜欢的饮料")
        self.assertIn("热可可", got)
        self.assertIn("还没记过", self.mod.recall_fact(key="没记过的"))

    def test_record_fact_requires_both(self):
        out = self.mod.record_fact(key="只有key")
        self.assertIn("❌", out)

    def test_scene_report_appends_and_counts(self):
        self.mod.scene_report(action="在整理待办")
        self.mod.scene_report(action="在陪主人聊天")
        db = waker._db()
        try:
            top = db.execute("SELECT action FROM scene ORDER BY id DESC "
                             "LIMIT 1").fetchone()[0]
            n = db.execute("SELECT COUNT(*) FROM scene").fetchone()[0]
            rel = db.execute("SELECT interactions FROM rel").fetchone()[0]
        finally:
            db.close()
        self.assertEqual(top, "在陪主人聊天")   # 最新在前
        self.assertEqual(n, 2)
        self.assertEqual(rel, 2)
        self.assertIn("状态已记录", self.mod.scene_report(action="x"))

    def test_scene_report_requires_action(self):
        self.assertIn("❌", self.mod.scene_report())


class WakeOnceAccountingTests(unittest.TestCase):
    """wake_once 落账：chat_log+meta 计数+跨日重置。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="xj3_lifemate_wake_")
        waker.set_data_dir(self._tmp)

    def tearDown(self):
        waker.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_wake_once_writes_log_and_counts(self):
        with patch.object(waker, "generate_wake_text",
                          return_value="主人~想你了 (´･ω･`)"), \
             patch.object(waker, "send_qq", return_value=True):
            now = datetime(2026, 10, 27, 14, 0, 0)
            self.assertTrue(waker.wake_once(now))
            self.assertTrue(waker.wake_once(now))
        db = waker._db()
        try:
            n = db.execute("SELECT COUNT(*) FROM chat_log WHERE "
                           "kind='proactive_wake'").fetchone()[0]
            cnt = waker.daily_count(db, now)
            ts = waker.last_speak_ts(db)
        finally:
            db.close()
        self.assertEqual(n, 2)
        self.assertEqual(cnt, 2)
        self.assertIsNotNone(ts)

    def test_daily_count_resets_next_day(self):
        with patch.object(waker, "generate_wake_text",
                          return_value="嗨"), \
             patch.object(waker, "send_qq", return_value=True):
            waker.wake_once(datetime(2026, 10, 27, 14, 0, 0))
        db = waker._db()
        try:
            self.assertEqual(waker.daily_count(
                db, datetime(2026, 10, 28, 9, 0, 0)), 0)   # 次日重置
        finally:
            db.close()

    def test_wake_once_send_fail_no_count(self):
        """发送失败不计次不写账（下轮重试）。"""
        with patch.object(waker, "generate_wake_text",
                          return_value="嗨"), \
             patch.object(waker, "send_qq", return_value=False):
            self.assertFalse(waker.wake_once(datetime(2026, 10, 27, 14, 0, 0)))
        db = waker._db()
        try:
            n = db.execute("SELECT COUNT(*) FROM chat_log").fetchone()[0]
            cnt = waker.daily_count(db, datetime(2026, 10, 27, 14, 0, 0))
        finally:
            db.close()
        self.assertEqual(n, 0)
        self.assertEqual(cnt, 0)

    def test_generate_wake_text_strips_think_and_quotes(self):
        """生成清洗：剥 <think>+剥引号包裹。"""
        with patch("brain.ask_local", return_value="<think>思考</think>“想你了”"):
            self.assertEqual(waker.generate_wake_text("在待命", self._now()),
                             "想你了")

    @staticmethod
    def _now():
        return datetime(2026, 10, 27, 14, 0, 0)


if __name__ == "__main__":
    unittest.main()
