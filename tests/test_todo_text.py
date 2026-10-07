# -*- coding: utf-8 -*-
"""plugins/todo_text 单元测试（#261 纯文字待办入口，2026-10-07 三拍板）。

全部离线：云端 ask_cloud 注入；库走 StateManager(tmp base_dir)；后台线程
用立即执行替身（照抄 test_dashboard._immediate_thread 口径）。
覆盖：路由命中/近似误报负例 / Lv.1 门禁 ⚠️ 前缀不落 brain（与链接链 ❌
口径差的刻意设计）/ 分享链接防呆 / 判级入库端到端（多格式喂模型解析）/
stream 端点三通道覆盖。
"""
import json
import shutil
import tempfile
import unittest
from unittest import mock

from agent_state.state_manager import StateManager
from intent_router import route
from permission import PermissionManager
from plugins import todo_text, todo_extractor


def _immediate_thread():
    """立即执行替身：Thread(target, args).start() 同步跑完（可断言落库）。"""
    class _ImmediateThread:
        def __init__(self, target=None, args=(), daemon=None):
            self._target, self._args = target, args

        def start(self):
            self._target(*self._args)
    return _ImmediateThread


class TodoTextRouteTests(unittest.TestCase):
    """意图路由层：命中形态 / 近似负例（#270 问用法、含链接、斜杠族）。"""

    def test_route_hits_text_todo(self):
        for msg in ("帮我记待办：1.周三交周报\n2.下单买米",
                    "记个待办 买米",
                    "待办：给老师发邮件"):
            result = route(msg)
            self.assertIsNotNone(result, msg)
            self.assertEqual(result.name, "todo_text_add")
            self.assertEqual(result.handler, "plugins.todo_text:add_from_message")
            self.assertTrue(result.args.get("text", "").strip(), msg)

    def test_route_misses_lookalikes(self):
        # #270 形态（问用法）→ 落对话；含分享链接 → 走链接提取链；
        # 斜杠族 → 指令分发；"记待办的方法"（无分隔符）→ 落对话
        for msg in ("待办怎么做",
                    "帮我记待办 https://chat.deepseek.com/share/abc",
                    "/todos",
                    "记待办的方法有哪些"):
            self.assertIsNone(route(msg), msg)


class TodoTextHandlerTests(unittest.TestCase):
    """处理器层：门禁 / 防呆 / 判级入库端到端。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_todo_text_")
        self.sm = StateManager(base_dir=self.tmp)
        self.pm = PermissionManager()
        self.pm.current_level = "Lv.2"   # 默认过门禁；门禁用例内层再覆写 Lv.1
        pm_patch = mock.patch.object(todo_text.main, "permission_manager",
                                     self.pm)
        pm_patch.start()
        self.addCleanup(pm_patch.stop)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _patches(self, level="Lv.2", cloud_reply='[{"content": "A"}]'):
        pm = PermissionManager()
        pm.current_level = level
        return [
            mock.patch.object(todo_text.main, "permission_manager", pm),
            mock.patch.object(todo_extractor, "ask_cloud",
                              return_value=cloud_reply),
            mock.patch.object(todo_extractor, "state_manager", self.sm),
            mock.patch("plugins.todo_text.threading.Thread",
                       _immediate_thread()),
        ]

    def test_gate_lv1_rejects_with_warning_prefix(self):
        """拍板口径锚：门禁拒绝用 ⚠️ 前缀（**非 ❌**）——handle_intent_command
        对 ❌ 返回 None 落回 brain（消息被模型重新解释=旧病复发），⚠️ 才会
        作为 ⚙️ 指令回复送出；与链接链 handle_todo_command 的 ❌ 口径差是
        刻意设计。云端零调用、零入库、零线程。"""
        import main
        pm = PermissionManager()
        pm.current_level = "Lv.1"
        with mock.patch.object(main, "permission_manager", pm), \
                mock.patch.object(todo_extractor, "ask_cloud") as ac, \
                mock.patch.object(todo_extractor, "state_manager", self.sm), \
                mock.patch("plugins.todo_text.threading.Thread",
                           _immediate_thread()):
            reply = todo_text.add_from_message("帮我记待办：1.测试")
            self.assertTrue(reply.startswith("⚠️"))
            self.assertFalse(reply.startswith("❌"))   # 刻意口径差：❌ 会被吞
            self.assertIn("Lv.2", reply)
            # 集成口径：handle_intent_command 必须把 ⚠️ 回复送出（非 None，
            # 不落 brain）
            surfaced = main.handle_intent_command("帮我记待办：1.测试", [])
        self.assertIsNotNone(surfaced)
        self.assertTrue(surfaced.startswith("⚠️"))
        ac.assert_not_called()
        self.assertEqual(self.sm.get_todos(status="pending"), [])

    def test_share_link_guard(self):
        """防呆锚：含 DeepSeek 分享链接的"记待办" → 引导走链接提取链，
        纯文字入口不处理链接（云端零调用）。"""
        with mock.patch.object(todo_extractor, "ask_cloud") as ac, \
                mock.patch.object(todo_extractor, "state_manager", self.sm):
            reply = todo_text.add_from_message(
                "帮我记待办 https://chat.deepseek.com/share/abc")
        self.assertIn("链接", reply)
        self.assertIn("todo_from_link", reply)
        ac.assert_not_called()

    def test_end_to_end_parse_and_save(self):
        """端到端锚：多格式原文（编号+换行）整段喂云端判级，解析两条入库；
        受理即回（🔄），_LAST_JOB 落 done。立即线程补丁防真线程竞态。"""
        with mock.patch.object(todo_extractor, "ask_cloud", return_value=(
                '[{"content": "周三交周报", "priority": "P1"},'
                ' {"content": "下单买米"}]')), \
                mock.patch.object(todo_extractor, "state_manager", self.sm), \
                mock.patch("plugins.todo_text.threading.Thread",
                           _immediate_thread()):
            reply = todo_text.add_from_message(
                "帮我记待办：1.周三交周报\n2.下单买米")
        self.assertTrue(reply.startswith("🔄"))
        contents = [t["content"] for t in self.sm.get_todos(status="pending")]
        self.assertEqual(contents, ["周三交周报", "下单买米"])
        self.assertEqual(todo_extractor.last_job()["state"], "done")
        self.assertEqual(todo_extractor.last_job()["inserted"], 2)

    def test_empty_content_reports_usage(self):
        """空内容防御锚：add_from_message("")（route 因 pattern 要求
        分隔符+内容不会送来空串，此为直调防御）→ 用法示例（不调云端）。"""
        with mock.patch.object(todo_extractor, "ask_cloud") as ac, \
                mock.patch.object(todo_extractor, "state_manager", self.sm):
            reply = todo_text.add_from_message("")
        self.assertIn("例如", reply)
        ac.assert_not_called()


class TodoTextStreamChannelTests(unittest.TestCase):
    """三通道覆盖锚：流式控制台发纯文字记待办 → ⚙️ 指令受理，不进模型。"""

    def setUp(self):
        import xiaoju3_dashboard as dashboard
        self.dashboard = dashboard
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_todo_text_stream_")
        self.sm = StateManager(base_dir=self.tmp)
        self.pm = PermissionManager()
        self.pm.current_level = "Lv.2"
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.client = dashboard.app.test_client()

    def test_stream_channel_covers_text_todo(self):
        with mock.patch.object(self.dashboard.brain, "smart_ask_stream") as ms, \
                mock.patch.object(self.dashboard.main, "permission_manager",
                                  self.pm), \
                mock.patch.object(todo_extractor, "ask_cloud", return_value=(
                    '[{"content": "锚点条目", "priority": "P1"}]')), \
                mock.patch.object(todo_extractor, "state_manager", self.sm), \
                mock.patch("plugins.todo_text.threading.Thread",
                           _immediate_thread()):
            resp = self.client.post(
                "/api/chat/stream",
                json={"message": "帮我记待办：1.锚点条目", "history": []})
        frames = []
        for block in resp.get_data(as_text=True).split("\n\n"):
            etype, data = "", ""
            for line in block.split("\n"):
                if line.startswith("event:"):
                    etype = line[6:].strip()
                elif line.startswith("data:"):
                    data += line[5:].strip()
            if data:
                frames.append((etype, json.loads(data)))
        self.assertEqual([e for e, _ in frames], ["done"])   # 单帧收口
        done = frames[-1][1]
        self.assertEqual(done["source"], "⚙️ 指令")
        self.assertIn("已受理", done["reply"])
        ms.assert_not_called()   # 不进模型
        self.assertEqual([t["content"] for t in self.sm.get_todos(
            status="pending")], ["锚点条目"])


if __name__ == "__main__":
    unittest.main()
