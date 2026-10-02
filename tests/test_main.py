# -*- coding: utf-8 -*-
"""QQ 接入层 main.py 离线单测（打 :5003 dashboard test client，大脑与 OneBot
网络全 mock）。

【架构合并（2026-10-01）：5002 端口废弃，HTTP 层宿主 :5003】main.py 已模块化
为纯 QQ 业务逻辑（不再监听任何端口），本套件全部 HTTP 用例改打
xiaoju3_dashboard.app 的 test client（POST /onebot 视图在 dashboard、业务体
main.onebot_event 一字未改）；指令族用例直接调 main.handle_message 不变。
行为断言与 5002 时代逐字一致，只改挂载位置。

- /onebot：私聊响应；群聊触发词 / @（CQ 码）/ 戳一戳彩蛋；图片收藏。
- /onebot LLOneBot 兼容容错：raw_message 缺失时从 OneBot 11 消息段数组重建
  （text 拼接、at/image 段按 CQ 码惯例还原）、post_type 缺失按 message 宽容
  处理、任何字段异常不崩统一返回 ok、发送失败打印 LLOneBot 排查提示。
- handle_message：标点清洗、内置指令族（/help、/register、/coder_auth、
  /sudo、/lv4_auth、/lv4_revoke、/confirm、/reset_fuse、/gen_log、/send_image、
  /clear、/reset、清空记忆、重置记忆——一键清空通道记忆）。
- 第二阶段 §7 权限接线：TOTP 激活 Lv.3 落盘持久、/sudo 写操作窗口、
  /lv4_auth 两步流（类 Root 警告 + 双因子 + 撤销）、/gen_log Lv.3 门槛、
  /send_image 等级 ≥ Lv.3。
- 第二阶段架构接线：意图路由命中/透传、前情提要压缩与失败回退、长期记忆
  存取注入、熔断重置、高危设备二次确认令牌流、/api/health 迁移守望端点。
- <think> 思维链剥离（brain 工具流程 <think> 包装契约的出口侧）：QQ /onebot
  发送前剥除 <think> 块，CQ 发图能力不受影响。
- 记忆与状态目录一律注入临时目录，不触碰真实 agent_state（identity.json /
  long_term.db 均经 patch 隔离）；TOTP 用固定测试密钥现场生成；mock 全部经
  unittest.mock.patch + addCleanup 自动还原，不向 sys.modules 注入任何伪模块。
"""
import contextlib
import io
import json
import os
import re
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import auth_lv4
import brain
import main
import xiaoju3_dashboard as dashboard
from agent_state.state_manager import StateManager
from intent_router import IntentResult
from permission import PermissionManager
from tools import execute_tool

# 固定 TOTP 测试密钥（Base32，仅测试用，与任何真实密钥无关）
TEST_TOTP_SECRET = "JBSWY3DPEHPK3PXP"


class _MainCase(unittest.TestCase):
    """公共夹具：临时目录注入 + 双通道记忆隔离 + 大脑/NapCat 全 mock。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_main_")
        self.state_dir = os.path.join(self.tmp, "state")
        self.mem_web = os.path.join(self.state_dir, "history_web.json")
        self.mem_qq = os.path.join(self.state_dir, "history_qq.json")
        self.totp_secret = TEST_TOTP_SECRET
        # 最近设备操作记录：注入临时路径（不存在 → 默认无注入），既隔离
        # 真实 agent_state，也兜住 /confirm 等真实工具链路产生的设备操作记录
        self.actions_file = os.path.join(self.tmp, "recent_actions.json")

        self.smart_ask = MagicMock(return_value=("测试回复", "🏠 本地"))
        self.napcat = MagicMock()
        state_manager = StateManager(self.state_dir)

        for target, value in [
            ("main.smart_ask", self.smart_ask),
            ("main.requests", self.napcat),
            ("main.MEMORY_FILE_WEB", self.mem_web),
            ("main.MEMORY_FILE_QQ", self.mem_qq),
            ("main.messages_web", [main.SYSTEM_PROMPT]),
            ("main.messages_qq", [main.SYSTEM_PROMPT]),
            ("main.state_manager", state_manager),
            ("tools.RECENT_ACTIONS_FILE", self.actions_file),
        ]:
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)

        # 权限单例的可变状态每例结束后还原，避免污染全局
        self.pm = main.permission_manager
        old_level, old_owner = self.pm.current_level, self.pm.owner

        def _restore_pm():
            self.pm.current_level = old_level
            self.pm.owner = old_owner
            self.pm._op_windows.clear()

        self.addCleanup(_restore_pm)
        # 2026-10-02 批次②：/confirm 令牌流删除，儿童锁内存表替代
        self.addCleanup(main._last_seen.clear)
        self.addCleanup(main._pending_child_requests.clear)

        # identity.json 一律指向临时目录：任何测试都不读写真实 agent_state 隔离区
        self.identity = os.path.join(self.tmp, "identity.json")
        p = patch.object(PermissionManager, "IDENTITY_PATH", self.identity)
        p.start()
        self.addCleanup(p.stop)

        self.client = dashboard.app.test_client()   # HTTP 层宿主 :5003（架构合并）

    # ---------- 小工具 ----------
    def onebot(self, payload):
        return self.client.post("/onebot", json=payload)

    def napcat_url(self, endpoint):
        return f"{main.ONEBOT_API_URL}/{endpoint}"

    def napcat_payload(self):
        return self.napcat.post.call_args[1]["json"]

    def make_ws(self):
        ws = os.path.join(self.tmp, "ws")
        os.makedirs(ws, exist_ok=True)
        return ws

    def touch(self, path, content=b"png"):
        with open(path, "wb") as f:
            f.write(content)
        return path

    def set_env(self, **kwargs):
        """注入环境变量（测试结束自动还原）。"""
        p = patch.dict(os.environ, kwargs)
        p.start()
        self.addCleanup(p.stop)

    def identity_path(self):
        """本例隔离的 identity.json 路径（夹具已统一 patch，见 setUp）。"""
        return self.identity

    def fresh_lv4(self):
        """给全局权限单例换上全新 Lv.4 因子链（TOTP + 生物），测试后还原。"""
        fresh = auth_lv4.LV4AuthManager(
            factors=[auth_lv4.TOTPFactor(), auth_lv4.BiometricFactor()])
        p = patch.object(self.pm, "_lv4", fresh)
        p.start()
        self.addCleanup(p.stop)

    def totp_code(self):
        """用固定测试密钥现场生成 6 位动态密码。"""
        return auth_lv4.generate_totp(self.totp_secret)


class TestMergedHosting(_MainCase):
    """架构合并形态（5002 废弃，HTTP 层宿主 :5003）：main 不再有 Flask app、
    旧版 POST /chat 路由不复活、/onebot 仅 POST。"""

    def test_main_module_has_no_flask_app(self):
        """main.py 模块化：纯业务逻辑模块，不再创建 Flask app / 监听端口。"""
        self.assertFalse(hasattr(main, "app"))
        self.assertIs(dashboard.main, main)   # dashboard 宿主的正是本业务模块

    def test_chat_route_removed(self):
        """POST /chat 旧版网页 API 不复活：返回 404。"""
        resp = self.client.post("/chat", json={"message": "你好"})
        self.assertEqual(resp.status_code, 404)

    def test_onebot_get_not_allowed(self):
        """/onebot 仅 POST：GET 返回 405。"""
        resp = self.client.get("/onebot")
        self.assertEqual(resp.status_code, 405)


class TestQqChannelKeepsCq(_MainCase):
    """QQ 出口保持 CQ 原文：/onebot 回复原样 POST 给 NapCat。

    （旧版 /chat 出口的 web_sanitize CQ 净化已随旧页一并下线，净化职责
    归 :5003 新版控制台自身；QQ 发图/发表情能力不受影响。）
    """

    def test_qq_channel_keeps_cq_verbatim(self):
        cq_reply = "[CQ:image,file=file:///ws/表情包.jpg]"
        self.smart_ask.return_value = (cq_reply, "🏠 本地")
        resp = self.onebot({
            "post_type": "message", "message_type": "private",
            "self_id": "10000", "sender": {"user_id": 123},
            "raw_message": "来个表情",
        })

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.napcat_payload()["message"], cq_reply)  # 原样透传，零净化


class TestThinkStrip(_MainCase):
    """<think> 思维链包装剥离（brain 工具流程 <think> 包装契约的出口侧）：
    QQ /onebot 发送前剥除 <think> 块（推理展示只属于 :5003 新前端），
    CQ 码发图能力不受影响。"""

    WRAPPED = "<think>[思考] 先查设备再开灯。</think>已为你打开卧室灯💡"

    def test_qq_reply_strips_think_block(self):
        self.smart_ask.return_value = (self.WRAPPED, "🏠 本地 (工具)")
        resp = self.onebot({
            "post_type": "message", "message_type": "private",
            "self_id": "10000", "sender": {"user_id": 123},
            "raw_message": "开灯",
        })
        self.assertEqual(resp.status_code, 200)
        # NapCat payload 不含 <think>：QQ 消息保持干净
        self.assertNotIn("<think>", self.napcat_payload()["message"])
        self.assertEqual(self.napcat_payload()["message"], "已为你打开卧室灯💡")

    def test_qq_multiline_think_stripped(self):
        # <think> 块内含换行的多行推理文本同样整块剥除（DOTALL）
        wrapped = ("<think>[思考] 主人要开灯。\n[计划] 1. 查设备 2. 开灯</think>"
                   "已为你打开卧室灯💡")
        self.smart_ask.return_value = (wrapped, "🏠 本地 (工具)")
        self.onebot({
            "post_type": "message", "message_type": "private",
            "self_id": "10000", "sender": {"user_id": 123},
            "raw_message": "开灯",
        })
        self.assertEqual(self.napcat_payload()["message"], "已为你打开卧室灯💡")

    def test_qq_reply_keeps_cq_after_think_strip(self):
        # 剥 think 不误伤 CQ 码：/send_image 等随回复链路的发图能力保持
        self.smart_ask.return_value = (
            "<think>[思考] 发个图。</think>[CQ:image,file=file:///ws/表情包.jpg]",
            "🏠 本地")
        self.onebot({
            "post_type": "message", "message_type": "private",
            "self_id": "10000", "sender": {"user_id": 123},
            "raw_message": "来个表情",
        })
        self.assertEqual(self.napcat_payload()["message"],
                         "[CQ:image,file=file:///ws/表情包.jpg]")

    def test_strip_think_helper(self):
        self.assertEqual(main._strip_think("<think>a</think>回复"), "回复")
        self.assertEqual(
            main._strip_think("<think>[思考] x\n[计划] y</think>好"), "好")
        self.assertEqual(main._strip_think("无包装回复"), "无包装回复")
        self.assertEqual(main._strip_think(None), "")
        self.assertEqual(main._strip_think("<think>只有思考没有正文</think>"), "")


class TestOnebotEntry(_MainCase):
    """QQ 入口：私聊/群聊/触发词/@/戳一戳/图片收藏。"""

    def test_private_message_responds(self):
        resp = self.onebot({
            "post_type": "message", "message_type": "private",
            "self_id": "10000", "sender": {"user_id": 123},
            "raw_message": "你好",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_called_once()
        self.napcat.post.assert_called_once()
        self.assertEqual(self.napcat.post.call_args[0][0], self.napcat_url("send_private_msg"))
        payload = self.napcat_payload()
        self.assertEqual(payload["user_id"], 123)
        self.assertEqual(payload["message"], "测试回复")

    def test_group_message_without_trigger_ignored(self):
        resp = self.onebot({
            "post_type": "message", "message_type": "group",
            "self_id": "10000", "group_id": 456, "sender": {"user_id": 123},
            "raw_message": "今天天气不错",
        })
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_not_called()
        self.napcat.post.assert_not_called()

    def test_group_message_with_trigger_word_responds(self):
        resp = self.onebot({
            "post_type": "message", "message_type": "group",
            "self_id": "10000", "group_id": 456, "sender": {"user_id": 123},
            "raw_message": "小橘 帮我看看",
        })
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_called_once()
        self.assertEqual(self.napcat.post.call_args[0][0], self.napcat_url("send_group_msg"))
        self.assertEqual(self.napcat_payload()["group_id"], 456)

    def test_group_at_me_responds(self):
        resp = self.onebot({
            "post_type": "message", "message_type": "group",
            "self_id": "10000", "group_id": 456, "sender": {"user_id": 123},
            "raw_message": "[CQ:at,qq=10000] 在吗",
        })
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_called_once()

    def test_group_at_other_user_ignored(self):
        resp = self.onebot({
            "post_type": "message", "message_type": "group",
            "self_id": "10000", "group_id": 456, "sender": {"user_id": 123},
            "raw_message": "[CQ:at,qq=999] 你好",
        })
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_not_called()
        self.napcat.post.assert_not_called()

    def test_group_at_without_self_id_lenient(self):
        """未携带 self_id 时无法识别被@对象，退化为任意 CQ:at 均响应。"""
        resp = self.onebot({
            "post_type": "message", "message_type": "group",
            "group_id": 456, "sender": {"user_id": 123},
            "raw_message": "[CQ:at,qq=555] 你好",
        })
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_called_once()

    def test_poke_easter_egg_in_group(self):
        resp = self.onebot({
            "post_type": "notice", "notice_type": "poke",
            "group_id": 456, "user_id": 123,
        })
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.napcat.post.assert_called_once()
        self.assertEqual(self.napcat.post.call_args[0][0], self.napcat_url("send_group_msg"))
        self.assertEqual(self.napcat_payload()["message"], "别戳啦，好痒！😆")
        self.smart_ask.assert_not_called()

    def test_poke_easter_egg_in_private(self):
        resp = self.onebot({
            "post_type": "notice", "notice_type": "poke",
            "user_id": 123,
        })
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.assertEqual(self.napcat.post.call_args[0][0], self.napcat_url("send_private_msg"))
        self.assertEqual(self.napcat_payload()["user_id"], 123)

    def test_image_message_saved_to_emoji_store(self):
        with patch("main.save_emoji_link", return_value=True) as save_mock:
            resp = self.onebot({
                "post_type": "message", "message_type": "private",
                "self_id": "10000", "sender": {"user_id": 123},
                "raw_message": "[CQ:image,file=https://gchat.qpic.cn/a.jpg]",
            })
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        save_mock.assert_called_once_with("https://gchat.qpic.cn/a.jpg")
        self.smart_ask.assert_not_called()
        self.assertEqual(self.napcat_payload()["message"], "收到你的表情啦！已经存进小仓库了😊")

    def test_group_image_without_at_saved(self):
        """群聊非 @ 的图片消息同样自动收藏（文档 §5 口径）。"""
        with patch("main.save_emoji_link", return_value=True) as save_mock:
            self.onebot({
                "post_type": "message", "message_type": "group",
                "self_id": "10000", "group_id": 456, "sender": {"user_id": 123},
                "raw_message": "[CQ:image,file=https://gchat.qpic.cn/b.jpg]",
            })
        save_mock.assert_called_once_with("https://gchat.qpic.cn/b.jpg")
        self.smart_ask.assert_not_called()

    def test_image_save_failure_reply(self):
        with patch("main.save_emoji_link", return_value=False):
            self.onebot({
                "post_type": "message", "message_type": "private",
                "self_id": "10000", "sender": {"user_id": 123},
                "raw_message": "[CQ:image,file=https://gchat.qpic.cn/c.jpg]",
            })
        self.assertEqual(self.napcat_payload()["message"], "这个表情我没存下来，下次再试试！")

    def test_meta_event_ignored(self):
        resp = self.onebot({"post_type": "meta_event", "meta_event_type": "heartbeat"})
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_not_called()
        self.napcat.post.assert_not_called()


class TestOnebotLLOneBotTolerance(_MainCase):
    """LLOneBot 兼容容错（/onebot）：raw_message 缺失时从 OneBot 11 消息段
    数组重建文本（at/image 段按 CQ 码惯例还原）、post_type 缺失按 message
    宽容处理、任何字段异常不崩、发送失败打印 LLOneBot 排查提示。"""

    def test_message_segments_rebuild_text(self):
        """raw_message 缺失：从消息段数组拼接 type=="text" 段的 data.text。"""
        resp = self.onebot({
            "post_type": "message", "message_type": "private",
            "self_id": "10000", "sender": {"user_id": 123},
            "message": [{"type": "text", "data": {"text": "你好"}}],
        })
        self.assertEqual(resp.status_code, 200)
        self.smart_ask.assert_called_once()
        args, _ = self.smart_ask.call_args
        self.assertEqual(args[0], "你好")

    def test_message_string_used_directly(self):
        """raw_message 缺失且 message 为字符串：直接使用。"""
        resp = self.onebot({
            "post_type": "message", "message_type": "private",
            "self_id": "10000", "sender": {"user_id": 123},
            "message": "字符串消息",
        })
        self.assertEqual(resp.status_code, 200)
        args, _ = self.smart_ask.call_args
        self.assertEqual(args[0], "字符串消息")

    def test_message_at_segment_restored_triggers_group_reply(self):
        """at 段还原 [CQ:at,qq=...]：群聊 @ 判定与回复链路保持可用。"""
        resp = self.onebot({
            "post_type": "message", "message_type": "group",
            "self_id": "10000", "group_id": 456, "sender": {"user_id": 123},
            "message": [{"type": "at", "data": {"qq": "10000"}},
                        {"type": "text", "data": {"text": " 在吗"}}],
        })
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_called_once()
        self.assertEqual(self.napcat.post.call_args[0][0],
                         self.napcat_url("send_group_msg"))

    def test_message_at_other_user_without_raw_message_ignored(self):
        """还原后的 at 段指向他人：群聊防刷屏过滤仍然生效。"""
        resp = self.onebot({
            "post_type": "message", "message_type": "group",
            "self_id": "10000", "group_id": 456, "sender": {"user_id": 123},
            "message": [{"type": "at", "data": {"qq": "999"}},
                        {"type": "text", "data": {"text": " 你好"}}],
        })
        self.smart_ask.assert_not_called()
        self.napcat.post.assert_not_called()

    def test_message_image_segment_restored_saves_emoji(self):
        """image 段还原 [CQ:image,file=...]：非 @ 图片收藏逻辑保持可用。"""
        with patch("main.save_emoji_link", return_value=True) as save_mock:
            resp = self.onebot({
                "post_type": "message", "message_type": "private",
                "self_id": "10000", "sender": {"user_id": 123},
                "message": [{"type": "image",
                             "data": {"file": "https://gchat.qpic.cn/d.jpg"}}],
            })
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        save_mock.assert_called_once_with("https://gchat.qpic.cn/d.jpg")
        self.smart_ask.assert_not_called()

    def test_missing_post_type_treated_as_message(self):
        """post_type 缺失：按 message 事件宽容处理（LLOneBot 兼容）。"""
        resp = self.onebot({
            "message_type": "private",
            "self_id": "10000", "sender": {"user_id": 123},
            "raw_message": "你好",
        })
        self.assertEqual(resp.status_code, 200)
        self.smart_ask.assert_called_once()

    def test_corrupted_fields_return_ok_without_crash(self):
        """字段类型损坏（如 sender 为非字典）：不崩，统一返回 ok。"""
        resp = self.onebot({
            "post_type": "message", "message_type": "private",
            "sender": 12345, "raw_message": "你好",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_not_called()

    def test_send_failure_prints_llonebot_hint(self):
        """发送端点连不上：打印 LLOneBot 排查提示（默认端口 3001），不阻断。"""
        self.napcat.post.side_effect = RuntimeError("connection refused")
        with patch("builtins.print") as print_mock:
            resp = self.onebot({
                "post_type": "message", "message_type": "private",
                "self_id": "10000", "sender": {"user_id": 123},
                "raw_message": "你好",
            })
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        printed = "\n".join(str(c.args[0]) for c in print_mock.call_args_list
                            if c.args)
        self.assertIn("无法连接至 OneBot 服务", printed)
        self.assertIn("LLOneBot", printed)
        self.assertIn("3001", printed)


class TestHandleMessageRouting(_MainCase):
    """handle_message 路由编排：清洗、内置指令。"""

    def test_punctuation_cleaned_before_brain(self):
        main.handle_message('web', 'u', None, "你好！今天，天气怎么样？")
        args, _ = self.smart_ask.call_args
        self.assertEqual(args[0], "你好今天天气怎么样")

    def test_punctuation_only_message_rejected(self):
        reply = main.handle_message('web', 'u', None, "！！！？？？。。。")
        self.assertEqual(reply, "（你发了一条空消息）")
        self.smart_ask.assert_not_called()

    def test_help_uses_help_menu_plugin(self):
        with patch("plugins.help_menu.get_help_menu", return_value="MENU") as menu_mock:
            reply = main.handle_message('web', 'u', None, "/help")
        self.assertEqual(reply, "MENU")
        menu_mock.assert_called_once_with(self.pm.current_level)

    def test_help_aliases(self):
        for word in ["菜单", "帮助", "指令"]:
            with patch("plugins.help_menu.get_help_menu", return_value="MENU"):
                self.assertEqual(main.handle_message('web', 'u', None, word), "MENU")

    def test_help_menu_contains_new_commands_and_lv4_section(self):
        """help_menu 展示新指令与 Lv.4 菜单段（§7）。"""
        from plugins.help_menu import get_help_menu
        lv4_menu = get_help_menu("Lv.4")
        for item in ["/register", "/lv4_auth", "/lv4_revoke",
                     "/reset_fuse", "/gen_log", "/send_image",
                     "主人级", "安全家居", "restart_service"]:
            self.assertIn(item, lv4_menu)
        # 2026-10-02 权限重构：/sudo 与 /confirm 旧口径条目移除
        self.assertNotIn("/sudo", lv4_menu)
        self.assertNotIn("/confirm", lv4_menu)
        # /coder_auth 升级指引对未达 Lv.3 的用户可见
        self.assertIn("/coder_auth", get_help_menu("Lv.2"))
        # 低等级看不到 Lv.4 段
        self.assertNotIn("主人级", get_help_menu("Lv.2"))

    # ---------- /register（Lv.2 注册，§7） ----------
    def test_register_success_upgrades_and_persists(self):
        identity = self.identity_path()
        self.set_env(XIAOJU3_REGISTER_PASSWORD="reg-pass-123")
        self.pm.current_level = "Lv.1"
        reply = main.handle_message('web', 'admin', None, "/register reg-pass-123")
        self.assertTrue(reply.startswith("✅"))
        self.assertIn("Lv.2", reply)
        self.assertEqual(self.pm.current_level, "Lv.2")
        # 等级持久化：identity.json 落盘，新实例读回 Lv.2（重启不回落）
        self.assertTrue(os.path.exists(identity))
        self.assertEqual(PermissionManager().current_level, "Lv.2")

    def test_register_wrong_password_rejected_and_not_persisted(self):
        identity = self.identity_path()
        self.set_env(XIAOJU3_REGISTER_PASSWORD="reg-pass-123")
        self.pm.current_level = "Lv.1"
        reply = main.handle_message('web', 'admin', None, "/register wrong-pass")
        self.assertTrue(reply.startswith("❌ 注册密码错误"))
        self.assertEqual(self.pm.current_level, "Lv.1")
        self.assertFalse(os.path.exists(identity))

    def test_register_degraded_without_env_password(self):
        """未配置注册密码时透传降级提示（§7：注册密码走 env，不硬编码）。"""
        self.identity_path()
        self.set_env(XIAOJU3_REGISTER_PASSWORD="")
        reply = main.handle_message('web', 'admin', None, "/register whatever")
        self.assertIn("注册功能未开放", reply)
        self.assertIn("XIAOJU3_REGISTER_PASSWORD", reply)

    # ---------- /coder_auth（TOTP 激活 Lv.3，§7 新语义） ----------
    def test_coder_auth_wrong_totp_rejected(self):
        self.identity_path()
        self.set_env(XIAOJU3_TOTP_SECRET=self.totp_secret)
        self.pm.current_level = "Lv.1"
        reply = main.handle_message('web', 'admin', None, "/coder_auth 000000")
        self.assertTrue(reply.startswith("❌"))
        self.assertEqual(self.pm.current_level, "Lv.1")

    def test_coder_auth_totp_activates_and_persists(self):
        """激活成功用例：TOTP 激活 Lv.3 并落盘（修复"重启回落"）。"""
        identity = self.identity_path()
        self.set_env(XIAOJU3_TOTP_SECRET=self.totp_secret)
        self.pm.current_level = "Lv.1"
        reply = main.handle_message('web', 'admin', None,
                                    f"/coder_auth {self.totp_code()}")
        self.assertTrue(reply.startswith("✅"))
        self.assertEqual(self.pm.current_level, "Lv.3")
        self.assertTrue(os.path.exists(identity))
        self.assertEqual(PermissionManager().current_level, "Lv.3")

    def test_coder_auth_degraded_without_totp_secret(self):
        self.identity_path()
        self.set_env(XIAOJU3_TOTP_SECRET="")
        self.pm.current_level = "Lv.1"
        reply = main.handle_message('web', 'admin', None, "/coder_auth 123456")
        self.assertIn("降级", reply)
        self.assertEqual(self.pm.current_level, "Lv.1")

    def test_lv3_write_file_directly_succeeds(self):
        """Lv.3 激活后写文件直接成功（逐次动态密码要求已由用户 2026-09-30 取消）。"""
        self.identity_path()
        self.set_env(XIAOJU3_TOTP_SECRET=self.totp_secret)
        ws = self.make_ws()
        self.pm.current_level = "Lv.1"
        with patch("tools.WORKSPACE", ws):
            # 激活 Lv.3
            reply = main.handle_message('web', 'admin', None,
                                        f"/coder_auth {self.totp_code()}")
            self.assertTrue(reply.startswith("✅"))
            self.assertEqual(self.pm.current_level, "Lv.3")
            # 激活后直接写文件：无需 /sudo 窗口或凭据
            ok = execute_tool("write_file",
                              {"filename": "a.txt", "content": "hi"}, self.pm)
            self.assertTrue(ok.startswith("✅"))

    # ---------- /sudo（120s 写操作窗口，§7） ----------
    def test_sudo_wrong_code_no_window(self):
        self.set_env(XIAOJU3_TOTP_SECRET=self.totp_secret)
        reply = main.handle_message('web', 'admin', None, "/sudo 000000")
        self.assertTrue(reply.startswith("❌"))
        self.assertFalse(self.pm.operation_window_active(None))

    def test_sudo_without_code_shows_usage(self):
        reply = main.handle_message('web', 'admin', None, "/sudo")
        self.assertIn("用法", reply)

    # ---------- /lv4_auth 两步流与 /lv4_revoke（§7） ----------
    def test_lv4_auth_step1_shows_root_warning(self):
        self.fresh_lv4()
        self.set_env(XIAOJU3_TOTP_SECRET=self.totp_secret, XIAOJU3_BIOMETRIC_SIM="1")
        self.pm.current_level = "Lv.1"
        reply = main.handle_message('web', 'admin', None, "/lv4_auth")
        # 类 Root 警告：敏感操作清单 + 后果 + 撤销途径
        self.assertIn("类 Root", reply)
        self.assertIn("门锁", reply)
        self.assertIn("revoke_lv4", reply)
        self.assertIn("/lv4_auth confirm", reply)
        self.smart_ask.assert_not_called()
        self.assertNotEqual(self.pm.current_level, "Lv.4")

    def test_lv4_auth_confirm_grants_and_records_mfa_session(self):
        self.fresh_lv4()
        self.set_env(XIAOJU3_TOTP_SECRET=self.totp_secret, XIAOJU3_BIOMETRIC_SIM="1")
        main.handle_message('web', 'admin', None, "/lv4_auth")   # 第一步：阅读警告
        reply = main.handle_message('web', 'admin', None,
                                    f"/lv4_auth confirm {self.totp_code()}")
        self.assertTrue(reply.startswith("✅"))
        self.assertEqual(self.pm.current_level, "Lv.4")
        self.assertTrue(self.pm.is_owner())
        # 2026-10-02 批次②：操作级 MFA 会话随 /confirm 令牌流删除
        self.assertFalse(hasattr(main, "_mfa_sessions"))

    def test_lv4_auth_confirm_without_biometric_fails_with_detail(self):
        """生物认证器未接入时透传"生物认证器未接入"明细（lv4_mfa_check）。"""
        self.fresh_lv4()
        self.set_env(XIAOJU3_TOTP_SECRET=self.totp_secret)   # 不开生物模拟
        self.pm.current_level = "Lv.1"
        reply = main.handle_message('web', 'admin', None,
                                    f"/lv4_auth confirm {self.totp_code()}")
        self.assertTrue(reply.startswith("❌"))
        self.assertIn("生物认证器未接入", reply)
        self.assertEqual(self.pm.current_level, "Lv.1")

    def test_lv4_revoke_immediately_downgrades(self):
        self.fresh_lv4()
        self.set_env(XIAOJU3_TOTP_SECRET=self.totp_secret, XIAOJU3_BIOMETRIC_SIM="1")
        main.handle_message('web', 'admin', None,
                            f"/lv4_auth confirm {self.totp_code()}")
        self.assertEqual(self.pm.current_level, "Lv.4")
        reply = main.handle_message('web', 'admin', None, "/lv4_revoke")
        self.assertTrue(reply.startswith("✅"))
        self.assertEqual(self.pm.current_level, "Lv.3")
        self.assertFalse(self.pm.is_owner())

    # ---------- /reset_fuse（Lv.2+ 熔断重置） ----------
    def test_reset_fuse_requires_lv2(self):
        self.pm.current_level = "Lv.1"
        with patch("main.reset_tool_fuse") as reset_mock:
            reply = main.handle_message('web', 'admin', None, "/reset_fuse")
        self.assertTrue(reply.startswith("❌"))
        reset_mock.assert_not_called()

    def test_reset_fuse_resets_for_lv2(self):
        self.pm.current_level = "Lv.2"
        with patch("main.reset_tool_fuse") as reset_mock:
            reply = main.handle_message('web', 'admin', None, "/reset_fuse")
        self.assertTrue(reply.startswith("✅"))
        reset_mock.assert_called_once_with()

    def test_new_session_first_message_resets_channel_fuse(self):
        """新会话首条消息（历史为空）自动重置该通道熔断计数。"""
        with patch("main.reset_tool_fuse") as reset_mock:
            main.handle_message('web', 'admin', None, "第一条")
            reset_mock.assert_called_once_with("web")
            reset_mock.reset_mock()
            # 历史已非空：不再触发自动重置
            main.handle_message('web', 'admin', None, "第二条")
            reset_mock.assert_not_called()

    # ---------- /send_image（等级 ≥ Lv.3，修复 Lv.4 主人被拒） ----------
    def test_send_image_requires_lv4(self):
        # 2026-10-02 权限重构：发图升 LV4（Lv.1/Lv.2/Lv.3 一律拒绝）
        ws = self.make_ws()
        img = self.touch(os.path.join(ws, "pic.png"))
        for level in ("Lv.1", "Lv.2", "Lv.3"):
            self.pm.current_level = level
            with patch("main.WORKSPACE", ws):
                reply = main.handle_message('qq', 123, None,
                                            f"/send_image {img}")
            self.assertTrue(reply.startswith("❌ 权限不足"), (level, reply))
            self.assertIn("Lv.4", reply)

    def test_send_image_allows_lv4_owner(self):
        self.pm.current_level = "Lv.4"
        ws = self.make_ws()
        img = self.touch(os.path.join(ws, "pic.png"))
        with patch("main.WORKSPACE", ws):
            reply = main.handle_message('qq', 123, None, f"/send_image {img}")
        self.assertEqual(reply, f"[CQ:image,file=file://{img}]")
        self.smart_ask.assert_not_called()

    def test_send_image_outside_workspace_denied(self):
        self.pm.current_level = "Lv.4"
        ws = self.make_ws()
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside, exist_ok=True)
        img = self.touch(os.path.join(outside, "evil.png"))
        with patch("main.WORKSPACE", ws):
            reply = main.handle_message('qq', 123, None, f"/send_image {img}")
        self.assertEqual(reply, "❌ 只能发送项目工作区内的图片。")

    def test_send_image_missing_file(self):
        self.pm.current_level = "Lv.4"
        ws = self.make_ws()
        missing = os.path.join(ws, "nope.png")
        with patch("main.WORKSPACE", ws):
            reply = main.handle_message('qq', 123, None, f"/send_image {missing}")
        self.assertTrue(reply.startswith("❌ 图片不存在"))

    def test_send_image_in_workspace_returns_cq(self):
        self.pm.current_level = "Lv.4"
        ws = self.make_ws()
        img = self.touch(os.path.join(ws, "pic.png"))
        with patch("main.WORKSPACE", ws):
            reply = main.handle_message('qq', 123, None, f"/send_image {img}")
        self.assertEqual(reply, f"[CQ:image,file=file://{img}]")
        self.smart_ask.assert_not_called()

    # ---------- /gen_log（Lv.3+ 门槛） ----------
    def test_gen_log_requires_lv3_and_skips_thread(self):
        self.pm.current_level = "Lv.1"
        with patch("main.threading.Thread") as thread_mock:
            reply = main.handle_message('web', 'u', None,
                                        "/gen_log https://chat.deepseek.com/share/abc")
        self.assertTrue(reply.startswith("❌"))
        self.assertIn("Lv.3", reply)
        thread_mock.assert_not_called()   # 权限不足不执行后台线程

    def test_gen_log_invalid_link(self):
        self.pm.current_level = "Lv.3"
        reply = main.handle_message('web', 'u', None, "/gen_log https://example.com/x")
        self.assertTrue(reply.startswith("⚠️"))

    def test_gen_log_valid_link_runs_background(self):
        self.pm.current_level = "Lv.3"

        class ImmediateThread:
            """把 Thread 换成同步执行，便于离线断言后台任务被调度。"""

            def __init__(self, target=None, args=(), kwargs=None, daemon=None):
                if target:
                    target(*args, **(kwargs or {}))

            def start(self):
                pass

        with patch("main.threading.Thread", ImmediateThread), \
                patch("run_link_log.run_link_log") as run_mock:
            reply = main.handle_message('web', 'u', None,
                                        "/gen_log https://chat.deepseek.com/share/abc123")
        self.assertTrue(reply.startswith("🔄"))
        run_mock.assert_called_once_with("https://chat.deepseek.com/share/abc123")


class TestIntentRouting(_MainCase):
    """意图路由接入（架构 §10 #4）：命中直达，None/失败透传 smart_ask。"""

    @staticmethod
    def _intent(name="accounting_add"):
        return IntentResult(name=name, args={}, confidence=0.95,
                            handler="plugins.accounting:add_record", source="rule")

    def test_intent_hit_short_circuits(self):
        intent = self._intent()
        with patch("main.route", return_value=intent), \
                patch("main.dispatch", return_value="已记账：-30.0 元（餐饮）") as d_mock:
            reply = main.handle_message('web', 'admin', None, "午饭花了30元")
        self.assertEqual(reply, "已记账：-30.0 元（餐饮）")
        d_mock.assert_called_once_with(intent)
        self.smart_ask.assert_not_called()

    def test_intent_none_falls_through_to_smart_ask(self):
        with patch("main.route", return_value=None):
            main.handle_message('web', 'admin', None, "随便聊聊今天的心情")
        self.smart_ask.assert_called_once()

    def test_intent_dispatch_exception_falls_through(self):
        """dispatch 抛错不吞消息：继续走原 smart_ask 链路。"""
        with patch("main.route", return_value=self._intent()), \
                patch("main.dispatch", side_effect=RuntimeError("boom")):
            main.handle_message('web', 'admin', None, "记一下账")
        self.smart_ask.assert_called_once()

    def test_intent_dispatch_denied_falls_through(self):
        """dispatch 返回 ❌ 失败串同样透传原链路，绝不吞消息。"""
        with patch("main.route", return_value=self._intent()), \
                patch("main.dispatch", return_value="❌ 意图执行失败：参数不全"):
            main.handle_message('web', 'admin', None, "记一下账")
        self.smart_ask.assert_called_once()

    def test_export_ebook_gets_channel_history(self):
        """export_ebook 意图：接线方把当前通道历史填进 args["history"]。"""
        intent = self._intent("export_ebook")
        with patch("main.route", return_value=intent), \
                patch("main.dispatch", return_value="电子书已生成") as d_mock:
            main.handle_message('web', 'admin', None, "把对话导出成电子书")
        sent = d_mock.call_args[0][0]
        self.assertEqual(sent.name, "export_ebook")
        self.assertEqual(sent.args["history"],
                         [{"role": "user", "content": "把对话导出成电子书"}])


class TestMemoryAndCompression(_MainCase):
    """双通道记忆 + 前情提要压缩（架构 §10 #2）+ 长期记忆（架构 §10 #3）。"""

    def test_dual_channel_separated(self):
        self.smart_ask.side_effect = [("QQ回复", "🏠 本地"), ("网页回复", "☁️ 云端")]
        main.handle_message('qq', 1, None, "来自QQ的消息")
        main.handle_message('web', 'admin', None, "来自网页的消息")

        with open(self.mem_qq, encoding="utf-8") as f:
            qq_hist = json.load(f)
        with open(self.mem_web, encoding="utf-8") as f:
            web_hist = json.load(f)

        self.assertEqual([m["content"] for m in qq_hist], ["来自QQ的消息", "QQ回复"])
        self.assertEqual([m["content"] for m in web_hist], ["来自网页的消息", "网页回复"])

        # state_manager.save_conversation 独立落盘
        self.assertTrue(os.path.exists(os.path.join(self.state_dir, "conversations", "qq_history.json")))
        self.assertTrue(os.path.exists(os.path.join(self.state_dir, "conversations", "web_history.json")))

    def test_smart_ask_receives_channel_history(self):
        main.handle_message('web', 'admin', None, "第一条")
        args, _ = self.smart_ask.call_args
        # 历史列表按引用传入（调用后 handle_message 会再追加 assistant 回复），
        # 这里断言调用时包含置顶 system 提示词与本条用户消息
        history = args[1]
        self.assertEqual(args[0], "第一条")
        self.assertEqual(history[0]["role"], "system")
        self.assertIn({"role": "user", "content": "第一条"}, history)

    # ---------- 前情提要压缩（架构 §10 #2） ----------
    def _prefill_web(self, count):
        prefilled = [{"role": "user", "content": f"旧消息{i}"} for i in range(count)]
        p = patch("main.messages_web", [main.SYSTEM_PROMPT] + prefilled)
        p.start()
        self.addCleanup(p.stop)

    def test_compression_adds_summary_to_history_head(self):
        """超过 20 条：旧消息浓缩为前情提要并入历史头部（QQ/网页同路径）。"""
        self._prefill_web(25)
        with patch("brain.ask_local", return_value="测试前情提要摘要"):
            main.handle_message('web', 'admin', None, "新消息")

        # 内存通道历史含前情提要（置顶提示词之后）
        self.assertTrue(any("【前情提要】" in (m.get("content") or "")
                            and "测试前情提要摘要" in (m.get("content") or "")
                            for m in main.messages_web))
        self.assertEqual(main.messages_web[0], main.SYSTEM_PROMPT)
        # 落盘历史同样携带前情提要（重启不丢）
        with open(self.mem_web, encoding="utf-8") as f:
            hist = json.load(f)
        self.assertTrue(any("【前情提要】" in (m.get("content") or "") for m in hist))
        # 压缩后体量收敛（系统提示 + 前情提要 + 最近 10 条）
        self.assertLessEqual(len(main.messages_web), 13)

    def test_compression_failure_falls_back_to_pure_truncation(self):
        """压缩失败（双脑不可用）：回退纯截断，50 条硬上限仍生效。"""
        self._prefill_web(60)
        with patch("brain.ask_local", side_effect=RuntimeError("local down")), \
                patch("brain.ask_cloud", return_value="⚠️ 云端连接异常: down"):
            main.handle_message('web', 'admin', None, "新消息")

        self.assertFalse(any("【前情提要】" in (m.get("content") or "")
                             for m in main.messages_web))
        with open(self.mem_web, encoding="utf-8") as f:
            hist = json.load(f)
        self.assertEqual(len(hist), 50)
        # 60 旧 + 1 新 user + 1 assistant = 62 → 滚动截断保留最近 50 条（丢弃前 12 条）
        self.assertEqual(hist[0]["content"], "旧消息12")
        self.assertEqual(hist[-1], {"role": "assistant", "content": "测试回复"})

    # ---------- 长期记忆（架构 §10 #3） ----------
    def test_remember_saves_long_term_memory_and_confirms(self):
        with patch.object(main.state_manager, "save_memory") as save_mock:
            reply = main.handle_message('web', 'admin', None, "帮我记住我最爱的水果是苹果")
        save_mock.assert_called_once_with("user", "我最爱的水果是苹果")
        self.assertIn("苹果", reply)
        self.assertIn("记住", reply)
        self.smart_ask.assert_not_called()

    def test_remember_plain_prefix_also_works(self):
        with patch.object(main.state_manager, "save_memory") as save_mock:
            main.handle_message('web', 'admin', None, "记住我的快递地址是幸福路1号")
        save_mock.assert_called_once_with("user", "我的快递地址是幸福路1号")

    def test_recent_memories_injected_into_smart_ask_context(self):
        """进入 smart_ask 前取 get_recent_memories(3) 拼入系统上下文。"""
        main.state_manager.save_memory("user", "用户喜欢蓝色")
        main.state_manager.save_memory("user", "用户养了一只猫")
        with patch.object(main.state_manager, "get_recent_memories",
                          return_value=[("user", "用户喜欢蓝色"),
                                        ("user", "用户养了一只猫")]) as mem_mock:
            main.handle_message('web', 'admin', None, "今天穿什么好")
        mem_mock.assert_called_once_with(3)
        args, _ = self.smart_ask.call_args
        blocks = [m for m in args[1]
                  if m.get("role") == "system" and "长期记忆" in (m.get("content") or "")]
        self.assertEqual(len(blocks), 1)
        self.assertIn("以下是关于用户的长期记忆", blocks[0]["content"])
        self.assertIn("用户喜欢蓝色", blocks[0]["content"])
        self.assertIn("用户养了一只猫", blocks[0]["content"])

    def test_no_memory_no_injection(self):
        """长期记忆为空则不拼注入块。"""
        with patch.object(main.state_manager, "get_recent_memories", return_value=[]):
            main.handle_message('web', 'admin', None, "你好")
        args, _ = self.smart_ask.call_args
        # 【主人位置】上下文由真实 brain.smart_ask 注入；本用例 mock 了
        # smart_ask，消息形状仍由 main 组装——只有置顶系统提示词一条
        self.assertEqual(len([m for m in args[1] if m.get("role") == "system"]), 1)


class TestClearMemoryCommand(_MainCase):
    """一键清空记忆（/clear、/reset、清空记忆、重置记忆）：
    精确匹配触发；内存列表 + 磁盘文件双清（文件置空数组 []）；另一通道不受
    影响；/reset_fuse 不被 /reset 误吞；清空后旧历史不复活。"""

    CLEAR_REPLY = "✨ 记忆已清空！我现在的大脑非常干净，可以重新开始对话了。"
    TRIGGERS = ("/clear", "/reset", "清空记忆", "重置记忆")

    def _seed_both(self):
        """两个通道各预置内存历史与磁盘文件（清空前已有旧记忆）。"""
        web_old = [main.SYSTEM_PROMPT,
                   {"role": "user", "content": "网页旧记忆"},
                   {"role": "assistant", "content": "网页旧回复"}]
        qq_old = [main.SYSTEM_PROMPT,
                  {"role": "user", "content": "QQ旧记忆"},
                  {"role": "assistant", "content": "QQ旧回复"}]
        for attr, seeded in (("main.messages_web", list(web_old)),
                             ("main.messages_qq", list(qq_old))):
            p = patch(attr, seeded)
            p.start()
            self.addCleanup(p.stop)
        brain.save_memory(web_old[1:], self.mem_web)
        brain.save_memory(qq_old[1:], self.mem_qq)

    def test_each_trigger_clears_web_channel_and_replies(self):
        """四个触发词（web 通道）：返回指定文案，内存+文件双清，QQ 通道不受影响。"""
        for word in self.TRIGGERS:
            with self.subTest(trigger=word):
                self._seed_both()
                reply = main.handle_message('web', 'admin', None, word)
                self.assertEqual(reply, self.CLEAR_REPLY)
                self.assertEqual(main.messages_web, [main.SYSTEM_PROMPT])
                with open(self.mem_web, encoding="utf-8") as f:
                    self.assertEqual(json.load(f), [])
                self.assertIn({"role": "user", "content": "QQ旧记忆"},
                              main.messages_qq)
                with open(self.mem_qq, encoding="utf-8") as f:
                    self.assertIn("QQ旧记忆", f.read())
                self.smart_ask.assert_not_called()

    def test_each_trigger_clears_qq_channel_and_replies(self):
        """四个触发词（QQ 私聊通道）：双清 QQ 记忆，网页通道不受影响。"""
        for word in self.TRIGGERS:
            with self.subTest(trigger=word):
                self._seed_both()
                reply = main.handle_message('qq', 10001, None, word)
                self.assertEqual(reply, self.CLEAR_REPLY)
                self.assertEqual(main.messages_qq, [main.SYSTEM_PROMPT])
                with open(self.mem_qq, encoding="utf-8") as f:
                    self.assertEqual(json.load(f), [])
                with open(self.mem_web, encoding="utf-8") as f:
                    self.assertIn("网页旧记忆", f.read())

    def test_reset_fuse_not_swallowed_by_reset(self):
        """/reset 存在后 /reset_fuse 仍正常工作，且不清空记忆。"""
        self._seed_both()
        self.pm.current_level = "Lv.2"
        with patch("main.reset_tool_fuse") as reset_mock:
            reply = main.handle_message('web', 'admin', None, "/reset_fuse")
        self.assertTrue(reply.startswith("✅ 防死循环熔断"))
        reset_mock.assert_called_once_with()
        self.assertIn({"role": "user", "content": "网页旧记忆"}, main.messages_web)
        with open(self.mem_web, encoding="utf-8") as f:
            self.assertIn("网页旧记忆", f.read())

    def test_memory_does_not_revive_after_clear(self):
        """内存确实被清空：清空后再发消息，落盘文件不复活旧历史。"""
        self._seed_both()
        main.handle_message('web', 'admin', None, "清空记忆")
        self.assertEqual(main.messages_web, [main.SYSTEM_PROMPT])
        main.handle_message('web', 'admin', None, "这是新的开始")
        with open(self.mem_web, encoding="utf-8") as f:
            hist = json.load(f)
        self.assertEqual([m["content"] for m in hist],
                         ["这是新的开始", "测试回复"])
        contents = [m.get("content") or "" for m in main.messages_web]
        self.assertNotIn("网页旧记忆", contents)
        self.assertEqual(main.messages_web[0], main.SYSTEM_PROMPT)

    def test_normal_sentence_containing_words_not_cleared(self):
        """精确匹配口径：含"清空记忆"的普通问句不触发清空，照常走大脑。"""
        self._seed_both()
        reply = main.handle_message('web', 'admin', None, "怎么清空记忆")
        self.smart_ask.assert_called_once()
        self.assertNotEqual(reply, self.CLEAR_REPLY)
        self.assertIn({"role": "user", "content": "怎么清空记忆"},
                      main.messages_web)


class TestRecentActionsInjection(_MainCase):
    """最近设备操作记录注入（指代消解上下文）：QQ/网页通道均注入、
    空记录不注入、损坏记录不炸主链路、注入块紧跟置顶系统提示词。"""

    def _seed_actions(self, details):
        """向 tmp 记录文件预置设备操作（与 tools.record_recent_action 同构）。"""
        entries = [{"ts": "2026-09-30 12:00:00", "tool": "control_ha_device",
                    "detail": d} for d in details]
        with open(self.actions_file, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False)

    def _action_blocks(self):
        args, _ = self.smart_ask.call_args
        return [m for m in args[1]
                if m.get("role") == "system"
                and (m.get("content") or "").startswith("以下是最近的设备操作记录")]

    def test_web_channel_injects_recent_actions(self):
        self._seed_actions(["control_ha_device: light.living → turn_on"])
        main.handle_message('web', 'admin', None, "把它关了")
        blocks = self._action_blocks()
        self.assertEqual(len(blocks), 1)
        self.assertIn("control_ha_device: light.living → turn_on",
                      blocks[0]["content"])
        self.smart_ask.assert_called_once()

    def test_qq_channel_injects_recent_actions(self):
        self._seed_actions(["adb_tap: 点击 (10, 20)"])
        main.handle_message('qq', 1, None, "再点一次")
        blocks = self._action_blocks()
        self.assertEqual(len(blocks), 1)
        self.assertIn("adb_tap: 点击 (10, 20)", blocks[0]["content"])

    def test_empty_records_no_injection(self):
        # 记录文件不存在（夹具默认）→ 不注入；2026-10-02 起额外有【主人位置】
        self.assertFalse(os.path.exists(self.actions_file))
        main.handle_message('web', 'admin', None, "你好")
        args, _ = self.smart_ask.call_args
        self.assertEqual([m for m in args[1] if m.get("role") == "system"],
                         [main.SYSTEM_PROMPT])

    def test_corrupted_records_no_injection_and_no_crash(self):
        with open(self.actions_file, "w", encoding="utf-8") as f:
            f.write("corrupted!")
        main.handle_message('web', 'admin', None, "你好")
        args, _ = self.smart_ask.call_args
        self.assertEqual([m for m in args[1] if m.get("role") == "system"],
                         [main.SYSTEM_PROMPT])
        self.assertEqual(args[0], "你好")   # 主链路照常走到 smart_ask

    def test_injection_block_sits_right_after_system_prompt(self):
        self._seed_actions(["control_ha_device: light.a → turn_off"])
        main.state_manager.save_memory("user", "用户喜欢蓝色")
        main.handle_message('web', 'admin', None, "关掉它")
        args, _ = self.smart_ask.call_args
        hist = args[1]
        self.assertEqual(hist[0], main.SYSTEM_PROMPT)
        self.assertTrue(hist[1]["content"].startswith("以下是最近的设备操作记录"))
        self.assertIn("长期记忆", hist[2]["content"])   # 长期记忆块次序不被破坏


class TestMigrationWiring(_MainCase):
    """迁移守望接入（架构 §8）：health_bp 注册（宿主 :5003）+ PeerWatch 默认不开。"""

    def test_health_endpoint_registered(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["device"])
        self.assertIsInstance(data["ts"], float)

    def test_peer_watch_gate_default_off(self):
        """守望开关默认关闭：未配置对端或未开 XIAOJU3_WATCH 都不启动。"""
        self.set_env(XIAOJU3_PEERS="", XIAOJU3_WATCH="")
        self.assertFalse(main._peer_watch_enabled())
        self.set_env(XIAOJU3_PEERS="http://peer.example.com:5002", XIAOJU3_WATCH="")
        self.assertFalse(main._peer_watch_enabled())

    def test_peer_watch_gate_on(self):
        """XIAOJU3_PEERS 非空且 XIAOJU3_WATCH=1 时开启。"""
        self.set_env(XIAOJU3_PEERS="http://peer.example.com:5002", XIAOJU3_WATCH="1")
        self.assertTrue(main._peer_watch_enabled())


class TestLocationCommands(unittest.TestCase):
    """位置指令（2026-10-02 隐私口径）：/set_location / /clear_location，
    QQ 与网页共用 main.handle_location_command；位置只存本地
    agent_state/user_location.json（gitignore），测试后清理。"""

    def setUp(self):
        from agent_state import state_manager
        self.sm = state_manager
        self.sm.clear_user_location()   # 起点干净

    def tearDown(self):
        self.sm.clear_user_location()

    def test_set_location_with_district(self):
        """/set_location 长沙 天心区 → 写入成功（城市+区县）。"""
        reply = main.handle_message('web', 'admin', None,
                                    "/set_location 长沙 天心区")
        self.assertIn("位置已记录", reply)
        self.assertIn("长沙", reply)
        self.assertIn("天心区", reply)
        self.assertEqual(self.sm.get_user_location(),
                         {"city": "长沙", "district": "天心区"})

    def test_set_location_city_only(self):
        """/set_location 长沙 → 只写城市、区县为空。"""
        reply = main.handle_message('qq', 'user1', None, "/set_location 长沙")
        self.assertIn("位置已记录", reply)
        self.assertEqual(self.sm.get_user_location(),
                         {"city": "长沙", "district": ""})

    def test_set_location_usage_hint(self):
        """/set_location 无参数 → 返回用法提示，不写入。"""
        reply = main.handle_location_command("/set_location")
        self.assertIn("用法", reply)
        self.assertIsNone(self.sm.get_user_location())

    def test_clear_location(self):
        """/clear_location → 清除成功（记录文件删除）。"""
        self.sm.save_user_location("长沙", "天心区")
        reply = main.handle_message('web', 'admin', None, "/clear_location")
        self.assertIn("已清除", reply)
        self.assertIsNone(self.sm.get_user_location())

    def test_clear_location_when_absent_still_ok(self):
        """/clear_location 无记录时同样返回成功文案（幂等）。"""
        reply = main.handle_location_command("/clear_location")
        self.assertIn("已清除", reply)

    def test_clear_location_marks_grace_period(self):
        """/clear_location 触发 brain 位置静默期标记（2026-10-02 用户口径：
        清除后 5 分钟内忽略历史位置，强制 AI 重新询问）。"""
        import brain
        self.addCleanup(setattr, brain, "_location_cleared_at", 0.0)
        main.handle_location_command("/clear_location")
        self.assertGreater(brain._location_cleared_at, 0)
        self.assertTrue(brain._location_in_clear_grace())

    def test_normal_message_not_intercepted(self):
        """普通对话（含"位置"字样）不被位置指令误拦截。"""
        self.assertIsNone(main.handle_location_command("你住什么位置呀"))

    def test_dashboard_api_chat_set_location(self):
        """网页端：/api/chat 走同一 helper（命中即系统消息返回，不进大脑）。"""
        from xiaoju3_dashboard import app
        client = app.test_client()
        resp = client.post("/api/chat",
                           json={"message": "/set_location 长沙 天心区"})
        payload = resp.get_json()
        self.assertEqual(payload["code"], 200)
        self.assertIn("位置已记录", payload["data"]["reply"])
        self.assertEqual(payload["data"]["source"], "⚙️ 系统")
        self.assertEqual(self.sm.get_user_location(),
                         {"city": "长沙", "district": "天心区"})

    def test_dashboard_api_chat_clear_location(self):
        """网页端 /clear_location：与 QQ 通道同效。"""
        self.sm.save_user_location("长沙", "天心区")
        from xiaoju3_dashboard import app
        client = app.test_client()
        resp = client.post("/api/chat", json={"message": "/clear_location"})
        payload = resp.get_json()
        self.assertEqual(payload["code"], 200)
        self.assertIn("已清除", payload["data"]["reply"])
        self.assertIsNone(self.sm.get_user_location())


class TestWaitingLocationWindow(_MainCase):
    """等待位置回答窗口（2026-10-02 群聊体验修复）：AI 问位置后，群聊裸
    回答"长沙天心区"（无 @）绕过防刷屏规则放行处理；无组合/超时仍忽略。"""

    def setUp(self):
        super().setUp()
        import brain
        self.brain = brain
        brain.clear_waiting_location()
        self.addCleanup(brain.clear_waiting_location)

    def _onebot_group(self, text):
        return self.onebot({
            "post_type": "message", "message_type": "group",
            "self_id": "10000", "group_id": 456, "sender": {"user_id": 123},
            "raw_message": text,
        })

    def test_location_answer_without_at_processed(self):
        """任务口径用例①：窗口内群聊裸回答"长沙天心区"（无 @）→ 放行进
        handle_message（smart_ask 被调用，不再被防刷屏规则忽略）。"""
        self.brain._mark_waiting_location()
        resp = self._onebot_group("长沙天心区")
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_called_once()
        self.napcat.post.assert_called_once()

    def test_normal_chat_without_combo_still_ignored(self):
        """任务口径用例②：窗口内无位置组合的普通聊天（"今天怎么样"）
        → 仍被忽略（不误处理普通聊天）。"""
        self.brain._mark_waiting_location()
        resp = self._onebot_group("今天怎么样")
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_not_called()
        self.napcat.post.assert_not_called()

    def test_window_expired_still_ignored(self):
        """任务口径用例③：窗口超时（6 分钟前开窗）→ 裸回答仍被忽略。"""
        import time as _time
        self.brain._waiting_location_until = _time.time() - 1   # 已超时
        resp = self._onebot_group("长沙天心区")
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_not_called()
        self.napcat.post.assert_not_called()

    def test_clear_location_closes_window(self):
        """任务口径用例④：/clear_location 关闭等待窗口（避免遗留状态）。"""
        self.brain._mark_waiting_location()
        self.assertTrue(self.brain._waiting_location_active())
        main.handle_message('web', 'admin', None, "/clear_location")
        self.assertFalse(self.brain._waiting_location_active())

    def test_webhook_bypass_extracts_and_writes(self):
        """任务 4 端到端（webhook 夹具）：窗口内群聊裸回答"长沙天心区"
        → handle_message 链路被调用 + 位置写入 user_location.json
        （生产链路中提取在 smart_ask 起步执行——smart_ask mock 的
        side_effect 显式走真实提取补偿，验证写入闭环）。"""
        from agent_state import state_manager as sm_module
        sm_module.clear_user_location()
        self.addCleanup(sm_module.clear_user_location)
        self.brain._mark_waiting_location()

        def fake_smart_ask(msg, hist, session_key="default"):
            self.brain._extract_location_from_user_message(msg)
            return ("好的，已记录你的位置！", "🏠 本地")

        self.smart_ask.side_effect = fake_smart_ask
        resp = self._onebot_group("长沙天心区")
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_called_once()
        self.napcat.post.assert_called_once()
        self.assertEqual(sm_module.get_user_location(),
                         {"city": "长沙", "district": "天心区"})
        # 窗口已关闭（提取成功即关窗）
        self.assertFalse(self.brain._waiting_location_active())

    def test_window_city_only_answer_bypasses(self):
        """窗口内只回城市（"长沙"，无区县）→ 同样放行（spec 伪代码口径：
        city 命中即 bypass；模型会继续追问区县，比挡掉体验好）。"""
        self.brain._mark_waiting_location()
        resp = self._onebot_group("长沙")
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_called_once()

    def test_per_message_debug_log_printed(self):
        """任务 2 日志口径：每条群聊消息打 📨 调试行（内容/窗口/组合三态）。"""
        self.brain._mark_waiting_location()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self._onebot_group("长沙天心区")
        self.assertIn("📨 [群聊] 收到消息: 内容=长沙天心区", buf.getvalue())
        self.assertIn("是否在等待窗口内=True", buf.getvalue())
        self.assertIn("是否含位置组合=True", buf.getvalue())
        self.assertIn("📍 [位置] 等待回答窗口内，绕过 @ 判断，尝试提取位置",
                      buf.getvalue())


class TestChildLockFlow(_MainCase):
    """儿童锁（2026-10-02 批次②）：儿童危险家电操作 → 在线成人确认流。

    覆盖：挂起+通知 / 无在线成人直接拒绝 / approve 代执行（主人级提权后
    还原）/ deny / 超时 / 成人直行 / 儿童锁关闭不拦截。
    """

    def setUp(self):
        super().setUp()
        self._lock_flag = patch("main.CHILD_LOCK_ENABLED", True)
        self._lock_flag.start()
        self.addCleanup(self._lock_flag.stop)
        # 登记 child 为儿童（is_adult=False）；admin 为在线成人 LV4
        #（等级设 Lv.4：handle_message 每次交互会用当前等级刷新 _last_seen）
        self.pm._is_adults["child"] = False
        self.addCleanup(self.pm._is_adults.pop, "child", None)
        self.pm.current_level = "Lv.4"
        main._last_seen["admin"] = {"ts": time.time(), "level": "Lv.4"}
        self.addCleanup(main._last_seen.pop, "admin", None)

    def _child_ask(self):
        """儿童发危险家电请求：smart_ask mock 内模拟模型发起工具调用，
        并把工具结果作为模型回复返回（贴近真实链路）。"""
        def fake_smart_ask(msg, hist, session_key="default"):
            result = brain.execute_tool(
                "control_ha_device",
                {"entity_id": "lock.front_door", "action": "unlock"},
                main.permission_manager)
            return (result, "🏠 本地")
        self.smart_ask.side_effect = fake_smart_ask
        return main.handle_message('qq', 'child', None, "帮我把前门锁打开")

    def _create_pending(self, expires_in=300):
        main._pending_child_requests["000001"] = {
            "user_id": "child", "tool_name": "control_ha_device",
            "args": {"entity_id": "lock.front_door", "action": "unlock"},
            "desc": "unlock lock.front_door",
            "expires": time.time() + expires_in}

    def test_child_request_pends_and_notifies_adults(self):
        with patch("main.execute_tool", return_value="✅ mock") as mexe:
            reply = self._child_ask()
        mexe.assert_not_called()   # 工具挂起未执行
        self.assertIn("已通知在线成人", reply)
        self.assertEqual(len(main._pending_child_requests), 1)
        self.napcat.post.assert_called()   # QQ 私聊通知在线成人

    def test_no_online_adult_direct_reject(self):
        main._last_seen.clear()   # 无在线成人
        self.pm.current_level = "Lv.1"   # 儿童交互刷新后等级不达标
        with patch("main.execute_tool", return_value="✅ mock") as mexe:
            reply = self._child_ask()
        mexe.assert_not_called()
        self.assertIn("❌ 儿童锁已开启，且无成人 LV4 在线确认，操作已拒绝。",
                      reply)
        self.assertEqual(main._pending_child_requests, {})

    def test_approve_executes_with_owner_level(self):
        self._create_pending()
        with patch("main.execute_tool",
                   return_value="✅ 已执行（mock）") as mexe:
            reply = main.handle_message('qq', 'admin', None, "/approve")
        self.assertTrue(reply.startswith("✅ 成人已确认"), reply)
        mexe.assert_called_once()
        args, _ = mexe.call_args
        self.assertEqual(args[0], "control_ha_device")
        self.assertEqual(args[1],
                         {"entity_id": "lock.front_door", "action": "unlock"})
        # 临时提权后还原到成人原等级（本类 admin 即 Lv.4，无残留变化）
        self.assertEqual(self.pm.current_level, "Lv.4")
        self.assertEqual(main._pending_child_requests, {})

    def test_approve_requires_online_adult(self):
        self._create_pending()
        # 裁决者交互会被 _last_seen 以"当时等级"刷新——把全局等级降为
        # Lv.1 模拟"无在线成人 LV4"（请求者交互后等级不达标）
        self.pm.current_level = "Lv.1"
        reply = main.handle_message('qq', 'someone', None, "/approve")
        self.assertTrue(reply.startswith("❌ 只有在线成人 LV4"), reply)
        self.assertEqual(len(main._pending_child_requests), 1)   # 请求保留

    def test_deny_rejects_request(self):
        self._create_pending()
        reply = main.handle_message('qq', 'admin', None, "/deny")
        self.assertIn("已拒绝该儿童操作请求", reply)
        self.assertEqual(main._pending_child_requests, {})

    def test_timeout_rejects(self):
        self._create_pending(expires_in=-1)   # 已超时
        reply = main.handle_message('qq', 'admin', None, "/approve")
        self.assertIn("已超时", reply)
        self.assertEqual(main._pending_child_requests, {})

    def test_adult_dangerous_request_bypasses_lock(self):
        """成人（is_adult 缺省 True）发起危险操作 → 不拦截、直接执行。"""
        self.pm.current_level = "Lv.4"

        def fake_smart_ask(msg, hist, session_key="default"):
            brain.execute_tool(
                "control_ha_device",
                {"entity_id": "lock.front_door", "action": "unlock"},
                main.permission_manager)
            return ("已执行", "🏠 本地")

        self.smart_ask.side_effect = fake_smart_ask
        with patch.object(brain, "execute_tool",
                          return_value="✅ 已执行（mock）") as mexe:
            reply = main.handle_message('qq', 'admin', None, "帮我开个门锁")
        mexe.assert_called_once()
        self.assertEqual(main._pending_child_requests, {})
        self.assertIn("已执行", reply)

    def test_child_lock_off_no_interception(self):
        """儿童锁关闭：儿童危险请求照常执行（按等级门禁，不进确认流）。"""
        self._lock_flag.stop()
        with patch.object(brain, "execute_tool",
                          return_value="✅ mock") as mexe:
            reply = self._child_ask()
        mexe.assert_called_once()
        self.assertEqual(main._pending_child_requests, {})


if __name__ == "__main__":

    unittest.main()
