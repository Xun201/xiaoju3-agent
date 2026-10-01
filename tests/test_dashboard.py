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
- 思维链前端展示（<think> 块）：console.js 解析切分（先切分后转义、正则
  非锚定——reply 含块即必出卡片）、
  渲染入口先判 thinkMatch（无 think 不插卡片、普通聊天零干扰）、思考
  卡片逐字打字（textContent 注入防注入）+ 打完自动折叠/点击展开、历史
  回放不打字、刷新重生成同步卡片、等待期 900ms 轮换状态；index.html
  .think-card / .think-card-header / .think-card-body 浅灰折叠样式。

mock 注意：所有 patch 均走 context manager / start+addCleanup（结束即还原），
不污染 sys.modules；历史文件一律注入 tmp 目录，可与其它测试文件在同一
进程中共存。
"""
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
import warnings
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import prompts  # noqa: E402
import web_sanitize  # noqa: E402
import xiaoju3  # noqa: E402
import xiaoju3_dashboard as dashboard  # noqa: E402


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
                         {"cpu", "memory", "temperature", "timestamp"})
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

        with mock.patch.object(dashboard, "psutil", fake_psutil), _quiet():
            resp = self.client.get("/api/status")

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(set(data.keys()),
                         {"cpu", "memory", "temperature", "timestamp"})
        self.assertEqual(data["cpu"], 0.0)
        self.assertEqual(data["memory"], 0.0)
        self.assertEqual(data["temperature"], 0.0)
        self.assertIsInstance(data["timestamp"], int)

    def test_status_sensors_empty_fallback(self):
        """sensors_temperatures 返回空：温度回退 0.0。"""
        fake_psutil = mock.Mock()
        fake_psutil.cpu_percent.return_value = 10.0
        fake_psutil.virtual_memory.return_value = mock.Mock(percent=20.0)
        fake_psutil.sensors_temperatures.return_value = {}

        with mock.patch.object(dashboard, "psutil", fake_psutil):
            data = self.client.get("/api/status").get_json()["data"]

        self.assertEqual(data["temperature"], 0.0)
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
            "xiaoju3-root",                      # 桌宠容器
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
        self.assertIn("d.cpu > 80", js)                       # >80% 阈值
        self.assertIn("d.memory > 80", js)
        self.assertIn("'#e0433f'", js)                        # 变红
        self.assertIn("'#2fa24c'", js)                        # 正常绿
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

    契约：brain.smart_ask 工具调用流程在 reply 最前面包装 <think>...</think>
    （内含 [思考]/[计划] 文本）；普通聊天回复没有该块——前端不渲染思考卡片。
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
        串首而静默漏卡；剔除按 thinkMatch.index 定位，块前字符保留进正文。"""
        js = self.console_js
        self.assertIn("/<think>([\\s\\S]*?)<\\/think>/", js)   # 非锚定正则
        self.assertNotIn("/^\\s*<think>", js)                  # 不再锚定串首
        self.assertIn("thinkMatch.index", js)                  # 按命中位置剔块

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


if __name__ == "__main__":
    unittest.main()
