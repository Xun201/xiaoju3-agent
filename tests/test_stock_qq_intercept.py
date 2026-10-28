# -*- coding: utf-8 -*-
"""选股强拦截·onebot_event 全链模拟测试（2026-10-28 真机惨败抢救）。

走完整 main.onebot_event 入口（含拟人节奏防抖逻辑），覆盖：
1. 私聊触发词 → 立即秒回提示（防抖不入桶）+ 后台扫描推送结果（合规压尾）；
2. 非触发词 + 节奏开 → 正常入防抖桶（不秒回）——防抖逻辑未被破坏；
3. 群聊触发词 → 不拦截（防群聊误触劫持），走原 handle_message 路径；
4. 并发防抖：扫描进行中再触发 → 只回"还在跑"提示，不起第二线程。
"""
import importlib.util
import os
import sys
import threading
import time
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import main  # noqa: E402

PLUGIN_SRC = os.path.join(PROJECT_ROOT, "agent_state", "plugins")

FAKE_RESULT = ("📊 净利润 top10 行业 × 国企 5-20 元筛选\n\n【政策面】\n"
               "电力：绿电政策利好。\n\n【筛选结果】\n"
               "【电力A】净利润约 100 亿\n  · 甲电力（600001）现价 8.8 元\n"
               "\n⚠️ 以上仅为基于公开数据的自动化筛选结果，"
               "不构成任何投资建议。")


def _register_plugin_module():
    """把真实插件注册成生产同款模块名（生产=启动装载后 sys.modules 可达）。"""
    if "agent_state_plugins_stock_assistant" in sys.modules:
        return sys.modules["agent_state_plugins_stock_assistant"]
    spec = importlib.util.spec_from_file_location(
        "agent_state_plugins_stock_assistant",
        os.path.join(PLUGIN_SRC, "stock_assistant.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["agent_state_plugins_stock_assistant"] = mod
    spec.loader.exec_module(mod)
    return mod


def _onebot_payload(text, user_id=123, group_id=None):
    return {"post_type": "message", "message_type":
            ("group" if group_id else "private"),
            "message": text, "raw_message": text,
            "sender": {"user_id": user_id, "nickname": "测试"},
            "user_id": user_id, "self_id": 10000,
            **({"group_id": group_id} if group_id else {})}


class QQStockInterceptTests(unittest.TestCase):
    def setUp(self):
        self.mod = _register_plugin_module()
        self.sent = []
        self._patchers = [
            mock.patch.object(main, "_send_reply_segments",
                              side_effect=lambda u, g, r, **kw:
                              self.sent.append((u, g, r))),
            mock.patch.dict(os.environ,
                            {"XIAOJU3_CHAT_RHYTHM_ENABLED": "1"}),
        ]
        for p in self._patchers:
            p.start()
            self.addCleanup(p.stop)
        # 扫描结果固定（不碰网络），工作线程立刻可 join
        p = mock.patch.object(self.mod, "stock_screen_text",
                              return_value=FAKE_RESULT)
        p.start()
        self.addCleanup(p.stop)
        # 等待可能的前测残worker退出（防锁与串扰）
        deadline = time.time() + 5
        while main._STOCK_SCAN_LOCK.locked() and time.time() < deadline:
            time.sleep(0.05)
        # 清防抖桶（10s Timer 泄漏会在测后真调大脑）
        with main._CHAT_BURSTS_LOCK:
            for b in main._CHAT_BURSTS.values():
                if b.get("timer"):
                    b["timer"].cancel()
            main._CHAT_BURSTS.clear()

    def _wait_worker(self, th, timeout=10):
        if th is not None:
            th.join(timeout)
        else:
            deadline = time.time() + timeout
            while main._STOCK_SCAN_LOCK.locked() and time.time() < deadline:
                time.sleep(0.05)

    def test_private_trigger_immediate_ack_and_async_push(self):
        self.sent.clear()
        th = main._stock_intercept_respond(123, None)
        self.assertLessEqual(1, len(self.sent))
        self.assertIn("二三十秒", self.sent[0][2])   # 首条必是秒回提示
        self._wait_worker(th)
        self.assertGreaterEqual(len(self.sent), 2, "后台跑完应推送结果")
        self.assertIn("不构成任何投资建议", self.sent[-1][2])

    def test_onebot_event_full_chain(self):
        """完整 onebot_event 链：触发词短路（不进 handle_message/防抖）。"""
        self.sent.clear()
        with mock.patch.object(main, "handle_message",
                               side_effect=AssertionError("不该进大脑")):
            resp = main.onebot_event(_onebot_payload("帮我选股一下"))
        self.assertEqual(resp, {"status": "ok", "retcode": 0})
        self.assertLessEqual(1, len(self.sent))
        self.assertIn("稍等片刻", self.sent[0][2])   # 首条必是秒回提示
        self._wait_worker(None)
        self.assertGreaterEqual(len(self.sent), 2)
        self.assertIn("不构成任何投资建议", self.sent[-1][2])

    def test_non_stock_goes_to_rhythm_bucket(self):
        """非触发词+节奏开 → 入防抖桶不秒回（防抖逻辑未被拦截破坏）。"""
        self.sent.clear()
        before = sum(len(b["texts"]) for b in main._CHAT_BURSTS.values())
        with mock.patch.object(main, "handle_message",
                               side_effect=AssertionError("不该进大脑")):
            main.onebot_event(_onebot_payload("今天心情怎么样"))
        self.assertEqual(len(self.sent), 0, "闲聊必须入桶不得秒回")
        after = sum(len(b["texts"]) for b in main._CHAT_BURSTS.values())
        self.assertEqual(after, before + 1)

    def test_group_not_intercepted(self):
        """群聊触发词不劫持（防误触），走原 handle_message 路径。"""
        self.sent.clear()
        with mock.patch.object(main, "handle_message",
                               return_value="群聊原路径") as hm:
            main.onebot_event(_onebot_payload("帮我选股一下", group_id=456))
        hm.assert_called_once()
        self.assertEqual(self.sent, [(123, 456, "群聊原路径")])

    def test_concurrent_scan_second_trigger_gets_hint(self):
        """并发防抖：扫描进行中再触发 → 只回提示不起第二线程。"""
        self.sent.clear()
        gate = threading.Event()
        with mock.patch.object(self.mod, "stock_screen_text",
                               side_effect=lambda **kw: (
                                   gate.wait(5), FAKE_RESULT)[1]):
            th1 = main._stock_intercept_respond(123, None)
            time.sleep(0.2)                     # 确保 th1 已持锁
            self.assertTrue(main._STOCK_SCAN_LOCK.locked())
            th2 = main._stock_intercept_respond(123, None)
            self.assertIsNone(th2, "在跑时不得起第二线程")
            self.assertTrue(any("还在跑" in r for _, _, r in self.sent))
            gate.set()
            self._wait_worker(th1)


if __name__ == "__main__":
    unittest.main()


class TokenGuardTests(QQStockInterceptTests):   # 继承 setUp（sent 捕获+节奏 env）
    """守卫在同步路径验证（生产节奏缺省关；节奏开=闲聊进桶另行处理）。"""

    def setUp(self):
        super().setUp()
        p = mock.patch.dict(os.environ,
                            {"XIAOJU3_CHAT_RHYTHM_ENABLED": "0"})
        p.start()
        self.addCleanup(p.stop)
    """Token 防刷守卫（2026-10-28"2的50次方烧光token"实锤）：幂运算直算
    不进大脑；超长纯文本截断 500；含 CQ 媒体消息不截。"""

    def tearDown(self):
        deadline = time.time() + 2
        while main._STOCK_SCAN_LOCK.locked() and time.time() < deadline:
            time.sleep(0.05)

    def test_pow_bait_computed_locally(self):
        self.sent.clear()
        with mock.patch.object(main, "handle_message",
                               side_effect=AssertionError("不该进大脑")):
            main.onebot_event(_onebot_payload(
                "小心我：2的50次方是多少，烧光你的token"))
        self.assertEqual(len(self.sent), 1)
        self.assertIn("1125899906842624", self.sent[0][2])
        # 去情绪化（队长拍板）：防刷是阻断成本不是表演，禁嘲讽/质问
        self.assertTrue(self.sent[0][2].startswith("计算结果："),
                        self.sent[0][2])
        for banned in ("哼", "小把戏", "烧", "尾巴"):
            self.assertNotIn(banned, self.sent[0][2])

    def test_huge_pow_reports_digits_only(self):
        self.sent.clear()
        with mock.patch.object(main, "handle_message",
                               side_effect=AssertionError("不该进大脑")):
            main.onebot_event(_onebot_payload("3的500次方等于多少"))
        self.assertEqual(len(self.sent), 1)
        self.assertIn("位数", self.sent[0][2])

    def test_non_math_passthrough(self):
        with mock.patch.object(main, "handle_message",
                               return_value="正常") as hm:
            main.onebot_event(_onebot_payload("今天天气怎么样"))
        hm.assert_called_once()

    def test_long_message_truncated(self):
        self.sent.clear()
        long_text = "啊" * 501
        with mock.patch.object(main, "handle_message",
                               return_value="好") as hm:
            main.onebot_event(_onebot_payload(long_text))
        got = hm.call_args[0][3]
        self.assertTrue(got.startswith("啊" * 100))
        self.assertIn("只看了前 500 字", got)   # 截断标记实证

    def test_cq_message_not_truncated(self):
        cq = "[CQ:image,file=abc]" + "啊" * 501
        with mock.patch.object(main, "handle_message",
                               return_value="好") as hm:
            main.onebot_event(_onebot_payload(cq))
        got = hm.call_args[0][3]
        self.assertTrue(got.startswith("[CQ:image"), "含 CQ 消息不得截断")


# TokenGuard（节奏=0）不继承节奏相关用例——防抖桶用例只在父类（节奏=1）语境有效
def _skip_rhythm_in_guard(self):
    self.skipTest("节奏用例只在父类（节奏=1）语境跑")
TokenGuardTests.test_non_stock_goes_to_rhythm_bucket = _skip_rhythm_in_guard
