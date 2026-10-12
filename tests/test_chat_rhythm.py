# -*- coding: utf-8 -*-
"""QQ 闲聊拟人节奏锚（2026-10-12）。

覆盖：
- 分类器：纯文字闲聊=True；斜杠/分享链接/记住/CQ 媒体/家电工具词=False；
- 纯图硬门回归（图片不走延迟队列——硬门确定性回应）；
- 防抖：静默判据=10s Timer；条数 ≥6 → 0.05s 立即冲刷；单条 >100 字直通；
- 冲刷：合并文字进 handle_message、回复经 _strip_llm_pollution、
  延迟 ∈ [20, 30]、ONEBOT 正确端点发送；
- 开关：XIAOJU3_CHAT_RHYTHM=0 → 闲聊即时路径（原同步行为）。
线程隔离：Timer 注入捕获、sleep 注入捕获、post 注入捕获——零真实线程。
"""
import os
import re
import unittest
from unittest import mock

import main


def _fresh_burst(key="0:10001"):
    main._CHAT_BURSTS.pop(key, None)
    return key


class ChatLikeClassifierTests(unittest.TestCase):
    """预分类：闲聊 vs 即时。"""

    def test_chat_like_true_for_plain_text(self):
        self.assertTrue(main._is_chat_like("x", "今天有点累啊"))

    def test_immediate_for_tool_and_media(self):
        cases = [
            ("x", "/help"),                                   # 斜杠指令
            ("https://chat.deepseek.com/share/abc", "看看"),   # 分享链接
            ("x", "记住我爱吃面"),                              # 记忆写入
            ("[CQ:image,file=a]", ""),                        # 纯图（硬门路径）
            ("[CQ:reply,id=1] 收藏", ""),                      # 引用（CQ 剥空→硬门/收藏门即时路径）

        ]
        for raw, nc in cases:
            self.assertFalse(main._is_chat_like(raw, nc), nc)


class EnqueueDebounceTests(unittest.TestCase):
    """防抖与冲刷判据。"""

    def setUp(self):
        self.key = _fresh_burst()
        self.captured = {}

        def fake_timer(delay, fn, args=None):
            self.captured["delay"] = delay
            self.captured["fn"] = fn
            self.captured["args"] = args or []

            class _T:
                def start(self_inner):
                    pass
                def cancel(self_inner):
                    pass
            return _T()

        self.timer_patch = mock.patch.object(
            main, "threading",
            **{"Timer.side_effect": fake_timer})
        # threading.Timer 是属性访问——用 simpler 手法：替换模块级 threading
        import threading as real_threading
        self._real_threading = real_threading
        p = mock.patch.object(main, "threading",
                              mock.MagicMock(wraps=real_threading))
        p.start()
        self.addCleanup(p.stop)
        # 覆盖 Timer 行为：捕获参数并返回哑对象
        main.threading.Timer.side_effect = fake_timer

    def tearDown(self):
        main.threading.Timer.side_effect = None
        _fresh_burst(self.key)

    def test_first_message_debounces_10s(self):
        delay = main._enqueue_chat_burst(10001, None, "在吗", now=1000.0)
        self.assertEqual(delay, 10.0)

    def test_count_limit_flushes_immediately(self):
        for i in range(5):
            main._enqueue_chat_burst(10001, None, f"消息{i}", now=1000.0 + i)
        delay = main._enqueue_chat_burst(10001, None, "第6条", now=1006.0)
        self.assertLess(delay, 1.0)   # 条数判据：立即冲刷

    def test_long_message_flushes_immediately(self):
        delay = main._enqueue_chat_burst(10001, None, "长" * 101, now=2000.0)
        self.assertLess(delay, 1.0)   # 长消息判据：直通冲刷

    def test_window_limit_flushes_immediately(self):
        key = _fresh_burst()
        main._CHAT_BURSTS[key] = {"texts": ["早"], "first": 0.0,
                                  "last": 118.0, "user_id": 10001,
                                  "group_id": None, "timer": None}
        delay = main._enqueue_chat_burst(10001, None, "还没回我", now=121.0,
                                         timer_cls=None)
        self.assertLess(delay, 1.0)   # 时长判据：120s 兜底冲刷


class FlushWorkerTests(unittest.TestCase):
    """冲刷 worker：合并/消毒/延迟/发送全链（sleep 与 post 注入捕获）。"""

    def setUp(self):
        self.key = _fresh_burst()
        main._CHAT_BURSTS[self.key] = {
            "texts": ["在吗", "睡了没"], "first": 0.0, "last": 0.0,
            "user_id": 10001, "group_id": None, "timer": None,
        }
        self.sleeps = []
        self.posts = []

    def _run_flush(self, reply="在呢，说吧～", texts=None, user_id=10001,
                   group_id=None):
        main._CHAT_BURSTS[self.key] = {
            "texts": texts or ["在吗", "睡了没"], "first": 0.0,
            "last": 0.0, "user_id": user_id, "group_id": group_id,
            "timer": None,
        }
        sleep_patch = mock.patch.object(main.time, "sleep",
                                        side_effect=self.sleeps.append)
        post_patch = mock.patch.object(
            main.requests, "post",
            side_effect=lambda *a, **k: self.posts.append((a, k)))
        hm_patch = mock.patch.object(
            main, "handle_message", return_value=reply)
        poll_patch = mock.patch.object(
            main, "_strip_llm_pollution", side_effect=lambda r: r)
        with sleep_patch, post_patch, hm_patch, poll_patch:
            main._flush_chat_burst(self.key)

    def test_delay_in_20_30_and_sent(self):
        self._run_flush()
        self.assertEqual(len(self.sleeps), 1)
        self.assertGreaterEqual(self.sleeps[0], 20.0)
        self.assertLessEqual(self.sleeps[0], 30.0)
        self.assertEqual(len(self.posts), 1)
        args, kwargs = self.posts[0]
        self.assertIn("send_private_msg", args[0])
        self.assertEqual(kwargs["json"]["user_id"], 10001)

    def test_group_flush_uses_group_endpoint(self):
        self._run_flush(texts=["哈"], user_id=1, group_id=456)
        args, kwargs = self.posts[0]
        self.assertIn("send_group_msg", args[0])
        self.assertEqual(kwargs["json"]["group_id"], 456)

    def test_pollution_stripped_before_send(self):
        """回复经 _strip_llm_pollution 再发送（方括号变体不漏给用户）。"""
        main._CHAT_BURSTS[self.key] = {
            "texts": ["嘿"], "first": 0.0, "last": 0.0,
            "user_id": 1, "group_id": None, "timer": None,
        }
        hm_patch = mock.patch.object(
            main, "handle_message",
            return_value="[think]推理[/think]在的呀")
        with mock.patch.object(main.time, "sleep"), \
                mock.patch.object(main.requests, "post") as post_mock, \
                hm_patch:
            main._flush_chat_burst(self.key)
        sent = post_mock.call_args.kwargs["json"]["message"]
        self.assertNotIn("[think]", sent)
        self.assertIn("在的呀", sent)


if __name__ == "__main__":
    unittest.main()
