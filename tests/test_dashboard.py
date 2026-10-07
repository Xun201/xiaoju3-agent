# -*- coding: utf-8 -*-
"""监控仪表盘（xiaoju3_dashboard）单元测试（全部离线）。

覆盖（任务口径，二阶段增补）：
- GET /api/status 结构断言（code / data 五字段、cpu/memory 为数值），
  psutil 正常与异常 mock 两态（异常字段回退 0.0）；
- GET /api/balance：mock requests 断言 GET CLOUD_BALANCE_URL + Bearer 头与
  返回结构；无 KEY / 请求失败 / 返回格式异常的回退结构（余额 0.0 + 错误提示）；
- POST /api/chat：mock brain.smart_ask 断言直连（不经路由层、不写
  agent_state 下 history_qq/history_web 双通道记忆落盘）与 {reply, source}
  返回；空消息 400、GET 405、大脑异常 500；成功问答落盘控制台历史
  （HISTORY_FILE 注入 tmp 目录，不污染真实 agent_state）；
- GET /api/history 返回结构（缺失文件回退空列表）、DELETE /api/history
  清空、POST /api/chat 后 50 条滚动截断、大脑异常不落盘；
- GET / 旧版页与 GET /console 新版控制台托管（含关键令牌）；
- 素材可达：/assets/DSniang1.jpg 200（修复界面文档 §5.1 的 404 已知问题）；
- Web 出口 CQ 码净化（纵深防御）：web_sanitize.sanitize_for_web 纯函数
  （face→Emoji、image→[表情]、其余剥除、本机路径不外泄）；/api/chat 返回与
  落盘前净化（mock smart_ask 注入 QQ 专用 CQ 回复）；
- 静态路由缓存失效：/console*、/assets* 统一 Cache-Control: no-store（接口不套用）；
- prompts 表情规则改版：回复一律普通 Emoji、禁止模型输出 [CQ:...] 码；
- 前端三件套静态断言：index.html 无外部 CDN、viewport meta、:root 令牌
  （默认深蓝 #203170 不变）+ data-theme="orange" 橘色主题、移动端断点与
  抽屉；console.js 2s 轮询与 >80% 变红、历史加载渲染、刷新/转发实装
  （无 alert 占位）、主题/音效开关；desktop-pet.js 桌宠规格（250 / 0.88 /
  拖拽阈值 9 / 5000ms / 60000ms / 报错端口 5003 且不含 5005）、真实素材
  DSniang1.jpg、scaleX(-1) 翻转、吸附阈值 24px、台词库、AudioContext、
  600px 移动端缩放；
- 思维链前端展示（<think> 块 + 裸 [思考]/[计划] 标记兜底）：console.js
  统一入口 splitThinkBlock 两段解析（先切分后转义、<think> 正则非锚定——
  reply 含块即必出卡片；裸 [思考]/[计划] 段并入思考卡并从正文剥离、
  [行动] 行与其后 JSON 不上屏、剥空占位"（操作已执行）"、普通聊天
  反例不误剥离）、
  渲染入口仅由 think !== null 守卫（后端 2026-10-01 全对话强制包装后，
  普通闲聊同样带"[思考] 正在理解你的意图..."默认占位符块；正文为自然
  语言或占位符都出卡，无块仍不插卡——前端行为零改动）、思考
  卡片逐字打字（textContent 注入防注入）+ 打完自动折叠/点击展开、历史
  回放不打字、刷新重生成同步卡片、等待期 900ms 轮换状态；index.html
  .think-card / .think-card-header / .think-card-body 浅灰折叠样式；
- T4a 诊断与强制兜底（2026-10-01）：RAW_REPLY / PARSED_THINK+PARSED_BODY /
  RENDERING_THINK_CARD 三处常驻诊断日志落点；插卡尝试后 querySelector
  实测校验 .think-card 真实存在，缺失且 think 非空时 createElement +
  classList.add('think-card') 手工构建（🧠 图标 + ▼ 折叠箭头 + 思考文本
  textContent 注入）并 prepend 强制补插，二次校验仍失败最终降级深色纯
  文本块；index.html .think-card 显式 display: block。

mock 注意：所有 patch 均走 context manager / start+addCleanup（结束即还原），
不污染 sys.modules；历史文件一律注入 tmp 目录，可与其它测试文件在同一
进程中共存。
"""
import contextlib
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
import warnings
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import prompts  # noqa: E402
import web_sanitize  # noqa: E402
import main  # noqa: E402  QQ 接入层业务模块（/onebot 迁移路由打桩用）
import xiaoju3  # noqa: E402
import xiaoju3_dashboard as dashboard  # noqa: E402
from agent_state.state_manager import StateManager  # noqa: E402
from permission import PermissionManager  # noqa: E402


@contextlib.contextmanager
def _quiet():
    """吞掉仪表盘的进度 print（含 emoji 与 traceback），保持测试输出干净。"""
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _history_files():
    """agent_state 目录下已有的 history_* 会话记忆文件集合。"""
    state_dir = xiaoju3.AGENT_STATE_DIR
    if not os.path.isdir(state_dir):
        return set()
    return {n for n in os.listdir(state_dir) if n.startswith("history_")}


def _read_json_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# GET /api/status
# ---------------------------------------------------------------------------

class StatusApiTests(unittest.TestCase):
    """系统状态接口：结构与 psutil 正常 / 异常两态。"""

    def setUp(self):
        self.client = dashboard.app.test_client()

    def test_status_structure_normal(self):
        """psutil 正常：code=200，data 恰好五字段且数值正确。"""
        fake_psutil = mock.Mock()
        fake_psutil.cpu_percent.return_value = 32.5
        fake_psutil.virtual_memory.return_value = mock.Mock(percent=61.2)
        fake_psutil.sensors_temperatures.return_value = {
            "coretemp": [mock.Mock(current=52.3), mock.Mock(current=45.0)],
        }
        fake_time = mock.Mock()
        fake_time.time.return_value = 1727654321.6

        with mock.patch.object(dashboard, "psutil", fake_psutil), \
                mock.patch.object(dashboard, "time", fake_time):
            resp = self.client.get("/api/status")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["code"], 200)
        data = payload["data"]
        self.assertEqual(set(data.keys()),
                         {"cpu", "memory", "temperature", "timestamp", "tts_voice", "creator", "version"})
        self.assertEqual(data["cpu"], 32.5)
        self.assertEqual(data["memory"], 61.2)
        self.assertEqual(data["temperature"], 52.3)  # 取首个可用温度
        self.assertEqual(data["timestamp"], 1727654321)
        self.assertIsInstance(data["timestamp"], int)
        for key in ("cpu", "memory", "temperature"):
            self.assertIsInstance(data[key], (int, float))
        fake_psutil.cpu_percent.assert_called_once_with(interval=0.5)

    def test_status_psutil_exception_fallback(self):
        """psutil 抛异常：cpu/memory/temperature 回退 0.0，接口不 500。"""
        fake_psutil = mock.Mock()
        fake_psutil.cpu_percent.side_effect = RuntimeError("psutil boom")
        fake_psutil.virtual_memory.side_effect = RuntimeError("psutil boom")
        fake_psutil.sensors_temperatures.side_effect = NotImplementedError(
            "sensors not supported")

        with mock.patch.dict(sys.modules, {"wmi": None}),              mock.patch.object(dashboard, "glob", glob),              mock.patch.object(dashboard, "psutil", fake_psutil), _quiet():
            resp = self.client.get("/api/status")

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(set(data.keys()),
                         {"cpu", "memory", "temperature", "timestamp", "tts_voice", "creator", "version"})
        self.assertEqual(data["cpu"], 0.0)
        self.assertEqual(data["memory"], 0.0)
        # 组 C 新口径：温度读取链全失败返回字符串占位（替换旧恒 0.0）
        self.assertEqual(data["temperature"], "暂无温度")
        self.assertIsInstance(data["timestamp"], int)

    def test_status_sensors_empty_fallback(self):
        """sensors_temperatures 返回空：温度回退 0.0。"""
        fake_psutil = mock.Mock()
        fake_psutil.cpu_percent.return_value = 10.0
        fake_psutil.virtual_memory.return_value = mock.Mock(percent=20.0)
        fake_psutil.sensors_temperatures.return_value = {}

        with mock.patch.dict(sys.modules, {"wmi": None}),              mock.patch.object(dashboard, "glob", glob),              mock.patch.object(dashboard, "psutil", fake_psutil):
            data = self.client.get("/api/status").get_json()["data"]

        # 组 C 新口径：sensors 空且 wmi/sys 均无 → 字符串占位
        self.assertEqual(data["temperature"], "暂无温度")
        self.assertEqual(data["cpu"], 10.0)


# ---------------------------------------------------------------------------
# GET /api/balance
# ---------------------------------------------------------------------------

class BalanceApiTests(unittest.TestCase):
    """余额接口：Bearer 请求、正常结构、无 KEY / 失败回退。"""

    def setUp(self):
        self.client = dashboard.app.test_client()

    def test_balance_success_with_bearer_header(self):
        """正常：GET CLOUD_BALANCE_URL + Bearer CLOUD_KEY，返回嵌套结构。"""
        fake_resp = mock.Mock()
        fake_resp.json.return_value = {
            "balance_infos": [{"total_balance": "12.34", "currency": "CNY"}],
        }
        with mock.patch.object(dashboard, "CLOUD_KEY", "test-key"), \
                mock.patch.object(dashboard, "CLOUD_BALANCE_URL",
                                  "https://api.example.com/user/balance"), \
                mock.patch.object(dashboard, "requests") as mr:
            mr.get.return_value = fake_resp
            payload = self.client.get("/api/balance").get_json()

        mr.get.assert_called_once_with(
            "https://api.example.com/user/balance",
            headers={"Authorization": "Bearer test-key"},
            timeout=10,
        )
        self.assertEqual(payload["code"], 200)
        self.assertEqual(payload["data"], {
            "balance": 12.34,
            "currency": "CNY",
            "today_usage": 0.0,   # 文档口径：今日已用恒 0.0
            "is_peak": False,
        })

    def test_balance_no_key_fallback(self):
        """无 KEY：不发起请求，回退余额 0.0 并附错误提示。"""
        with mock.patch.object(dashboard, "CLOUD_KEY", ""), \
                mock.patch.object(dashboard, "requests") as mr:
            payload = self.client.get("/api/balance").get_json()

        mr.get.assert_not_called()
        self.assertEqual(payload["code"], 500)
        self.assertTrue(payload.get("error"))
        self.assertEqual(payload["data"]["balance"], 0.0)
        self.assertEqual(payload["data"]["today_usage"], 0.0)
        self.assertEqual(payload["data"]["is_peak"], False)

    def test_balance_request_failure_fallback(self):
        """请求异常：回退余额 0.0，error 含失败原因。"""
        with mock.patch.object(dashboard, "CLOUD_KEY", "test-key"), \
                mock.patch.object(dashboard, "requests") as mr:
            mr.get.side_effect = OSError("network down")
            payload = self.client.get("/api/balance").get_json()

        self.assertEqual(payload["code"], 500)
        self.assertIn("network down", payload["error"])
        self.assertEqual(payload["data"]["balance"], 0.0)

    def test_balance_abnormal_payload_fallback(self):
        """返回缺 balance_infos：按格式异常回退。"""
        fake_resp = mock.Mock()
        fake_resp.json.return_value = {"error": {"message": "bad request"}}
        with mock.patch.object(dashboard, "CLOUD_KEY", "test-key"), \
                mock.patch.object(dashboard, "requests") as mr:
            mr.get.return_value = fake_resp
            payload = self.client.get("/api/balance").get_json()

        self.assertEqual(payload["code"], 500)
        self.assertIn("格式异常", payload["error"])
        self.assertEqual(payload["data"]["balance"], 0.0)


# ---------------------------------------------------------------------------
# 控制台聊天历史持久化（功能文档 §12 / 界面文档 §10.4 近期项）
# ---------------------------------------------------------------------------

class HistoryApiTestsBase(unittest.TestCase):
    """历史接口测试基类：HISTORY_FILE 注入 tmp 目录（自动还原）。"""

    def setUp(self):
        self.client = dashboard.app.test_client()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.history_file = os.path.join(tmp.name, "history_console.json")
        patcher = mock.patch.object(dashboard, "HISTORY_FILE", self.history_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write_history(self, messages):
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False)


class HistoryApiTests(HistoryApiTestsBase):
    """/api/history：GET 结构、DELETE 清空、方法限制。"""

    def test_get_history_structure(self):
        """GET 返回 {code, data:{messages:[...]}}，消息按落盘顺序返回。"""
        self._write_history([
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好呀~", "source": "🏠 本地"},
        ])
        payload = self.client.get("/api/history").get_json()

        self.assertEqual(payload["code"], 200)
        self.assertIn("messages", payload["data"])
        msgs = payload["data"]["messages"]
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[0]["content"], "你好")
        self.assertEqual(msgs[1]["role"], "assistant")
        self.assertEqual(msgs[1]["source"], "🏠 本地")

    def test_get_history_missing_file_returns_empty(self):
        """历史文件缺失：GET 回退空列表，不 500。"""
        payload = self.client.get("/api/history").get_json()
        self.assertEqual(payload["code"], 200)
        self.assertEqual(payload["data"]["messages"], [])

    def test_delete_history_clears_file(self):
        """DELETE 清空：文件写回空列表，GET 返回空。"""
        self._write_history([{"role": "user", "content": "旧消息"}] * 3)
        payload = self.client.delete("/api/history").get_json()

        self.assertEqual(payload["code"], 200)
        self.assertEqual(payload["data"]["messages"], [])
        self.assertEqual(_read_json_file(self.history_file), [])
        self.assertEqual(self.client.get("/api/history").get_json()
                         ["data"]["messages"], [])

    def test_history_post_not_allowed(self):
        """/api/history 仅 GET/DELETE：POST 返回 405。"""
        resp = self.client.post("/api/history", json={"message": "x"})
        self.assertEqual(resp.status_code, 405)


class TerminalHistoryApiTests(HistoryApiTestsBase):
    """GET /api/history?source=terminal（2026-10-01 跨组钉死契约，组 R3 依赖）：
    终端 CLI 通道 history_terminal.json 的读取端（写端为 xiaoju3.CLI_MEMORY_FILE）；
    缺省（无 source 参数）保持现状只读控制台通道。"""

    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.terminal_file = os.path.join(tmp.name, "history_terminal.json")
        patcher = mock.patch.object(dashboard, "TERMINAL_HISTORY_FILE",
                                    self.terminal_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write_terminal(self, messages):
        os.makedirs(os.path.dirname(self.terminal_file), exist_ok=True)
        with open(self.terminal_file, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False)

    def test_terminal_source_reads_terminal_file(self):
        """source=terminal：返回 history_terminal.json 内容（同结构）。"""
        self._write_terminal([
            {"role": "user", "content": "终端里的问题"},
            {"role": "assistant", "content": "终端里的回答"},
        ])
        payload = self.client.get("/api/history?source=terminal").get_json()

        self.assertEqual(payload["code"], 200)
        self.assertEqual(payload["data"]["messages"],
                         [{"role": "user", "content": "终端里的问题"},
                          {"role": "assistant", "content": "终端里的回答"}])

    def test_terminal_source_missing_file_returns_empty(self):
        """终端历史文件缺失：{code:200, data:{messages:[]}}，不 500。"""
        payload = self.client.get("/api/history?source=terminal").get_json()
        self.assertEqual(payload["code"], 200)
        self.assertEqual(payload["data"]["messages"], [])

    def test_default_source_stays_console_and_ignores_terminal(self):
        """缺省保持现状：只读控制台通道，终端文件存在也不混入。"""
        self._write_terminal([{"role": "user", "content": "终端专属"}])
        self._write_history([{"role": "user", "content": "控制台专属"}])

        default = self.client.get("/api/history").get_json()
        self.assertEqual([m["content"] for m in default["data"]["messages"]],
                         ["控制台专属"])
        terminal = self.client.get("/api/history?source=terminal").get_json()
        self.assertEqual([m["content"] for m in terminal["data"]["messages"]],
                         ["终端专属"])

    def test_terminal_source_value_matched_after_trim_and_case(self):
        """source 取值宽松匹配（首尾空白 / 大小写）：TERMINAL 同样命中终端通道。"""
        self._write_terminal([{"role": "user", "content": "终端"}])
        payload = self.client.get("/api/history?source=%20TERMINAL%20").get_json()
        self.assertEqual(payload["data"]["messages"],
                         [{"role": "user", "content": "终端"}])
        # 未知 source 一律回退控制台通道（缺省语义）
        other = self.client.get("/api/history?source=qq").get_json()
        self.assertEqual(other["code"], 200)
        self.assertEqual(other["data"]["messages"], [])   # 控制台文件未写 → 空


class ChatHistoryPersistenceTests(HistoryApiTestsBase):
    """POST /api/chat 成功后的历史落盘与 50 条滚动截断。"""

    def test_chat_persists_user_and_assistant(self):
        """成功问答：用户消息与回复（含 source）追加落盘。"""
        with mock.patch.object(dashboard, "smart_ask") as ms, _quiet():
            ms.return_value = ("你好呀，主人~", "🏠 本地")
            resp = self.client.post("/api/chat", json={"message": "你好"})

        self.assertEqual(resp.status_code, 200)
        stored = _read_json_file(self.history_file)
        self.assertEqual(stored[0], {"role": "user", "content": "你好"})
        self.assertEqual(stored[1]["role"], "assistant")
        self.assertEqual(stored[1]["content"], "你好呀，主人~")
        self.assertEqual(stored[1]["source"], "🏠 本地")

    def test_chat_history_truncated_to_50(self):
        """50 条滚动截断：旧消息 + 新问答超过 50 条时保留最近 50 条。"""
        old = [{"role": "user", "content": f"旧消息{i}"} for i in range(49)]
        self._write_history(old)

        with mock.patch.object(dashboard, "smart_ask") as ms, _quiet():
            ms.return_value = ("收到", "☁️ 云端")
            resp = self.client.post("/api/chat", json={"message": "新消息"})

        self.assertEqual(resp.status_code, 200)
        stored = _read_json_file(self.history_file)
        self.assertEqual(len(stored), dashboard.MAX_MESSAGES)   # 50 条
        self.assertEqual(stored[0]["content"], "旧消息1")        # 最旧的被截断
        self.assertEqual(stored[-2]["content"], "新消息")        # 新问答在末尾
        self.assertEqual(stored[-1]["content"], "收到")

    def test_chat_brain_failure_persists_nothing(self):
        """大脑异常 500：不落盘（仅成功问答持久化）。"""
        self._write_history([{"role": "user", "content": "已有"}])
        with mock.patch.object(dashboard, "smart_ask",
                               side_effect=RuntimeError("brain boom")), _quiet():
            resp = self.client.post("/api/chat", json={"message": "hi"})

        self.assertEqual(resp.status_code, 500)
        self.assertEqual(_read_json_file(self.history_file),
                         [{"role": "user", "content": "已有"}])

    def test_chat_empty_message_persists_nothing(self):
        """空消息 400：不落盘。"""
        with _quiet():
            resp = self.client.post("/api/chat", json={"message": ""})
        self.assertEqual(resp.get_json()["code"], 400)
        self.assertFalse(os.path.exists(self.history_file))


# ---------------------------------------------------------------------------
# POST /api/chat（直连大脑与双通道隔离）
# ---------------------------------------------------------------------------

class ChatApiTests(HistoryApiTestsBase):
    """聊天接口：直连 brain.smart_ask，不写 QQ/网页双通道记忆落盘。"""

    def test_chat_direct_to_brain_and_returns_source(self):
        """mock smart_ask：直连传参 (message, history)，返回 reply + source。"""
        history = [{"role": "user", "content": "早上好"},
                   {"role": "assistant", "content": "早呀"}]
        before = _history_files()
        with mock.patch.object(dashboard, "smart_ask") as ms, _quiet():
            ms.return_value = ("你好呀，主人~", "🏠 本地")
            resp = self.client.post("/api/chat",
                                    json={"message": "你好", "history": history})

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["code"], 200)
        self.assertEqual(payload["data"]["reply"], "你好呀，主人~")
        self.assertEqual(payload["data"]["source"], "🏠 本地")
        ms.assert_called_once_with("你好", history)
        # 直连大脑：不写 QQ/网页双通道记忆，agent_state 下无新 history 落盘
        # （控制台历史已注入 tmp 目录，真实 agent_state 不受影响）
        self.assertEqual(_history_files(), before)
        # 控制台侧问答成功后落盘（HISTORY_FILE 已注入 tmp）
        self.assertTrue(os.path.exists(self.history_file))

    def test_chat_default_empty_history(self):
        """未传 history：以空列表传给 smart_ask。"""
        with mock.patch.object(dashboard, "smart_ask") as ms, _quiet():
            ms.return_value = ("嗯嗯", "☁️ 云端")
            resp = self.client.post("/api/chat", json={"message": "在吗"})

        self.assertEqual(resp.status_code, 200)
        ms.assert_called_once_with("在吗", [])

    def test_console_help_returns_menu_not_llm(self):
        """控制台 /help 接线（2026-10-04）：命中菜单别名 → 返回 help_menu
        渲染（含"指令菜单"标题、source=⚙️ 系统），绝不落 smart_ask
        （修复"/help 落 LLM"——api_chat 此前从未接线 help_menu，
        QQ 通道 main.py:774 一直正常）。"""
        with mock.patch.object(dashboard, "smart_ask") as ms, _quiet():
            resp = self.client.post("/api/chat", json={"message": "/help"})

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["code"], 200)
        self.assertIn("指令菜单", payload["data"]["reply"])
        self.assertEqual(payload["data"]["source"], "⚙️ 系统")
        ms.assert_not_called()

    def test_console_help_aliases_share_menu(self):
        """别名（菜单/帮助/指令）同走菜单；每个别名都不得触达 LLM。"""
        for word in ("菜单", "帮助", "指令"):
            with mock.patch.object(dashboard, "smart_ask") as ms, _quiet():
                resp = self.client.post("/api/chat", json={"message": word})

            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.get_json()["data"]["source"], "⚙️ 系统")
            self.assertIn("指令菜单", resp.get_json()["data"]["reply"])
            ms.assert_not_called()


class ConsoleIntentRouteTests(HistoryApiTestsBase):
    """控制台意图路由直达（#247，2026-10-05）：api_chat/stream 复用
    main.handle_intent_command——记账/电子书/搜索三意图不落 LLM；
    未命中/❌ 透传 smart_ask（绝不吞消息，与 QQ 链路同语义）；
    export_ebook 注入通道历史（非 system，截最近 50 条）；
    流式命中单帧 done（与斜杠拦截同模式）。route/dispatch 一律 mock
    （不触真实账本/导出）。"""

    def _fake_intent(self, name="accounting_add", args=None):
        intent = mock.MagicMock()
        intent.name = name
        intent.args = dict(args or {})
        return intent

    def test_accounting_message_hits_direct_not_llm(self):
        with mock.patch.object(main, "route",
                               return_value=self._fake_intent()), \
             mock.patch.object(main, "dispatch",
                               return_value="✅（测试）已记账"), \
             mock.patch.object(dashboard, "smart_ask") as ms, _quiet():
            resp = self.client.post(
                "/api/chat", json={"message": "记一下账 花了30元"})
        data = resp.get_json()["data"]
        self.assertEqual(data["source"], "⚙️ 指令")
        self.assertIn("已记账", data["reply"])
        ms.assert_not_called()   # 直达铁律：不落 LLM

    def test_ebook_intent_gets_history_injected_and_trimmed(self):
        history = [{"role": "system", "content": "置顶提示词"}] + [
            {"role": "user" if i % 2 == 0 else "assistant",
             "content": f"m{i}"} for i in range(55)]
        captured = {}

        def fake_dispatch(intent):
            captured["args"] = dict(intent.args or {})
            return "📚 电子书已生成（共 3 章）：x.epub"

        with mock.patch.object(
                main, "route",
                return_value=self._fake_intent("export_ebook")), \
             mock.patch.object(main, "dispatch",
                               side_effect=fake_dispatch), \
             mock.patch.object(dashboard, "smart_ask") as ms, _quiet():
            resp = self.client.post("/api/chat", json={
                "message": "把对话导出成电子书", "history": history})
        self.assertIn("电子书", resp.get_json()["data"]["reply"])
        ms.assert_not_called()
        injected = captured["args"]["history"]
        self.assertEqual(len(injected), 50)   # 截最近 50 条（对齐 QQ 口径）
        self.assertTrue(all(m.get("role") != "system" for m in injected))
        self.assertEqual(injected[-1]["content"], "m54")   # 保留最新

    def test_unmatched_message_falls_through_to_llm(self):
        with mock.patch.object(dashboard, "smart_ask") as ms, _quiet():
            ms.return_value = ("模型回复", "🏠 本地")
            resp = self.client.post(
                "/api/chat", json={"message": "今天天气不错"})
        self.assertEqual(resp.get_json()["data"]["reply"], "模型回复")
        ms.assert_called_once_with("今天天气不错", [])   # 空记录不注入

    def test_dispatch_error_reply_falls_through_to_llm(self):
        # ❌ 透传语义与 QQ 链路一致：dispatch 失败不吞消息
        with mock.patch.object(main, "route",
                               return_value=self._fake_intent()), \
             mock.patch.object(main, "dispatch",
                               return_value="❌ 意图执行失败"), \
             mock.patch.object(dashboard, "smart_ask") as ms, _quiet():
            ms.return_value = ("模型回复", "🏠 本地")
            resp = self.client.post("/api/chat", json={"message": "记一下账"})
        self.assertEqual(resp.get_json()["data"]["reply"], "模型回复")
        ms.assert_called_once()

    def test_stream_intent_hits_single_done_frame(self):
        with mock.patch.object(main, "route",
                               return_value=self._fake_intent()), \
             mock.patch.object(main, "dispatch",
                               return_value="✅（测试）已记账"), \
             mock.patch.object(dashboard.brain, "smart_ask_stream") as mss, \
             _quiet():
            resp = self.client.post(
                "/api/chat/stream", json={"message": "记一下账"})
        body = resp.get_data(as_text=True)
        self.assertEqual(body.count("event: done"), 1)   # 单帧收口
        self.assertNotIn("event: think", body)
        self.assertNotIn("event: answer", body)
        self.assertIn("⚙️ 指令", body)
        mss.assert_not_called()


class ConsoleSlashWiringTests(HistoryApiTestsBase):
    """控制台斜杠指令接线（C' 第一批，2026-10-04）：_console_slash_intercept
    复用 main 既有函数（main.py 零改动）——每条命中处理器、不落 LLM；
    等级门同口径；/clear 只清控制台历史（QQ 记忆文件反向锚）；
    /lv4_auth 两步流；清单一致性（拦截集 ⊆ main 分发集，/send_image 排除）。
    权限方法一律 mock（接线测试不触真实 identity/agent_state）。"""

    def setUp(self):
        super().setUp()
        self.pm = main.permission_manager

    def _post(self, message):
        with mock.patch.object(dashboard, "smart_ask") as ms, _quiet():
            resp = self.client.post("/api/chat", json={"message": message})
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["code"], 200)
        ms.assert_not_called()   # 命中拦截 = 不落 LLM（逐条铁律）
        return payload["data"]

    # ---------- ⚙️ /clear：只清控制台历史 ----------
    def test_clear_console_history_only(self):
        self._write_history([{"role": "user", "content": "旧对话"}])
        qq_before = list(main.messages_qq)
        web_before = list(main.messages_web)
        data = self._post("/clear")
        self.assertIn("控制台对话记忆已清空", data["reply"])
        self.assertEqual(data["source"], "⚙️ 系统")
        with open(dashboard.HISTORY_FILE, encoding="utf-8") as f:
            self.assertEqual(json.load(f), [])   # 控制台历史已清
        self.assertEqual(list(main.messages_qq), qq_before)  # QQ 记忆不动
        self.assertEqual(list(main.messages_web), web_before)

    # ---------- 🔑 权限族：复用 permission_manager（mock 收口） ----------
    def test_register_wired_with_args(self):
        with mock.patch.object(
                self.pm, "register_user",
                return_value="✅ 注册成功，等级 Lv.2") as mu:
            data = self._post("/register reg-pass-123 小白")
        self.assertIn("注册成功", data["reply"])
        self.assertEqual(data["source"], "🔑 权限")
        mu.assert_called_once_with("console", "reg-pass-123", name="小白")

    def test_coder_auth_wired(self):
        with mock.patch.object(
                self.pm, "activate_lv3",
                return_value="✅ Lv.3 已激活") as mu:
            data = self._post("/coder_auth 123456")
        self.assertIn("Lv.3", data["reply"])
        mu.assert_called_once_with("console", "123456")

    def test_sudo_usage_and_window(self):
        data = self._post("/sudo")
        self.assertIn("用法", data["reply"])
        with mock.patch.object(
                self.pm, "open_operation_window",
                return_value="✅ 写操作窗口已开启") as mu:
            data = self._post("/sudo 654321")
        self.assertIn("窗口", data["reply"])
        mu.assert_called_once_with(None, totp_code="654321")

    def test_lv4_auth_two_step_flow(self):
        # 第一步（无参）：类 Root 警告（真实 root_warning，纯文本无副作用）
        data = self._post("/lv4_auth")
        self.assertIn("双因子授权", data["reply"])
        # 第二步 confirm：mfa 通过 → grant_lv4（mock 收口）
        with mock.patch.object(
                self.pm, "lv4_mfa_check",
                return_value=(True, "OK")) as mfa, \
             mock.patch.object(
                 self.pm, "grant_lv4",
                 return_value="✅ Lv.4 授权生效") as grant:
            data = self._post("/lv4_auth confirm 123456")
        self.assertIn("Lv.4", data["reply"])
        mfa.assert_called_once()
        grant.assert_called_once()
        # mfa 未通过：明细透传
        with mock.patch.object(self.pm, "lv4_mfa_check",
                               return_value=(False, "动态密码错误")):
            data = self._post("/lv4_auth confirm 000000")
        self.assertIn("未通过", data["reply"])
        self.assertIn("动态密码错误", data["reply"])

    def test_lv4_revoke_wired(self):
        with mock.patch.object(
                self.pm, "revoke_lv4",
                return_value="✅ 主人级权限已撤销") as mu:
            data = self._post("/lv4_revoke")
        self.assertIn("撤销", data["reply"])
        mu.assert_called_once_with("console")

    # ---------- 🧠 / 🧪 灵魂备份：等级门（真实门）+ 接线（mock） ----------
    def test_soul_export_lv1_denied_by_real_gate(self):
        with mock.patch.object(self.pm, "current_level", "Lv.1"), _quiet():
            data = self._post("/soul_export")
        self.assertTrue(data["reply"].startswith("❌"))   # 真实等级门拒绝

    def test_soul_commands_wired(self):
        with mock.patch.object(
                main, "handle_soul_command",
                return_value="✅ 灵魂备份完成") as mu:
            data = self._post("/soul_export")
        self.assertIn("灵魂备份", data["reply"])
        mu.assert_called_once()
        with mock.patch.object(
                main, "handle_soul_command",
                return_value="✅ 灵魂恢复完成") as mu2:
            data = self._post("/soul_import x.zip")
        self.assertIn("灵魂恢复", data["reply"])
        mu2.assert_called_once()

    # ---------- ⚙️ /name /reset_fuse /gen_log ----------
    def test_name_wired(self):
        with mock.patch.object(
                self.pm, "claim_name",
                return_value="✅ 称呼已设为「小白」") as mu:
            data = self._post("/name 小白")
        self.assertIn("小白", data["reply"])
        self.assertEqual(data["source"], "⚙️ 系统")
        mu.assert_called_once_with("console", "小白")

    def test_reset_fuse_level_gate_and_wiring(self):
        with mock.patch.object(self.pm, "current_level", "Lv.1"), _quiet():
            data = self._post("/reset_fuse")
        self.assertIn("Lv.2", data["reply"])   # 等级门拒绝
        with mock.patch.object(self.pm, "current_level", "Lv.2"), \
             mock.patch.object(main, "reset_tool_fuse") as mu, _quiet():
            data = self._post("/reset_fuse")
        self.assertIn("已重置", data["reply"])
        mu.assert_called_once_with()

    def test_gen_log_gate_format_and_wiring(self):
        good = "/gen_log https://chat.deepseek.com/share/abc123"
        with mock.patch.object(self.pm, "current_level", "Lv.1"), _quiet():
            data = self._post(good)
        self.assertIn("Lv.3", data["reply"])   # 等级门拒绝
        with mock.patch.object(self.pm, "current_level", "Lv.3"), _quiet():
            data = self._post("/gen_log 不是链接")
        self.assertIn("分享链接", data["reply"])   # 格式门
        fake = types.ModuleType("run_link_log")
        fake.run_link_log = mock.MagicMock()
        with mock.patch.object(self.pm, "current_level", "Lv.3"), \
             mock.patch.dict(sys.modules, {"run_link_log": fake}), \
             _quiet():
            data = self._post(good)
        self.assertIn("后台", data["reply"])   # 受理（后台线程跑 fake）
        self.assertEqual(data["source"], "⚙️ 系统")
        time.sleep(0.2)   # 让 daemon 线程跑完 fake，避免 patch 退出后竞态

    # ---------- 回归与一致性 ----------
    def test_unmatched_slash_still_goes_to_llm(self):
        """回归锚：未命中斜杠仍走 LLM（拦截不吞正常对话）。"""
        with mock.patch.object(dashboard, "smart_ask") as ms, _quiet():
            ms.return_value = ("模型回复", "🏠 本地")
            resp = self.client.post("/api/chat",
                                    json={"message": "/not_a_command"})
        self.assertEqual(resp.get_json()["data"]["reply"], "模型回复")
        ms.assert_called_once_with("/not_a_command", [])

    def test_wiring_set_subset_of_main_dispatch(self):
        """清单一致性锚：控制台拦截集 ⊆ main 分发集（防平行清单漂移）；
        /send_image 永久排除（QQ 专属）。"""
        src_path = os.path.join(PROJECT_ROOT, "xiaoju3_dashboard.py")
        with open(src_path, encoding="utf-8") as f:
            dash_src = f.read()
        main_path = os.path.join(PROJECT_ROOT, "main.py")
        with open(main_path, encoding="utf-8") as f:
            main_src = f.read()
        wired = ["/clear", "/name", "/reset_fuse", "/register",
                 "/coder_auth", "/sudo", "/lv4_auth", "/lv4_revoke",
                 "/soul_export", "/soul_import", "/gen_log"]
        for cmd in wired:
            self.assertIn(cmd, dash_src, f"控制台拦截缺 {cmd}")
            self.assertIn(cmd, main_src, f"main 分发缺 {cmd}")
        # /send_image 永久排除（QQ 专属）：无分发分支（注释提及不受限）
        self.assertNotIn('startswith("/send_image")', dash_src)

    def test_chat_empty_message_rejected(self):
        """空消息：业务码 400 + 中文错误提示（参考口径：HTTP 200、body 携带 code）。"""
        with _quiet():
            resp = self.client.post("/api/chat", json={"message": ""})
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["code"], 400)
        self.assertEqual(payload["error"], "消息不能为空")

    def test_chat_missing_body_rejected(self):
        """无 JSON 体：同样业务码 400，不 500。"""
        with _quiet():
            resp = self.client.post("/api/chat")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["code"], 400)

    def test_chat_get_not_allowed(self):
        """/api/chat 仅 POST：GET 返回 405。"""
        resp = self.client.get("/api/chat")
        self.assertEqual(resp.status_code, 405)

    def test_chat_brain_exception_returns_500(self):
        """smart_ask 抛异常：500 + 错误结构。"""
        with mock.patch.object(dashboard, "smart_ask",
                               side_effect=RuntimeError("brain boom")), _quiet():
            resp = self.client.post("/api/chat", json={"message": "hi"})

        self.assertEqual(resp.status_code, 500)
        payload = resp.get_json()
        self.assertEqual(payload["code"], 500)
        self.assertIn("brain boom", payload["error"])


# ---------------------------------------------------------------------------
# QQ 接入层 webhook（原 :5002 POST /onebot，2026-10-01 架构合并宿主 :5003）
# ---------------------------------------------------------------------------

class OnebotWebhookMigratedBase(unittest.TestCase):
    """/onebot 迁移路由夹具：main 业务模块状态注入 tmp 目录（同 test_main 口径，
    不触碰真实 agent_state），大脑与 NapCat 网络 mock，结束自动还原。"""

    def setUp(self):
        self.client = dashboard.app.test_client()
        tmp = tempfile.TemporaryDirectory()
        self.tmp = tmp.name
        self.addCleanup(tmp.cleanup)
        state_dir = os.path.join(self.tmp, "state")
        self.smart_ask = mock.MagicMock(return_value=("测试回复", "🏠 本地"))
        self.napcat = mock.MagicMock()
        state_manager = StateManager(state_dir)

        for target, value in [
            ("main.smart_ask", self.smart_ask),
            ("main.requests", self.napcat),
            ("main.MEMORY_FILE_WEB", os.path.join(state_dir, "history_web.json")),
            ("main.MEMORY_FILE_QQ", os.path.join(state_dir, "history_qq.json")),
            ("main.messages_web", [main.SYSTEM_PROMPT]),
            ("main.messages_qq", [main.SYSTEM_PROMPT]),
            ("main.state_manager", state_manager),
            ("tools.RECENT_ACTIONS_FILE", os.path.join(self.tmp, "recent_actions.json")),
        ]:
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        # meta_event 心跳线程标记防御性清理（与 test_status_temp_logging 同口径）
        self.addCleanup(dashboard._onebot_meta_local.__dict__.pop,
                        "is_meta_event", None)

    def onebot(self, payload):
        return self.client.post("/onebot", json=payload)

    def napcat_payload(self):
        return self.napcat.post.call_args[1]["json"]


class OnebotWebhookMigratedTests(OnebotWebhookMigratedBase):
    """POST /onebot 迁移路由行为断言（与 5002 时代逐字一致，零变化口径）：
    webhook 数据结构 / think 剥离 / 触发词 / 戳一戳 / meta_event 心跳标记 /
    LLOneBot 兼容容错。"""

    def test_private_message_full_chain(self):
        """私聊：webhook → main.onebot_event → smart_ask → NapCat 回发。"""
        with _quiet():
            resp = self.onebot({
                "post_type": "message", "message_type": "private",
                "self_id": "10000", "sender": {"user_id": 123},
                "raw_message": "你好",
            })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_called_once()
        self.napcat.post.assert_called_once()
        self.assertEqual(self.napcat.post.call_args[0][0],
                         f"{main.ONEBOT_API_URL}/send_private_msg")
        payload = self.napcat_payload()
        self.assertEqual(payload["user_id"], 123)
        self.assertEqual(payload["message"], "测试回复")

    def test_group_trigger_word_routes_to_group(self):
        """群聊触发词：回发 send_group_msg 且携带 group_id。"""
        with _quiet():
            resp = self.onebot({
                "post_type": "message", "message_type": "group",
                "self_id": "10000", "group_id": 456, "sender": {"user_id": 123},
                "raw_message": "小橘 帮我看看",
            })
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_called_once()
        self.assertEqual(self.napcat.post.call_args[0][0],
                         f"{main.ONEBOT_API_URL}/send_group_msg")
        self.assertEqual(self.napcat_payload()["group_id"], 456)

    def test_group_without_trigger_ignored(self):
        """群聊无触发词 / 非 @：不打扰大脑、不回发（防刷屏）。"""
        with _quiet():
            resp = self.onebot({
                "post_type": "message", "message_type": "group",
                "self_id": "10000", "group_id": 456, "sender": {"user_id": 123},
                "raw_message": "今天天气不错",
            })
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_not_called()
        self.napcat.post.assert_not_called()

    def test_reply_think_block_stripped_before_send(self):
        """think 剥离：QQ 回复发送前剥除 <think> 块（CQ 码不受影响）。"""
        self.smart_ask.return_value = (
            "<think>[思考] 先查设备再开灯。</think>已为你打开卧室灯💡", "🏠 本地")
        with _quiet():
            self.onebot({
                "post_type": "message", "message_type": "private",
                "self_id": "10000", "sender": {"user_id": 123},
                "raw_message": "开灯",
            })
        self.assertNotIn("<think>", self.napcat_payload()["message"])
        self.assertEqual(self.napcat_payload()["message"], "已为你打开卧室灯💡")

    def test_poke_easter_egg(self):
        """戳一戳彩蛋：不进大脑，直接回发彩蛋文案。"""
        with _quiet():
            resp = self.onebot({
                "post_type": "notice", "notice_type": "poke",
                "group_id": 456, "user_id": 123,
            })
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.napcat.post.assert_called_once()
        self.assertEqual(self.napcat_payload()["message"], "别戳啦，好痒！😆")
        self.smart_ask.assert_not_called()

    def test_meta_event_marks_thread_and_ignored(self):
        """meta_event 心跳：打一次性线程标记（访问日志拦截用）、不进大脑。"""
        with _quiet():
            resp = self.onebot({"post_type": "meta_event",
                                "meta_event_type": "heartbeat"})
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.assertTrue(dashboard._onebot_meta_local.is_meta_event)
        self.smart_ask.assert_not_called()
        self.napcat.post.assert_not_called()

    def test_corrupted_fields_return_ok_without_crash(self):
        """字段损坏（sender 非字典）：不崩，统一返回 ok（LLOneBot 容错）。"""
        with _quiet():
            resp = self.onebot({
                "post_type": "message", "message_type": "private",
                "sender": 12345, "raw_message": "你好",
            })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok", "retcode": 0})
        self.smart_ask.assert_not_called()

    def test_health_endpoint_hosted_on_5003(self):
        """GET /api/health（原 :5002 端点）随架构合并迁入 :5003 可用。"""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["device"])


# ---------------------------------------------------------------------------
# 旧版页与新版控制台托管
# ---------------------------------------------------------------------------

class ServingTests(unittest.TestCase):
    """GET / 旧版蓝色单页与 /console 新版控制台静态托管。"""

    def setUp(self):
        self.client = dashboard.app.test_client()

    def test_legacy_index_renders(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("系统监控", html)
        self.assertIn("运行时长", html)
        self.assertIn("我是小橘3号", html)
        # 已知问题修复断言：旧版页改读嵌套字段，不再读取 data.temp/data.uptime
        self.assertIn("d.temperature", html)
        self.assertIn("BOOT_TS", html)
        self.assertNotIn("data.uptime", html)
        self.assertNotIn("data.temp.", html)

    def test_console_page_with_key_tokens(self):
        resp = self.client.get("/console")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("#203170", html)
        self.assertIn("你好！我是小橘3号，很高兴为你服务喵~", html)

    def test_console_static_scripts(self):
        for path in ("/console/console.js", "/console/desktop-pet.js"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)  # werkzeug 读文件句柄告警
                resp = self.client.get(path)
            self.assertEqual(resp.status_code, 200, path)

    def test_console_loads_desktop_pet(self):
        """桌宠完整形态回归（2026-10-02）：/console 页面重新挂载
        desktop-pet.js（2026-10-01 曾注释停载；2026-10-03 口径=最小化桌宠
        缩球，控制台永不缩；script 带 mtime 防缓存 ?v= 参数，与 console.js
        同机制）。"""
        resp = self.client.get("/console")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertRegex(
            html, r'<script src="/console/desktop-pet\.js(\?v=\d+)"></script>')
        self.assertNotIn("<!-- <script src=\"/console/desktop-pet.js\">", html)

    def test_mascot_asset_served(self):
        """素材已补齐：/assets/DSniang1.jpg 可达（修复界面文档 §5.1 的 404 已知问题）。"""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            resp = self.client.get("/assets/DSniang1.jpg")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_data())                       # 内容非空
        self.assertIn("image", resp.headers.get("Content-Type", ""))

    def test_missing_static_asset_returns_404(self):
        """不存在的静态资源 404。"""
        resp = self.client.get("/console/__no_such_file__.js")
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# 前端三件套静态断言（直接读文件内容）
# ---------------------------------------------------------------------------

class FrontendStaticTests(unittest.TestCase):
    """前端行为以文件内容静态断言（无浏览器，离线可跑）。"""

    @classmethod
    def setUpClass(cls):
        def _read(name):
            with open(os.path.join(PROJECT_ROOT, name), "r", encoding="utf-8") as f:
                return f.read()
        cls.index_html = _read("index.html")
        cls.console_js = _read("console.js")
        cls.pet_js = _read("desktop-pet.js")

    def test_index_has_no_external_cdn(self):
        html = self.index_html.lower()
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("src='//", html)

    def test_index_design_tokens(self):
        """令牌表重构为 :root CSS 变量（界面 §1.3 → §10.1 皮肤系统基础），
        默认主题保持深蓝 #203170 不变。"""
        html = self.index_html
        tokens = (
            ":root",                             # CSS 变量令牌表
            "--color-primary: #203170",          # 主色（默认深蓝，保持不变）
            "--color-primary-hover: #2f4488",    # 主色悬停
            "--color-bg: #f4f6f9", "--color-bg-chat: #f9fbfe",   # 页面底色分层
            "--color-success: #2fa24c",          # 进度条正常态
            "--color-danger: #e0433f",           # 警示色
            "--color-like: #ef4444", "--color-like-bg: #fef2f2", # 点赞激活
            "--color-dislike: #3b82f6", "--color-dislike-bg: #eff6ff",  # 点踩激活
            "--radius-bubble: 10px",             # 气泡圆角令牌
            "--shadow-sidebar: 2px 0 10px rgba(0,0,0,0.02)",     # 侧栏单向阴影
            "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif",   # 全局字体栈
            "width: 33.33%", "min-width: 300px", # 双栏骨架
            "100vh",                             # 无页面滚动
            "你好！我是小橘3号，很高兴为你服务喵~",   # 欢迎语
            "onkeypress",                        # 回车发送
            ".xiaoju-root",                      # 桌宠（运行时自建节点，缩球隐藏规则锚）
        )
        for token in tokens:
            self.assertIn(token, html)

    def test_index_orange_theme(self):
        """橘色主题（界面 §10.1）：data-theme="orange" 全套变量成体系，
        右上角主题切换按钮 + localStorage 记忆（记忆逻辑在 console.js）。"""
        html = self.index_html
        self.assertIn('[data-theme="orange"]', html)          # 属性选择器
        orange_tokens = (
            "--color-primary: #d96f2b",      # 主色·暖橘（狐毛同源）
            "--color-primary-hover: #e8853f",
            "--color-bg: #fdf6ee",
            "--color-card: #fffdf9",
            "--color-border: #f0e0cb",
            "--color-text-secondary: #a9683a",
            "--color-progress-track: #f7ebdb",
            "--color-danger: #e0433f",       # 警示色成体系保留
        )
        for token in orange_tokens:
            self.assertIn(token, html)
        self.assertIn("theme-toggle", html)  # 主题切换按钮挂载点

    def test_index_mobile_responsive(self):
        """移动端适配（界面 §7）：viewport meta + ≤768px 断点单栏折叠
        （监控侧栏收为可展开抽屉）。"""
        html = self.index_html
        self.assertIn('name="viewport"', html)                # viewport meta
        self.assertIn("initial-scale=1.0", html)
        self.assertIn("@media (max-width: 768px)", html)      # 移动端断点
        self.assertIn("sidebar-toggle", html)                 # 抽屉开关按钮
        self.assertIn("translateX(-105%)", html)              # 抽屉收起态
        self.assertIn(".sidebar.open", html)                  # 抽屉展开态
        # 输入区窄屏可用：不因 min-width 挤压
        self.assertIn("font-size: 16px", html)                # 防 iOS 聚焦放大

    def test_index_card_and_toast(self):
        """MAA 风格卡片化（令牌化圆角+轻阴影）与 toast 提示挂载点。"""
        html = self.index_html
        for token in ("--radius-card", "--shadow-card",
                      "header-actions", "xiaoju3-toast"):
            self.assertIn(token, html)

    def test_console_js_polling_and_threshold(self):
        js = self.console_js
        self.assertIn("setInterval(fetchStatus, 2000)", js)   # 2 秒轮询
        # 尾巴 H：三档阈值常量（CPU/内存各自独立 applyBar）
        self.assertIn("const BAR_THRESHOLDS = { mid: 60, high: 85 };", js)
        self.assertIn("applyBar(cpuBar, d.cpu)", js)
        self.assertIn("applyBar(memBar, d.memory)", js)
        self.assertIn("'#e0433f'", js)                        # 高档红
        self.assertIn("'#2fa24c'", js)                        # 低档绿
        self.assertIn("fetchStatus();", js)                   # 加载即请求一次
        # 聊天行为
        self.assertIn("小橘3号正在思考... 🧠", js)             # 占位气泡
        self.assertIn("speechSynthesis", js)                  # TTS
        self.assertIn("speechSynthesis.cancel()", js)         # 清队列后朗读
        self.assertIn("navigator.clipboard", js)              # 剪贴板复制
        self.assertIn("已复制", js)
        self.assertIn("active-like", js)                      # 点赞/点踩互斥
        self.assertIn("active-dislike", js)
        self.assertIn("source-badge", js)                     # 大脑来源徽标
        self.assertIn("res.data.source", js)                  # 消费 source 字段

    def test_console_js_history_load(self):
        """聊天历史持久化前端侧（功能文档 §12 / 界面 §10.4 近期项）。"""
        js = self.console_js
        self.assertIn("loadHistory", js)                      # 页面加载拉取历史
        self.assertIn("'/api/history'", js)                   # 历史接口
        self.assertIn("res.data.messages", js)                # 渲染 messages
        self.assertIn("method: 'DELETE'", js)                 # 清空历史（带确认）
        self.assertIn("confirm(", js)                         # 确认语义

    def test_console_js_refresh_forward_implemented(self):
        """刷新/转发按钮实装（界面 §4.2）：移除 alert 占位。"""
        js = self.console_js
        # 刷新：对触发该回复的原消息重新 POST /api/chat 并替换当前回复气泡
        self.assertIn("refreshMsg", js)
        self.assertIn("dataset.prompt", js)                   # 记录原消息
        self.assertIn("正在重新生成", js)                      # 刷新占位
        # 转发：剪贴板复制全文并提示可粘贴转发
        self.assertIn("forwardMsg", js)
        self.assertIn("可粘贴转发", js)
        # 移除 alert("开发中") 占位（整个文件不再使用 alert）
        self.assertNotIn("开发中", js)
        self.assertNotIn("alert(", js)
        # toast 轻提示与 XSS 转义（界面 §4.4/§10.4 近期项）
        self.assertIn("showToast", js)
        self.assertIn("escapeHtml", js)

    def test_console_js_theme_and_sound(self):
        """主题切换（localStorage 记忆）与回复到达提示音接线。"""
        js = self.console_js
        self.assertIn("xiaoju3_theme", js)                    # 主题记忆键
        self.assertIn("data-theme", js)                       # 橘色主题切换
        self.assertIn("xiaoju3Sound", js)                     # 桌宠音效引擎
        self.assertIn("ding()", js)                           # 回复到达提示音
        self.assertIn("sound-toggle", js)                     # 音效总开关按钮

    def test_desktop_pet_specs(self):
        js = self.pet_js
        self.assertIn("window.__xiaoju3Pet", js)              # IIFE 单例防重复注入
        self.assertIn("250px * var(--pet-scale)", js)         # 250px 基准缩放
        self.assertIn("scaleY(0.88) scaleX(1.05)", js)        # 按压形变
        self.assertIn("cubic-bezier(.34,1.56,.64,1)", js)     # 0.22s 回弹曲线
        self.assertIn("setPointerCapture", js)                # Pointer Events 拖拽
        self.assertIn("dx * dx + dy * dy > 9", js)            # 拖拽阈值（位移平方）
        self.assertIn("chat-area", js)                        # 左界：聊天区左缘
        self.assertIn("chat-input-area", js)                  # 下界：输入区上沿
        self.assertIn("window.addEventListener('resize'", js) # resize 重钳制
        self.assertIn("5000", js)                             # 气泡 5s 自动关闭
        self.assertIn("60000", js)                            # 余额 60s 轮询
        self.assertIn("今日已用", js)                          # 气泡含今日已用
        self.assertIn("5003", js)                             # 报错端口写 5003
        self.assertNotIn("5005", js)                          # 不含参考的 5005 笔误

    def test_desktop_pet_real_asset(self):
        """真实素材挂载（界面 §5.1 的 404 已知问题修复）。"""
        js = self.pet_js
        self.assertIn("/assets/DSniang1.jpg", js)             # 官方素材图
        self.assertNotIn("DSniang1.png", js)                  # 不再引用不存在的 png
        self.assertIn("xiaoju-overlay", js)                   # 素材气泡区文字覆盖层
        self.assertIn("img-ok", js)                           # 素材可用性检测
        self.assertIn("xiaoju-pop", js)                       # SVG 兜底气泡保留

    def test_desktop_pet_flip(self):
        """左右翻转（界面 §5.2）：拖拽方向决定面向，scaleX(-1) 镜像。"""
        js = self.pet_js
        self.assertIn("scaleX(-1)", js)                       # 镜像切换
        self.assertIn("facing-right", js)                     # 面向状态类
        self.assertIn("facing", js)                           # 面向变量（拖拽方向决定）
        self.assertIn("xiaoju-flip", js)                      # 独立翻转层（与按压形变分离）

    def test_desktop_pet_edge_snap(self):
        """边缘吸附（界面 §5.2）：松手后距屏幕左/右边缘 < 24px 磁吸贴边。"""
        js = self.pet_js
        self.assertIn("SNAP_THRESHOLD = 24", js)              # 吸附阈值 24px
        self.assertIn("snapToEdge", js)                       # 吸附逻辑

    def test_desktop_pet_random_lines(self):
        """随机台词气泡（界面 §5.3/§10.2）：内置 8-12 条中文台词，与余额轮换。"""
        js = self.pet_js
        self.assertIn("PET_LINES", js)                        # 台词库常量
        start = js.index("const PET_LINES = [")
        block = js[start:js.index("];", start)]
        count = block.count("',")                             # 每行台词以 ', 结尾
        self.assertGreaterEqual(count, 8)                     # 台词库 ≥ 8 条
        self.assertLessEqual(count, 12)                       # 台词库 ≤ 12 条
        self.assertIn("bubbleTurn", js)                       # 轮换计数

    def test_desktop_pet_sound_and_mobile_scale(self):
        """音效（界面 §6.2）与移动端缩放（界面 §7）。"""
        js = self.pet_js
        self.assertIn("AudioContext", js)                     # WebAudio 程序合成
        self.assertIn("webkitAudioContext", js)               # 兼容前缀 + 静默降级
        self.assertIn("xiaoju3_sound", js)                    # 总开关 localStorage 记忆
        self.assertIn("createOscillator", js)                 # 零外部音频文件（程序合成）
        self.assertIn("vw < 600", js)                         # 视口 <600px 缩放
        self.assertIn("--pet-scale", js)                      # 复用 --pet-scale 机制




class CQFaceRenderTests(unittest.TestCase):
    """console.js 的 [CQ:face,id=XX] Emoji 渲染与 CQ 码兜底（静态断言）。"""

    def setUp(self):
        with open("console.js", "r", encoding="utf-8") as f:
            self.content = f.read()

    def test_cq_face_mapper_present(self):
        self.assertIn("CQ_FACE_EMOJI", self.content)
        self.assertIn("[CQ:face,id=", self.content)

    def test_render_rich_applies_cq_mapping(self):
        self.assertIn("renderCQFace(escapeHtml(text))", self.content)

    def test_all_bot_paths_go_through_render_rich(self):
        """实时回复 / /api/history 历史加载 / 刷新重生成：三条机器人渲染
        路径全部经 appendBotMessage→renderRich→renderCQFace（历史回放与
        实时发送共用同一个气泡入口）；刷新重生成先剥离 <think> 再渲染。"""
        self.assertIn("renderRich(reply)", self.content)              # 气泡正文（think 已剥离）
        self.assertIn("const reply = thinkParts.body", self.content)  # 刷新重生成先剥离 think
        self.assertIn("appendBotMessage(m.content, m.source || '', lastUser",
                      self.content)                                 # 历史回放同入口

    def test_face_mapping_covers_full_classic_range(self):
        """经典表情 id 0-103 全量收录 + 既有扩展 id（109/124/129/144/146），
        常用 20 偷笑 / 34 晕 / 49 委屈等不再漏出方括号原文。"""
        start = self.content.index("const CQ_FACE_EMOJI")
        block = self.content[start:self.content.index("};", start)]
        ids = {int(m) for m in re.findall(r"(\d+):\s*'[^']*'", block)}
        missing = sorted(set(range(104)) - ids)
        self.assertEqual(missing, [], msg="经典 0-103 存在缺号")
        for extra in (109, 124, 129, 144, 146):
            self.assertIn(extra, ids)

    def test_unknown_face_falls_back_not_verbatim(self):
        """未收录 id 兜底通用表情 😊，不再原样保留方括号原文
        （旧'未收录原样保留'断言口径随本次修复废止）。"""
        self.assertIn("CQ_FACE_FALLBACK", self.content)
        self.assertNotIn(": m;", self.content)      # 旧实现未命中 return m

    def test_non_face_cq_codes_sanitized(self):
        """非 face CQ 码前端同样兜底：image→[表情] 占位，其余剥除
        （与后端 web_sanitize 同口径，双保险）。"""
        self.assertIn("[表情]", self.content)
        self.assertIn(r"/\[CQ:image,[^\]]*\]/g", self.content)
        self.assertIn(r"/\[CQ:[^\]]*\]/g", self.content)


# ---------------------------------------------------------------------------
# 思维链（<think> 块）前端展示：折叠卡片 + 逐字打字 + 等待期轮换状态
# ---------------------------------------------------------------------------

class ThinkCardFrontendTests(unittest.TestCase):
    """console.js / index.html 思维链展示静态断言（离线，无浏览器）。

    契约（2026-10-01 全对话强制包装口径）：brain.smart_ask 对所有自然语言
    回复一律在 reply 最前面包装 <think>...</think> 块——工具流程用原生
    [思考]/[计划] 或按工具名生成的占位符，普通闲聊（无工具调用）注入
    "[思考] 正在理解你的意图..."默认占位符；前端裸标记扫描保留作纵深
    防御——万一仍有旁路/旧版后端漏出裸 [思考]/[计划]/[行动] 文本，统一
    入口 splitThinkBlock 对两种形态（<think> 包装 / 裸标记）都剥离并收敛
    到同一张折叠卡片，[行动] 行与其后的 JSON 不上屏；渲染入口仅由
    think !== null 守卫，正文为自然语言或占位符都出卡。
    """

    @classmethod
    def setUpClass(cls):
        def _read(name):
            with open(os.path.join(PROJECT_ROOT, name), "r", encoding="utf-8") as f:
                return f.read()
        cls.console_js = _read("console.js")
        cls.index_html = _read("index.html")

    # ---------- console.js：<think> 解析与切分 ----------

    def test_think_parse_regex_present(self):
        """console.js 含 <think> 块解析正则、切分函数与 thinkMatch 判定。"""
        js = self.console_js
        self.assertIn("<think>", js)                      # 解析正则
        self.assertIn("splitThinkBlock", js)              # 切分函数
        self.assertIn("thinkMatch", js)                   # 渲染入口先判 thinkMatch

    def test_think_block_regex_non_anchored(self):
        """解析正则非锚定（串内任意位置命中）：即使净化/表情转换等环节在块前
        插入了任何字符，只要 reply 含 <think> 块就必定渲染思考卡片，不因锚定
        串首而静默漏卡；剔除按 thinkMatch.index 循环定位（多块全收），用户
        口径：正文只保留最后一个 </think> 之后的部分，块前杂散字符丢弃。"""
        js = self.console_js
        self.assertIn("/<think>([\\s\\S]*?)<\\/think>/", js)   # 非锚定正则
        self.assertNotIn("/^\\s*<think>", js)                  # 不再锚定串首
        self.assertIn("thinkMatch.index", js)                  # 按命中位置剔块
        # 用户口径锁定：循环剔块（多个 <think> 块并入同一张卡）；
        # 正文 = 最后一个 </think> 之后的部分；旧"块前字符保留进正文"已废止
        self.assertIn("while ((thinkMatch = body.match(THINK_BLOCK_RE)) !== null)", js)
        self.assertIn("body = body.slice(thinkMatch.index + thinkMatch[0].length)", js)
        self.assertNotIn("body.slice(0, thinkMatch.index)", js)

    def test_simple_text_reply_card_rendering_contract(self):
        """简单文本 reply（如 "<think>[思考] 准备调用 list_files 尝试完成操作。
        </think>文件列表…"）必出卡片的渲染契约：三条机器人渲染路径全部
        以 think !== null 守卫插卡——实时回复（appendBotMessage 渲染入口）、
        历史回放（同入口、animateThink=false）、刷新重生成（syncThinkCard）。"""
        js = self.console_js
        self.assertIn("splitThinkBlock(rawReply)", js)                 # 先切分
        self.assertIn("if (thinkParts.think !== null)", js)            # 实时路径守卫
        self.assertIn("syncThinkCard(msgEl, thinkParts.think)", js)    # 刷新路径同步
        self.assertIn("if (thinkText === null) return;", js)           # 刷新无块不插卡
        self.assertIn("appendBotMessage(m.content, m.source || '', lastUser",
                      js)                                              # 历史回放同入口

    def test_card_render_guarded_by_think_match(self):
        """无 <think> 块不插卡片（默认不渲染）：appendBotMessage 渲染入口
        先在原始 reply 上切分，卡片构建调用位于 thinkMatch 守卫之内。"""
        js = self.console_js
        start = js.index("function appendBotMessage")
        end = js.index("==================== 3.", start)   # 函数体到下一节为止
        body = js[start:end]
        self.assertIn("splitThinkBlock(rawReply)", body)       # 先在原始 reply 上切分
        self.assertIn("if (thinkParts.think !== null)", body)  # 渲染入口守卫
        guard = body.index("if (thinkParts.think !== null)")
        self.assertLess(guard, body.index("buildThinkCardEl()"))  # 守卫先于插卡
        self.assertIn("options.animateThink !== false", body)  # 历史回放可关打字

    def test_history_replay_no_typing(self):
        """历史回放共用 appendBotMessage 入口，但不打字（animateThink=false）。"""
        self.assertIn(
            "appendBotMessage(m.content, m.source || '', lastUser, { animateThink: false })",
            self.console_js)

    # ---------- console.js：打字机与折叠 ----------

    def test_typewriter_and_auto_collapse(self):
        """思考正文逐字打字（textContent 注入防注入），打完自动折叠、
        点击标题可再展开/收起。"""
        js = self.console_js
        self.assertIn("startThinkTypewriter", js)                     # 打字函数
        self.assertIn("THINK_TYPE_MS", js)                            # 打字间隔常量
        self.assertIn("body.textContent = text.slice(0, shown)", js)  # textContent 注入
        self.assertIn("renderCQFace(thinkText)", js)                  # 思考正文同口径净化
        self.assertIn("classList.add('think-collapsed')", js)         # 打完自动折叠
        self.assertIn("window.toggleThinkCard", js)                   # 点击标题展开/收起
        self.assertIn("classList.toggle('think-collapsed')", js)

    def test_refresh_regenerate_syncs_think_card(self):
        """刷新重生成同样先切分 <think>：卡片同步 + 正文剥离后再渲染。"""
        js = self.console_js
        start = js.index("window.refreshMsg")
        end = js.index("window.forwardMsg", start)
        body = js[start:end]
        self.assertIn("splitThinkBlock(res.data.reply)", body)
        self.assertIn("syncThinkCard(msgEl, thinkParts.think)", body)
        self.assertIn("renderRich(reply)", body)

    # ---------- 裸 [思考]/[计划] 标记扫描（正文剥离兜底） ----------

    def test_bare_marker_scan_regexes_present(self):
        """splitThinkBlock 含裸 [思考]/[计划] 段扫描正则与 [行动] 剥离正则：
        后端 _seal_bare_cot 已对"捕获到原生思考的普通回复"封口包装，前端
        裸标记扫描保留作纵深防御——万一仍有旁路/旧版后端漏出裸 CoT，
        裸标记同样收敛进思考卡（解析失败宁可隐藏裸文本）。"""
        js = self.console_js
        self.assertIn("BARE_THINK_RE", js)
        self.assertIn("BARE_PLAN_RE", js)
        self.assertIn("BARE_ACTION_RE", js)
        # 任务规格正则（非锚定、前瞻零消费）：[思考] 段止于 [计划]/[行动]/
        # 串尾，[计划] 段止于 [行动]/串尾——标记本身留给下一段/[行动] 剥离
        self.assertIn(r"/(\[思考\][\s\S]*?)(?=\[行动\]|\[计划\]|$)/", js)
        self.assertIn(r"/(\[计划\][\s\S]*?)(?=\[行动\]|$)/", js)

    def test_bare_scan_lives_in_split_think_block(self):
        """裸标记扫描位于统一入口 splitThinkBlock 内（实时回复/历史回放/
        刷新重生成三条渲染路径共用）：思考段→计划段 replace 剥离并
        bareParts 并卡，[行动] 行剥离与剥空占位依次发生。"""
        start = self.console_js.index("function splitThinkBlock")
        end = self.console_js.index("function buildThinkCardEl", start)
        body = self.console_js[start:end]
        self.assertIn("body.replace(BARE_THINK_RE", body)
        self.assertIn("body.replace(BARE_PLAN_RE", body)
        self.assertIn("bareParts.push", body)
        self.assertIn("bareParts.join('\\n')", body)   # 裸段并入思考卡内容
        self.assertIn("body.replace(BARE_ACTION_RE", body)
        self.assertIn("（操作已执行）", body)           # 剥空占位文案
        # 剥离顺序：思考段 → 计划段 → 行动行 → 返回
        self.assertLess(body.index("body.replace(BARE_THINK_RE"),
                        body.index("body.replace(BARE_PLAN_RE"))
        self.assertLess(body.index("body.replace(BARE_PLAN_RE"),
                        body.index("body.replace(BARE_ACTION_RE"))
        self.assertLess(body.index("body.replace(BARE_ACTION_RE"),
                        body.index("return { think: think, body: body }"))

    def _extract_js_regex(self, name):
        """从 console.js 源码提取具名 JS 正则字面量并编译为 Python re
        （所选正则语法为 JS/Python 公共子集，可直接编译复跑）。"""
        m = re.search(re.escape(name) + r"\s*=\s*/(.+)/;", self.console_js)
        self.assertIsNotNone(m, msg="console.js 缺少 %s 正则" % name)
        return re.compile(m.group(1))

    def _bare_strip_pipeline(self, body):
        """按 splitThinkBlock 的剥离顺序（思考段→计划段→行动行）复跑源码中
        同一组正则，返回（并入思考卡的裸段列表, 剥离后正文）。"""
        bare_think = self._extract_js_regex("BARE_THINK_RE")
        bare_plan = self._extract_js_regex("BARE_PLAN_RE")
        bare_action = self._extract_js_regex("BARE_ACTION_RE")
        parts = []

        def _collect(match):
            seg = (match.group(1) or "").strip()
            if seg:
                parts.append(seg)
            return ""

        body = bare_think.sub(_collect, body)
        body = bare_plan.sub(_collect, body)
        body = bare_action.sub("", body).strip()
        return parts, body

    def test_bare_cot_stripped_and_action_json_hidden(self):
        """正文剥离行为（用源码同一组正则复跑锁定）：裸 CoT 全漏场景——
        [思考]/[计划] 段并入思考卡并从正文剥离；[行动] 标记与其后的
        JSON 工具调用原文一并剥离（JSON 不上屏也不进思考卡）；
        剥离后正文为空 → 前端显示"（操作已执行）"占位。"""
        parts, body = self._bare_strip_pipeline(
            "[思考] 需要点击WLAN，先UI解析，失败用视觉.\n"
            "[计划] 1. UI解析 2. 失败用视觉\n"
            '[行动] {"tool": "ui_tap_element", "args": {"text": "WLAN"}}')
        self.assertEqual(len(parts), 2)
        self.assertTrue(parts[0].startswith("[思考]"))
        self.assertTrue(parts[1].startswith("[计划]"))
        self.assertNotIn('"tool"', "\n".join(parts))   # JSON 不进思考卡
        self.assertEqual(body, "")                     # 剥空 → 占位文案
        # 其后有最终自然语言回复时：正文只留该回复，[行动] 后的 JSON 不显示
        parts, body = self._bare_strip_pipeline(
            "[思考] a\n[计划] b\n"
            '[行动] {"tool": "list_files", "args": {"path": "."}}\n'
            "好的，文件列表已经拿到啦~")
        self.assertEqual(len(parts), 2)
        self.assertEqual(body, "好的，文件列表已经拿到啦~")
        self.assertNotIn("list_files", body)
        self.assertNotIn('"tool"', body)

    def test_bare_cot_bluetooth_scenario_convergence(self):
        """用户实测场景（"帮我点击手机屏幕上的蓝牙"旁路漏出形态）复跑锁定：
        全裸 [思考]/[计划]/[行动]+JSON、无自然语言收尾——思考/计划两段并入
        思考卡、[行动] 行与其后 JSON 不上屏也不进卡、正文剥空 → 前端显示
        "（操作已执行）"占位，绝不裸漏过程原文。"""
        parts, body = self._bare_strip_pipeline(
            "[思考] 主人要点击蓝牙，先定位设置入口。\n"
            "[计划] 1. UI解析找蓝牙 2. 失败转视觉点击\n"
            '[行动] {"tool": "ui_tap_element", "args": {"text": "蓝牙"}}')
        self.assertEqual(len(parts), 2)
        self.assertTrue(parts[0].startswith("[思考]"))
        self.assertIn("蓝牙", parts[0])
        self.assertTrue(parts[1].startswith("[计划]"))
        joined = "\n".join(parts)
        self.assertNotIn('"tool"', joined)          # JSON 不进思考卡
        self.assertNotIn("ui_tap_element", joined)
        self.assertEqual(body, "")                  # 剥空 → 占位文案兜底

    def test_bare_cot_with_braces_in_think_convergence(self):
        """[思考] 文本含花括号（后端按 { 边界截断思考，剥不干净的残余）时的
        收敛：段落照常剥离并入卡、[行动]+JSON 不上屏、剩余自然语言正文
        原样保留。"""
        parts, body = self._bare_strip_pipeline(
            "[思考] 先看 {配置} 再决定。\n"
            '[行动] {"tool": "read_file", "args": {"filename": "a.json"}}\n'
            "文件已经读好啦")
        self.assertEqual(len(parts), 1)
        self.assertIn("{配置}", parts[0])
        self.assertNotIn("read_file", body)
        self.assertNotIn('"tool"', body)
        self.assertEqual(body, "文件已经读好啦")

    def test_seal_placeholder_literal_matches_backend(self):
        """跨端占位契约：前端剥空占位字面量与后端 brain.
        BARE_COT_BODY_PLACEHOLDER 完全一致（后端封口剥空时注入同款占位，
        前端不得二次改写）。"""
        with open(os.path.join(PROJECT_ROOT, "brain.py"), "r",
                  encoding="utf-8") as f:
            src = f.read()
        m = re.search(r'BARE_COT_BODY_PLACEHOLDER\s*=\s*"([^"]+)"', src)
        self.assertIsNotNone(m, "brain.py 缺少 BARE_COT_BODY_PLACEHOLDER 常量")
        self.assertIn(m.group(1), self.console_js)

    def test_action_strip_placeholder_contract(self):
        """占位契约（代码结构级）：剥离后正文为空且确有过程输出被剥离
        （有思考卡或剥过 [行动]）时，正文显示"（操作已执行）"；
        普通空回复不受影响。"""
        js = self.console_js
        self.assertIn("const hadAction = BARE_ACTION_RE.test(body)", js)
        self.assertIn("if (!body && (think !== null || hadAction)) "
                      "body = '（操作已执行）';", js)

    # ---------- 用户点名场景（2026-10-01）：占位符正文 + <think> 块 → 卡片必显示 ----------

    def _extract_split_chunk(self):
        """提取 console.js 中 THINK_BLOCK_RE 声明起、打字机常量前的整段源码
        （含 THINK_BLOCK_RE 与裸标记正则、splitThinkBlock、buildThinkCardEl，
        剥离 IIFE 后可独立运行）。"""
        js = self.console_js
        start = js.index("const THINK_BLOCK_RE")
        end = js.index("const THINK_TYPE_MS")
        return js[start:end]

    def _think_wrap_pipeline(self, raw_reply):
        """按 splitThinkBlock 的 <think> 循环剔块 + 剥空占位规则，用源码里
        同一个 THINK_BLOCK_RE（JS/Python 公共子集，_extract_js_regex 可直接
        编译）在 Python 侧复跑，返回（think, body）——node 不可用时的
        离线等价验证。"""
        block_re = self._extract_js_regex("THINK_BLOCK_RE")
        think = None
        body = raw_reply
        m = block_re.search(body)
        while m:
            think = ((think + "\n") if think else "") + m.group(1).strip()
            body = body[m.end():]
            m = block_re.search(body)
        if think is not None and not body.strip():
            body = "（操作已执行）"
        return think, body

    def test_placeholder_body_with_think_block_card_must_render(self):
        """用户点名场景：reply 为"<think>块内容</think>（操作已执行）"形态
        （正文只剩占位符）时灰色思维链卡片必显示。三层断言：
        ① 渲染入口插卡仅由 think !== null 守卫，与正文是否为占位符无关
           （守卫与插卡之间不得出现占位符/空正文二次条件），且先构建完整
           卡片元素、再插入 DOM；
        ② Python 复跑 <think> 剔块管线：两种占位形态 think 都非空、
           body 都为占位符；
        ③ node 实跑验证见 test_placeholder_body_node_live_run。"""
        js = self.console_js
        start = js.index("function appendBotMessage")
        end = js.index("==================== 3.", start)
        body = js[start:end]
        self.assertIn("if (thinkParts.think !== null)", body)      # 唯一插卡守卫
        guard = body.index("if (thinkParts.think !== null)")
        build = body.index("buildThinkCardEl()")
        self.assertLess(guard, build)                              # 守卫先于插卡
        # 占位正文不得拦卡：守卫与插卡之间不得出现"正文为占位符/为空"类条件
        between = body[guard:build]
        self.assertNotIn("（操作已执行）", between)
        self.assertNotIn("!reply", between)
        # 先构建完整元素、再手工插入 DOM（F4 加固，不依赖 ChildNode.before()）：
        # 赋值给局部变量后用显式父引用 insertBefore 插到气泡正文上方
        self.assertIn("= buildThinkCardEl()", body)
        self.assertIn("parentEl.insertBefore(thinkCard, bubbleEl)", body)
        self.assertNotIn(".before(", body)
        # ② Python 复跑："<think>块内容</think>（操作已执行）"→ think 非空 + 占位正文
        think, body_text = self._think_wrap_pipeline(
            "<think>块内容</think>（操作已执行）")
        self.assertEqual(think, "块内容")
        self.assertEqual(body_text, "（操作已执行）")
        # 块后无任何正文的形态（剥空占位由前端注入）：think 同样非空
        think, body_text = self._think_wrap_pipeline("<think>有思考内容</think>")
        self.assertIsNotNone(think)
        self.assertTrue(think)
        self.assertEqual(body_text, "（操作已执行）")

    def test_placeholder_body_node_live_run(self):
        """node 实跑验证元素结构（环境无 node 时跳过，上一测试的静态断言
        仍全量生效）：提取 console.js 的 splitThinkBlock + buildThinkCardEl
        源码经 stdin 喂给 node 真实运行——"<think>块内容</think>（操作已
        执行）"切分结果 think 非空、body 为占位符；卡片节点存在、类名为
        think-card think-collapsed、含"思考过程"标题与 .think-card-body
        正文容器。纯计算子进程（stdin 管道、无网络、无临时文件）。"""
        if not shutil.which("node"):
            self.skipTest("环境无 node，跳过 JS 实跑（静态断言已覆盖）")
        script = (
            # 最小 DOM 桩：buildThinkCardEl 只用 createElement + 属性赋值
            "var document = { createElement: function (tag) "
            "{ return { nodeName: tag, className: '', innerHTML: '' }; } };\n"
            + self._extract_split_chunk() + "\n"
            "var r = splitThinkBlock('<think>块内容</think>（操作已执行）');\n"
            "var rEmpty = splitThinkBlock('<think>有思考内容</think>');\n"
            "var card = buildThinkCardEl();\n"
            "console.log(JSON.stringify({\n"
            "  think: r.think, body: r.body,\n"
            "  emptyBody: rEmpty.body,\n"
            "  cardClass: card.className,\n"
            "  hasTitle: card.innerHTML.indexOf('思考过程') !== -1,\n"
            "  hasBodyDiv: card.innerHTML.indexOf('think-card-body') !== -1\n"
            "}));\n")
        proc = subprocess.run(["node"], input=script.encode("utf-8"),
                              capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode("utf-8", "replace"))
        out = json.loads(proc.stdout.decode("utf-8"))
        self.assertEqual(out["think"], "块内容")            # 思考内容完整进卡
        self.assertEqual(out["body"], "（操作已执行）")      # 正文为占位符
        self.assertEqual(out["emptyBody"], "（操作已执行）")  # 剥空占位同样成立
        self.assertEqual(out["cardClass"], "think-card think-collapsed")  # 卡片节点存在
        self.assertTrue(out["hasTitle"])                    # 含"思考过程"标题
        self.assertTrue(out["hasBodyDiv"])                  # 含 .think-card-body 正文容器

    def test_card_guard_independent_of_body_form(self):
        """全对话强制包装契约（2026-10-01）：后端所有自然语言回复都带
        <think> 块——正文可为自然语言（普通闲聊默认占位符包装下的聊天
        正文）或占位符（"（操作已执行）"）；渲染入口插卡仅由
        think !== null 守卫，与正文形态无关：守卫条件全文唯一，且守卫与
        插卡之间不得出现任何基于正文内容的二次条件。"""
        js = self.console_js
        start = js.index("function appendBotMessage")
        end = js.index("==================== 3.", start)
        body = js[start:end]
        # 唯一插卡守卫：think !== null（appendBotMessage 内仅出现一次）
        self.assertEqual(body.count("think !== null"), 1, body)
        guard = body.index("if (thinkParts.think !== null)")
        build = body.index("buildThinkCardEl()")
        between = body[guard:build]
        # 守卫与插卡之间不得出现"正文为占位符/为空"类拦截条件
        self.assertNotIn("（操作已执行）", between)
        self.assertNotIn("正在理解你的意图", between)
        self.assertNotIn("!reply", between)
        # Python 复跑切分管线：占位符正文与自然语言正文两种形态 think 都
        # 非空（卡片由 think !== null 守卫渲染，与正文内容无关）
        think, body_text = self._think_wrap_pipeline(
            "<think>[思考] 正在理解你的意图...</think>（操作已执行）")
        self.assertEqual(think, "[思考] 正在理解你的意图...")
        self.assertEqual(body_text, "（操作已执行）")
        think, body_text = self._think_wrap_pipeline(
            "<think>[思考] 正在理解你的意图...</think>今天天气不错哦～")
        self.assertEqual(think, "[思考] 正在理解你的意图...")
        self.assertEqual(body_text, "今天天气不错哦～")

    def test_chat_placeholder_body_node_live_run(self):
        """node 实跑（环境无 node 时跳过，上一测试的静态断言仍全量生效）：
        普通闲聊默认占位符包装形态 "<think>[思考] 正在理解你的意图...
        </think>今天天气不错哦～" 切分结果 think 非空、正文原样保留；
        占位符正文形态 "<think>...</think>（操作已执行）" 同样成立——
        两种正文形态都满足 think !== null 出卡条件。纯计算子进程
        （stdin 管道、无网络、无临时文件）。"""
        if not shutil.which("node"):
            self.skipTest("环境无 node，跳过 JS 实跑（静态断言已覆盖）")
        script = (
            "var document = { createElement: function (tag) "
            "{ return { nodeName: tag, className: '', innerHTML: '' }; } };\n"
            + self._extract_split_chunk() + "\n"
            "var rChat = splitThinkBlock('<think>[思考] 正在理解你的意图..."
            "</think>今天天气不错哦～');\n"
            "var rPh = splitThinkBlock('<think>[思考] 正在理解你的意图..."
            "</think>（操作已执行）');\n"
            "console.log(JSON.stringify({\n"
            "  chatThink: rChat.think, chatBody: rChat.body,\n"
            "  phThink: rPh.think, phBody: rPh.body\n"
            "}));\n")
        proc = subprocess.run(["node"], input=script.encode("utf-8"),
                              capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode("utf-8", "replace"))
        out = json.loads(proc.stdout.decode("utf-8"))
        self.assertEqual(out["chatThink"], "[思考] 正在理解你的意图...")
        self.assertEqual(out["chatBody"], "今天天气不错哦～")   # 自然语言正文原样
        self.assertEqual(out["phThink"], "[思考] 正在理解你的意图...")
        self.assertEqual(out["phBody"], "（操作已执行）")        # 占位符正文同样成立

    # ---------- T3b 容错加固：未配对 <think>（无闭合）任何位置出现 → 剥离丢弃，不作正文 ----------

    def _replay_split_pipeline(self, raw_reply):
        """按 splitThinkBlock 全管线（成对剔块 → 孤儿闭合 → 未配对开头 →
        裸标记扫描 → [行动] 剥离 → 游离标签安全网 → 剥空占位）用源码同一组
        正则在 Python 侧复跑，返回（think, body）——node 实跑的离线等价
        验证。JS String.replace 无 /g 标志只替换首处，对应 re.sub(count=1)。"""
        block_re = self._extract_js_regex("THINK_BLOCK_RE")
        bare_think = self._extract_js_regex("BARE_THINK_RE")
        bare_plan = self._extract_js_regex("BARE_PLAN_RE")
        bare_action = self._extract_js_regex("BARE_ACTION_RE")
        think = None
        body = raw_reply

        def _append(cur, seg):
            return (cur + "\n" if cur else "") + seg

        m = block_re.search(body)
        while m:
            think = _append(think, m.group(1).strip())
            body = body[m.end():]
            m = block_re.search(body)
        close = body.rfind("</think>")
        if close != -1:
            before = re.sub(r"</?think>", "", body[:close]).strip()
            if before:
                think = _append(think, before)
            body = body[close + len("</think>"):]
        open_idx = body.find("<think>")
        if open_idx != -1:
            head = body[:open_idx].strip()
            orphan = re.sub(r"</?think>", "", body[open_idx:]).strip()
            if orphan:
                think = _append(think, orphan)
            body = head
        body = body.strip()
        parts = []

        def _collect(match):
            seg = (match.group(1) or "").strip()
            if seg:
                parts.append(seg)
            return ""

        body = bare_think.sub(_collect, body, count=1)
        body = bare_plan.sub(_collect, body, count=1)
        if parts:
            think = _append(think, "\n".join(parts))
        had_action = bool(bare_action.search(body))
        body = bare_action.sub("", body, count=1).strip()
        body = re.sub(r"</?think>", "", body).strip()
        if think is not None:
            think = re.sub(r"</?think>", "", think).strip()
        if not body and (think is not None or had_action):
            body = "（操作已执行）"
        return think, body

    def test_unpaired_think_opener_handling_present(self):
        """console.js 含未配对 <think> 的一般化剥离（indexOf 任意位置定位，
        不再限于串首 trimStart().startsWith 旧口径）：标签及其后截断思考
        整段并入思考卡、标签前正文保留，绝不作为正文上屏。"""
        start = self.console_js.index("function splitThinkBlock")
        end = self.console_js.index("function buildThinkCardEl", start)
        body = self.console_js[start:end]
        self.assertIn("const openIdx = body.indexOf('<think>')", body)
        self.assertIn("body.slice(0, openIdx)", body)                # 标签前正文保留
        self.assertNotIn('trimStart().startsWith("<think>")', body)  # 串首限定已废止

    def test_unpaired_think_opener_anywhere_stripped(self):
        """T3b 用户口径（Python 复跑全管线锁定）：未配对 <think>（其后无
        </think>）出现在任何位置都剥离丢弃——截断思考并入思考卡、绝不
        作为正文；标签前正文保留；剥离后正文剥空走既有占位口径。"""
        # 正文中间出现（原盲区）：截断思考不漏进正文，标签前正文保留
        think, body = self._replay_split_pipeline("你好 <think>这是被截断的思考")
        self.assertEqual(think, "这是被截断的思考")
        self.assertEqual(body, "你好")
        # 标签后无内容：仅剥标签，标签前正文原样保留、不出卡
        think, body = self._replay_split_pipeline("你好呀 <think>")
        self.assertIsNone(think)
        self.assertEqual(body, "你好呀")
        # 裸标签独占全文：剥离丢弃，正文不残留任何标签
        think, body = self._replay_split_pipeline("<think>")
        self.assertIsNone(think)
        self.assertEqual(body, "")
        # 串首截断（既有行为保持）：整段进卡、正文剥空 → 占位
        think, body = self._replay_split_pipeline("<think>只有开头的截断思考")
        self.assertEqual(think, "只有开头的截断思考")
        self.assertEqual(body, "（操作已执行）")
        # 闭合在前、未配对开头在后：两处游离各自收敛
        think, body = self._replay_split_pipeline("abc</think>def <think>ghi")
        self.assertEqual(think, "abc\nghi")
        self.assertEqual(body, "def")
        # 配对块 + 尾部未配对：配对进卡不受影响，尾部截断并入卡
        think, body = self._replay_split_pipeline("<think>a</think>中间<think>")
        self.assertEqual(think, "a")
        self.assertEqual(body, "中间")

    def test_unpaired_think_opener_node_live_run(self):
        """node 实跑（环境无 node 时跳过，上一测试的静态/复跑断言仍全量
        生效）：提取 console.js 真实 splitThinkBlock 验证——"你好 <think>
        这是被截断的思考" 正文只有"你好"、截断思考进卡不漏正文；"你好呀
        <think>" 仅剥标签；配对/占位/裸标记场景零回退。纯计算子进程
        （stdin 管道、无网络、无临时文件）。"""
        if not shutil.which("node"):
            self.skipTest("环境无 node，跳过 JS 实跑（静态断言已覆盖）")
        script = (
            "var document = { createElement: function (tag) "
            "{ return { nodeName: tag, className: '', innerHTML: '' }; } };\n"
            + self._extract_split_chunk() + "\n"
            "var rMid = splitThinkBlock('你好 <think>这是被截断的思考');\n"
            "var rTag = splitThinkBlock('你好呀 <think>');\n"
            "var rPair = splitThinkBlock('<think>配对</think>正常正文');\n"
            "var rMulti = splitThinkBlock('<think>a</think>中间<think>b</think>尾');\n"
            "var rPh = splitThinkBlock('<think>块内容</think>（操作已执行）');\n"
            "var rBare = splitThinkBlock('[思考] 裸思考\\n[计划] 裸计划\\n"
            "[行动] {\"tool\": \"x\"}\\n最终回复');\n"
            "console.log(JSON.stringify({\n"
            "  midThink: rMid.think, midBody: rMid.body,\n"
            "  tagThink: rTag.think, tagBody: rTag.body,\n"
            "  pairThink: rPair.think, pairBody: rPair.body,\n"
            "  multiThink: rMulti.think, multiBody: rMulti.body,\n"
            "  phThink: rPh.think, phBody: rPh.body,\n"
            "  bareThink: rBare.think, bareBody: rBare.body\n"
            "}));\n")
        proc = subprocess.run(["node"], input=script.encode("utf-8"),
                              capture_output=True, timeout=60)
        self.assertEqual(proc.returncode, 0,
                         proc.stderr.decode("utf-8", "replace"))
        out = json.loads(proc.stdout.decode("utf-8"))
        # 盲区修复：中间未配对 <think> 的截断思考进卡，绝不作为正文
        self.assertEqual(out["midThink"], "这是被截断的思考")
        self.assertEqual(out["midBody"], "你好")
        self.assertNotIn("<think>", out["midBody"])
        self.assertNotIn("这是被截断的思考", out["midBody"])
        # 标签后无内容：仅剥标签，正文保留，无卡片内容
        self.assertIsNone(out["tagThink"])
        self.assertEqual(out["tagBody"], "你好呀")
        # 配对场景零回退
        self.assertEqual(out["pairThink"], "配对")
        self.assertEqual(out["pairBody"], "正常正文")
        self.assertEqual(out["multiThink"], "a\nb")
        self.assertEqual(out["multiBody"], "尾")
        # 占位形态零回退
        self.assertEqual(out["phThink"], "块内容")
        self.assertEqual(out["phBody"], "（操作已执行）")
        # 裸标记/[行动] 剥离零回退
        self.assertIn("[思考] 裸思考", out["bareThink"])
        self.assertEqual(out["bareBody"], "最终回复")

    def test_plain_chat_mentioning_thinking_not_stripped(self):
        """反例：普通聊天提到"思考"二字（无 [思考] 方括号标记）不触发
        剥离——正文原样保留、不产生思考卡内容、不误显示占位。"""
        text = "让我思考一下这个问题，稍后给你答案。"
        parts, body = self._bare_strip_pipeline(text)
        self.assertEqual(parts, [])
        self.assertEqual(body, text)

    # ---------- console.js：等待期轮换状态 ----------

    def test_waiting_status_rotation(self):
        """发送后占位气泡动态轮换：900ms 间隔、四条状态循环、回复到达即停。"""
        js = self.console_js
        self.assertIn("THINKING_STATUS", js)
        for phrase in ("正在思考执行方案", "正在分析屏幕",
                       "正在读取文件", "正在执行操作"):
            self.assertIn(phrase, js)
        self.assertIn("THINKING_ROTATE_MS = 900", js)         # 每 900ms 轮换
        self.assertIn("clearInterval(rotateTimer)", js)       # 收到回复/出错停止轮换
        self.assertIn("小橘3号正在思考... 🧠", js)             # 初始占位文案保留

    # ---------- index.html：思维链卡片样式 ----------

    def test_index_think_card_styles(self):
        """index.html 内联样式区含 .think-card / .think-card-header /
        .think-card-body：浅灰背景 #f3f4f6、圆角 10px、13px 字号、
        折叠用 .think-collapsed 类 + display 切换。"""
        html = self.index_html
        for cls in (".think-card {", ".think-card-header {", ".think-card-body {"):
            self.assertIn(cls, html)
        start = html.index(".think-card {")
        block = html[start:html.index("}", start)]
        self.assertIn("#f3f4f6", block)             # 浅灰背景
        self.assertIn("border-radius: 10px", block)  # 圆角 10px
        self.assertIn("font-size: 13px", block)      # 13px 字号
        # 折叠实现：.think-collapsed 类 + 正文 display:none
        self.assertIn(".think-card.think-collapsed .think-card-body", html)

    # ---------- F4 渲染加固：异常捕获 + 手工 DOM 插入 + 深色降级兜底 + 容器 ID ----------

    def test_split_think_block_try_catch_guard(self):
        """splitThinkBlock 函数体整体包 try/catch（F4 加固）：解析任何异常
        都不影响后续消息渲染——catch 记录 "CoT Render Error" 日志并返回
        安全降级值（think=已剥离出的部分或 null、body=原文）。"""
        js = self.console_js
        start = js.index("function splitThinkBlock")
        end = js.index("function buildThinkCardEl", start)
        body = js[start:end]
        self.assertIn("try {", body)
        self.assertIn("} catch (e) {", body)
        self.assertLess(body.index("try {"), body.index("} catch (e) {"))
        self.assertIn('console.error("CoT Render Error: ", e)', body)
        # 正常返回与异常降级返回并存：降级正文回退原文（raw）
        self.assertIn("return { think: think, body: body }", body)
        self.assertIn("return { think: think, body: raw }", body)

    def test_card_insert_manual_dom_and_fallback(self):
        """卡片插入手工 DOM 化（F4 加固，不依赖 ChildNode.before()）：
        appendBotMessage 与 syncThinkCard 均用显式父引用 + insertBefore 把
        卡片插到气泡正文上方；插入处包 try/catch，失败时降级为深色纯文本块
        （仍插在气泡上方），思考过程任何情况下可见。"""
        js = self.console_js
        self.assertNotIn(".before(", js)   # 全文件不再使用 before() 插卡
        # 实时路径：appendBotMessage
        start = js.index("function appendBotMessage")
        end = js.index("==================== 3.", start)
        bot_body = js[start:end]
        self.assertIn("parentEl.insertBefore(thinkCard, bubbleEl)", bot_body)
        self.assertIn('console.error("CoT Render Error: ", e)', bot_body)
        self.assertIn("buildThinkFallbackBlock(thinkParts.think)", bot_body)
        # 降级块仍插在气泡上方（消息容器首子节点之前）
        self.assertIn("botMsg.insertBefore(", bot_body)
        # 刷新重生成路径：syncThinkCard 同口径
        start = js.index("function syncThinkCard")
        end = js.index("function appendUserMessage", start)
        sync_body = js[start:end]
        self.assertIn("bubble.parentNode.insertBefore(card, bubble)", sync_body)
        self.assertIn("buildThinkFallbackBlock(thinkText)", sync_body)

    def test_think_fallback_dark_block(self):
        """深色降级兜底块 buildThinkFallbackBlock（F4 加固）：纯 createElement
        + 内联深色样式（#1f2937 底、白字、13px 字号），内容为思考文本前
        200 字、textContent 注入免 XSS——卡片插入失败时思考过程仍然可见。"""
        js = self.console_js
        self.assertIn("function buildThinkFallbackBlock", js)
        start = js.index("function buildThinkFallbackBlock")
        end = js.index("const THINK_TYPE_MS", start)
        body = js[start:end]
        self.assertIn("document.createElement('div')", body)
        self.assertIn("#1f2937", body)               # 深色背景（任务规格色）
        self.assertIn("#ffffff", body)               # 白字
        self.assertIn("13px", body)                  # 13px 字号
        self.assertIn("slice(0, 200)", body)         # 思考文本前 200 字
        self.assertIn("block.textContent =", body)   # 纯文本注入，免 XSS

    def test_chat_container_id_consistency(self):
        """容器 ID 逐一核对（双向互查，F4 加固）：console.js 所有
        getElementById 参数（除运行时按需 createElement 的 toast 挂载点）
        都必须在 index.html 有对应 id="..." 定义；聊天记录容器
        chat-history 双向锁定。"""
        html_ids = set(re.findall(r'id="([^"]+)"', self.index_html))
        js_ids = set(re.findall(r"getElementById\('([^']+)'\)", self.console_js))
        self.assertTrue(js_ids, msg="console.js 未发现 getElementById 调用")
        dynamic_ids = {"xiaoju3-toast"}   # showToast 首次调用时 createElement 自建
        missing = js_ids - dynamic_ids - html_ids
        self.assertEqual(missing, set(),
                         msg="console.js 引用了 index.html 不存在的 id: %s" % missing)
        # 聊天记录容器（本任务核对主体）双向锁定
        self.assertIn("chat-history", html_ids)
        self.assertIn("chat-history", js_ids)


# ---------------------------------------------------------------------------
# T4a：CoT 前端诊断日志（三处常驻埋点）+ 卡片强制渲染兜底
# ---------------------------------------------------------------------------

class CoTDiagnosticAndForcedFallbackTests(unittest.TestCase):
    """T4a（2026-10-01 用户口径）：思维链卡片"渲染代码没被执行/执行了但
    插入失败被静默吞掉"问题的前端诊断与强制渲染兜底。

    ① 三处常驻诊断日志（用户指定文案，保留在代码中）：
       sendMessage 收到后端响应处 RAW_REPLY、appendBotMessage 切分后
       PARSED_THINK/PARSED_BODY、卡片渲染分支入口 RENDERING_THINK_CARD；
    ② 强制卡片渲染兜底：插卡尝试后实测校验 botMsg.querySelector('.think-card')
       真实存在，缺失且 think 非空时用 createElement + classList.add 手工
       构建卡片（🧠 图标 + ▼ 折叠箭头 + 可展开思考文本 textContent 注入）
       并 prepend 强制补插（不依赖 before()），兜底后再校验一次，仍失败
       最终降级为深色纯文本块（F4 既有 buildThinkFallbackBlock）；
    ③ index.html .think-card 显式 display: block（整卡永不被隐藏，
       .think-collapsed 只藏正文）。
    """

    @classmethod
    def setUpClass(cls):
        def _read(name):
            with open(os.path.join(PROJECT_ROOT, name), "r", encoding="utf-8") as f:
                return f.read()
        cls.console_js = _read("console.js")
        cls.index_html = _read("index.html")

    def _bot_body(self):
        """提取 console.js 中 appendBotMessage 函数体（到下一节标记为止）。"""
        start = self.console_js.index("function appendBotMessage")
        end = self.console_js.index("==================== 3.", start)
        return self.console_js[start:end]

    def _forced_fallback_region(self, body):
        """提取强制兜底区段（首次 .think-card 实测校验 → 打字机启动之前）。"""
        start = body.index("botMsg.querySelector('.think-card')")
        end = body.index("startThinkTypewriter(botMsg, thinkParts.think")
        return body[start:end]

    # ---------- ① 三处常驻诊断日志 ----------

    def test_diagnostic_log_raw_reply_in_send_message(self):
        """诊断埋点①：sendMessage 收到后端响应处打印完整原始 reply，
        位于成功分支内（res.data.reply 必存在）且先于卡片渲染入口。"""
        start = self.console_js.index("window.sendMessage")
        end = self.console_js.index("==================== 5.", start)
        body = self.console_js[start:end]
        self.assertIn('console.log("RAW_REPLY:", res.data.reply)', body)
        self.assertLess(body.index('console.log("RAW_REPLY:"'),
                        body.index("appendBotMessage(res.data.reply"))

    def test_diagnostic_log_parsed_think_in_append_bot(self):
        """诊断埋点②：appendBotMessage 调 splitThinkBlock 之后打印切分
        结果（PARSED_THINK + PARSED_BODY）——RAW_REPLY 含 <think> 而本行
        think 为 null 即切分环节异常。"""
        body = self._bot_body()
        self.assertIn('console.log("PARSED_THINK:", thinkParts.think, '
                      '"PARSED_BODY:", thinkParts.body)', body)
        self.assertLess(body.index("splitThinkBlock(rawReply)"),
                        body.index('console.log("PARSED_THINK:"'))

    def test_diagnostic_log_rendering_entry(self):
        """诊断埋点③：卡片渲染分支入口打印 RENDERING_THINK_CARD——位于
        think 守卫之后、插卡动作之前（分支入口处）。"""
        body = self._bot_body()
        guard = body.index("if (thinkParts.think !== null)")
        entry = body.index('console.log("RENDERING_THINK_CARD...")')
        self.assertLess(guard, entry)
        self.assertLess(entry, body.index("buildThinkCardEl()"))

    # ---------- ② 强制卡片渲染兜底 ----------

    def test_forced_card_fallback_after_insert(self):
        """强制兜底：插卡尝试（F4 insertBefore 通道）之后实测校验
        .think-card 真实存在；兜底区段含 createElement 手工构建 +
        classList.add('think-card') + prepend 补插 + 二次校验。"""
        body = self._bot_body()
        guard = body.index("if (thinkParts.think !== null)")
        # 实测校验在渲染守卫之内、主插卡通道之后
        forced_start = body.index("botMsg.querySelector('.think-card')")
        self.assertLess(guard, forced_start)
        self.assertLess(body.index("parentEl.insertBefore(thinkCard, bubbleEl)"),
                        forced_start)
        forced = self._forced_fallback_region(body)
        # 校验 + 兜底插入后再校验一次：恰为两处实测
        self.assertEqual(forced.count("botMsg.querySelector('.think-card')"), 2)
        self.assertIn("document.createElement('div')", forced)   # 手工构建
        self.assertIn("classList.add('think-card')", forced)     # 类名注入
        self.assertIn("botMsg.prepend(", forced)                 # prepend 补插通道
        # 兜底位于打字机启动之前（打字机按类名找到补插的卡片照常填充）
        self.assertLess(body.index("botMsg.prepend("),
                        body.index("startThinkTypewriter(botMsg, thinkParts.think"))

    def test_forced_fallback_card_content_and_final_degrade(self):
        """手工兜底卡片必含 🧠 图标、▼ 折叠箭头、思考文本 textContent 注入
        （可展开）；二次校验仍失败最终降级复用 F4 深色纯文本块。"""
        forced = self._forced_fallback_region(self._bot_body())
        self.assertIn("🧠", forced)
        self.assertIn("▼", forced)
        self.assertIn("textContent =", forced)              # 思考文本纯文本注入
        self.assertIn("classList.add('think-collapsed')", forced)  # 初始折叠态
        self.assertIn("buildThinkFallbackBlock(thinkParts.think)", forced)  # 最终降级

    # ---------- ③ index.html .think-card 显式 display: block ----------

    def test_think_card_display_block_style(self):
        """index.html .think-card 样式含显式 display: block——整卡永远可见，
        .think-collapsed 只藏正文（display:none 只作用于 .think-card-body）。"""
        html = self.index_html
        start = html.index(".think-card {")
        block = html[start:html.index("}", start)]
        self.assertIn("display: block", block)
        # 折叠只藏正文：display:none 不在 .think-card 本体块内
        self.assertNotIn("display: none", block)


# ---------------------------------------------------------------------------
# Web 出口 CQ 码净化（纵深防御：web_sanitize + /api/chat 接线）
# ---------------------------------------------------------------------------

class WebSanitizeTests(unittest.TestCase):
    """web_sanitize.sanitize_for_web 纯函数：face→Emoji、image→[表情]、其余剥除。"""

    def test_mapped_face_to_emoji(self):
        self.assertEqual(web_sanitize.sanitize_for_web("[CQ:face,id=4] 得意"),
                         "😎 得意")

    def test_unknown_face_falls_back_to_generic(self):
        """未收录 id 不留方括号原文，兜底通用微笑。"""
        self.assertEqual(web_sanitize.sanitize_for_web("[CQ:face,id=999]"), "😊")

    def test_image_replaced_and_path_not_leaked(self):
        """[CQ:image] → [表情] 占位：本机绝对路径不外泄给网页用户。"""
        out = web_sanitize.sanitize_for_web(
            "看这个 [CQ:image,file=file:///home/orangepi/workspace/emoji_library/开心_1234.jpg]")
        self.assertEqual(out, "看这个 [表情]")
        self.assertNotIn("file://", out)
        self.assertNotIn("CQ", out)

    def test_other_cq_codes_stripped(self):
        """[CQ:at]/[CQ:record] 等其余类型剥除，不留方括号。"""
        out = web_sanitize.sanitize_for_web("[CQ:at,qq=123] 在吗 [CQ:record,file=x.amr]")
        self.assertEqual(out, "在吗")
        self.assertNotIn("[", out)

    def test_plain_text_untouched(self):
        """普通文本（含普通 Emoji）原样返回，无副作用。"""
        self.assertEqual(web_sanitize.sanitize_for_web("普通回复 😊，没有专用码。"),
                         "普通回复 😊，没有专用码。")

    def test_mixed_codes_all_resolved(self):
        """face + image + at 混合：一次净化全部消化。"""
        out = web_sanitize.sanitize_for_web(
            "好[CQ:face,id=20]看图[CQ:image,file=file:///ws/a.jpg][CQ:at,qq=1]完[CQ:face,id=999]")
        self.assertEqual(out, "好🤭看图[表情]完😊")

    def test_face_mapping_matches_frontend_table(self):
        """前后端映射同源：web_sanitize 与 console.js 的 CQ_FACE_EMOJI 键集一致。"""
        with open("console.js", "r", encoding="utf-8") as f:
            js = f.read()
        start = js.index("const CQ_FACE_EMOJI")
        block = js[start:js.index("};", start)]
        js_ids = {m for m in re.findall(r"(\d+):\s*'[^']*'", block)}
        self.assertEqual(js_ids, set(web_sanitize.CQ_FACE_EMOJI))


class ChatCqSanitizeTests(HistoryApiTestsBase):
    """纵深防御接线：/api/chat 返回与落盘前净化（mock smart_ask 注入 QQ 专用回复）。"""

    def test_chat_face_code_converted_to_emoji(self):
        """face 码在返回与落盘前转 Emoji：/api/history 回放不再有方括号原文。"""
        with mock.patch.object(dashboard, "smart_ask") as ms, _quiet():
            ms.return_value = ("得意[CQ:face,id=4]流泪[CQ:face,id=5]", "🏠 本地")
            resp = self.client.post("/api/chat", json={"message": "嗨"})

        payload = resp.get_json()
        self.assertEqual(payload["code"], 200)
        self.assertEqual(payload["data"]["reply"], "得意😎流泪😢")
        self.assertNotIn("CQ", payload["data"]["reply"])
        stored = _read_json_file(self.history_file)
        self.assertEqual(stored[-1]["content"], "得意😎流泪😢")

    def test_chat_image_code_replaced_without_path_leak(self):
        """translate_emoji 注入的 [CQ:image] 表情包码：换 [表情] 占位，
        服务器本机绝对路径不进响应也不落盘。"""
        with mock.patch.object(dashboard, "smart_ask") as ms, _quiet():
            ms.return_value = (
                "看这个[CQ:image,file=file:///home/orangepi/workspace/emoji_library/开心_1234.jpg]",
                "🏠 本地")
            payload = self.client.post("/api/chat", json={"message": "表情"}).get_json()

        self.assertEqual(payload["data"]["reply"], "看这个[表情]")
        self.assertNotIn("file://", payload["data"]["reply"])
        stored = _read_json_file(self.history_file)
        self.assertEqual(stored[-1]["content"], "看这个[表情]")

    def test_chat_unknown_face_and_other_cq_codes(self):
        """未收录 face id 兜底 😊；at/record 等其余 CQ 码剥除。"""
        with mock.patch.object(dashboard, "smart_ask") as ms, _quiet():
            ms.return_value = ("嗯[CQ:face,id=999]好[CQ:at,qq=123]呀[CQ:record,file=x.amr]",
                               "☁️ 云端")
            payload = self.client.post("/api/chat", json={"message": "在吗"}).get_json()

        self.assertEqual(payload["data"]["reply"], "嗯😊好呀")

    def test_chat_wrapped_think_reply_survives_full_chain(self):
        """全链路 think 存活断言（CoT 数据传递链路 b+c 环节）：smart_ask 返回
        <think>[思考]…[计划]…</think>最终回答 形态 → /api/chat 经真实
        sanitize_for_web 后 <think>/</think> 标签原样存活（不被剥掉/转义/
        破坏）、思考文本与最终回答完整，前端才可能渲染折叠卡片；
        思考内容混入的 CQ face 码仍按 Web 口径转 Emoji。"""
        wrapped = ("<think>[思考] 要点WLAN，先定位控件。[CQ:face,id=4]\n"
                   "[计划] uiautomator 定位后点击。</think>"
                   "好的，已经帮你点开WLAN设置页面了。")
        with mock.patch.object(dashboard, "smart_ask") as ms, _quiet():
            ms.return_value = (wrapped, "🏠 本地 (工具)")
            payload = self.client.post(
                "/api/chat", json={"message": "帮我点击手机屏幕上的WLAN"}).get_json()

        self.assertEqual(payload["code"], 200)
        reply = payload["data"]["reply"]
        self.assertTrue(reply.startswith("<think>[思考] 要点WLAN，先定位控件。😎\n"),
                        reply)
        self.assertIn("[计划] uiautomator 定位后点击。</think>", reply)
        self.assertTrue(reply.endswith("好的，已经帮你点开WLAN设置页面了。"))
        self.assertEqual(reply.count("<think>"), 1)       # 标签恰好一对，未被破坏
        self.assertEqual(reply.count("</think>"), 1)
        # 落盘历史同样保持 think 完整（刷新/历史回放渲染同源）
        stored = _read_json_file(self.history_file)
        self.assertEqual(stored[-1]["content"], reply)


# ---------------------------------------------------------------------------
# 静态资源缓存失效（浏览器刷新即取最新 JS）
# ---------------------------------------------------------------------------

class StaticCacheHeaderTests(unittest.TestCase):
    """静态路由统一 Cache-Control: no-store：跨 Werkzeug 版本/反代行为确定。"""

    def setUp(self):
        self.client = dashboard.app.test_client()

    def test_console_and_assets_no_store(self):
        """/console* 与 /assets* 全部 no-store，正常刷新即拿到新版 JS。"""
        for path in ("/console", "/console/console.js",
                     "/console/desktop-pet.js", "/assets/DSniang1.jpg"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)  # werkzeug 读文件句柄告警
                resp = self.client.get(path)
            self.assertEqual(resp.status_code, 200, path)
            self.assertEqual(resp.headers.get("Cache-Control"), "no-store", path)

    def test_api_routes_keep_default_cache_policy(self):
        """no-store 只套静态路由，/api/* 接口响应不显式改缓存策略。"""
        resp = self.client.get("/api/history")
        self.assertEqual(resp.status_code, 200)
        self.assertNotEqual(resp.headers.get("Cache-Control"), "no-store")


# ---------------------------------------------------------------------------
# prompts 表情规则改版（回复一律普通 Emoji、禁止输出 CQ 码）
# ---------------------------------------------------------------------------

class PromptEmojiRuleTests(unittest.TestCase):
    """系统提示词表情规则（静态断言，与前端/后端净化口径配套）。"""

    @classmethod
    def setUpClass(cls):
        cls.content = prompts.SYSTEM_PROMPT["content"]

    def test_reply_uses_plain_emoji(self):
        """回复文本一律普通 Emoji；旧'禁止使用任何Emoji'口径废止。"""
        self.assertIn("一律使用普通 Emoji", self.content)
        self.assertNotIn("禁止使用任何Emoji", self.content)

    def test_cq_codes_forbidden_for_model_output(self):
        """禁止模型输出任何以 [CQ: 开头的代码；CQ 码仅限系统内部场景。
        提示词不再举 CQ 具体示例，防止模型模仿输出。"""
        self.assertIn("禁止输出任何以 [CQ:", self.content)
        self.assertIn("系统内部", self.content)
        self.assertNotIn("[CQ:face", self.content)
        self.assertNotIn("[CQ:image", self.content)




class ConsoleCacheBustingTests(unittest.TestCase):
    """防缓存终极方案：/console 注入时间戳版本参数（2026-10-01 用户指令）。"""

    def setUp(self):
        self.client = dashboard.app.test_client()

    def test_console_html_has_version_params(self):
        resp = self.client.get("/console")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("console.js?v=", html)
        self.assertIn("desktop-pet.js?v=", html)

    def test_version_changes_when_file_mtime_changes(self):
        resp1 = self.client.get("/console")
        import re as _re
        m1 = _re.search(r"console\.js\?v=(\d+)", resp1.get_data(as_text=True))
        self.assertIsNotNone(m1)
        # 触碰 console.js 的 mtime → 版本号必须变化（浏览器缓存随之失效）
        path = os.path.join(PROJECT_ROOT, "console.js")
        new_mtime = int(time.time()) + 100
        os.utime(path, (new_mtime, new_mtime))
        try:
            resp2 = self.client.get("/console")
            m2 = _re.search(r"console\.js\?v=(\d+)", resp2.get_data(as_text=True))
            self.assertIsNotNone(m2)
            self.assertNotEqual(m1.group(1), m2.group(1))
        finally:
            os.utime(path, (1000000000, 1000000000))

    def test_static_js_route_still_served(self):
        # 带版本参数的请求与裸请求都应命中静态路由（query 不参与路由匹配）
        for qs in ("", "?v=123"):
            resp = self.client.get("/console/console.js" + qs)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("no-store", resp.headers.get("Cache-Control", ""))


class CreatorCommandTests(unittest.TestCase):
    """/api/chat /creator 分流（2026-10-02 修复：与 QQ 通道共用
    main.handle_creator_command，缺失时返回开源项目链接）。"""

    def test_console_page_title_has_no_creator_suffix(self):
        """2026-10-02 用户口径：标题栏隐藏"为 XUN 而建"——/console 页面
        header-title 保持"小橘3号 · 控制台"原样（署名只走 /creator 命令
        与启动日志）。"""
        import xiaoju3_dashboard as dashboard
        client = dashboard.app.test_client()
        html = client.get("/console").get_data(as_text=True)
        self.assertIn('class="header-title">小橘3号 · 控制台<', html)
        self.assertNotIn("而建", html)
        # 防缓存版本参数随 mtime 变化，确保浏览器刷新拉到新 console.js
        import re as _re
        m = _re.search(r'/console/console\.js\?v=(\d+)', html)
        self.assertIsNotNone(m)

    def test_creator_with_name_returns_card(self):
        import xiaoju3_dashboard as dashboard
        from xiaoju3_dashboard import main
        with mock.patch.object(main, "get_creator_name",
                               return_value="XUN"):
            client = dashboard.app.test_client()
            resp = client.post("/api/chat", json={"message": "/creator"})
        payload = resp.get_json()
        self.assertEqual(payload["code"], 200)
        self.assertEqual(payload["data"]["reply"],
                         "🦊 小橘3号 · 由 XUN 创造与维护")
        self.assertEqual(payload["data"]["source"], "⚙️ 系统")

    def test_creator_without_name_returns_oss_link(self):
        import xiaoju3_dashboard as dashboard
        from xiaoju3_dashboard import main
        with mock.patch.object(main, "get_creator_name", return_value=""):
            client = dashboard.app.test_client()
            resp = client.post("/api/chat", json={"message": "/creator"})
        payload = resp.get_json()
        self.assertIn("https://github.com/Xun201/xiaoju3-agent",
                      payload["data"]["reply"])


if __name__ == "__main__":
    unittest.main()


class TestVersionBadge(unittest.TestCase):
    """版本统一（安装器方案步 A1）：/api/status 下发 version + 前端徽标锚。"""

    def setUp(self):
        self.client = dashboard.app.test_client()

    def test_api_status_includes_version(self):
        """/api/status data.version == xiaoju3.XIAOJU3_VERSION（单一事实源）。"""
        resp = self.client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(data["version"], xiaoju3.XIAOJU3_VERSION)  # 单一事实源透传 + 版本钉（引常量，升版零改动）

    def test_header_version_element_in_console_html(self):
        """/console 页（index.html）含 header-version 徽标元素与样式锚
        （console.js 动态填充内容，此处锁定壳存在）。"""
        with open(os.path.join(PROJECT_ROOT, "index.html"),
                  "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('id="header-version"', html)
        self.assertIn("header-version", html)
        with open(os.path.join(PROJECT_ROOT, "console.js"),
                  "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("header-version", js)


class TodosApiTests(unittest.TestCase):
    """待办 API（2026-10-04 待办提取，docs/TODO_EXTRACT_DESIGN.md §6）：
    GET /api/todos 与 POST /api/todos/<id>/done，storage 走 tmp 隔离。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_dash_todos_")
        self.sm = StateManager(base_dir=self.tmp)
        self._state_patcher = mock.patch("xiaoju3_dashboard.state_manager", self.sm)
        self._state_patcher.start()
        self._job_patcher = mock.patch("plugins.todo_extractor.last_job",
                                       return_value=None)
        self._job_patcher.start()
        self.client = dashboard.app.test_client()

    def tearDown(self):
        self._job_patcher.stop()
        self._state_patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_get_empty(self):
        resp = self.client.get("/api/todos")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(data["todos"], [])
        self.assertEqual(data["pending_count"], 0)
        self.assertEqual(data["done_count"], 0)
        self.assertIsNone(data["last_job"])

    def test_get_with_counts_and_last_job(self):
        self.sm.save_todos(["A", "B"], source_url="u1")
        self.sm.complete_todo(1)
        with mock.patch("plugins.todo_extractor.last_job",
                        return_value={"state": "done", "inserted": 2}):
            resp = self.client.get("/api/todos")
        data = resp.get_json()["data"]
        self.assertEqual(data["pending_count"], 1)
        self.assertEqual(data["done_count"], 1)
        self.assertEqual(data["last_job"]["state"], "done")

    def test_post_done_200_then_404(self):
        self.sm.save_todos(["A"], source_url="u1")
        ok = self.client.post("/api/todos/1/done")
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.get_json()["data"]["ok"])
        self.assertEqual(ok.get_json()["data"]["todo"]["status"], "done")
        missing = self.client.post("/api/todos/999/done")
        self.assertEqual(missing.status_code, 404)
        # GET 侧状态翻转（pending → done）
        data = self.client.get("/api/todos").get_json()["data"]
        self.assertEqual(data["pending_count"], 0)
        self.assertEqual(data["done_count"], 1)

    def test_post_done_is_idempotent_404(self):
        self.sm.save_todos(["A"], source_url="u1")
        self.client.post("/api/todos/1/done")
        again = self.client.post("/api/todos/1/done")   # 已 done → 404（幂等）
        self.assertEqual(again.status_code, 404)

    def test_collapsed_groups_roundtrip(self):
        # 尾巴 I 服务端承载：GET 下发 / POST 保存（非法体 400）
        resp = self.client.post("/api/todos/collapsed_groups",
                                json={"collapsed_groups": ["P2", "P3"]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"]["collapsed_groups"], ["P2", "P3"])
        data = self.client.get("/api/todos").get_json()["data"]
        self.assertEqual(data["collapsed_groups"], ["P2", "P3"])
        bad = self.client.post("/api/todos/collapsed_groups", json={"collapsed_groups": "P2"})
        self.assertEqual(bad.status_code, 400)
        empty = self.client.post("/api/todos/collapsed_groups", json={})
        self.assertEqual(empty.status_code, 400)

    def test_priority_migration_and_default(self):
        # 尾巴 C：新库建列 + 默认 P1（迁移路径由 test_state_manager 旧库用例覆盖）
        import sqlite3
        conn = sqlite3.connect(self.sm.memory_db)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(todos)")]
        conn.close()
        self.assertIn("priority", cols)
        self.sm.save_todos(["X"], source_url="u")
        self.assertEqual(self.sm.get_todos()[0]["priority"], "P1")

    def test_post_priority_sets_and_normalizes(self):
        # 尾巴 C：pill 端点——合法值落库、非法归一 P1、不存在 404
        self.sm.save_todos([{"content": "A", "priority": "P2"}], source_url="u1")
        resp = self.client.post("/api/todos/1/priority", json={"priority": "P0"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["data"]["todo"]["priority"], "P0")
        bad = self.client.post("/api/todos/1/priority", json={"priority": "urgent"})
        self.assertEqual(bad.status_code, 200)
        self.assertEqual(bad.get_json()["data"]["todo"]["priority"], "P1")
        missing = self.client.post("/api/todos/999/priority", json={"priority": "P0"})
        self.assertEqual(missing.status_code, 404)

    def test_post_reopen_restores_pending(self):
        # 尾巴 1：复选框取消钩——reopen 翻回 pending，GET 计数随之翻转
        self.sm.save_todos(["A"], source_url="u1")
        self.client.post("/api/todos/1/done")
        resp = self.client.post("/api/todos/1/reopen")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["data"]["ok"])
        self.assertEqual(resp.get_json()["data"]["todo"]["status"], "pending")
        data = self.client.get("/api/todos").get_json()["data"]
        self.assertEqual(data["pending_count"], 1)
        self.assertEqual(data["done_count"], 0)
        missing = self.client.post("/api/todos/1/reopen")   # 已是 pending → 404
        self.assertEqual(missing.status_code, 404)

    def test_delete_hard_deletes_and_404s_missing(self):
        # #238：DELETE 硬删单条——200 后行消失（done_count 归零）、
        # 再删 404、其余端点对该 id 也 404
        self.sm.save_todos(["A", "B"], source_url="u1")
        self.client.post("/api/todos/1/done")
        resp = self.client.delete("/api/todos/1")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["data"]["ok"])
        data = self.client.get("/api/todos").get_json()["data"]
        self.assertEqual(data["done_count"], 0)
        self.assertEqual(len(data["todos"]), 1)      # 邻行不伤
        missing = self.client.delete("/api/todos/1") # 已删 → 404
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(
            self.client.post("/api/todos/1/done").status_code, 404)


class TodosFrontendAnchorTests(unittest.TestCase):
    """待办卡片前端静态锚：卡片标记存在 + console.js 轮询/标完成链路在位。"""

    def test_index_has_todos_card(self):
        with open(os.path.join(PROJECT_ROOT, "index.html"),
                  "r", encoding="utf-8") as f:
            html = f.read()
        for anchor in ('id="todos-list"', 'id="todos-job-line"',
                       'id="todos-count-text"', "todos-card"):
            self.assertIn(anchor, html)

    def test_console_js_polls_and_marks_done(self):
        with open(os.path.join(PROJECT_ROOT, "console.js"),
                  "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("fetch('/api/todos')", js)
        self.assertIn("TODOS_REFRESH_MS = 30000", js)
        # 尾巴 1：复选框双向——勾=done、取消=reopen（动态 action 端点）
        self.assertIn("class=\"todo-check\"", js)
        self.assertIn("box.checked ? 'done' : 'reopen'", js)
        self.assertIn("/${action}`, { method: 'POST' }", js)
        self.assertIn("escapeHtml(t.content)", js)   # XSS 防护：待办文本转义渲染

    def test_console_todo_items_retain_done_entries(self):
        # 尾巴 1：完成态保留显示（不再折叠消失）——全量渲染 + 划线灰显类
        with open(os.path.join(PROJECT_ROOT, "console.js"),
                  "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("const items = data.todos;", js)               # 全量渲染
        self.assertIn("todo-item${doneCls}", js)                     # 完成态类随行
        self.assertNotIn("done.slice(0, 3)", js)                     # 旧"只显 3 条"折叠口径退役

    def test_gear_edit_mode_lock(self):
        # 尾巴 F：⚙️ 齿轮编辑模式——默认锁定（disabled）、点击切换重渲染
        with open(os.path.join(PROJECT_ROOT, "console.js"),
                  "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("let todoEditing = false;", js)
        # 尾巴 C 扩展：锁定=只读徽标（不可改），编辑态=六档下拉选择器
        self.assertIn("const prControl = todoEditing", js)
        self.assertIn('select class="todo-pr-select"', js)
        self.assertIn('span class="todo-pr-badge"', js)
        self.assertIn("todoEditing = !todoEditing;", js)
        self.assertIn("gearEl.classList.toggle('editing', todoEditing)", js)   # F2：状态类
        self.assertNotIn("'🔓'", js)                                            # F2：单图标
        with open(os.path.join(PROJECT_ROOT, "index.html"),
                  "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('id="todos-edit-gear"', html)
        self.assertIn(".todo-pr:disabled", html)

    def test_todos_card_full_quota(self):
        # 尾巴 G：卡片全量口径（dashboard 侧 limit=200，不再默认 50 截断）
        import inspect
        src = inspect.getsource(dashboard.api_todos)
        self.assertIn("limit=200", src)

    def test_console_priority_pills_and_grouping(self):
        # 尾巴 C 精确版+扩展：分区视图（── Px ── 标题、空分区 continue 跳过，
        # P0-P5 六档）、下拉选择器选择即改 POST priority、改后 loadTodos
        # 全量刷新=实时移动分区
        with open(os.path.join(PROJECT_ROOT, "console.js"),
                  "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("todo-group-title", js)
        self.assertIn("── ${pr} ──", js)
        self.assertIn("if (!group.length) continue;", js)   # 空分区不显示
        # 时间老化（2026-10-07）：分组键=生效档 effective_priority（COALESCE，
        # 未老化=原档）+ "↑已升"标记（生效档≠原档渲染）
        self.assertIn("const eff = t.effective_priority || t.priority || 'P1';", js)
        self.assertIn("(byPriority[eff] || byPriority.P1).push(t);", js)
        self.assertIn('class="todo-aged"', js)
        self.assertIn("['P0', 'P1', 'P2', 'P3', 'P4', 'P5']", js)   # 六档
        # 回归锚（v11 齿轮失效根因）：分组字典必须六键齐全 + 循环防御兜底
        self.assertIn(
            "const byPriority = { P0: [], P1: [], P2: [], P3: [], P4: [], P5: [] };", js)
        self.assertIn("const group = byPriority[pr] || [];", js)
        self.assertIn('select class="todo-pr-select"', js)
        self.assertIn("/priority`, {", js)
        self.assertIn("JSON.stringify({ priority: sel.value })", js)
        self.assertIn(".then(() => loadTodos())", js)       # 改后刷新=实时移动

    def test_console_delete_button_anchor(self):
        # #238：垃圾桶仅对已完成项渲染 + confirm 二次确认 + DELETE 硬删 +
        # click 委托内第四分支（防回流 change/渲染模板漏挂）
        with open(os.path.join(PROJECT_ROOT, "console.js"),
                  "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("const delBtn = t.status === 'done'", js)   # 仅 done 渲染
        self.assertIn('class="todo-del" data-id="${t.id}"', js)
        self.assertIn("${prControl}${delBtn}</li>", js)           # 模板已挂
        self.assertIn("确定删除这条已完成的待办？删除后不可恢复。", js)
        self.assertIn("fetch(`/api/todos/${tid}`, { method: 'DELETE' })", js)
        del_start = js.index("button.todo-del')")          # 分支必须在 click 委托体内
        click_start = js.index("todosListEl.addEventListener('click'")
        self.assertGreater(del_start, click_start)
        self.assertLess(del_start, js.index("addEventListener('change'", click_start))
        with open(os.path.join(PROJECT_ROOT, "index.html"),
                  "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn(".todo-del {", html)                 # 红色样式在位

    def test_console_collapsible_groups(self):
        # 尾巴 I：分区折叠——标题带 data-pr/箭头/条数、折叠分区不输出条目、
        # 状态服务端承载（WebView2 InPrivate 下 localStorage 跨启动即焚，
        # 同 first_run 方案 C 口径）
        with open(os.path.join(PROJECT_ROOT, "console.js"),
                  "r", encoding="utf-8") as f:
            js = f.read()
        self.assertIn('class="todo-group-title" data-pr="${pr}"', js)
        self.assertIn("if (collapsed) continue;", js)   # 折叠分区不输出条目
        self.assertIn("toggleGroup(title.dataset.pr)", js)
        # 回归锚（v12 死代码根因）：标题折叠必须在 click 监听器内，
        # 不得回流 change 监听器（标题无值变化，change 永不触发）
        click_start = js.index("todosListEl.addEventListener('click'")
        click_body = js[click_start:js.index("});", click_start)]
        self.assertIn("toggleGroup(title.dataset.pr)", click_body)
        change_start = js.index("todosListEl.addEventListener('change'")
        change_body = js[change_start:js.index("});", change_start)]
        self.assertNotIn("todo-group-title", change_body)
        arrow_anchor = "'%s' : '%s'" % (chr(0x25B8), chr(0x25BE))
        self.assertIn(arrow_anchor, js)                  # 折叠/展开箭头
        self.assertIn("(${group.length})", js)          # 标题显示条数
        # 服务端承载：渲染时装载下发状态、切换 POST collapsed_groups
        self.assertIn("collapsedGroups = data.collapsed_groups", js)
        self.assertIn("fetch('/api/todos/collapsed_groups', {", js)
        self.assertIn("JSON.stringify({ collapsed_groups: collapsedGroups })", js)
        # localStorage 口径退役（InPrivate 即焚，不回流）
        self.assertNotIn("todos_collapsed_groups", js)
        self.assertNotIn("readCollapsedGroups", js)

    def test_index_group_title_style(self):
        with open(os.path.join(PROJECT_ROOT, "index.html"),
                  "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("todo-group-title", html)

    def test_index_xss_guard_note(self):
        # 待办内容含 HTML 时由 escapeHtml 转义——锚定渲染处不直接插值原文
        with open(os.path.join(PROJECT_ROOT, "console.js"),
                  "r", encoding="utf-8") as f:
            js = f.read()
        self.assertNotIn("${t.content}", js)          # 禁止未转义插值

    def test_bubble_text_selectable(self):
        # 尾巴 2：气泡文本显式可选中 + 深浅两底高可见选区
        with open(os.path.join(PROJECT_ROOT, "index.html"),
                  "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn(".message,\n        .message .bubble-content {", html)
        self.assertIn("user-select: text", html)
        self.assertIn(".user-message ::selection", html)
        self.assertIn(".bot-message ::selection", html)


class BarThresholdAnchorTests(unittest.TestCase):
    """尾巴 H：CPU/内存进度条三档变色静态锚——阈值常量、各自独立判定、
    三档 CSS 类在位、旧两档硬编码退役。"""

    def _js(self):
        with open(os.path.join(PROJECT_ROOT, "console.js"),
                  "r", encoding="utf-8") as f:
            return f.read()

    def test_threshold_constants_and_branch(self):
        js = self._js()
        self.assertIn("const BAR_THRESHOLDS = { mid: 60, high: 85 };", js)
        self.assertIn("function barLevel(percent)", js)
        self.assertIn("if (percent > BAR_THRESHOLDS.high) return 'high';", js)
        self.assertIn("if (percent >= BAR_THRESHOLDS.mid) return 'mid';", js)

    def test_cpu_and_mem_independent(self):
        js = self._js()
        self.assertIn("applyBar(cpuBar, d.cpu)", js)
        self.assertIn("applyBar(memBar, d.memory)", js)   # 内存独立三档（旧版无变色）

    def test_three_level_css_classes(self):
        with open(os.path.join(PROJECT_ROOT, "index.html"),
                  "r", encoding="utf-8") as f:
            html = f.read()
        for cls in (".stat-bar-fill.bar-low", ".stat-bar-fill.bar-mid",
                    ".stat-bar-fill.bar-high"):
            self.assertIn(cls, html)
        js = self._js()
        self.assertIn("barEl.classList.add('bar-' + level)", js)
        # 旧两档硬编码退役
        self.assertNotIn("d.cpu > 80 ? '#e0433f' : '#2fa24c'", js)
        self.assertNotIn("d.memory > 80 ? '#e0433f' : '#2fa24c'", js)


class TodoCommandInterceptTests(unittest.TestCase):
    """控制台待办指令拦截（2026-10-04 Bug 1 修复）：/api/chat 命中 todo 指令族
    时不进模型（smart_ask 零调用），门禁与 QQ 路径同一份（main.handle_todo_command）；
    非待办消息照常进模型（拦截透明）。尾巴 3：指令回复带 <think> 过程卡片。"""


class ThinkProgressiveAnchorTests(unittest.TestCase):
    """尾巴 2：思维链渐进展示静态锚——进行中展开（打字机）、完成后自动折叠、
    手动可重开，三类来源（模型/指令/工具）共用 appendBotMessage 单渲染管线。"""

    def _js(self):
        with open(os.path.join(PROJECT_ROOT, "console.js"),
                  "r", encoding="utf-8") as f:
            return f.read()

    def test_progressive_pipeline_intact(self):
        js = self._js()
        # 进行中展开：新消息默认走打字机动画（animateThink !== false）
        self.assertIn("startThinkTypewriter(botMsg, thinkParts.think, options.animateThink !== false)", js)
        # 完成后自动折叠：打完 → 延时 → 动画折叠 → think-collapsed
        self.assertIn("scheduleThinkCollapse(card, msgEl)", js)
        self.assertIn("think-collapsed", js)
        # 手动可重开：折叠态点击标题可再展开（toggle 处理在位）
        self.assertIn("think-card-header", js)

    def test_command_reply_shares_same_pipeline(self):
        # 指令/模型回复同一渲染单点：sendMessage 对 /api/chat 的返回无差别
        # 走 appendBotMessage（⚙️ 指令的 <think> 因此自动获得同款渐进卡片）
        js = self._js()
        self.assertIn("appendBotMessage(res.data.reply, res.data.source, text)", js)

    def test_history_replay_stays_collapsed(self):
        # 历史回放 animateThink:false 直接折叠全文——正确的非渐进特例，防误改
        js = self._js()
        self.assertIn("animateThink: false", js)


class TodoCommandInterceptTests(unittest.TestCase):
    """控制台待办指令拦截（2026-10-04 Bug 1 修复）：/api/chat 命中 todo 指令族
    时不进模型（smart_ask 零调用），门禁与 QQ 路径同一份（main.handle_todo_command）；
    非待办消息照常进模型（拦截透明）。尾巴 3：指令回复带 <think> 过程卡片。"""

    URL = "https://chat.deepseek.com/share/abc123"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_dash_cmd_")
        self.sm = StateManager(base_dir=self.tmp)
        self.pm = PermissionManager()
        self._patches = [
            mock.patch("xiaoju3_dashboard.state_manager", self.sm),
            mock.patch("xiaoju3_dashboard.smart_ask"),
            mock.patch("main.state_manager", self.sm),
            mock.patch("main.permission_manager", self.pm),
            mock.patch("main.extract_todos_from_url_sync"),
            mock.patch("main.check_recent_url", return_value=False),
            mock.patch("main.mark_url"),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)
        self.client = dashboard.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _chat(self, msg):
        resp = self.client.post("/api/chat", json={"message": msg, "history": []})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        return data["reply"], data["source"]

    @staticmethod
    def _body(reply):
        """取 <think> 包裹后的正文（尾巴 3：指令回复带过程卡片）。"""
        assert "<think>" in reply and "</think>" in reply, reply
        return reply.split("</think>", 1)[1]

    def test_todos_lv1_rejected_without_model(self):
        self.pm.current_level = "Lv.1"
        reply, source = self._chat("/todos")
        body = self._body(reply)
        self.assertTrue(body.startswith("❌"))
        self.assertIn("Lv.2", body)
        self.assertIn("门禁拒绝：需要 Lv.2，当前 Lv.1", reply)   # 过程卡片步骤
        self.assertEqual(source, "⚙️ 指令")
        dashboard.smart_ask.assert_not_called()

    def test_todo_from_link_lv1_rejected_without_model(self):
        self.pm.current_level = "Lv.1"
        reply, source = self._chat(f"/todo_from_link {self.URL}")
        body = self._body(reply)
        self.assertTrue(body.startswith("❌"))
        self.assertIn("Lv.2", body)
        self.assertIn("收到指令 /todo_from_link", reply)
        self.assertEqual(source, "⚙️ 指令")
        dashboard.smart_ask.assert_not_called()

    def test_todos_lv2_lists_from_shared_store(self):
        self.pm.current_level = "Lv.2"
        self.sm.save_todos(["A", "B"], source_url="u1")
        self.sm.complete_todo(1)
        reply, source = self._chat("/todos")
        body = self._body(reply)
        self.assertIn("未完成 1 条", body)
        self.assertIn("#2 [P1] B", body)   # 尾巴 C：清单带优先级前缀
        self.assertIn("查询待办：未完成 1 条 / 已完成 1 条", reply)   # 过程步骤
        self.assertEqual(source, "⚙️ 指令")
        dashboard.smart_ask.assert_not_called()

    def test_todo_from_link_lv2_accepted_background(self):
        self.pm.current_level = "Lv.2"
        extract_mock = mock.MagicMock(return_value={"ok": True, "inserted": 1})
        with mock.patch("main.threading.Thread", _immediate_thread()), \
                mock.patch("main.extract_todos_from_url_sync", extract_mock):
            reply, source = self._chat(f"/todo_from_link {self.URL}")
        body = self._body(reply)
        self.assertTrue(body.startswith("🔄"))
        self.assertIn("后台提取线程已启动", reply)   # 过程步骤
        self.assertEqual(source, "⚙️ 指令")
        extract_mock.assert_called_once_with(
            self.URL, mock.ANY, mock.ANY, notify=mock.ANY)
        dashboard.smart_ask.assert_not_called()

    def test_non_todo_message_reaches_model(self):
        self.pm.current_level = "Lv.2"
        dashboard.smart_ask.return_value = ("模型回复", "☁️ 云端")
        reply, source = self._chat("今天天气怎么样")
        self.assertEqual(reply, "模型回复")
        dashboard.smart_ask.assert_called_once()

    def test_handle_todo_command_signature_has_steps_outparam(self):
        # 尾巴 3 锚：steps 出参在签名上（QQ 链路不传=行为不变，控制台传=收步骤）
        import inspect
        params = inspect.signature(main.handle_todo_command).parameters
        self.assertIn("steps", params)
        self.assertEqual(params["steps"].default, None)


def _immediate_thread():
    """把 Thread 换成同步执行（同 test_main 待办指令测试口径）。"""

    class ImmediateThread:
        def __init__(self, target=None, args=(), kwargs=None, daemon=None):
            if target:
                target(*args, **(kwargs or {}))

        def start(self):
            pass

    return ImmediateThread


class FrozenSpecPlaywrightAnchorTests(unittest.TestCase):
    """spec 收录 playwright 静态锚（2026-10-04 拍板②方案 A）：excludes 除名 +
    collect_all 在位——防回退到"exe 不打 playwright"旧口径（那会让待办提取
    在冻结形态永远抓不了页面）。"""

    def _spec_text(self):
        with open(os.path.join(PROJECT_ROOT, "xiaoju3.spec"),
                  "r", encoding="utf-8") as f:
            return f.read()

    def test_playwright_not_in_excludes(self):
        spec = self._spec_text()
        excludes_start = spec.index("excludes=[")
        excludes_end = spec.index("]", excludes_start)
        self.assertNotIn("playwright", spec[excludes_start:excludes_end])

    def test_collect_all_wired_into_analysis(self):
        spec = self._spec_text()
        self.assertIn("collect_all('playwright')", spec)
        self.assertIn("binaries=pw_binaries", spec)
        self.assertIn("+ pw_datas", spec)
        self.assertIn("+ pw_hiddenimports", spec)


class OpenAiPreheatAnchorTests(unittest.TestCase):
    """openai 后台预热接线静态锚（2026-10-04 启动优化拍板①）：dashboard
    serve() 在 app.run 前调 vision_tools.preheat_openai_async()——防预热
    挂钩被误删回退到"视觉首用卡 ≈0.6s 导入"的旧口径。"""

    def test_serve_calls_preheat_before_app_run(self):
        with open(os.path.join(PROJECT_ROOT, "xiaoju3_dashboard.py"),
                  "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("import vision_tools", src)
        call_at = src.index("vision_tools.preheat_openai_async()")
        app_run_at = src.index("app.run(host=")
        self.assertLess(call_at, app_run_at)


class ConnectingHintAnchorTests(unittest.TestCase):
    """前端失败加载态锚（2026-10-04 启动优化拍板② B/C 小补）：console.js
    fetchStatus/loadTodos 失败 catch 调 markConnecting()——失败显"连接中…"
    而非静止旧值像"没数据"（下一轮 2s/30s 轮询自愈，无重试逻辑）。"""

    def _console_js(self):
        with open(os.path.join(PROJECT_ROOT, "console.js"), "r",
                  encoding="utf-8") as f:
            return f.read()

    def test_markconnecting_defined_and_wired_to_both_catches(self):
        js = self._console_js()
        self.assertIn("function markConnecting()", js)
        self.assertIn("'连接中…'", js)
        status_at = js.index("console.error('获取系统状态失败', err)")
        todos_at = js.index("console.error('获取待办失败', err)")
        self.assertIn("markConnecting()", js[status_at:status_at + 200])
        self.assertIn("markConnecting()", js[todos_at:todos_at + 200])


if __name__ == "__main__":
    unittest.main()
