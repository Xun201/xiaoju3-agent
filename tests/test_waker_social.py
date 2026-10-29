# -*- coding: utf-8 -*-
"""社交池多目标随机串门测试（2026-10-30，好友池灌池批配套）。

覆盖（异常用例优先——保命红线不许假绿）：
- _parse_social_pool：f:/g:/裸数字/空/空白 五形态；
- 全局日限 3：真实 k/v 计数累加、第 4 次阻断、计数列名回归（2026-10-30
  实锤旧版按 meta(key,value) 读写与 _db() 的 meta(k,v) 不匹配=日限静默失效）；
- fail-closed：计数库读不到 → 不发送（宁可不出手）；
- 24h 冷却：social_log 落账后同目标当日不再选（建表缺失回归）；
- 主人豁免：OWNER_QQ 绝不落入社交池（专属唤醒通道带全量记忆）；
- 隐私隔离：社交模式 Prompt 红线原文 + chat_fn 注入零记忆；
- 拟人延迟：发送前 sleep 3-6s（_SOCIAL_DELAY 接线，2026-10-30 补）。
"""
import importlib.util
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

PLUGIN_SRC = os.path.join(PROJECT_ROOT, "agent_state", "plugins",
                          "qq_lifemate")
# 与 waker 内部 import 同一 sys.modules 实例（先插插件目录）
if PLUGIN_SRC not in sys.path:
    sys.path.insert(0, PLUGIN_SRC)
import waker  # noqa: E402


def _temp_db():
    """临时库（生产同款 meta(k,v) 口径；social_log 由 _ensure_social_tables
    幂等自建——顺带覆盖建表缺失回归）。"""
    db = sqlite3.connect(":memory:")
    db.executescript("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);")
    return db


class SocialPoolParseTests(unittest.TestCase):
    """XIAOJU3_SOCIAL_POOL 五形态解析。"""

    def test_friend_group_and_bare(self):
        with patch.dict(os.environ, {"XIAOJU3_SOCIAL_POOL": "f:111,g:222,333"}):
            self.assertEqual(waker._parse_social_pool(),
                             [("friend", "111"), ("group", "222"),
                              ("group", "333")])

    def test_empty_and_whitespace(self):
        for raw in ("", "   "):
            with patch.dict(os.environ, {"XIAOJU3_SOCIAL_POOL": raw}):
                self.assertEqual(waker._parse_social_pool(), [])

    def test_items_stripped(self):
        with patch.dict(os.environ, {"XIAOJU3_SOCIAL_POOL": " f:444 , g:555 "}):
            self.assertEqual(waker._parse_social_pool(),
                             [("friend", "444"), ("group", "555")])


class SocialVisitSafetyTests(unittest.TestCase):
    """日限/冷却/主人豁免/fail-closed（保命红线四件）。"""

    def setUp(self):
        self.db = _temp_db()
        self.sent = []
        patcher_env = patch.dict(
            os.environ, {"XIAOJU3_SOCIAL_POOL": "f:111,f:222",
                         "XIAOJU3_OWNER_QQ": "999999"})
        patcher_greet = patch.object(waker, "_social_greeting",
                                     return_value="在吗，摸鱼吗")
        patcher_send = patch.object(
            waker, "_social_send",
            side_effect=lambda tt, tid, text: self.sent.append((tt, tid)) or True)
        patcher_sleep = patch("time.sleep")
        patcher_env.start(); self.addCleanup(patcher_env.stop)
        patcher_greet.start(); self.addCleanup(patcher_greet.stop)
        patcher_send.start(); self.addCleanup(patcher_send.stop)
        patcher_sleep.start(); self.addCleanup(patcher_sleep.stop)

    def _count(self):
        row = self.db.execute(
            "SELECT v FROM meta WHERE k='social_count'").fetchone()
        return int(row[0]) if row else 0

    def test_first_send_records_kv_and_log(self):
        self.assertTrue(waker.social_visit(db=self.db))
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self._count(), 1)   # k/v 列名回归：旧版写不进
        row = self.db.execute(
            "SELECT target_id, target_type FROM social_log").fetchone()
        self.assertIsNotNone(row)
        self.assertIn(row[0], ("111", "222"))

    def test_daily_cap_blocks_fourth(self):
        # 池 5 目标：前三次各发一个（洗牌随机、冷却互不挡），第 4 次被日限帽拦
        with patch.dict(os.environ,
                        {"XIAOJU3_SOCIAL_POOL": "f:101,f:102,f:103,f:104,f:105"}):
            for _ in range(3):
                self.assertTrue(waker.social_visit(db=self.db))
        self.assertEqual(self._count(), 3)
        self.assertEqual(len(self.sent), 3)
        self.assertFalse(waker.social_visit(db=self.db))
        self.assertEqual(len(self.sent), 3)   # 第 4 次绝不发送

    def test_fail_closed_when_db_broken(self):
        self.db.close()
        self.assertFalse(waker.social_visit(db=self.db))
        self.assertEqual(self.sent, [])   # 计数读不到=不出手

    def test_owner_qq_never_targeted(self):
        with patch.dict(os.environ, {"XIAOJU3_SOCIAL_POOL": "f:999999"}):
            self.assertFalse(waker.social_visit(db=self.db))
        self.assertEqual(self.sent, [])   # 主人走专属唤醒通道，绝不进社交池

    def test_cooldown_blocks_same_target_next_visit(self):
        with patch.dict(os.environ, {"XIAOJU3_SOCIAL_POOL": "f:111"}):
            self.assertTrue(waker.social_visit(db=self.db))
            self.assertFalse(waker.social_visit(db=self.db))   # 24h 冷却内
        self.assertEqual(len(self.sent), 1)


class SocialPrivacyTests(unittest.TestCase):
    """社交模式隐私隔离（非 Owner 好友零主人信息）。"""

    def test_prompt_redline_wording(self):
        self.assertIn("严禁暴露关于主人的任何信息", waker._SOCIAL_MODE_PROMPT)
        self.assertIn("1-2 句即可", waker._SOCIAL_MODE_PROMPT)

    def test_greeting_uses_isolated_prompt_zero_memory(self):
        captured = []

        def fake_chat(prompt):
            captured.append(prompt)
            return "大家早上好呀"

        out = waker._social_greeting("好友 111", chat_fn=fake_chat)
        self.assertEqual(out, "大家早上好呀")
        self.assertEqual(len(captured), 1)
        msgs = captured[0]
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[0]["content"], waker._SOCIAL_MODE_PROMPT)
        # 场景隔离：整个 prompt 只含目标描述，零记忆/零主人上下文
        joined = " ".join(m["content"] for m in msgs)
        self.assertNotIn("主人喜欢", joined)
        self.assertNotIn("记忆", joined)

    def test_delay_before_send_in_3_to_6s(self):
        sleeps = []
        db = _temp_db()
        with patch.dict(os.environ, {"XIAOJU3_SOCIAL_POOL": "f:111"}), \
             patch.object(waker, "_social_greeting", return_value="嗨"), \
             patch.object(waker, "_social_send", return_value=True), \
             patch("time.sleep", side_effect=lambda s: sleeps.append(s)):
            self.assertTrue(waker.social_visit(db=db))
        self.assertEqual(len(sleeps), 1)
        self.assertGreaterEqual(sleeps[0], 3.0)
        self.assertLessEqual(sleeps[0], 6.0)


if __name__ == "__main__":
    unittest.main()
