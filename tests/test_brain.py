# -*- coding: utf-8 -*-
"""brain 双脑决策层单元测试（全部离线，requests 全 mock）。

覆盖（任务口径）：
- ask_local / ask_cloud 请求结构与超时、异常传播与错误文案；
  LLM_TEMPERATURE 采样温度（默认 0.7、env 覆盖、两后端 payload 落点）；
- 本地探测成功 → ask_local；探测失败 / ask_local 异常 → 热切换 ask_cloud；
  双脑全挂的报错文案；
- 工具 JSON 正则提取（正常 / 夹在文字中 / 多行 / 非 JSON）、白名单外工具
  被拒、工具结果喂回汇总轮（本地优先：成功走 ask_local，异常/不可用转
  ask_cloud）、每轮最多一次工具调用、❌ 开头结果切断重试；
- 防死循环熔断：同一工具 + 等价参数连续被拒达阈值 → 强制打断、剥夺工具
  调用权退回纯文本；换参数/成功执行归零；reset 接口；阈值可配；
- 思维链 <think> 包装（前端推理卡片契约）：工具调用发生（解析出 JSON 且
  执行）时最终 reply 最前面包装捕获的 [思考]/[计划] 文本，模型没输出时按
  实际解析出的工具名动态生成占位符"[思考] 准备调用 {工具名} 尝试完成
  操作."（解析不出工具名回退固定占位符）；❌ 切断/熔断通知同属工具流程
  同样包装；全对话强制包装（2026-10-01 用户指令，废止旧"普通聊天零包装"
  口径）：_seal_bare_cot 对 smart_ask 全部自然语言回复出口封口——旁路普通
  回复/URL 总结/熔断剥夺路径捕获到原生思考用原生，残缺形态回退工具占位符
  （正文剥空由 _wrap_think 正文回补——真实回复从思考卡提升回正文——回补
  不了以"操作已完成。"兜底，"（操作已执行）"绝不作为正文出现；正文已以
  <think> 开头防重入不二次
  包）；无任何标记的普通闲聊注入 CHAT_THINKING_PLACEHOLDER 默认占位符
  （"[思考] 正在理解你的意图..."）；抓取失败/双脑全挂/空回复等固定文案
  同样注入默认占位符；CoT 花括号内容
  不干扰 JSON 提取（贪婪正则失败回退逐 { raw_decode 扫描）；[CoT] 终端日志
  （兜底占位符注入 / 模型原生思考输出各一条，redirect_stdout 捕获）；
  游离标签防御：包装统一走 _wrap_think——thinking/body 两侧剥除模型自吐
  的 <think>/</think> 字面量 + 拼装后成对校验，恰一对标签且在最前；
  成对保证（ThinkPairGuaranteeTests，2026-10-01 修复"你好"网页直出纯文本
  <think>）：空思考注入默认占位符、模型自吐无闭合开标签的防重入透传
  先做成对校验（残缺修复/完整透传）、用户指定 re.search 最终门禁 +
  重拼/纯文本两级兜底；WRAPPED_TEXT 输出诊断日志（_wrap_think 最终
  return 前、每条一行、300 字符截断，与返回 reply 逐字对账）；
  下发通道实测（WebExitThinkTagContractTests）：仪表盘 sanitize_for_web
  标签完好存活、QQ/旧页 _strip_think 设计性整块剥标；
- 裸 CoT 泄漏扫描总测试（BareCotLeakSweepTests，P2 "穷举封死"）：smart_ask
  全部 11 条 return 路径参数化扫描——ui_tap→vision 回退分支汇总轮复读裸
  CoT（用户实测"帮我点击蓝牙"漏点，_seal_tool_summary 修复）、[行动] 残缺
  形态（_seal_bare_cot 任意标记触发）、❌ 切断防御 strip、回退分支端到端
  （真实 tools.execute_tool 分发）等，逐条断言无裸 [思考]/[计划]/[行动]
  漏出（判定口径见该类 docstring）；
- URL 输入触发网页抓取（script/style 被剔除）；
- MAX_MESSAGES=50 截断；translate_emoji 转换正确且已接入 smart_ask 回复链；
- smart_ask 返回二元组与来源标签（🏠 本地 / ☁️ 云端 / (工具) / ⛔ 熔断）正确；
- _build_messages 前缀白名单：最近设备操作记录 system 条目保留注入，
  既有【前情提要】/长期记忆前缀不回退；
- W1 核心功能接线（2026-10-01）：前情提要压缩（>20 条 → compress_context
  前情提要 + 最近 10 条明细；缓存持久化命中复用 / 历史变化失效重压 /
  压缩失败降级硬截断 / 缓存损坏重压）；长期记忆（关键词规则落库
  preference/event、回答前 get_recent_memories(5) 注入、SQLite 异常静默、
  与 main 先行注入不重复）；表情降级（下载失败/模块缺席/链路异常 →
  "[表情: 标签]"纯文本，绝不再返回未转换的 [EMOJI: 原文）。

外部模块（home_tools / adb_tools / vision_tools / android_ui_tools）由并行
开发负责，与 tests/test_tools.py 相同：在 import brain（→ tools）之前向
sys.modules 注入 mock；emoji_manager 用 patch.dict 按需注入；
agent_state.state_manager 由 setUpModule 注入进程内 fake（测试期全局生效、
tearDownModule 还原）——brain 对它是函数内延迟导入，不拦截会触碰真实
agent_state/long_term.db（隔离区红线），且真实库有历史记忆时会污染
消息结构断言。
"""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


_MISSING = object()


def _install_mock_modules():
    """注入 tools.py 的四个外围依赖 mock（必须在 import brain 之前）。

    返回注入前的 sys.modules 快照，供 import brain 之后还原，避免污染
    同进程内后续加载、需要真实模块的其它测试。
    """
    saved = {}
    for name in ("home_tools", "adb_tools", "vision_tools", "android_ui_tools"):
        saved[name] = sys.modules.get(name, _MISSING)
        sys.modules.pop(name, None)

    home_tools = types.ModuleType("home_tools")
    home_tools.get_ha_devices = lambda: "【mock】设备列表：light.test=on"
    home_tools.control_ha_device = lambda entity_id, action: f"【mock】已对 {entity_id} 执行 {action}"
    # 高危实体分类（与真实 home_tools.is_dangerous_entity 同语义：lock.*/gas/燃气）。
    # 必须与真实模块同步：tools.py 在本测试进程内 import 的 home_tools 是这里的
    # mock，若缺该属性，test_main 的 /confirm 链路（真实 tools.execute_tool）会
    # 因 AttributeError 误报失败（组合运行顺序：test_brain 先于 test_main）。
    home_tools.is_dangerous_entity = lambda entity_id: (
        str(entity_id or "").lower().split(".", 1)[0] == "lock"
        or "gas" in str(entity_id or "").lower()
        or "燃气" in str(entity_id or ""))
    sys.modules["home_tools"] = home_tools

    adb_tools = types.ModuleType("adb_tools")
    adb_tools.adb_screenshot = lambda: "【mock】截图已保存"
    adb_tools.adb_tap = lambda x, y: f"【mock】点击 {x},{y}"
    adb_tools.adb_swipe = lambda x1, y1, x2, y2: f"【mock】滑动 {x1},{y1}->{x2},{y2}"
    sys.modules["adb_tools"] = adb_tools

    vision_tools = types.ModuleType("vision_tools")
    vision_tools.vision_tap_element = lambda name: f"【mock】视觉点击 {name}"
    sys.modules["vision_tools"] = vision_tools

    android_ui_tools = types.ModuleType("android_ui_tools")
    android_ui_tools.ui_tap_element = lambda name: f"【mock】UI 点击 {name}"
    sys.modules["android_ui_tools"] = android_ui_tools

    # emoji_manager 走函数内延迟导入，各测试按需 patch.dict 注入
    saved["emoji_manager"] = sys.modules.get("emoji_manager", _MISSING)
    sys.modules.pop("emoji_manager", None)
    return saved


_SAVED_MODULES = _install_mock_modules()

import brain  # noqa: E402
import prompts  # noqa: E402
import xiaoju3  # noqa: E402

# brain（→ tools）已完成导入，tools 内部绑定到此处的 mock；立刻还原
# sys.modules，避免污染同一进程中随后加载的其它测试模块
# （如 test_home_tools / test_adb_tools 需要导入真实模块）。
for _name, _old in _SAVED_MODULES.items():
    if _old is _MISSING:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _old


# ---------------------------------------------------------------------------
# agent_state.state_manager 进程内 fake（本模块测试期全局生效）
# ---------------------------------------------------------------------------

_STATE_FAKE = None
_STATE_FAKE_PATCHER = None


def setUpModule():
    """挂载 agent_state / agent_state.state_manager 的进程内 fake。

    brain 对长期记忆是函数内延迟导入：不拦截的话，任意一次 smart_ask 都会
    触碰真实 agent_state/long_term.db（违反隔离区红线），且真实库有历史
    记忆时会向模型消息注入记忆条目、破坏既有断言。tearDownModule 还原，
    不影响其它测试模块；记忆专项用例经 _STATE_FAKE 操控 fake。
    """
    global _STATE_FAKE, _STATE_FAKE_PATCHER
    fake_pkg = types.ModuleType("agent_state")
    fake_pkg.__path__ = []  # 标记为包，杜绝真实文件系统查找
    fake_mod = types.ModuleType("agent_state.state_manager")
    fake_mod.state_manager = mock.MagicMock(name="state_manager")
    fake_mod.state_manager.get_recent_memories.return_value = []
    fake_mod.state_manager.save_memory.return_value = None
    fake_pkg.state_manager = fake_mod
    _STATE_FAKE = fake_mod
    _STATE_FAKE_PATCHER = mock.patch.dict(sys.modules, {
        "agent_state": fake_pkg,
        "agent_state.state_manager": fake_mod,
    })
    _STATE_FAKE_PATCHER.start()


def tearDownModule():
    """还原 sys.modules，真实 agent_state.state_manager 对后续模块可见。"""
    global _STATE_FAKE, _STATE_FAKE_PATCHER
    if _STATE_FAKE_PATCHER is not None:
        _STATE_FAKE_PATCHER.stop()
    _STATE_FAKE_PATCHER = None
    _STATE_FAKE = None


# ---------------------------------------------------------------------------
# 公共工具
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _quiet():
    """吞掉 brain 的进度 print（含 emoji），保持测试输出干净。"""
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _resp(payload):
    """构造 requests.Response 替身。"""
    resp = mock.Mock()
    resp.json.return_value = payload
    resp.raise_for_status = mock.Mock()
    return resp


def _local_resp(content):
    """Ollama /api/chat 响应结构。"""
    return _resp({"message": {"content": content}})


def _cloud_resp(content):
    """DeepSeek /chat/completions 响应结构。"""
    return _resp({"choices": [{"message": {"content": content}}]})


class _DenyPermissionManager:
    """恒拒绝的权限管理器替身（验证 LV1 高危门禁联动）。"""

    current_level = "Lv.1"

    def has_permission(self, action):
        return False


# ---------------------------------------------------------------------------
# ask_local / ask_cloud / probe_local
# ---------------------------------------------------------------------------

class AskLocalTests(unittest.TestCase):
    """ask_local：POST LOCAL_URL，Ollama /api/chat 结构，异常向上抛。"""

    def test_request_structure_and_timeout(self):
        with mock.patch.object(brain, "requests") as mr:
            mr.post.return_value = _local_resp("本地回答")
            msgs = [{"role": "user", "content": "你好"}]
            self.assertEqual(brain.ask_local(msgs), "本地回答")

            mr.post.assert_called_once()
            args, kwargs = mr.post.call_args
            self.assertEqual(args[0], xiaoju3.LOCAL_URL)
            self.assertEqual(kwargs["json"], {"model": xiaoju3.LOCAL_MODEL,
                                              "messages": msgs, "stream": False,
                                              "keep_alive": -1,
                                              "options": {"temperature":
                                                          brain.LLM_TEMPERATURE}})
            self.assertEqual(kwargs["timeout"], brain.LOCAL_GENERATE_TIMEOUT)

    def test_exception_propagates(self):
        # 异常向上抛（由 smart_ask 热切换云端）
        with mock.patch.object(brain, "requests") as mr:
            mr.post.side_effect = ConnectionError("boom")
            with self.assertRaises(ConnectionError):
                brain.ask_local([{"role": "user", "content": "hi"}])


class AskCloudTests(unittest.TestCase):
    """ask_cloud：Bearer 鉴权、choices 解析、API 报错与连接异常文案。"""

    def test_request_structure_and_timeout(self):
        with mock.patch.object(brain, "requests") as mr:
            mr.post.return_value = _cloud_resp("云端回答")
            msgs = [{"role": "user", "content": "你好"}]
            self.assertEqual(brain.ask_cloud(msgs), "云端回答")

            args, kwargs = mr.post.call_args
            self.assertEqual(args[0], xiaoju3.CLOUD_URL)
            self.assertEqual(kwargs["headers"]["Authorization"],
                             f"Bearer {brain.CLOUD_KEY}")
            self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
            self.assertEqual(kwargs["json"], {"model": xiaoju3.CLOUD_MODEL,
                                              "messages": msgs, "stream": False,
                                              "temperature": brain.LLM_TEMPERATURE})
            self.assertEqual(kwargs["timeout"], brain.CLOUD_TIMEOUT)
            mr.post.return_value.raise_for_status.assert_called_once()

    def test_api_error_dict_detail(self):
        with mock.patch.object(brain, "requests") as mr:
            mr.post.return_value = _resp({"error": {"message": "余额不足"}})
            self.assertEqual(brain.ask_cloud([]), "⚠️ API接口报错: 余额不足")

    def test_api_error_non_dict(self):
        with mock.patch.object(brain, "requests") as mr:
            mr.post.return_value = _resp({"error": "model not found"})
            self.assertEqual(brain.ask_cloud([]), "⚠️ API接口报错: model not found")

    def test_api_error_missing_detail(self):
        with mock.patch.object(brain, "requests") as mr:
            mr.post.return_value = _resp({"unexpected": True})
            self.assertEqual(brain.ask_cloud([]), "⚠️ API接口报错: 未知错误")

    def test_connection_exception_returns_warning_text(self):
        # ask_cloud 不抛异常，把连接异常转成 ⚠️ 文案（参考实现口径）
        with mock.patch.object(brain, "requests") as mr:
            mr.post.side_effect = Exception("refused")
            self.assertEqual(brain.ask_cloud([]), "⚠️ 云端连接异常: refused")

    def test_http_status_error_returns_warning_text(self):
        with mock.patch.object(brain, "requests") as mr:
            resp = _cloud_resp("x")
            resp.raise_for_status.side_effect = Exception("500 Server Error")
            mr.post.return_value = resp
            self.assertEqual(brain.ask_cloud([]),
                             "⚠️ 云端连接异常: 500 Server Error")


class TemperatureConfigTests(unittest.TestCase):
    """LLM_TEMPERATURE：默认 0.7；env LLM_TEMPERATURE 可覆盖（float 容错）；
    两个后端的 payload 落点不同（Ollama 嵌套 options / DeepSeek 顶层）。"""

    def test_module_constant_is_float_default_0_7(self):
        self.assertIsInstance(brain.LLM_TEMPERATURE, float)
        self.assertAlmostEqual(brain.LLM_TEMPERATURE, 0.7)

    def _read_const_in_subprocess(self, env_value=None):
        """子进程读取 brain.LLM_TEMPERATURE（env 覆盖手法参照
        test_cli_config.HardwareAdaptiveConfigTests.test_env_override）。"""
        import subprocess
        env = dict(os.environ)
        env.pop("LLM_TEMPERATURE", None)
        if env_value is not None:
            env["LLM_TEMPERATURE"] = env_value
        code = "import brain; print(brain.LLM_TEMPERATURE)"
        out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, env=env,
                             cwd=os.path.dirname(os.path.dirname(
                                 os.path.abspath(__file__))))
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout.strip()

    def test_env_override_via_subprocess(self):
        self.assertEqual(self._read_const_in_subprocess("0.2"), "0.2")

    def test_invalid_env_falls_back_to_default(self):
        # float 解析容错：非数字回退 0.7，不让 import 崩溃
        self.assertEqual(self._read_const_in_subprocess("not-a-number"), "0.7")

    def test_payload_placement_both_backends(self):
        # Ollama /api/chat：嵌套 options.temperature；DeepSeek：顶层 temperature
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "LLM_TEMPERATURE", 0.35):
            mr.post.return_value = _local_resp("本地回答")
            brain.ask_local([{"role": "user", "content": "hi"}])
            local_json = mr.post.call_args.kwargs["json"]
            self.assertEqual(local_json["options"], {"temperature": 0.35})

            mr.post.return_value = _cloud_resp("云端回答")
            brain.ask_cloud([{"role": "user", "content": "hi"}])
            cloud_json = mr.post.call_args.kwargs["json"]
            self.assertEqual(cloud_json["temperature"], 0.35)
            self.assertNotIn("options", cloud_json)


class ProbeLocalTests(unittest.TestCase):
    """probe_local：约 1 秒（LOCAL_TIMEOUT）探测 LOCAL_PROBE_URL。"""

    def test_online_returns_true(self):
        with mock.patch.object(brain, "requests") as mr:
            mr.get.return_value = mock.Mock()
            self.assertTrue(brain.probe_local())
            args, kwargs = mr.get.call_args
            self.assertEqual(args[0], xiaoju3.LOCAL_PROBE_URL)
            self.assertEqual(kwargs["timeout"], xiaoju3.LOCAL_TIMEOUT)

    def test_offline_returns_false(self):
        with mock.patch.object(brain, "requests") as mr:
            mr.get.side_effect = OSError("refused")
            self.assertFalse(brain.probe_local())


# ---------------------------------------------------------------------------
# smart_ask：双脑路由与来源标签
# ---------------------------------------------------------------------------

class SmartAskRoutingTests(unittest.TestCase):
    """本地优先 / 热切换 / 双脑全挂 / 消息组装 / 来源标签。"""

    def setUp(self):
        # 硬件自适应路由默认档位固定为 high，保证既有用例确定性（档位专项见
        # HardwareAdaptiveRoutingTests）
        tp = mock.patch.object(brain, "_resolve_tier", return_value="high")
        tp.start()
        self.addCleanup(tp.stop)

    def test_probe_ok_uses_local_and_label(self):
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            mr.get.return_value = mock.Mock()          # 探测成功
            mr.post.return_value = _local_resp("你好呀，我是小橘！")
            result = brain.smart_ask("你好", [])

        # 全对话强制包装：普通闲聊无原生思考 → 注入默认占位符包装
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>你好呀，我是小橘！",
             "🏠 本地"))
        mcloud.assert_not_called()                     # 本地可用时不惊动云端
        args, kwargs = mr.post.call_args
        self.assertEqual(args[0], xiaoju3.LOCAL_URL)
        self.assertEqual(kwargs["json"]["model"], xiaoju3.LOCAL_MODEL)
        self.assertEqual(kwargs["json"]["stream"], False)

    def test_probe_fail_hot_switch_to_cloud(self):
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.side_effect = OSError("refused")    # 探测失败
            mr.post.return_value = _cloud_resp("云端回答")
            result = brain.smart_ask("你好", [])

        # 全对话强制包装：云端热切换的普通回复同样注入默认占位符
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>云端回答", "☁️ 云端"))
        args, _ = mr.post.call_args
        self.assertEqual(args[0], xiaoju3.CLOUD_URL)

    def test_local_exception_hot_switch_to_cloud(self):
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()          # 探测成功
            mr.post.side_effect = [ConnectionError("本地挂了"), _cloud_resp("云端回答")]
            result = brain.smart_ask("你好", [])

        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>云端回答", "☁️ 云端"))
        self.assertEqual(mr.post.call_count, 2)

    def test_both_brains_down_error_message(self):
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.side_effect = OSError("探测失败")
            mr.post.side_effect = Exception("network down")
            reply, source = brain.smart_ask("你好", [])

        # 全对话强制包装：双脑全挂的固定失败文案同样注入默认占位符
        self.assertTrue(reply.startswith(
            f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>"), reply)
        self.assertIn("❌ 大脑连接失败，请检查网络。错误：", reply)
        self.assertIn("云端连接异常", reply)
        self.assertEqual(source, "❌ 失败")

    def test_system_prompt_on_top(self):
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("好")
            brain.smart_ask("早", [])

        msgs = mr.post.call_args.kwargs["json"]["messages"]
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[0]["content"], prompts.SYSTEM_PROMPT["content"])
        # 2026-10-02 位置隐私模式：+【主人位置】系统上下文（紧跟置顶提示词）
        self.assertTrue(msgs[1]["content"].startswith("【主人位置】"))
        self.assertEqual(sum(1 for m in msgs if m["role"] == "system"), 2)
        self.assertEqual(msgs[-1], {"role": "user", "content": "早"})

    def test_history_system_prompt_not_duplicated(self):
        # 调用方传入 [SYSTEM_PROMPT] + 历史（参考实现口径）→ 不出现第二条 system
        history = [dict(prompts.SYSTEM_PROMPT),
                   {"role": "user", "content": "昨天聊到哪了"},
                   {"role": "assistant", "content": "聊到记忆压缩"}]
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("继续聊呀")
            brain.smart_ask("那继续", history)

        msgs = mr.post.call_args.kwargs["json"]["messages"]
        # 2026-10-02 位置隐私模式：+【主人位置】系统上下文（不与历史重复）
        self.assertEqual(sum(1 for m in msgs if m["role"] == "system"), 2)
        self.assertTrue(msgs[1]["content"].startswith("【主人位置】"))
        self.assertEqual([m["content"] for m in msgs[2:]],
                         ["昨天聊到哪了", "聊到记忆压缩", "那继续"])

    def test_history_with_pre_appended_user_message_dedup(self):
        # 参考实现口径：调用方先把用户消息 append 进 history 再调用 → 去重
        history = [{"role": "user", "content": "你好"}]
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("你好呀")
            brain.smart_ask("你好", history)

        msgs = mr.post.call_args.kwargs["json"]["messages"]
        self.assertEqual(len(msgs), 3)  # system + 【主人位置】 + 去重后的 user
        self.assertEqual(msgs[-1]["content"], "你好")

    def test_history_not_mutated(self):
        history = [{"role": "user", "content": "你好"}]
        snapshot = [dict(m) for m in history]
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("好")
            brain.smart_ask("你好", history)
        self.assertEqual(history, snapshot)

    def test_empty_local_reply_fallback_text(self):
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("")
            result = brain.smart_ask("你好", [])
        # 全对话强制包装：空回复道歉文案同样注入默认占位符
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>"
             "抱歉，小橘3号刚才脑袋短路了，请再说一遍吧。", "🏠 本地"))

    def test_result_is_always_tuple_of_two(self):
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("好")
            self.assertEqual(
                brain.smart_ask("你好", []),
                (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>好", "🏠 本地"))
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.side_effect = OSError("探测失败")
            mr.post.side_effect = Exception("network down")
            result = brain.smart_ask("你好", [])
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)


# ---------------------------------------------------------------------------
# smart_ask：工具调用协议
# ---------------------------------------------------------------------------

def _run_tool_flow(raw_reply, tool_result="✅ 已完成",
                   summary_reply="已经帮你弄好了", probe_ok=True):
    """探测 + 本地首轮返回 raw_reply 的公共流程（模块级，供多个用例类复用）。

    mr.post 依次返回两轮响应（首轮工具 JSON、次轮本地汇总文本）；
    ask_cloud 打桩兜底（本地优先路径下不应被调用）。
    返回 (result, mexec, mcloud, mr)。
    """
    with mock.patch.object(brain, "requests") as mr, \
            mock.patch.object(brain, "execute_tool") as mexec, \
            mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
        if probe_ok:
            mr.get.return_value = mock.Mock()
        else:
            mr.get.side_effect = OSError("refused")
        mr.post.side_effect = [_local_resp(raw_reply),
                               _local_resp(summary_reply)]
        mexec.return_value = tool_result
        mcloud.return_value = summary_reply
        result = brain.smart_ask("帮我操作", [])
    return result, mexec, mcloud, mr


class SmartAskToolTests(unittest.TestCase):
    """JSON 提取、白名单校验、喂回汇总轮（本地优先）、❌ 切断、每轮一次工具调用。"""

    def setUp(self):
        # 工具流程会写熔断计数，用例间互不串扰
        brain.tool_fuse.reset()
        tp = mock.patch.object(brain, "_resolve_tier", return_value="high")
        tp.start()
        self.addCleanup(tp.stop)

    def tearDown(self):
        brain.tool_fuse.reset()

    def test_whitelist_matches_thirteen_tools(self):
        self.assertEqual(
            sorted(brain.TOOL_WHITELIST),
            sorted(["list_files", "read_file", "write_file", "get_ha_devices",
                    "control_ha_device", "adb_tap", "adb_swipe", "adb_screenshot",
                    "vision_tap_element", "ui_tap_element", "web_search",
                    "system_manage", "read_core_memory"]))

    def test_build_messages_keeps_wired_system_entries(self):
        """前情提要/长期记忆注入的 system 条目应保留，其余 system 剔除（§10 #2/#3 接线）。"""
        history = [
            {"role": "system", "content": "【前情提要】用户此前聊过装修与养猫。"},
            {"role": "system", "content": "以下是关于用户的长期记忆：喜欢橙色。"},
            {"role": "system", "content": "来路不明的系统指令"},
            {"role": "user", "content": "早上好"},
        ]
        msgs = brain._build_messages("在吗", history)
        system_texts = [m["content"] for m in msgs if m["role"] == "system"]
        self.assertEqual(len(system_texts), 3)  # 置顶提示词 + 两条合法注入
        self.assertIn("【前情提要】用户此前聊过装修与养猫。", system_texts)
        self.assertIn("以下是关于用户的长期记忆：喜欢橙色。", system_texts)
        self.assertNotIn("来路不明的系统指令", system_texts)
        self.assertEqual(msgs[-1], {"role": "user", "content": "在吗"})

    def test_plain_json_tool_executed_and_summarized_by_local(self):
        # 汇总轮本地优先（§10 #14）：探测在线 → ask_local 汇总成功
        raw = '{"tool": "list_files", "args": {}}'
        result, mexec, mcloud, mr = _run_tool_flow(
            raw, tool_result="（工作区为空）")

        # 无 CoT 输出 → 按实际工具名动态生成占位符包装（<think> 契约）
        self.assertEqual(
            result,
            (f"<think>{brain._tool_thinking_placeholder('list_files')}</think>已经帮你弄好了",
             "🏠 本地 (工具)"))
        mexec.assert_called_once_with("list_files", {}, brain.permission_manager)
        mcloud.assert_not_called()               # 本地汇总成功，不惊动云端

        # 工具结果以 system 角色喂回（发给本地模型的第二轮），且要求不再输出 JSON
        self.assertEqual(mr.post.call_count, 2)
        msgs = mr.post.call_args_list[1].kwargs["json"]["messages"]
        self.assertEqual(msgs[-2], {"role": "assistant", "content": raw})
        self.assertEqual(msgs[-1]["role"], "system")
        self.assertIn("工具执行结果：", msgs[-1]["content"])
        self.assertIn("（工作区为空）", msgs[-1]["content"])
        self.assertIn("绝对不要再输出 JSON", msgs[-1]["content"])

    def test_summary_falls_back_to_cloud_when_local_fails(self):
        # 本地汇总异常 → 自动转 ask_cloud，来源标签如实标注
        raw = '{"tool": "list_files", "args": {}}'
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool") as mexec, \
                mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.side_effect = [_local_resp(raw),
                                   ConnectionError("本地汇总挂了")]
            mexec.return_value = "（工作区为空）"
            mcloud.return_value = "云端汇总好了"
            result = brain.smart_ask("帮我操作", [])

        self.assertEqual(
            result,
            (f"<think>{brain._tool_thinking_placeholder('list_files')}</think>云端汇总好了",
             "☁️ 云端 (工具)"))
        mcloud.assert_called_once()
        # 喂回的消息同样传给云端汇总轮
        self.assertIn("工具执行结果：",
                      mcloud.call_args.args[0][-1]["content"])

    def test_summary_falls_back_to_cloud_when_local_reply_empty(self):
        # 本地汇总返回空白视为"不可用" → 转云端
        raw = '{"tool": "list_files", "args": {}}'
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool") as mexec, \
                mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.side_effect = [_local_resp(raw), _local_resp("   ")]
            mexec.return_value = "（工作区为空）"
            mcloud.return_value = "云端汇总好了"
            result = brain.smart_ask("帮我操作", [])

        self.assertEqual(
            result,
            (f"<think>{brain._tool_thinking_placeholder('list_files')}</think>云端汇总好了",
             "☁️ 云端 (工具)"))
        mcloud.assert_called_once()

    def test_summary_goes_straight_to_cloud_when_local_offline(self):
        # 本地不在线（探测失败）→ 首轮与汇总轮都走云端
        raw = '{"tool": "list_files", "args": {}}'
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool") as mexec, \
                mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            mr.get.side_effect = OSError("refused")   # 探测失败
            mexec.return_value = "（工作区为空）"
            mcloud.side_effect = [raw, "云端汇总好了"]
            result = brain.smart_ask("帮我操作", [])

        self.assertEqual(
            result,
            (f"<think>{brain._tool_thinking_placeholder('list_files')}</think>云端汇总好了",
             "☁️ 云端 (工具)"))
        self.assertEqual(mcloud.call_count, 2)

    def test_tool_json_sandwiched_in_text(self):
        raw = '好的，我来看看！{"tool": "list_files", "args": {}} 马上就好'
        result, mexec, _, _ = _run_tool_flow(raw)
        self.assertEqual(result[1], "🏠 本地 (工具)")
        mexec.assert_called_once_with("list_files", {}, brain.permission_manager)

    def test_tool_json_multiline(self):
        raw = ('好的，马上为你操作：\n{\n  "tool": "control_ha_device",\n'
               '  "args": {"entity_id": "light.room", "action": "turn_on"}\n}')
        result, mexec, _, _ = _run_tool_flow(raw, tool_result="✅ 已开灯")
        self.assertEqual(result[1], "🏠 本地 (工具)")
        mexec.assert_called_once_with(
            "control_ha_device",
            {"entity_id": "light.room", "action": "turn_on"},
            brain.permission_manager)

    def test_invalid_json_treated_as_plain_reply(self):
        raw = '{"tool": list_files}'  # 非 JSON（值没加引号）
        result, mexec, mcloud, _ = _run_tool_flow(raw)
        # 全对话强制包装：旁路普通回复（无裸标记）注入默认占位符，原文随正文保留
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>{raw}", "🏠 本地"))
        mexec.assert_not_called()
        mcloud.assert_not_called()

    def test_tool_outside_whitelist_rejected(self):
        raw = '{"tool": "format_disk", "args": {}}'
        result, mexec, mcloud, _ = _run_tool_flow(raw)
        # 白名单外：不执行工具，按普通文本回复处理（强制包装注入默认占位符）
        mexec.assert_not_called()
        mcloud.assert_not_called()
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>{raw}", "🏠 本地"))

    def test_tool_result_starting_with_x_cuts_retry(self):
        # 防死循环硬拦截（单轮）：被拒结果不再喂回模型重试，直接返回拒绝文案
        raw = '{"tool": "write_file", "args": {"filename": "a.txt", "content": "x"}}'
        deny = "❌ 安全拒绝：当前权限不足，无法执行此物理控制操作！"
        result, mexec, mcloud, _ = _run_tool_flow(raw, tool_result=deny)

        # ❌ 切断路径同样属于工具调用流程：拒绝文案前同样有 <think> 包装
        self.assertEqual(
            result,
            (f"<think>{brain._tool_thinking_placeholder('write_file')}</think>{deny}",
             "☁️ 云端 (工具)"))
        mexec.assert_called_once()
        mcloud.assert_not_called()

    def test_real_gate_lv1_denies_write_file_and_cuts_retry(self):
        # 走真实 tools.execute_tool：LV1 请求 write_file → 门禁拒绝 → 切断
        raw = '{"tool": "write_file", "args": {"filename": "a.txt", "content": "x"}}'
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "permission_manager", _DenyPermissionManager()), \
                mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp(raw)
            reply, source = brain.smart_ask("帮我写文件", [])

        self.assertTrue(reply.startswith("<think>"), reply)
        self.assertIn("❌ 安全拒绝：当前权限不足", reply)
        self.assertEqual(source, "☁️ 云端 (工具)")
        mcloud.assert_not_called()

    def test_at_most_one_tool_call_per_round(self):
        # 汇总轮即使再吐工具 JSON，也不再执行（每轮最多一次工具调用）
        raw = '{"tool": "list_files", "args": {}}'
        again = '{"tool": "read_file", "args": {"filename": "x"}}'
        result, mexec, _, _ = _run_tool_flow(raw, summary_reply=again)

        # 汇总轮的回复也属于工具调用流程：同样有按工具名动态生成的占位符 <think> 包装
        self.assertEqual(
            result,
            (f"<think>{brain._tool_thinking_placeholder('list_files')}</think>{again}",
             "🏠 本地 (工具)"))
        mexec.assert_called_once()


# ---------------------------------------------------------------------------
# 思维链 <think> 包装（前端推理卡片契约，并行前端组同口径）
# ---------------------------------------------------------------------------

class ThinkWrapTests(unittest.TestCase):
    """CoT <think> 包装契约：
    - 工具调用发生（解析出 JSON 且执行）→ 最终 reply 最前面包装
      <think>捕获的[思考]/[计划]文本</think>（❌ 切断/熔断通知同属工具流程）；
    - 模型没输出任何 [思考]/[计划] → 按实际工具名动态生成占位符包装
      （"[思考] 准备调用 {工具名} 尝试完成操作."，解析不出工具名回退固定
      占位符）；
    - 全对话强制包装（_seal_bare_cot，2026-10-01 用户指令，显式废止旧
      "普通聊天零包装零干扰"）：模型输出了 [思考]/[计划] 但 JSON 解析失败/
      工具不在白名单等旁路普通回复、URL 总结、熔断剥夺路径 → 捕获到原生
      思考用原生（正文剥空由 _wrap_think 正文回补——真实回复回到正文——
      回补不了以"操作已完成。"兜底；正文已以 <think> 开头
      防重入不再二次包）；无任何标记的普通闲聊 → 注入 CHAT_THINKING_
      PLACEHOLDER 默认占位符"[思考] 正在理解你的意图..."（正文原样保留，
      提到"思考"二字不误触发剥标）；抓取失败/双脑全挂/空回复等固定文案
      同样注入默认占位符；
    - CoT 文本里混入花括号内容不得干扰工具 JSON 提取（先提取 JSON 再裁思考）；
    - 游离标签防御：包装统一走 _wrap_think（thinking/body 两侧剥除模型
      自吐的 <think>/</think> 字面量 + 拼装后成对校验）——模型回复自带
      </think>/<think> 字面量时最终 reply 仍恰一对标签且在最前，杜绝
      "</think>[思考]…" 原文直出网页。
    """

    COT_RAW = ('[思考] 主人要开灯，先确认设备在线。\n'
               '[计划] 1. 查设备 2. 开灯\n'
               '[行动] {"tool": "control_ha_device", '
               '"args": {"entity_id": "light.room", "action": "turn_on"}}')
    COT_THINKING = "[思考] 主人要开灯，先确认设备在线。\n[计划] 1. 查设备 2. 开灯"

    def setUp(self):
        brain.tool_fuse.reset()
        tp = mock.patch.object(brain, "_resolve_tier", return_value="high")
        tp.start()
        self.addCleanup(tp.stop)

    def tearDown(self):
        brain.tool_fuse.reset()

    def test_capture_thinking_both_markers(self):
        # [思考]/[计划] 分别捕获到 [计划]/[行动]/{ 或串尾为止（DOTALL 跨行）
        self.assertEqual(brain._capture_thinking(self.COT_RAW), self.COT_THINKING)

    def test_capture_thinking_single_marker(self):
        # 捕获其一即可：只输出 [思考] / 只输出 [计划]
        self.assertEqual(brain._capture_thinking("[思考] 只想了这一步"),
                         "[思考] 只想了这一步")
        self.assertEqual(brain._capture_thinking("好的 [计划] 1. 开灯"),
                         "[计划] 1. 开灯")

    def test_capture_thinking_fullwidth_variant_and_none(self):
        # 全角【】变体同样兼容；都没有（或只有空白）→ 空串，调用方回退占位符
        self.assertEqual(brain._capture_thinking("【思考】全角变体"),
                         "[思考] 全角变体")
        self.assertEqual(brain._capture_thinking('{"tool": "list_files", "args": {}}'), "")
        self.assertEqual(brain._capture_thinking("[思考]   [计划]  "), "")

    def test_capture_thinking_stops_at_brace(self):
        # 思考文本在第一个 { 处截断，绝不把工具 JSON 吞进推理展示
        raw = '[思考] 先看 {"path": "a.json"} 的配置。\n[计划] 1. 读文件'
        self.assertEqual(brain._capture_thinking(raw),
                         "[思考] 先看\n[计划] 1. 读文件")

    def test_tool_flow_wraps_captured_thinking(self):
        result, mexec, _, _ = _run_tool_flow(self.COT_RAW, tool_result="✅ 已开灯")
        self.assertEqual(
            result,
            (f"<think>{self.COT_THINKING}</think>已经帮你弄好了", "🏠 本地 (工具)"))
        mexec.assert_called_once_with(
            "control_ha_device",
            {"entity_id": "light.room", "action": "turn_on"},
            brain.permission_manager)

    def test_wlan_tap_scenario_wraps_captured_cot(self):
        # 用户实测场景："帮我点击手机屏幕上的WLAN"：模型按 [思考] → [计划] →
        # [行动]+JSON 三段协议输出，最终 reply 必须以
        # <think>[思考]…[计划]…</think> 开头且拼接在最终回答最前面
        raw = ('[思考] 主人想打开手机上的WLAN，先看清屏幕布局找到入口。\n'
               '[计划] 用uiautomator定位文字为"WLAN"的控件并点击中心点。\n'
               '[行动] {"tool": "ui_tap_element", "args": {"text": "WLAN"}}')
        result, mexec, _, _ = _run_tool_flow(
            raw, tool_result="【mock】UI 点击 WLAN", summary_reply="好的，已经帮你点开WLAN设置页面了。")

        reply, source = result
        self.assertEqual(source, "🏠 本地 (工具)")
        self.assertTrue(reply.startswith("<think>[思考] "), reply)
        self.assertIn("[计划] 用uiautomator定位", reply)
        self.assertTrue(
            reply.startswith(f"<think>{brain._capture_thinking(raw)}</think>"), reply)
        self.assertTrue(reply.endswith("好的，已经帮你点开WLAN设置页面了。"))
        mexec.assert_called_once_with("ui_tap_element", {"text": "WLAN"},
                                      brain.permission_manager)

    def test_execute_tool_exception_still_wrapped_and_cut(self):
        # 🛡️ 漏包装分支补齐：[CoT] 日志打印后 execute_tool 抛异常（依赖缺失/
        # 子进程崩溃等）→ 按 ❌ 切断口径返回，<think> 包装保持完整，
        # 裸 CoT 原文绝不漏成普通回复；异常按"被拒"计入熔断连续计数
        raw = ('[思考] 先定位控件。\n'
               '[计划] 点击WLAN。\n'
               '[行动] {"tool": "ui_tap_element", "args": {"text": "WLAN"}}')
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool",
                                  side_effect=RuntimeError("uiautomator boom")), \
                mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.side_effect = [_local_resp(raw), _local_resp("不会走到这")]
            mcloud.return_value = "不会走到这"
            reply, source = brain.smart_ask("帮我点击手机屏幕上的WLAN", [])

        self.assertEqual(source, "☁️ 云端 (工具)")
        self.assertTrue(reply.startswith("<think>[思考] 先定位控件。"), reply)
        self.assertIn("</think>❌ 工具执行异常: uiautomator boom", reply)
        mcloud.assert_not_called()   # ❌ 切断：异常结果不喂回模型重试
        # 熔断联动：异常计入"同一工具+等价参数被拒"连续次数，达到阈值的那一次
        # 强制打断并返回 ⛔ 熔断来源（熔断通知回复同样带 <think> 包装；
        # 之后的会话轮退回纯文本，不再解析工具）
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool",
                                  side_effect=RuntimeError("uiautomator boom")), \
                mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            mr.get.return_value = mock.Mock()
            mcloud.return_value = "x"
            fused = None
            for _ in range(brain.TOOL_FUSE_LIMIT):
                mr.post.side_effect = [_local_resp(raw), _local_resp("x")]
                cand = brain.smart_ask("帮我点击手机屏幕上的WLAN", [])
                if cand[1] == "⛔ 熔断":
                    fused = cand
                    break
        self.assertIsNotNone(fused, "连续异常达到阈值未触发熔断")
        # 熔断通知回复同样带 <think> 包装（完整捕获思考 + ⛔ 打断文案）
        self.assertTrue(fused[0].startswith("<think>[思考] 先定位控件。"), fused[0])
        self.assertIn("</think>⛔ 小橘3号连续多次尝试同一被拒绝的操作", fused[0])

    def test_wrapped_reply_survives_web_sanitize(self):
        # 净化透传契约：包装后的 reply 经 web_sanitize.sanitize_for_web 原样
        # 存活（<think>/</think> 标签不被剥掉/转义/破坏），前端才能渲染卡片；
        # 思考内容里混入的 CQ 码仍按 Web 口径净化（face→Emoji）
        from web_sanitize import sanitize_for_web
        wrapped = (f"<think>{self.COT_THINKING}</think>已经帮你弄好了")
        self.assertEqual(sanitize_for_web(wrapped), wrapped)
        with_cq = "<think>[思考] 表情[CQ:face,id=4]参考</think>正文[CQ:image,file=file:///x/a.jpg]"
        out = sanitize_for_web(with_cq)
        self.assertTrue(out.startswith("<think>[思考] 表情😎参考</think>正文"), out)
        self.assertIn("</think>", out)
        self.assertNotIn("CQ", out)


    def test_tool_flow_default_placeholder_without_cot(self):
        result, mexec, _, _ = _run_tool_flow('{"tool": "list_files", "args": {}}')
        # 契约字面量锁定：固定兜底占位符与前端约定一致；无 CoT 时优先按
        # 实际工具名动态生成含工具名的 [思考] 行，<think> 包装机制零改动
        self.assertEqual(brain.TOOL_THINKING_PLACEHOLDER,
                         "[思考] 已按计划执行工具调用。")
        self.assertEqual(
            result,
            ("<think>[思考] 准备调用 list_files 尝试完成操作。</think>已经帮你弄好了",
             "🏠 本地 (工具)"))
        mexec.assert_called_once_with("list_files", {}, brain.permission_manager)

    def test_tool_flow_dynamic_placeholder_names_tap_tool(self):
        # 用户口径：ui_tap_element 等点击工具在占位符里也要点名（无 CoT 时）
        raw = '{"tool": "ui_tap_element", "args": {"element_name": "设置"}}'
        result, mexec, _, _ = _run_tool_flow(raw, tool_result="【mock】UI 点击 设置")
        self.assertEqual(
            result,
            ("<think>[思考] 准备调用 ui_tap_element 尝试完成操作。</think>已经帮你弄好了",
             "🏠 本地 (工具)"))
        mexec.assert_called_once_with(
            "ui_tap_element", {"element_name": "设置"}, brain.permission_manager)

    def test_workspace_listing_scenario_wraps_placeholder(self):
        # 用户实测场景："帮我看看工作区有什么文件"（本地 Ollama 不在线 → 云端，
        # 真实部署口径）；模型只吐一行 JSON：注入含实际工具名的兜底占位符包装
        raw = '{"tool": "list_files", "args": {}}'
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool") as mexec, \
                mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            mr.get.side_effect = OSError("refused")   # 探测失败 → 全程云端
            mcloud.side_effect = [raw, "主人，工作区里有 a.txt 和 b.txt"]
            mexec.return_value = "a.txt\nb.txt"
            reply, source = brain.smart_ask("帮我看看工作区有什么文件", [])

        self.assertEqual(source, "☁️ 云端 (工具)")
        self.assertTrue(reply.startswith("<think>"), reply)
        # 契约字面量：<think>[思考] 准备调用 list_files 尝试完成操作。</think>在最前
        self.assertTrue(
            reply.startswith("<think>[思考] 准备调用 list_files 尝试完成操作。</think>"),
            reply)
        self.assertTrue(reply.endswith("主人，工作区里有 a.txt 和 b.txt"))
        mexec.assert_called_once_with("list_files", {}, brain.permission_manager)

    def test_cot_terminal_logs_placeholder_and_native(self):
        # [CoT] 终端日志契约（redirect_stdout 捕获）：
        # 模型没输出思考 → 打印"[CoT] 已注入兜底占位符"，不打印原生思考日志；
        # 模型原生输出 [思考]/[计划] → 打印"[CoT] 模型原生输出思考内容"
        raw = '{"tool": "list_files", "args": {}}'
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool") as mexec, \
                mock.patch.object(brain, "ask_cloud") as mcloud:
            mr.get.side_effect = OSError("refused")
            mcloud.side_effect = [raw, "弄好了"]
            mexec.return_value = "（工作区为空）"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                brain.smart_ask("帮我看看工作区有什么文件", [])
        self.assertIn("[CoT] 已注入兜底占位符", buf.getvalue())
        self.assertNotIn("[CoT] 模型原生输出思考内容", buf.getvalue())

        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool") as mexec, \
                mock.patch.object(brain, "ask_cloud") as mcloud:
            mr.get.side_effect = OSError("refused")
            mcloud.side_effect = [self.COT_RAW, "已开灯"]
            mexec.return_value = "✅ 已开灯"
            buf2 = io.StringIO()
            with contextlib.redirect_stdout(buf2):
                brain.smart_ask("开灯", [])
        self.assertIn("[CoT] 模型原生输出思考内容", buf2.getvalue())
        self.assertNotIn("[CoT] 已注入兜底占位符", buf2.getvalue())

    def test_tool_thinking_placeholder_fallback_without_tool_name(self):
        # 解析不出工具名（空值/纯空白）→ 回退固定占位符；
        # 有工具名 → 动态生成含实际工具名的 [思考] 占位符
        self.assertEqual(brain._tool_thinking_placeholder(None),
                         brain.TOOL_THINKING_PLACEHOLDER)
        self.assertEqual(brain._tool_thinking_placeholder(""),
                         brain.TOOL_THINKING_PLACEHOLDER)
        self.assertEqual(brain._tool_thinking_placeholder("   "),
                         brain.TOOL_THINKING_PLACEHOLDER)
        self.assertEqual(brain._tool_thinking_placeholder("adb_tap"),
                         "[思考] 准备调用 adb_tap 尝试完成操作。")
        self.assertEqual(brain._tool_thinking_placeholder("vision_tap_element"),
                         "[思考] 准备调用 vision_tap_element 尝试完成操作。")
        self.assertTrue(
            brain._tool_thinking_placeholder("ui_tap_element").startswith("[思考] "))

    def test_plain_chat_reply_wrapped_with_default_placeholder(self):
        # 全对话强制包装（2026-10-01 用户指令，反转旧"零包装"断言）：普通
        # 闲聊无原生思考 → 注入默认占位符，前端必定渲染思维链卡片；正文原样
        self.assertEqual(brain.CHAT_THINKING_PLACEHOLDER,
                         "[思考] 正在理解你的意图...")
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("今天天气不错哦～")
            result = brain.smart_ask("你好", [])
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>今天天气不错哦～",
             "🏠 本地"))

    def test_cot_braces_do_not_break_json_extraction(self):
        # CoT 里混入花括号内容：贪婪正则整体解析失败 → 回退逐 { 扫描提取，
        # 真正的工具 JSON 不受干扰，思考文本按 { 边界裁剪
        raw = ('[思考] 先看 {"path": "a.json"} 的配置。\n'
               '[计划] 1. 读文件\n'
               '[行动] {"tool": "read_file", "args": {"filename": "a.json"}}')
        result, mexec, _, _ = _run_tool_flow(raw, tool_result="文件内容...")
        mexec.assert_called_once_with("read_file", {"filename": "a.json"},
                                      brain.permission_manager)
        self.assertEqual(
            result,
            ("<think>[思考] 先看\n[计划] 1. 读文件</think>已经帮你弄好了",
             "🏠 本地 (工具)"))

    def test_cot_without_tool_json_still_wrapped_no_bare_leak(self):
        # 裸 CoT 封口（2026-10-01 用户口径）：有思考、有花括号，但没有合法
        # 工具 JSON → 旁路普通回复路径同样包装 <think>，裸 [思考] 绝不漏出；
        # 正文保留剥离裸标记后的剩余文本（"宁可隐藏裸文本"）
        raw = '[思考] 我先想想 {看看} 再说。'
        result, mexec, mcloud, _ = _run_tool_flow(raw)
        self.assertEqual(
            result,
            ("<think>[思考] 我先想想</think>{看看} 再说。", "🏠 本地"))
        mexec.assert_not_called()
        mcloud.assert_not_called()

    def test_cot_with_unparseable_json_sealed_with_placeholder(self):
        # 用户实测场景封口（"帮我点击手机屏幕上的蓝牙"）：模型按协议输出
        # [思考]/[计划]/[行动]+JSON 但 JSON 残缺（缺逗号）解析不出 → 普通
        # 回复路径同样包装 <think>；正文剥空 → [计划] 等裸标记不借回补漏进
        # 正文，以"操作已完成。"兜底（2026-10-01 T5 新口径，废止旧
        # "（操作已执行）"占位），[行动] 行与 JSON 载荷绝不裸漏
        raw = ('[思考] 主人要点击蓝牙，先定位设置入口。\n'
               '[计划] 1. UI解析找蓝牙 2. 失败转视觉\n'
               '[行动] {"tool": "ui_tap_element" "args": {}}')
        result, mexec, mcloud, _ = _run_tool_flow(raw, summary_reply="x")
        reply, source = result
        self.assertEqual(source, "🏠 本地")
        self.assertTrue(reply.startswith("<think>[思考] 主人要点击蓝牙"), reply)
        self.assertIn("[计划] 1. UI解析找蓝牙", reply)
        self.assertTrue(reply.endswith("</think>操作已完成。"), reply)
        body_part = reply.split("</think>", 1)[1]
        self.assertNotIn(brain.BARE_COT_BODY_PLACEHOLDER, reply)
        self.assertNotIn("[行动]", body_part)
        self.assertNotIn('"tool"', body_part)
        mexec.assert_not_called()
        mcloud.assert_not_called()

    def test_cot_with_whitelist_rejected_tool_still_sealed(self):
        # 旁路封口：JSON 合法但工具不在白名单 → 不执行，普通回复路径同样包装；
        # 正文剥空以"操作已完成。"兜底（T5 新口径）
        raw = ('[思考] 试试危险的工具。\n'
               '[计划] 调用未知工具\n'
               '[行动] {"tool": "format_disk", "args": {}}')
        result, mexec, mcloud, _ = _run_tool_flow(raw, summary_reply="x")
        reply, source = result
        self.assertEqual(source, "🏠 本地")
        self.assertTrue(reply.startswith("<think>[思考] 试试危险的工具。"), reply)
        self.assertTrue(reply.endswith("</think>操作已完成。"), reply)
        self.assertNotIn(brain.BARE_COT_BODY_PLACEHOLDER, reply)
        mexec.assert_not_called()
        mcloud.assert_not_called()

    def test_plain_chat_mentioning_marker_word_wrapped_with_placeholder(self):
        # 反转口径（2026-10-01 强制包装）：回复提到"思考"二字（无方括号标记）
        # 不触发裸标记剥除——正文原样保留，但仍注入默认占位符包装
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("让我思考一下再回答你哦。")
            result = brain.smart_ask("你好", [])
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>让我思考一下再回答你哦。",
             "🏠 本地"))

    def test_seal_bare_cot_placeholder_constant_and_reentry_guard(self):
        # 防重入：body 已以 <think> 开头（模型自包/上游已包）→ 不再二次包装，
        # 只剥净裸标记；占位符常量与前端契约字面量一致
        self.assertEqual(brain.BARE_COT_BODY_PLACEHOLDER, "（操作已执行）")
        self.assertEqual(brain.CHAT_THINKING_PLACEHOLDER,
                         "[思考] 正在理解你的意图...")
        with _quiet():
            sealed = brain._seal_bare_cot("<think>a</think>[思考] b\nc")
        self.assertEqual(sealed.count("<think>"), 1, sealed)
        self.assertEqual(sealed.count("</think>"), 1, sealed)
        self.assertTrue(sealed.startswith("<think>a</think>"), sealed)
        self.assertNotIn("[思考]", sealed)
        # 无标记的普通闲聊同样防重入：模型自吐 <think> 原生包装 → 原样透传
        with _quiet():
            native = brain._seal_bare_cot("<think>原生</think>直接聊")
        self.assertEqual(native, "<think>原生</think>直接聊")

    def test_extract_tool_json_multiline_still_works(self):
        # 既有能力不回退：多行 JSON 与夹在文字中的 JSON 照常提取
        multiline = ('好的，马上为你操作：\n{\n  "tool": "control_ha_device",\n'
                     '  "args": {"entity_id": "light.room", "action": "turn_on"}\n}')
        self.assertEqual(
            brain._extract_tool_json(multiline),
            '{\n  "tool": "control_ha_device",\n'
            '  "args": {"entity_id": "light.room", "action": "turn_on"}\n}')
        self.assertEqual(brain._extract_tool_json(
            '好的 {"tool": "list_files", "args": {}} 马上就好'),
            '{"tool": "list_files", "args": {}}')
        # 非 JSON / 无 tool 键 → None（绝不抛异常）
        self.assertIsNone(brain._extract_tool_json('{"tool": list_files}'))
        self.assertIsNone(brain._extract_tool_json('{"path": "a"} 纯闲聊'))

    def test_denied_tool_result_also_wrapped(self):
        raw = '{"tool": "write_file", "args": {"filename": "a.txt", "content": "x"}}'
        deny = "❌ 安全拒绝：当前权限不足，无法执行此物理控制操作！"
        result, mexec, mcloud, _ = _run_tool_flow(raw, tool_result=deny)
        self.assertEqual(
            result,
            (f"<think>{brain._tool_thinking_placeholder('write_file')}</think>{deny}",
             "☁️ 云端 (工具)"))
        mexec.assert_called_once()
        mcloud.assert_not_called()

    def test_url_summary_wrapped_with_default_placeholder(self):
        # 全对话强制包装（反转旧"零包装"断言）：URL 总结路径无工具调用、
        # 无原生思考 → 注入默认占位符，前端必定渲染思维链卡片
        url = "https://example.com/page"
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            def get_side_effect(target, **kwargs):
                if target == url:
                    resp = mock.Mock()
                    resp.text = "<p>网页正文</p>"
                    return resp
                raise OSError("refused")   # 探测失败 → 走云端

            mr.get.side_effect = get_side_effect
            mcloud.return_value = "这是网页总结"
            result = brain.smart_ask(f"帮我总结 {url}", [])
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>这是网页总结",
             "☁️ 云端 (总结)"))

    def test_url_summary_with_native_cot_sealed(self):
        # URL 总结路径旁路封口：总结文本若带模型原生 [思考]/[计划]（如复读
        # 页面协议文本），捕获文本进推理卡片不裸漏；无标记总结注入默认占位
        # 符由上一用例锁定
        url = "https://example.com/page"
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            def get_side_effect(target, **kwargs):
                if target == url:
                    resp = mock.Mock()
                    resp.text = "<p>网页正文</p>"
                    return resp
                raise OSError("refused")   # 探测失败 → 走云端

            mr.get.side_effect = get_side_effect
            mcloud.return_value = "[思考] 先梳理正文。\n[计划] 提炼要点\n这是网页总结"
            reply, source = brain.smart_ask(f"帮我总结 {url}", [])
        self.assertEqual(source, "☁️ 云端 (总结)")
        self.assertTrue(reply.startswith("<think>"), reply)
        body_part = reply.split("</think>", 1)[1]
        self.assertNotIn("[思考]", body_part)
        self.assertNotIn("[计划]", body_part)
        self.assertNotIn("[行动]", body_part)

    # ---- 游离标签防御（_wrap_think 统一包装 + 成对校验）----
    # 实测复现口径：模型原生输出自带的 <think>/</think> 字面量是游离标签
    # 唯一来源——首轮混进 [思考] 文本被 _capture_thinking 捕获、汇总轮随
    # final_reply 进入 body。旧手写拼接把它们原样拼进 reply（1 个 <think>
    # 对 2 个 </think> 一类），前端非贪婪正则截到第一个 </think> 后把余文
    # （含游离标签与裸 [计划] 文本）原文直出聊天正文。

    RAW_STRAY_CLOSE = (
        '[思考] 主人要开灯</think>先确认设备在线。\n'
        '[计划] 1. 查设备 2. 开灯\n'
        '[行动] {"tool": "control_ha_device", '
        '"args": {"entity_id": "light.room", "action": "turn_on"}}')

    def _assert_single_think_pair(self, reply):
        """契约断言：恰一对标签、<think> 在最前、闭合在开启之后。"""
        self.assertTrue(reply.startswith("<think>"), reply)
        self.assertEqual(reply.count("<think>"), 1, reply)
        self.assertEqual(reply.count("</think>"), 1, reply)
        self.assertLess(reply.index("<think>"), reply.index("</think>"), reply)

    def test_wrap_think_strips_stray_tags_from_dirty_input(self):
        # 纯函数单测：脏输入直接喂 _wrap_think —— thinking/body 两侧的
        # <think>/</think> 字面量一律剥除（文本内容保留），产出恰一对标签
        #（_quiet：吞掉 _wrap_think 末尾的 WRAPPED_TEXT 诊断日志，下同）
        with _quiet():
            out = brain._wrap_think("[思考] 先想想</think>再想想",
                                    "好的<think>嗯</think>")
        self.assertEqual(out, "<think>[思考] 先想想再想想</think>好的嗯")
        self._assert_single_think_pair(out)
        # 大小写/带属性变体同样剥除；None/空白思考注入默认占位符——
        # 成对保证（2026-10-01 用户口径）：绝不允许空 <think>（3.8 兼容纯函数）。
        # body 为 None（剥空）而 thinking 含真实内容 → 正文回补（T5 新口径：
        # 剥除 [思考] 前缀后的内容提升为正文，思考卡同时保留）
        with _quiet():
            out2 = brain._wrap_think("<THINK >x</THINK>y", None)
            # 2026-10-02 出口去重口径：回补后思考与正文完全相同（无 [思考]
            # 标记前缀的裸形态，think==body）→ 思考卡降级默认占位符，正文
            # 保留一份——绝不再产出"卡片与正文同文"的重复显示
            self.assertEqual(
                out2,
                f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>xy")
            self._assert_single_think_pair(out2)
            self.assertEqual(brain._wrap_think(None, "正文"),
                             f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>正文")
            self.assertEqual(brain._wrap_think("[思考] x", None),
                             "<think>[思考] x</think>x")

    def test_wrap_think_clean_input_format_unchanged(self):
        # 干净输入（正常 CoT / 动态占位符）产出与旧手写拼接逐字一致，零回退
        with _quiet():
            self.assertEqual(
                brain._wrap_think(self.COT_THINKING, "已经帮你弄好了"),
                f"<think>{self.COT_THINKING}</think>已经帮你弄好了")
            self.assertEqual(
                brain._wrap_think(brain._tool_thinking_placeholder("list_files"),
                                  "主人，工作区里有 a.txt"),
                f"<think>{brain._tool_thinking_placeholder('list_files')}"
                f"</think>主人，工作区里有 a.txt")

    def test_model_stray_close_tag_in_cot_reply_stays_paired(self):
        # 模型首轮 CoT 自带 </think> 字面量（被 _capture_thinking 捕获进
        # 思考文本）→ 最终 reply 标签严格成对、游离字面量剥除
        result, mexec, _, _ = _run_tool_flow(self.RAW_STRAY_CLOSE,
                                             tool_result="✅ 已开灯")
        reply, source = result
        self.assertEqual(source, "🏠 本地 (工具)")
        self._assert_single_think_pair(reply)
        self.assertEqual(
            reply,
            "<think>[思考] 主人要开灯先确认设备在线。\n"
            "[计划] 1. 查设备 2. 开灯</think>已经帮你弄好了")
        mexec.assert_called_once_with(
            "control_ha_device",
            {"entity_id": "light.room", "action": "turn_on"},
            brain.permission_manager)

    def test_model_stray_open_tag_in_cot_reply_stays_paired(self):
        # 模型首轮 CoT 自带 <think> 字面量（嵌套风险）→ 同样剥除后成对
        raw = ('[思考] <think>主人要开灯，先确认设备在线。\n'
               '[计划] 1. 查设备 2. 开灯\n'
               '[行动] {"tool": "control_ha_device", '
               '"args": {"entity_id": "light.room", "action": "turn_on"}}')
        reply, _ = _run_tool_flow(raw, tool_result="✅ 已开灯")[0]
        self._assert_single_think_pair(reply)
        self.assertEqual(
            reply,
            "<think>[思考] 主人要开灯，先确认设备在线。\n"
            "[计划] 1. 查设备 2. 开灯</think>已经帮你弄好了")

    def test_summary_reply_with_think_literals_stripped(self):
        # 汇总轮（body 侧防御）：reasoner 式 </think> 前缀 / 复读
        # <think>…</think> → body 先剥净标签再拼装（复读的文本内容保留）
        raw = '{"tool": "list_files", "args": {}}'
        cases = ["</think>主人，工作区里有 a.txt",
                 "<think>数一下</think>主人，工作区里有 a.txt"]
        reply = None
        for summary in cases:
            result, _, _, _ = _run_tool_flow(raw, tool_result="a.txt",
                                             summary_reply=summary)
            reply, source = result
            self.assertEqual(source, "🏠 本地 (工具)")
            self._assert_single_think_pair(reply)
            self.assertTrue(reply.endswith("主人，工作区里有 a.txt"), reply)
        # 只剥标签字面量、复读的文本内容按原位保留在正文
        self.assertIn("数一下主人，工作区里有 a.txt", reply)


class ThinkPairGuaranteeTests(unittest.TestCase):
    """_wrap_think 成对保证（2026-10-01 用户口径，修复"你好"网页直出纯文本
    <think> 的实测固化）。

    实测根因（修复前 python mock 网络复现证据）：
    - 模型首轮自吐无闭合的开标签（截断输出 "<think>你好呀" / 孤立 "<think>"）
      → _seal_bare_cot 防重入透传分支 startswith("<think>") 原样放行，
      smart_ask 返回未闭合的 <think>，前端正则匹配不到成对标签，把标签
      字面量当纯文本直出（无内容、无闭合）；
    - "<think>你好\\n[计划] 再想"（打完 "[CoT] 模型原生输出思考内容" 日志后
      仍透传残缺标签）——与用户报障"终端有 [CoT] 日志但输出不完整"吻合。
    修复口径（用户指定三条）：
    - thinking 为 None/空串/纯空白 → 注入 CHAT_THINKING_PLACEHOLDER 默认
      占位符，绝不允许空 <think> 或只有开头的 <think>；
    - thinking/body 两侧剥除模型自吐 <think>/</think> 字面量（既有逻辑
      核实加固）；
    - 包装完成后按用户指定正则 re.search(r'<think>.*?</think>', final_text,
      re.DOTALL) 校验：不匹配强制从干净两侧重拼一次，重拼仍不匹配退化为
      剥离全部 think 标签的纯文本（宁可无标签也不出畸形）。
    T5 增补（2026-10-01 用户实测缺陷"真实回复被占位符顶替"修复固化）：
    终端实测 WRAPPED_TEXT: <think>[思考] ...嘿...有什么可以帮到你的？</think>
    （操作已执行）——模型自吐 </think> 后的真实回复被上游剥空、以占位符顶替
    正文。现 _wrap_think 四条新口径：两侧彻底剥除标签字面量与"（操作已执行）"
    占位符；正文剥空而 thinking 含真实内容 → 回补为正文（真实回复回到正文，
    思考卡同时保留）；双空才注入默认占位（思考=CHAT 占位、正文="操作已完成。
    "）；成对门禁与 WRAPPED_TEXT 日志打印清洗回补后的最终产出。
    """

    def _assert_paired(self, text):
        """用户指定门禁口径：文本中必须能搜到成对 <think>...</think>。"""
        self.assertTrue(re.search(r'<think>.*?</think>', text, re.DOTALL),
                        repr(text))

    def _chat(self, model_reply):
        """mock 本地大脑在线返回 model_reply 的"你好"闲聊一轮。"""
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()            # 探测在线 → 本地
            mr.post.return_value = _local_resp(model_reply)
            return brain.smart_ask("你好", [])

    # ---- 根因回归：残缺原生 <think> 不再透传 ----

    def test_hello_chat_unpaired_open_tag_repaired(self):
        # 根因形态一：模型截断输出 "<think>你好呀…"（有内容无闭合）
        reply, source = self._chat("<think>你好呀，我是小橘！")
        self.assertEqual(source, "🏠 本地")
        self._assert_paired(reply)
        self.assertEqual(
            reply,
            f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>你好呀，我是小橘！")

    def test_hello_chat_lone_open_tag_repaired(self):
        # 根因形态二（用户报障原文）：模型只吐一个 <think>（无内容无闭合）
        # → 修复前网页直出纯文本 <think>；现产出成对且思考非空的完整卡片
        reply, _source = self._chat("<think>")
        self._assert_paired(reply)
        self.assertEqual(
            reply, f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>")

    def test_hello_chat_empty_native_pair_swapped_for_placeholder(self):
        # 空原生对（qwen3 非思考形态 "<think>\\n\\n</think>"）→ 空卡片同样
        # 不允许，注入非空默认占位符
        reply, _source = self._chat("<think>\n\n</think>你好呀")
        self._assert_paired(reply)
        self.assertEqual(
            reply, f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>你好呀")

    def test_hello_chat_plain_baseline_unchanged(self):
        # 用户口径基线："你好"闲聊 → <think>[思考] 正在理解你的意图...</think>正文
        # （成对且非空思考；G2 反转的"普通聊天必包装"断言保持零回退）
        reply, _source = self._chat("你好呀，很高兴见到你！")
        m = re.match(r'^<think>(.*?)</think>(.*)$', reply, re.DOTALL)
        self.assertIsNotNone(m, repr(reply))
        self.assertEqual(m.group(1), brain.CHAT_THINKING_PLACEHOLDER)
        self.assertTrue(m.group(1).strip())              # 思考非空
        self.assertEqual(m.group(2), "你好呀，很高兴见到你！")

    def test_seal_bare_cot_repair_and_passthrough_matrix(self):
        # _seal_bare_cot 直接单测：残缺修复、成对透传（零回退）两不误
        with _quiet():
            self.assertEqual(
                brain._seal_bare_cot("<think>你好呀"),
                f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>你好呀")
            self._assert_paired(brain._seal_bare_cot("<think>"))
            # 完整原生卡片（思考非空）仍原样透传
            self.assertEqual(brain._seal_bare_cot("<think>原生</think>直接聊"),
                             "<think>原生</think>直接聊")

    def test_marked_branch_unpaired_native_body_repaired(self):
        # 根因形态三：残缺 <think> + 裸标记并存（打完 [CoT] 日志后透传的漏点）
        # → 剥净标签字面量按捕获思考重新包装，正文保留、无裸标记直出
        with _quiet():
            sealed = brain._seal_bare_cot("<think>你好\n[计划] 再想")
        self._assert_paired(sealed)
        self.assertTrue(sealed.startswith("<think>"), repr(sealed))
        self.assertIn("你好", sealed)
        self.assertNotIn("[计划]", sealed.split("</think>", 1)[1])
        self.assertNotIn("<think>", sealed.split("</think>", 1)[1])

    # ---- _wrap_think 成对保证：空思考占位符 / 两侧清洗 / 最终门禁 ----

    def test_wrap_think_blank_thinking_injects_placeholder(self):
        # None/空串/纯空白一律注入默认占位符，绝无空 <think></think>
        for blank in (None, "", "   ", "\n\t "):
            with _quiet():
                self.assertEqual(
                    brain._wrap_think(blank, "正文"),
                    f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>正文")

    def test_wrap_think_self_emitted_close_literal_cleaned_paired(self):
        # thinking 含自吐 </think> 字面量 → 两侧清洗后恰一对标签（用户口径用例）
        with _quiet():
            out = brain._wrap_think("[思考] 想到一半</think>继续想", "正文<think>嗯</think>")
        self.assertEqual(out, "<think>[思考] 想到一半继续想</think>正文嗯")
        self._assert_paired(out)
        self.assertEqual(out.count("<think>"), 1, out)
        self.assertEqual(out.count("</think>"), 1, out)
        self.assertTrue(out.startswith("<think>"), out)

    def test_wrap_think_dirty_inputs_always_pair(self):
        # 门禁口径扫掠：任意脏输入 → 输出必匹配 r'<think>.*?</think>'（DOTALL）
        dirty = [
            ("[思考] a</think>b", "好的<think>嗯</think>x"),
            ("<think>嵌套开标签", "body<think>y"),
            ("</think></think>", "</think>正文"),
            ("<THINK >大小写</THINK>", None),
            (None, None),
            ("", "  "),
        ]
        for t, b in dirty:
            with _quiet():
                out = brain._wrap_think(t, b)
            self._assert_paired(out)
            self.assertTrue(out.startswith("<think>"), repr(out))
            self.assertEqual(out.count("<think>"), 1, repr(out))
            self.assertEqual(out.count("</think>"), 1, repr(out))

    def test_wrap_think_final_gate_degrades_to_plain_text(self):
        # 用户指定兜底链：门禁不匹配 → 从干净两侧重拼一次 → 仍不匹配 →
        # 退化为剥离全部 think 标签的纯文本（patch 门禁正则为永不匹配，
        # 模拟清洗/拼装被未来改动破坏的极端态，验证兜底真实可达）
        never = re.compile(r"(?!x)x")
        with mock.patch.object(brain, "_THINK_HAS_PAIR_RE", never), _quiet():
            out = brain._wrap_think("[思考] 想想", "正文")
        self.assertNotIn("<think>", out)
        self.assertNotIn("</think>", out)
        self.assertIn("[思考] 想想", out)
        self.assertIn("正文", out)

    def test_final_gate_constant_matches_user_regex(self):
        # 门禁正则常量与用户指定字面量一致（防未来静默改动）
        self.assertEqual(brain._THINK_HAS_PAIR_RE.pattern, r'<think>.*?</think>')
        self.assertEqual(brain._THINK_HAS_PAIR_RE.flags & re.DOTALL, re.DOTALL)

    # ---- 正文回补（T5，2026-10-01 用户实测"（操作已执行）"顶替真实回复）----

    # 用户终端实测畸形态的输入侧：[思考] 真实内容 + "（操作已执行）"占位 body
    DEFECT_THINKING = "[思考] ...嘿...有什么可以帮到你的？"
    DEFECT_FIXED = ("<think>[思考] ...嘿...有什么可以帮到你的？</think>"
                    "...嘿...有什么可以帮到你的？")

    def test_user_defect_placeholder_body_backfilled_from_thinking(self):
        # 纯函数复现：喂入会产生旧畸形态 <think>[思考] ...</think>（操作已执行）
        # 的输入（[思考] 内容 + 占位 body）→ 真实回复回到正文，思考卡同时保留
        with _quiet():
            out = brain._wrap_think(self.DEFECT_THINKING, "（操作已执行）")
        self.assertEqual(out, self.DEFECT_FIXED)
        self._assert_paired(out)
        # 负例：占位符绝不作为正文出现（全文断言，卡内也不允许）
        self.assertNotIn(brain.BARE_COT_BODY_PLACEHOLDER, out)

    def test_user_defect_e2e_real_reply_returns_to_body(self):
        # 端到端复现（用户终端实测口径）：模型输出 [思考]+真实回复、上游剥空
        # body 的旧畸形态 → smart_ask 新产出 = <think>[思考] ...</think>真实回复
        reply, source = self._chat(self.DEFECT_THINKING)
        self.assertEqual(source, "🏠 本地")
        self.assertEqual(reply, self.DEFECT_FIXED)
        self.assertNotIn(brain.BARE_COT_BODY_PLACEHOLDER, reply)

    def test_body_placeholder_literal_stripped_from_both_sides(self):
        # 清洗加固（用户口径①）："（操作已执行）"（含前后空白变体）在
        # thinking/body 两侧一律彻底剥除
        with _quiet():
            out = brain._wrap_think("（操作已执行） [思考] 想想",
                                    "（操作已执行）正文（操作已执行）")
        self.assertEqual(out, "<think>[思考] 想想</think>正文")
        self.assertNotIn(brain.BARE_COT_BODY_PLACEHOLDER, out)

    def test_placeholder_thinking_never_promoted_to_body(self):
        # 注入型占位思考不回补正文：闲聊占位保持"只有卡片"输出（孤标签修复
        # 形态零回退）；工具占位思考剥空正文以"操作已完成。"兜底——
        # 绝不允许正文成为"（操作已执行）"，也不把占位文案复制进正文
        with _quiet():
            self.assertEqual(
                brain._wrap_think(brain.CHAT_THINKING_PLACEHOLDER,
                                  "（操作已执行）"),
                f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>")
            self.assertEqual(
                brain._wrap_think(brain.TOOL_THINKING_PLACEHOLDER, None),
                f"<think>{brain.TOOL_THINKING_PLACEHOLDER}</think>"
                f"{brain.DEFAULT_BODY_PLACEHOLDER}")
        self.assertNotIn(brain.BARE_COT_BODY_PLACEHOLDER,
                         brain.DEFAULT_BODY_PLACEHOLDER)

    def test_double_blank_falls_back_to_default_body_placeholder(self):
        # 双空兜底（用户口径③）：body 与 thinking 清洗后都为空 → 思考注入
        # CHAT 默认占位符、正文注入简短"操作已完成。"；常量字面量锁定
        self.assertEqual(brain.DEFAULT_BODY_PLACEHOLDER, "操作已完成。")
        for blank_body in (None, "", "   ", "（操作已执行）"):
            with _quiet():
                out = brain._wrap_think(None, blank_body)
            self.assertEqual(
                out,
                f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>"
                f"{brain.DEFAULT_BODY_PLACEHOLDER}")
            self.assertNotIn(brain.BARE_COT_BODY_PLACEHOLDER, out)

    def test_backfill_skipped_when_marker_would_leak_body(self):
        # 多段思考（[思考]+[计划]）不可整段提升——裸标记绝不借回补漏进正文，
        # 以"操作已完成。"兜底（正文回补只服务单段纯文本的真实回复）
        with _quiet():
            out = brain._wrap_think("[思考] 先定位入口。\n[计划] 点击蓝牙图标",
                                    "（操作已执行）")
        self.assertEqual(
            out,
            "<think>[思考] 先定位入口。\n[计划] 点击蓝牙图标</think>操作已完成。")
        self.assertNotIn("[计划]", out.split("</think>", 1)[1])
        self.assertNotIn(brain.BARE_COT_BODY_PLACEHOLDER, out)

    # ---- 输出诊断日志（2026-10-01 用户口径）：_wrap_think 最终 return 前 ----

    def test_wrap_think_prints_wrapped_text_log_of_final_output(self):
        # WRAPPED_TEXT 日志 = 最终产出本体：含成对 <think> 且紧贴正文，
        # 日志行逐字等于函数返回值（部署侧据此与网页形态对账）；
        # 2026-10-02 降噪：改走 "xiaoju3.brain" logger 的 DEBUG 级别
        # （默认终端不输出，assertLogs 开 DEBUG 捕获验证）
        with self.assertLogs("xiaoju3.brain", level="DEBUG") as captured:
            out = brain._wrap_think("[思考] 想想", "正文")
        log_text = "\n".join(captured.output)
        self.assertIn(f"WRAPPED_TEXT: {out}", log_text)
        self.assertIn("WRAPPED_TEXT: <think>", log_text)

    def test_wrap_think_wrapped_text_log_truncated_at_300_chars(self):
        # 防刷屏截断：超 300 字符截断加 "..."（载荷恰为 300+3 字符），
        # 开头 <think> 成对标签仍保留在行首
        with self.assertLogs("xiaoju3.brain", level="DEBUG") as captured:
            brain._wrap_think("[思考] 想想", "字" * 400)
        payload = "\n".join(captured.output).split("WRAPPED_TEXT: ", 1)[1].rstrip("\n")
        self.assertTrue(payload.endswith("..."), repr(payload[-10:]))
        self.assertEqual(len(payload), 303)
        self.assertTrue(payload.startswith("<think>[思考] 想想</think>"), payload)

    def test_wrap_think_degraded_plain_text_log_has_no_tags(self):
        # 兜底退化路径（门禁永不匹配）记录的最终产出同样逐字对账：
        # 纯文本无任何 think 标签（"宁可无标签"口径在日志里可见）
        never = re.compile(r"(?!x)x")
        with self.assertLogs("xiaoju3.brain", level="DEBUG") as captured:
            with mock.patch.object(brain, "_THINK_HAS_PAIR_RE", never):
                out = brain._wrap_think("[思考] 想想", "正文")
        log_text = "\n".join(captured.output)
        self.assertNotIn("<think>", log_text)
        self.assertIn(f"WRAPPED_TEXT: {out}", log_text)

    def test_smart_ask_hello_wrapped_text_log_matches_reply(self):
        # 端到端对账（用户报障"你好"口径）：smart_ask 记录的 WRAPPED_TEXT
        # 与返回给前端的 reply 逐字一致——后端下发的 <think> 包装完好，
        # "网页只显示纯文本"嫌疑收敛到前端渲染分支或剥标出口（见
        # WebExitThinkTagContractTests 的通道实测）
        with mock.patch.object(brain, "requests") as mr:
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("你好呀，很高兴见到你！")
            with self.assertLogs("xiaoju3.brain", level="DEBUG") as captured:
                reply, _source = brain.smart_ask("你好", [])
        log_text = "\n".join(captured.output)
        self.assertIn(f"WRAPPED_TEXT: {reply}", log_text)
        self.assertTrue(
            reply.startswith(f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>"),
            reply)


class WebExitThinkTagContractTests(unittest.TestCase):
    """<think> 包装两条下发通道实测口径（2026-10-01 python 实测，排查"你好"
    网页只显示纯文本无思维链卡片；结论固化进 brain._wrap_think docstring）：
    - 仪表盘 /api/chat（直连 smart_ask，出口 web_sanitize.sanitize_for_web）：
      sanitize 只净化 CQ 码（face→Emoji/image→[表情]/其余剥除），实测
      <think>/</think> 标签原样存活（思考内混 CQ 码时标签同样完好成对）
      ——后端下发的包装完好，前端拿到的文本可直接渲染卡片；
    - QQ 与旧版网页（main.py _strip_think：re.sub(r'<think>.*?</think>',
      '', DOTALL) 后 strip）：设计上整块剥除思维链（含标签本体），QQ/旧页
      拿到纯文本正文——通道口径差异，不是标签丢失。
    据此排除"后端输出标签被剥"这一嫌疑：网页只见纯正文时，应查前端
    渲染分支（console.js，并行组维护）或确认该回复是否走了剥标出口。
    """

    WRAPPED = "<think>[思考] 正在理解你的意图...</think>你好呀，很高兴见到你！"
    WRAPPED_CQ = ("<think>[思考] 表情[CQ:face,id=4]参考</think>"
                  "正文[CQ:image,file=file:///x/a.jpg]")

    def test_dashboard_sanitize_keeps_think_tags_intact(self):
        # 仪表盘出口：干净包装逐字透传（恰一对标签）；思考内混 CQ 码时
        # CQ 码被净化而 <think> 标签完好成对
        from web_sanitize import sanitize_for_web
        self.assertEqual(sanitize_for_web(self.WRAPPED), self.WRAPPED)
        out = sanitize_for_web(self.WRAPPED_CQ)
        self.assertTrue(out.startswith("<think>[思考] 表情😎参考</think>"), out)
        self.assertEqual(out.count("<think>"), 1, out)
        self.assertEqual(out.count("</think>"), 1, out)

    def test_qq_strip_think_removes_block_by_design(self):
        # QQ/旧版网页出口（main._strip_think 等价正则，与 main.py 同口径）：
        # 整块剥除 <think>...</think>（含标签本体）只留纯文本正文——设计口径
        stripped = re.sub(r'<think>.*?</think>', '', str(self.WRAPPED or ""),
                          flags=re.DOTALL).strip()
        self.assertEqual(stripped, "你好呀，很高兴见到你！")
        self.assertNotIn("<think>", stripped)
        self.assertNotIn("</think>", stripped)
        # 汇总轮带 CQ 发图的回复同理：思维块剥净、正文与 CQ 码原样保留
        stripped_cq = re.sub(r'<think>.*?</think>', '',
                             str(self.WRAPPED_CQ or ""), flags=re.DOTALL).strip()
        self.assertEqual(stripped_cq, "正文[CQ:image,file=file:///x/a.jpg]")


class RecentActionsPrefixTests(unittest.TestCase):
    """_build_messages 前缀白名单：新前缀"以下是最近的设备操作记录"的 system
    条目被保留注入；既有【前情提要】/长期记忆两条前缀不回退；来路不明
    system 仍剔除；调用方 history 不被修改。"""

    ACTIONS_BLOCK = ("以下是最近的设备操作记录（最新在最后），主人提到"
                     "\"它/再一次/刚才那个\"等指代时可据此解析：\n"
                     "· control_ha_device: light.living → turn_on")

    def test_recent_actions_system_entry_kept_along_existing_prefixes(self):
        history = [
            {"role": "system", "content": "【前情提要】用户此前聊过装修与养猫。"},
            {"role": "system", "content": "以下是关于用户的长期记忆：喜欢橙色。"},
            {"role": "system", "content": self.ACTIONS_BLOCK},
            {"role": "system", "content": "来路不明的系统指令"},
            {"role": "user", "content": "把它关了"},
        ]
        msgs = brain._build_messages("把它关了", history)
        system_texts = [m["content"] for m in msgs if m["role"] == "system"]
        # 置顶提示词 + 三条合法注入（前情提要 / 长期记忆 / 设备操作记录）
        self.assertEqual(len(system_texts), 4)
        self.assertIn(self.ACTIONS_BLOCK, system_texts)
        self.assertIn("【前情提要】用户此前聊过装修与养猫。", system_texts)
        self.assertIn("以下是关于用户的长期记忆：喜欢橙色。", system_texts)
        self.assertNotIn("来路不明的系统指令", system_texts)
        self.assertEqual(msgs[-1], {"role": "user", "content": "把它关了"})

    def test_unknown_system_still_dropped_without_new_prefix(self):
        # 无新前缀标记的 system 依旧被剔除（白名单机制未被放宽）
        msgs = brain._build_messages("在吗", [{"role": "system",
                                               "content": "最近的操作：x"}])
        system_texts = [m["content"] for m in msgs if m["role"] == "system"]
        self.assertEqual(len(system_texts), 1)   # 只剩置顶提示词
        self.assertNotIn("最近的操作：x", system_texts)

    def test_history_not_mutated(self):
        history = [{"role": "system", "content": self.ACTIONS_BLOCK},
                   {"role": "user", "content": "hi"}]
        snapshot = [dict(m) for m in history]
        brain._build_messages("hi", history)
        self.assertEqual(history, snapshot)


# ---------------------------------------------------------------------------
# 防死循环熔断（架构 §10 #1 / 开发日志第四章"小犟3号"事件）
# ---------------------------------------------------------------------------

class ToolLoopFuseTests(unittest.TestCase):
    """跨轮熔断：连续同参被拒计数、触发打断、退回纯文本、成功归零、reset。"""

    DENY = "❌ 安全拒绝：当前权限不足，无法执行此物理控制操作！"
    RAW = '{"tool": "write_file", "args": {"filename": "a.txt", "content": "x"}}'

    def setUp(self):
        brain.tool_fuse.reset()
        tp = mock.patch.object(brain, "_resolve_tier", return_value="high")
        tp.start()
        self.addCleanup(tp.stop)

    def tearDown(self):
        brain.tool_fuse.reset()

    def _round(self, raw_reply=None, tool_result=None, session_key="default"):
        """跑一轮工具调用流程（本地吐 JSON + execute_tool 打桩结果）。"""
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool") as mexec, \
                mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.side_effect = [_local_resp(raw_reply or self.RAW),
                                   _local_resp("已经帮你弄好了")]
            mexec.return_value = "✅ 完成" if tool_result is None else tool_result
            mcloud.return_value = "已经帮你弄好了"
            return brain.smart_ask("帮我操作", [], session_key=session_key)

    def test_rejections_below_threshold_keep_denial_reply(self):
        r1 = self._round(tool_result=self.DENY)
        r2 = self._round(tool_result=self.DENY)
        # ❌ 切断文案前有 <think> 动态占位符包装（工具调用流程统一契约）
        wrapped = f"<think>{brain._tool_thinking_placeholder('write_file')}</think>{self.DENY}"
        self.assertEqual(r1, (wrapped, "☁️ 云端 (工具)"))
        self.assertEqual(r2, (wrapped, "☁️ 云端 (工具)"))
        self.assertFalse(brain.tool_fuse.is_tripped("default"))

    def test_third_identical_rejection_trips_fuse(self):
        # 连续 3 次（默认阈值）同一工具 + 相同参数被拒 → 强制打断
        for _ in range(2):
            self._round(tool_result=self.DENY)
        r3 = self._round(tool_result=self.DENY)
        # 熔断通知同属工具调用流程返回：同样带 <think> 包装
        self.assertEqual(
            r3,
            (f"<think>{brain._tool_thinking_placeholder('write_file')}</think>{brain.TOOL_FUSE_NOTICE}",
             "⛔ 熔断"))
        self.assertTrue(brain.tool_fuse.is_tripped("default"))
        # 提示语说明"已暂停工具使用"及"如何继续"
        self.assertIn("工具", brain.TOOL_FUSE_NOTICE)
        self.assertIn("重置", brain.TOOL_FUSE_NOTICE)

    def test_tripped_session_revokes_tool_rights(self):
        # 熔断后：模型再吐工具 JSON 也不执行，退回纯文本回复
        for _ in range(3):
            self._round(tool_result=self.DENY)
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool") as mexec, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp(self.RAW)
            result = brain.smart_ask("再试一次", [], session_key="default")

        mexec.assert_not_called()
        # 全对话强制包装：熔断退回的纯文本（无裸标记）同样注入默认占位符
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>{self.RAW}",
             "🏠 本地"))

    def test_tripped_session_still_seals_bare_cot(self):
        # 熔断剥夺路径同样封口：模型退回纯文本时若仍输出 [思考]/[计划]/[行动]
        # （工具 JSON 已不再解析），同样包装 <think> 不裸漏；
        # 无任何标记的纯文本回复注入默认占位符包装（上一用例锁定）
        for _ in range(3):
            self._round(tool_result=self.DENY)
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool") as mexec, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp(
                "[思考] 工具被暂停了，先解释。\n"
                "[计划] 纯文字说明\n"
                '[行动] {"tool": "list_files"}\n'
                "主人，工具刚刚被暂停啦，我们先聊点别的吧。")
            result = brain.smart_ask("再试一次", [], session_key="default")

        mexec.assert_not_called()
        reply, source = result
        self.assertEqual(source, "🏠 本地")
        self.assertEqual(
            reply,
            "<think>[思考] 工具被暂停了，先解释。\n"
            "[计划] 纯文字说明</think>"
            "主人，工具刚刚被暂停啦，我们先聊点别的吧。")

    def test_tripped_session_injects_system_note(self):
        # 熔断期间注入系统提示，要求模型本轮直接纯文本回答
        for _ in range(3):
            self._round(tool_result=self.DENY)
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("好的，我用文字说明。")
            brain.smart_ask("再试一次", [], session_key="default")
        msgs = mr.post.call_args.kwargs["json"]["messages"]
        system_notes = [m["content"] for m in msgs
                        if m.get("role") == "system"]
        self.assertIn(brain.TOOL_FUSE_SYSTEM_NOTE, system_notes)

    def test_different_args_reset_streak(self):
        # 换参数 = 新指纹：连续计数归 1，不触发熔断
        self._round(tool_result=self.DENY)
        self._round(tool_result=self.DENY)
        alt = '{"tool": "write_file", "args": {"filename": "b.txt", "content": "y"}}'
        self._round(raw_reply=alt, tool_result=self.DENY)
        self._round(raw_reply=alt, tool_result=self.DENY)
        self.assertFalse(brain.tool_fuse.is_tripped("default"))

    def test_equivalent_args_count_as_same(self):
        # 等价参数（int/str 值、键序不同）视为同一指纹
        fp1 = brain.ToolLoopFuse.fingerprint("adb_tap", {"x": 10, "y": 20})
        fp2 = brain.ToolLoopFuse.fingerprint("adb_tap", {"y": "20", "x": "10"})
        self.assertEqual(fp1, fp2)
        fuse = brain.ToolLoopFuse(limit=2)
        fuse.record_rejection("s", "adb_tap", {"x": 10, "y": 20})
        fuse.record_rejection("s", "adb_tap", {"y": "20", "x": "10"})
        self.assertTrue(fuse.is_tripped("s"))

    def test_success_resets_streak(self):
        # 一次成功执行打断"连续被拒"计数
        self._round(tool_result=self.DENY)
        self._round(tool_result=self.DENY)
        self._round(tool_result="✅ 完成")
        self._round(tool_result=self.DENY)
        self._round(tool_result=self.DENY)
        self.assertFalse(brain.tool_fuse.is_tripped("default"))

    def test_sessions_are_independent(self):
        # 熔断按会话隔离：QQ 会话熔断不影响网页会话
        for _ in range(3):
            self._round(tool_result=self.DENY, session_key="qq")
        self.assertTrue(brain.tool_fuse.is_tripped("qq"))
        self.assertFalse(brain.tool_fuse.is_tripped("web"))

    def test_reset_restores_tool_rights(self):
        for _ in range(3):
            self._round(tool_result=self.DENY, session_key="qq")
        brain.reset_tool_fuse("qq")
        self.assertFalse(brain.tool_fuse.is_tripped("qq"))

        # 重置后工具调用权恢复（execute_tool 再次被执行）
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool") as mexec, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.side_effect = [_local_resp(self.RAW),
                                   _local_resp("弄好了")]
            mexec.return_value = "✅ 完成"
            result = brain.smart_ask("帮我操作", [], session_key="qq")

        mexec.assert_called_once()
        self.assertEqual(
            result,
            (f"<think>{brain._tool_thinking_placeholder('write_file')}</think>弄好了",
             "🏠 本地 (工具)"))

    def test_reset_all_sessions(self):
        brain.tool_fuse.record_rejection("a", "t", {})
        brain.tool_fuse.record_rejection("b", "t", {})
        brain.reset_tool_fuse()      # session_key=None 清空全部
        self.assertFalse(brain.tool_fuse.is_tripped("a"))
        self.assertFalse(brain.tool_fuse.is_tripped("b"))

    def test_custom_limit_configurable(self):
        fuse = brain.ToolLoopFuse(limit=2)
        fuse.record_rejection("s", "t", {"a": 1})
        self.assertFalse(fuse.is_tripped("s"))
        fuse.record_rejection("s", "t", {"a": 1})
        self.assertTrue(fuse.is_tripped("s"))

    def test_default_limit_follows_module_constant(self):
        self.assertEqual(brain.ToolLoopFuse().limit, brain.TOOL_FUSE_LIMIT)
        self.assertGreaterEqual(brain.TOOL_FUSE_LIMIT, 1)


# ---------------------------------------------------------------------------
# smart_ask：URL 网页抓取总结
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 裸 CoT 泄漏扫描总测试（P2 · 2026-10-01 用户口径"穷举封死"）
# ---------------------------------------------------------------------------

class _Lv3PermissionManager:
    """恒放行的 Lv.3 权限替身（tools._level_at_least 走 level_value() 数值门）。"""

    def level_value(self):
        return 3

    def has_permission(self, action):
        return True


class BareCotLeakSweepTests(unittest.TestCase):
    """smart_ask 全部 return 路径的裸 CoT 封口扫描总测试。

    背景（用户实测"帮我点击蓝牙"网页漏出裸 [思考]... [计划]... [行动]...）：
    该轮恰为 ui_tap_element 失败自动回退 vision_tap_element 的分支——视觉
    点击成功（非 ❌）后汇总轮模型复读裸 CoT，旧代码只包装首轮 thinking，
    汇总轮正文原样直出（brain.py 已修复：汇总轮统一经 _seal_tool_summary
    封口；_seal_bare_cot 触发条件同步放宽为"出现任意裸协议标记"，只有
    [行动]+JSON 的残缺形态也封）。

    判定口径（每条路径统一断言 _assert_sealed）：
    - reply 含 <think> 包装 → 裸标记字面量只允许出现在包装内部，</think>
      之后的正文不得再出现任何裸标记或游离标签；
    - reply 无 <think> 包装 → 全文不得出现任何裸标记。

    全对话强制包装（2026-10-01 用户指令）：另有
    test_all_return_paths_force_wrapped_with_think_block 对全部路径追加
    "reply 一律以 <think> 开头"断言——有原生思考用原生，无则注入默认
    占位符，前端必定渲染思维链卡片。

    return 路径全集（11 条，与 brain.smart_ask 一一对应；今后新增返回路径
    必须在 _sweep_cases 登记同款用例——跑
    test_all_return_paths_seal_bare_cot 即可兜住）：
      0. 无工具普通回复（强制包装：无标记注入 CHAT 默认占位符）
      1. URL 抓取失败（固定文案 + 默认占位符，无模型轮）
      2. 双脑全挂（固定文案 + 默认占位符，无模型轮）
      3. 云端 ⚠️ 兜底转失败文案（固定文案 + 默认占位符，无模型轮）
      4. 模型空回复（固定道歉文案 + 默认占位符）
      5. URL 总结（_seal_bare_cot）
      6. 熔断剥夺纯文本（_seal_bare_cot）
      7. 熔断触发通知（_wrap_think 固定文案）
      8. ❌ 硬切断（_wrap_think + 防御 strip）
      9. 工具汇总轮失败（_wrap_think 固定文案）
     10. 工具成功汇总（_seal_tool_summary ← 本次修复的漏点）
     11. 旁路普通回复：白名单外 / 解析失败 / [行动] 残缺形态（_seal_bare_cot）
    """

    # 首轮模型输出：原生 [思考]/[计划]/[行动]+JSON 完整协议形态
    COT_RAW = ('[思考] 主人要点击蓝牙，先定位设置入口。\n'
               '[计划] 1. UI解析找蓝牙 2. 失败转视觉\n'
               '[行动] {"tool": "ui_tap_element", "args": {"element_name": "蓝牙"}}')
    # 汇总轮模型输出：复读裸 CoT（用户实测漏点形态）+ 最终自然语言收尾
    SUMMARY_BARE_COT = ('[思考] UI解析没找到蓝牙，已自动改用视觉模型。\n'
                        '[计划] 视觉定位坐标并点击\n'
                        '[行动] {"x": 123, "y": 456}\n'
                        '主人，蓝牙已经帮你点开啦！')
    # 残缺形态：只有 [行动]+JSON、无任何思考文本（_capture_thinking 捕获为空，
    # 旧判定"捕获到思考才封口"对此整段裸漏——含工具 JSON 原文）
    COT_ACTION_ONLY = '[行动] {"tool": "format_disk", "args": {}}'
    URL = "https://example.com/page"
    SESSION = "sweep"

    _BARE_MARKERS = ("[思考]", "[计划]", "[行动]",
                     "【思考】", "【计划】", "【行动】")

    def setUp(self):
        brain.tool_fuse.reset()
        tp = mock.patch.object(brain, "_resolve_tier", return_value="high")
        tp.start()
        self.addCleanup(tp.stop)

    def tearDown(self):
        brain.tool_fuse.reset()

    # ---- 判定口径（统一的封口断言）----

    def _assert_sealed(self, reply):
        reply = "" if reply is None else str(reply)
        # "（操作已执行）"绝不作为正文出现（T5 新口径负例：全文断言——
        # _wrap_think 两侧清洗剥除后，最终产出里该占位符零出现）
        self.assertNotIn(brain.BARE_COT_BODY_PLACEHOLDER, reply, reply)
        match = re.match(r"^<think>(.*?)</think>", reply, re.DOTALL)
        if match:
            body = reply[match.end():]
            self.assertNotIn("<think>", body, reply)
            self.assertNotIn("</think>", body, reply)
        else:
            body = reply
        for marker in self._BARE_MARKERS:
            self.assertNotIn(marker, body, reply)

    # ---- 复现场景 runner：每个 return 路径一个零参闭包 → (reply, source) ----

    def _tool_round(self, raw_reply, summary_reply, tool_result,
                    session_key=None):
        """通用一轮工具流程：本地首轮 raw_reply、次轮 summary_reply、
        execute_tool 打桩 tool_result（探测在线 → 本地优先）。"""
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool") as mexec, \
                mock.patch.object(brain, "ask_cloud") as mcloud, \
                contextlib.redirect_stdout(io.StringIO()):
            mr.get.return_value = mock.Mock()
            mr.post.side_effect = [_local_resp(raw_reply),
                                   _local_resp(summary_reply)]
            mexec.return_value = tool_result
            mcloud.return_value = summary_reply
            return brain.smart_ask("帮我点击蓝牙", [],
                                   session_key=session_key or self.SESSION)

    def _sweep_cases(self):
        """路径全集 → [(路径名, 零参闭包)]；闭包返回 smart_ask 的 (reply, source)。"""
        cases = []
        add = cases.append

        # 0. 无工具普通回复：无任何标记 → 注入默认占位符包装，也绝无泄漏
        def plain_chat():
            with mock.patch.object(brain, "requests") as mr, \
                    contextlib.redirect_stdout(io.StringIO()):
                mr.get.return_value = mock.Mock()
                mr.post.return_value = _local_resp("今天天气不错哦～")
                return brain.smart_ask("你好", [], session_key=self.SESSION)
        add(("0.无工具普通回复", plain_chat))

        # 1. URL 抓取失败：固定文案（无模型轮；纳入扫描防未来改动引入动态内容）
        def url_fetch_failure():
            with mock.patch.object(brain, "requests") as mr, \
                    contextlib.redirect_stdout(io.StringIO()):
                mr.get.side_effect = OSError("timed out")
                return brain.smart_ask(f"帮我总结 {self.URL}", [],
                                       session_key=self.SESSION)
        add(("1.URL抓取失败", url_fetch_failure))

        # 2. 双脑全挂：ask_local 抛 + ask_cloud 抛 → 固定失败文案
        def both_brains_down():
            with mock.patch.object(brain, "requests") as mr, \
                    mock.patch.object(brain, "ask_cloud") as mcloud, \
                    contextlib.redirect_stdout(io.StringIO()):
                mr.get.return_value = mock.Mock()            # 探测在线
                mr.post.side_effect = OSError("本地大脑挂了")
                mcloud.side_effect = Exception("云端也挂了")
                return brain.smart_ask("帮我点击蓝牙", [],
                                       session_key=self.SESSION)
        add(("2.双脑全挂", both_brains_down))

        # 3. 云端 ⚠️ 兜底 → 失败文案（探测失败直接云端，ask_cloud 返回 ⚠️ 串）
        def cloud_warning_fallback():
            with mock.patch.object(brain, "requests") as mr, \
                    mock.patch.object(brain, "ask_cloud") as mcloud, \
                    contextlib.redirect_stdout(io.StringIO()):
                mr.get.side_effect = OSError("refused")
                mcloud.return_value = "⚠️ 云端连接异常: connection reset"
                return brain.smart_ask("帮我点击蓝牙", [],
                                       session_key=self.SESSION)
        add(("3.云端警告兜底", cloud_warning_fallback))

        # 4. 模型空回复 → 固定道歉文案
        def empty_reply():
            with mock.patch.object(brain, "requests") as mr, \
                    contextlib.redirect_stdout(io.StringIO()):
                mr.get.return_value = mock.Mock()
                mr.post.return_value = _local_resp("   ")
                return brain.smart_ask("帮我点击蓝牙", [],
                                       session_key=self.SESSION)
        add(("4.空回复", empty_reply))

        # 5. URL 总结：总结文本带原生 [思考]/[计划]/[行动]+JSON → 封口
        def url_summary():
            with mock.patch.object(brain, "requests") as mr, \
                    mock.patch.object(brain, "ask_cloud") as mcloud, \
                    contextlib.redirect_stdout(io.StringIO()):
                def get_side_effect(url, **kwargs):
                    if url == self.URL:
                        resp = mock.Mock()
                        resp.text = "<p>网页正文</p>"
                        return resp
                    raise OSError("refused")   # 探测失败 → 云端
                mr.get.side_effect = get_side_effect
                mcloud.return_value = ("[思考] 先梳理正文要点。\n"
                                       "[计划] 提炼总结\n"
                                       '[行动] {"tool": "web_search"}\n'
                                       "这是网页总结。")
                return brain.smart_ask(f"帮我总结 {self.URL}", [],
                                       session_key=self.SESSION)
        add(("5.URL总结", url_summary))

        # 6. 熔断剥夺纯文本：模型仍输出完整 CoT（工具权已被剥夺，不再解析）
        def fused_plain_text():
            for _ in range(brain.TOOL_FUSE_LIMIT):
                brain.tool_fuse.record_rejection(
                    self.SESSION, "ui_tap_element", {"element_name": "蓝牙"})
            with mock.patch.object(brain, "requests") as mr, \
                    mock.patch.object(brain, "execute_tool") as mexec, \
                    contextlib.redirect_stdout(io.StringIO()):
                mr.get.return_value = mock.Mock()
                mr.post.return_value = _local_resp(self.COT_RAW)
                mexec.return_value = "不应被执行"
                return brain.smart_ask("再试一次", [], session_key=self.SESSION)
        add(("6.熔断剥夺纯文本", fused_plain_text))

        # 7. 熔断触发通知：❌ 结果连续达阈值 → ⛔ 固定通知文案（_wrap_think）
        def fuse_notice():
            with mock.patch.object(brain, "requests") as mr, \
                    mock.patch.object(brain, "execute_tool") as mexec, \
                    contextlib.redirect_stdout(io.StringIO()):
                mr.get.return_value = mock.Mock()
                mexec.return_value = "❌ 安全拒绝：当前权限不足"
                result = None
                for _ in range(brain.TOOL_FUSE_LIMIT):
                    mr.post.side_effect = [_local_resp(self.COT_RAW),
                                           _local_resp("不会走到这")]
                    result = brain.smart_ask("帮我点击蓝牙", [],
                                             session_key=self.SESSION)
                self.assertEqual(result[1], "⛔ 熔断")
                return result
        add(("7.熔断通知", fuse_notice))

        # 8. ❌ 硬切断：vision 回退失败的返回串形态（_wrap_think + 防御 strip）
        def vision_cutoff():
            return self._tool_round(
                self.COT_RAW, "不会走到这",
                "❌ 视觉模型在屏幕上未找到【蓝牙】。 ⚠️ 请确认手机屏幕已亮屏"
                "且停留在目标页面，同时确认 .env 中的 VISION_MODEL 是真正的视觉模型")
        add(("8.视觉回退失败切断", vision_cutoff))

        # 9. 工具汇总轮失败：本地汇总抛 + 云端汇总抛 → 固定失败文案（_wrap_think）
        def summarize_failure():
            with mock.patch.object(brain, "requests") as mr, \
                    mock.patch.object(brain, "execute_tool") as mexec, \
                    mock.patch.object(brain, "ask_cloud") as mcloud, \
                    contextlib.redirect_stdout(io.StringIO()):
                mr.get.return_value = mock.Mock()
                mr.post.side_effect = [_local_resp(self.COT_RAW),
                                       ConnectionError("本地汇总挂了")]
                mexec.return_value = "✅ 已模拟点击坐标: (123, 456)"
                mcloud.side_effect = Exception("云端汇总也挂了")
                return brain.smart_ask("帮我点击蓝牙", [],
                                       session_key=self.SESSION)
        add(("9.汇总轮失败", summarize_failure))

        # 10. 工具成功汇总（本次修复的漏点）：汇总轮复读裸 CoT
        #     → _seal_tool_summary（两轮思考并卡、正文只留收尾）
        def tool_summary_bare_cot():
            return self._tool_round(
                self.COT_RAW, self.SUMMARY_BARE_COT,
                "✅ 已模拟点击坐标: (123, 456)（已执行二次确认点击）")
        add(("10.工具成功汇总(漏点)", tool_summary_bare_cot))

        # 11a. 旁路普通回复：JSON 合法但工具白名单外 → 不执行，封口
        def whitelist_rejected():
            return self._tool_round(
                self.COT_RAW.replace("ui_tap_element", "format_disk"),
                "不会走到这", "不应被执行")
        add(("11a.白名单外", whitelist_rejected))

        # 11b. 旁路普通回复：JSON 残缺解析不出 → 封口
        def unparseable_json():
            return self._tool_round(
                '[思考] 主人要点击蓝牙，先定位设置入口。\n'
                '[计划] 1. UI解析找蓝牙 2. 失败转视觉\n'
                '[行动] {"tool": "ui_tap_element" "args": {}}',
                "不会走到这", "不应被执行")
        add(("11b.解析失败", unparseable_json))

        # 11c. 残缺形态：只有 [行动]+JSON 无思考文本 → 任意标记触发封口
        def action_only():
            return self._tool_round(self.COT_ACTION_ONLY, "不会走到这",
                                    "不应被执行")
        add(("11c.行动残缺形态", action_only))

        return cases

    # ---- 总测试：路径全集参数化，逐条断言无裸 CoT 漏出 ----

    def test_all_return_paths_seal_bare_cot(self):
        for name, runner in self._sweep_cases():
            with self.subTest(path=name):
                brain.tool_fuse.reset()   # 各路径用例间熔断状态互不串扰
                reply, _source = runner()
                self._assert_sealed(reply)

    def test_all_return_paths_force_wrapped_with_think_block(self):
        """全对话强制包装（2026-10-01 用户指令）：全部 return 路径的 reply
        一律以 <think> 开头——有原生思考用原生，无则注入默认占位符
        （"[思考] 正在理解你的意图..."），前端必定渲染思维链卡片。"""
        for name, runner in self._sweep_cases():
            with self.subTest(path=name):
                brain.tool_fuse.reset()   # 各路径用例间熔断状态互不串扰
                reply, _source = runner()
                self.assertTrue(str(reply).startswith("<think>"), (name, reply))
                self.assertIn("</think>", str(reply), (name, reply))

    # ---- 漏点与封口细节（路径 8 / 10 / 11c 专项）----

    def test_leak_path_tool_summary_folds_round2_cot_into_card(self):
        """漏点详情（路径 10）：ui_tap 失败→vision 回退成功后的汇总轮复读裸
        CoT——两轮思考并入同一张推理卡片，正文只留最终自然语言回复，
        汇总轮 [行动] JSON 载荷不上屏；[CoT] 原生思考日志首轮+汇总轮各一条。"""
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool") as mexec, \
                mock.patch.object(brain, "ask_cloud") as mcloud:
            mr.get.return_value = mock.Mock()
            mr.post.side_effect = [_local_resp(self.COT_RAW),
                                   _local_resp(self.SUMMARY_BARE_COT)]
            mexec.return_value = "✅ 已模拟点击坐标: (123, 456)"
            mcloud.return_value = "x"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                reply, source = brain.smart_ask("帮我点击蓝牙", [],
                                                session_key=self.SESSION)
        self.assertEqual(source, "🏠 本地 (工具)")
        self._assert_sealed(reply)
        self.assertTrue(reply.startswith("<think>[思考] 主人要点击蓝牙"), reply)
        inner = reply.split("</think>", 1)[0]
        self.assertIn("[思考] UI解析没找到蓝牙", inner)     # 汇总轮思考并入卡片
        self.assertIn("[计划] 视觉定位坐标并点击", inner)
        self.assertTrue(reply.endswith("主人，蓝牙已经帮你点开啦！"), reply)
        body_part = reply.split("</think>", 1)[1]
        self.assertNotIn('"x": 123', body_part)             # 汇总轮载荷不上屏
        # [CoT] 终端日志：首轮与汇总轮各一条（部署侧可确认两轮思考来源）
        self.assertEqual(buf.getvalue().count("[CoT] 模型原生输出思考内容"), 2)

    def test_action_only_bare_cot_sealed_with_placeholder_thinking(self):
        """残缺形态（路径 11c）封口细节：只有 [行动]+JSON、无思考文本——
        旧判定（捕获到思考才封口）整段裸漏（含工具 JSON 原文），现按任意
        标记触发封口 + 占位思考 + 正文剥空兜底（T5 新口径：注入型工具占位
        思考不回补正文，以"操作已完成。"兜底，废止旧"（操作已执行）"占位）。"""
        result = self._tool_round(self.COT_ACTION_ONLY, "不会走到这",
                                  "不应被执行")
        reply, _source = result
        self._assert_sealed(reply)
        self.assertTrue(reply.startswith(
            f"<think>{brain.TOOL_THINKING_PLACEHOLDER}</think>"
            f"{brain.DEFAULT_BODY_PLACEHOLDER}"),
            reply)
        self.assertNotIn(brain.BARE_COT_BODY_PLACEHOLDER, reply)
        self.assertNotIn('"tool"', reply.split("</think>", 1)[1])

    def test_action_only_marker_with_whitelisted_tool_reaches_tool_path(self):
        """[行动]+JSON 且工具在白名单：照常走工具路径（占位思考包装），
        封口加固不改变既有工具行为。"""
        result = self._tool_round(
            '[行动] {"tool": "list_files", "args": {}}',
            "已经帮你弄好了", "（工作区为空）")
        reply, source = result
        self.assertEqual(source, "🏠 本地 (工具)")
        self._assert_sealed(reply)
        self.assertTrue(reply.endswith("已经帮你弄好了"), reply)

    def test_plain_chat_wrapped_with_default_placeholder(self):
        """反转口径（2026-10-01 全对话强制包装）：无任何标记的普通聊天注入
        默认占位符包装，正文原样保留——前端必定渲染思维链卡片。"""
        with mock.patch.object(brain, "requests") as mr, \
                contextlib.redirect_stdout(io.StringIO()):
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("让我想想再回答你哦。")
            reply, source = brain.smart_ask("你好", [], session_key=self.SESSION)
        self.assertEqual(
            (reply, source),
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>让我想想再回答你哦。",
             "🏠 本地"))

    def test_marker_with_empty_content_still_sealed(self):
        """[思考] 标记后只有空白（捕获为空）→ 任意标记触发封口，
        标记本身不再裸漏。"""
        result = self._tool_round("[思考] [计划] ", "x", "不应被执行")
        reply, _source = result
        self._assert_sealed(reply)
        self.assertTrue(reply.startswith("<think>"), reply)

    def test_cutoff_body_with_embedded_model_cot_stripped(self):
        """❌ 切断防御封口（路径 8）：vision_tools 解析失败形态会把视觉模型
        原文拼进返回串——原文混入裸 CoT 时正文侧剥净（错误前缀保留），
        绝不直出网页。"""
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool") as mexec, \
                mock.patch.object(brain, "ask_cloud") as mcloud, \
                contextlib.redirect_stdout(io.StringIO()):
            mr.get.side_effect = OSError("refused")
            mcloud.side_effect = [self.COT_RAW]
            mexec.return_value = ('❌ 视觉模型未能识别出坐标。回复内容：'
                                  '[思考] 我看到屏幕上有设置图标\n'
                                  '[计划] 给出坐标\n[行动] {"x": 1, "y": 2}')
            reply, source = brain.smart_ask("帮我点击蓝牙", [],
                                            session_key=self.SESSION)
        self.assertEqual(source, "☁️ 云端 (工具)")
        self._assert_sealed(reply)
        body_part = reply.split("</think>", 1)[1]
        self.assertTrue(body_part.startswith("❌ 视觉模型未能识别出坐标。"),
                        body_part)
        self.assertNotIn("[思考]", body_part)

    # ---- ui_tap→vision 回退分支端到端（真实 tools.execute_tool 分发）----

    def test_ui_tap_to_vision_fallback_success_summary_sealed(self):
        """用户实测漏点端到端复现：ui_tap_element 解析失败 → 自动回退
        vision_tap_element → 视觉点击成功（非 ❌）→ 汇总轮模型复读裸
        [思考]/[计划]/[行动]（旧代码在此直出网页）→ 现已封口：两轮思考
        并入同一张推理卡片，正文只留最终自然语言回复。"""
        import tools
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "permission_manager",
                                  _Lv3PermissionManager()), \
                mock.patch.object(tools, "ui_tap_element",
                                  return_value="❌ 未找到元素: 蓝牙"), \
                mock.patch.object(tools, "vision_tap_element",
                                  return_value="✅ 已模拟点击坐标: (123, 456)"), \
                mock.patch.object(tools, "VISION_MODEL", "qwen-vl-test"), \
                mock.patch.object(tools, "VISION_KEY", "sk-test"), \
                mock.patch.object(brain, "ask_cloud") as mcloud, \
                contextlib.redirect_stdout(io.StringIO()):
            mr.get.side_effect = OSError("refused")   # 探测失败 → 全程云端
            mcloud.side_effect = [self.COT_RAW, self.SUMMARY_BARE_COT]
            reply, source = brain.smart_ask("帮我点击蓝牙", [],
                                            session_key=self.SESSION)
        self.assertEqual(source, "☁️ 云端 (工具)")
        self._assert_sealed(reply)
        self.assertTrue(reply.startswith("<think>[思考] 主人要点击蓝牙"), reply)
        inner = reply.split("</think>", 1)[0]
        self.assertIn("[思考] UI解析没找到蓝牙", inner)   # 汇总轮思考并入同卡
        self.assertTrue(reply.endswith("主人，蓝牙已经帮你点开啦！"), reply)

    def test_ui_tap_to_vision_fallback_failure_cutoff_sealed(self):
        """回退分支 ❌ 结果（视觉也未找到）：❌ 硬切断路径——首轮思考包装 +
        拒绝文案直出正文（❌ 文案无裸标记），封口判定通过。"""
        import tools
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "permission_manager",
                                  _Lv3PermissionManager()), \
                mock.patch.object(tools, "ui_tap_element",
                                  return_value="❌ 未找到元素: 蓝牙"), \
                mock.patch.object(tools, "vision_tap_element",
                                  return_value="❌ 视觉模型在屏幕上未找到【蓝牙】。"), \
                mock.patch.object(tools, "VISION_MODEL", "qwen-vl-test"), \
                mock.patch.object(tools, "VISION_KEY", "sk-test"), \
                mock.patch.object(brain, "ask_cloud") as mcloud, \
                contextlib.redirect_stdout(io.StringIO()):
            mr.get.side_effect = OSError("refused")
            mcloud.side_effect = [self.COT_RAW]
            reply, source = brain.smart_ask("帮我点击蓝牙", [],
                                            session_key=self.SESSION)
        self.assertEqual(source, "☁️ 云端 (工具)")
        self._assert_sealed(reply)
        self.assertTrue(reply.startswith("<think>[思考] 主人要点击蓝牙"), reply)
        self.assertIn("❌ 视觉模型在屏幕上未找到【蓝牙】", reply)


class SmartAskUrlTests(unittest.TestCase):
    """输入含 URL：先抓正文（剔除 script/style）→ 以总结方式并入提问。"""

    HTML = ("<html><head><title>测试页</title>"
            "<style>body { color: red; }</style></head>"
            "<body><script>var secret = 'SECRET_SCRIPT';</script>"
            "<p>这是正文内容，包含关键信息。</p>"
            "<div>第二段正文</div></body></html>")
    URL = "https://example.com/page"

    def setUp(self):
        tp = mock.patch.object(brain, "_resolve_tier", return_value="high")
        tp.start()
        self.addCleanup(tp.stop)

    def _run(self, probe_ok, page=None, get_error=None, cloud_reply="这是网页总结"):
        """probe_ok 决定探测结果；page 为抓取到的 HTML（get_error 时直接抛错）。

        ask_cloud 打桩返回 cloud_reply；同时把本地响应也设为同一文案，保证
        探测成功时 ask_local（经 mr.post）返回相同内容，便于断言来源标签。
        """
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            mr.post.return_value = _local_resp(cloud_reply)
            if get_error is not None:
                mr.get.side_effect = get_error
            else:
                def get_side_effect(url, **kwargs):
                    if url == self.URL:
                        resp = mock.Mock()
                        resp.text = page
                        return resp
                    # 探测请求
                    if probe_ok:
                        return mock.Mock()
                    raise OSError("refused")

                mr.get.side_effect = get_side_effect
            mcloud.return_value = cloud_reply
            result = brain.smart_ask(f"帮我总结 {self.URL}", [])
        return result, mcloud

    def test_url_fetch_cloud_summary_label(self):
        result, mcloud = self._run(probe_ok=False, page=self.HTML)
        # 全对话强制包装：无标记总结注入默认占位符
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>这是网页总结",
             "☁️ 云端 (总结)"))

        msgs = mcloud.call_args.args[0]
        self.assertEqual(msgs[0]["content"], prompts.SYSTEM_PROMPT["content"])
        self.assertEqual(msgs[-2], {"role": "user", "content": f"帮我总结 {self.URL}"})
        web_msg = msgs[-1]
        self.assertEqual(web_msg["role"], "system")
        self.assertIn("已为你抓取好网页，请直接总结，不要输出任何 JSON！", web_msg["content"])
        self.assertIn("网页内容：", web_msg["content"])

    def test_script_and_style_stripped(self):
        # 探测成功：走 ask_local（经 mr.post），检查发往本地模型的网页内容
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            def get_side_effect(url, **kwargs):
                if url == self.URL:
                    resp = mock.Mock()
                    resp.text = self.HTML
                    return resp
                return mock.Mock()  # 探测成功

            mr.get.side_effect = get_side_effect
            mr.post.return_value = _local_resp("这是网页总结")
            result = brain.smart_ask(f"帮我总结 {self.URL}", [])

        # 全对话强制包装：无标记总结注入默认占位符
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>这是网页总结",
             "🏠 本地 (总结)"))
        web_msg = mr.post.call_args.kwargs["json"]["messages"][-1]["content"]
        self.assertIn("已为你抓取好网页，请直接总结，不要输出任何 JSON！", web_msg)
        self.assertIn("这是正文内容，包含关键信息。", web_msg)
        self.assertIn("第二段正文", web_msg)
        self.assertNotIn("SECRET_SCRIPT", web_msg)
        self.assertNotIn("color: red", web_msg)
        self.assertNotIn("<p>", web_msg)

    def test_fetch_failure_returns_error(self):
        result, mcloud = self._run(probe_ok=True, get_error=OSError("timed out"))
        # 全对话强制包装：抓取失败固定文案同样注入默认占位符
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>"
             "❌ 抓取网页失败: timed out", "❌ 失败"))
        mcloud.assert_not_called()

    def test_body_truncated_to_2000_chars(self):
        long_body = "<p>" + "橘" * 5000 + "</p>"
        result, mcloud = self._run(probe_ok=False, page=long_body)
        web_msg = mcloud.call_args.args[0][-1]["content"]
        body = web_msg.split("网页内容：\n", 1)[1]
        self.assertEqual(len(body), 2000)


# ---------------------------------------------------------------------------
# 会话记忆：MAX_MESSAGES=50 截断
# ---------------------------------------------------------------------------

class HardwareAdaptiveRoutingTests(unittest.TestCase):
    """硬件自适应路由：high/medium/low 三档的本地/云端优先级与模型选择。"""

    SMALL = xiaoju3.LOCAL_MODEL_SMALL

    def _tier(self, value):
        tp = mock.patch.object(brain, "_resolve_tier", return_value=value)
        tp.start()
        self.addCleanup(tp.stop)

    def test_low_skips_probe_and_goes_cloud(self):
        """low 档：不探测本地（省 1 秒），直接云端，标签 ☁️。"""
        self._tier("low")
        with mock.patch.object(brain, "probe_local") as mprobe,                 mock.patch.object(brain, "ask_local") as mlocal,                 mock.patch.object(brain, "requests") as mr, _quiet():
            mr.post.return_value = _cloud_resp("云端回答")
            result = brain.smart_ask("你好", [])
        mprobe.assert_not_called()
        mlocal.assert_not_called()
        # 全对话强制包装：普通闲聊注入默认占位符
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>云端回答", "☁️ 云端"))
        args, _kwargs = mr.post.call_args
        self.assertEqual(args[0], xiaoju3.CLOUD_URL)

    def test_medium_uses_small_model(self):
        """medium 档：探测本地并用小模型（LOCAL_MODEL_SMALL）。"""
        self._tier("medium")
        with mock.patch.object(brain, "requests") as mr,                 mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("小模型回答")
            result = brain.smart_ask("你好", [])
        # 全对话强制包装：普通闲聊注入默认占位符
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>小模型回答", "🏠 本地"))
        args, kwargs = mr.post.call_args
        self.assertEqual(args[0], xiaoju3.LOCAL_URL)
        self.assertEqual(kwargs["json"]["model"], self.SMALL)
        mcloud.assert_not_called()

    def test_medium_summary_round_goes_cloud(self):
        """medium 档：工具成功后汇总轮固定走云端（不试本地）。"""
        self._tier("medium")
        raw = '{"tool": "list_files", "args": {}}'
        with mock.patch.object(brain, "requests") as mr,                 mock.patch.object(brain, "probe_local", return_value=True),                 mock.patch.object(brain, "execute_tool", return_value="✅ 文件列表"),                 mock.patch.object(brain, "ask_local") as mlocal, _quiet():
            mlocal.return_value = _local_resp(raw).json()["message"]["content"]
            mr.post.return_value = _cloud_resp("汇总：工作区有 3 个文件")
            result = brain.smart_ask("看看工作区", [])
        self.assertEqual(mlocal.call_count, 1)      # 只有主轮用了本地
        mlocal.assert_called_once_with(mock.ANY, model=self.SMALL)
        self.assertEqual(
            result,
            (f"<think>{brain._tool_thinking_placeholder('list_files')}</think>汇总：工作区有 3 个文件",
             "☁️ 云端 (工具)"))

    def test_high_summary_round_keeps_local_first(self):
        """high 档：汇总轮本地优先（既有 §10 #14 行为）。"""
        self._tier("high")
        raw = '{"tool": "list_files", "args": {}}'
        with mock.patch.object(brain, "requests") as mr,                 mock.patch.object(brain, "probe_local", return_value=True),                 mock.patch.object(brain, "execute_tool", return_value="✅ 文件列表"),                 mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            mr.post.side_effect = [_local_resp(raw), _local_resp("汇总：3 个文件")]
            result = brain.smart_ask("看看工作区", [])
        self.assertEqual(
            result,
            (f"<think>{brain._tool_thinking_placeholder('list_files')}</think>汇总：3 个文件",
             "🏠 本地 (工具)"))
        mcloud.assert_not_called()
        models = [c.kwargs["json"]["model"] for c in mr.post.call_args_list]
        self.assertEqual(models, [xiaoju3.LOCAL_MODEL, xiaoju3.LOCAL_MODEL])

    def test_medium_local_down_falls_back_cloud(self):
        """medium 档：本地探测在线但小模型调用异常 → 热切换云端。"""
        self._tier("medium")
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.side_effect = [OSError("小模型崩了"), _cloud_resp("云端回答")]
            result = brain.smart_ask("你好", [])
        # 全对话强制包装：热切换的普通回复同样注入默认占位符
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>云端回答", "☁️ 云端"))

    def test_explicit_tier_overrides_auto(self):
        """显式 DEVICE_TIER 优先于 auto 探测；探测缓存可重置。"""
        brain._reset_tier_cache()
        with mock.patch.object(xiaoju3, "DEVICE_TIER", "low"),                 mock.patch("hardware_profiler.detect_tier", return_value="high") as mdet,                 mock.patch.object(brain, "probe_local") as mprobe,                 mock.patch.object(brain, "requests") as mr, _quiet():
            mr.post.return_value = _cloud_resp("云端回答")
            brain.smart_ask("你好", [])
        mdet.assert_not_called()
        mprobe.assert_not_called()
        brain._reset_tier_cache()

    def test_auto_resolves_via_profiler(self):
        """auto：经 hardware_profiler 探测并缓存；非法值同样按 auto 处理。"""
        brain._reset_tier_cache()
        with mock.patch.object(xiaoju3, "DEVICE_TIER", "auto"),                 mock.patch("hardware_profiler.detect_tier", return_value="low") as mdet,                 mock.patch.object(brain, "probe_local") as mprobe,                 mock.patch.object(brain, "requests") as mr, _quiet():
            mr.post.return_value = _cloud_resp("云端回答")
            brain.smart_ask("你好", [])
            brain.smart_ask("再问一句", [])
        mdet.assert_called_once()                    # 进程内只探一次
        self.assertEqual(mprobe.call_count, 0)
        brain._reset_tier_cache()

    def test_invalid_tier_falls_back_to_auto_detection(self):
        brain._reset_tier_cache()
        with mock.patch.object(xiaoju3, "DEVICE_TIER", "bogus"),                 mock.patch("hardware_profiler.detect_tier", return_value="medium"),                 mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()        # medium：探测在线 → 本地小模型
            mr.post.return_value = _local_resp("小模型回答")
            result = brain.smart_ask("你好", [])
        # 全对话强制包装：普通闲聊注入默认占位符
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>小模型回答", "🏠 本地"))
        brain._reset_tier_cache()

    def test_ask_local_model_parameter(self):
        """ask_local 支持按档位传模型；缺省仍用 LOCAL_MODEL。"""
        with mock.patch.object(brain, "requests") as mr:
            mr.post.return_value = _local_resp("ok")
            brain.ask_local([{"role": "user", "content": "hi"}])
            args, kwargs = mr.post.call_args
            self.assertEqual(kwargs["json"]["model"], xiaoju3.LOCAL_MODEL)
            brain.ask_local([{"role": "user", "content": "hi"}], model=self.SMALL)
            args, kwargs = mr.post.call_args
            self.assertEqual(kwargs["json"]["model"], self.SMALL)


class MemoryTests(unittest.TestCase):
    """load_memory / save_memory：滚动保留最近 50 条。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="xiaoju3_brain_test_")
        self.path = os.path.join(self.tmpdir, "history_test.json")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_truncates_to_last_50(self):
        history = [{"role": "user", "content": f"m{i}"} for i in range(60)]
        brain.save_memory(history, self.path)
        loaded = brain.load_memory(self.path)
        self.assertEqual(len(loaded), xiaoju3.MAX_MESSAGES)
        self.assertEqual(len(loaded), 50)
        self.assertEqual(loaded[0]["content"], "m10")   # 丢最旧的 10 条
        self.assertEqual(loaded[-1]["content"], "m59")

    def test_save_under_limit_kept_whole(self):
        history = [{"role": "user", "content": "你好，小橘！"}]
        brain.save_memory(history, self.path)
        self.assertEqual(brain.load_memory(self.path), history)
        # ensure_ascii=False：中文原样落盘
        with open(self.path, "r", encoding="utf-8") as f:
            self.assertIn("你好，小橘！", f.read())

    def test_load_missing_file_returns_empty(self):
        self.assertEqual(brain.load_memory(os.path.join(self.tmpdir, "nope.json")), [])

    def test_load_corrupted_file_returns_empty(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{bad json")
        self.assertEqual(brain.load_memory(self.path), [])

    def test_save_creates_parent_dirs(self):
        deep = os.path.join(self.tmpdir, "a", "b", "history.json")
        brain.save_memory([{"role": "user", "content": "x"}], deep)
        self.assertTrue(os.path.exists(deep))


# ---------------------------------------------------------------------------
# translate_emoji：转换正确，且不接入 smart_ask 回复链
# ---------------------------------------------------------------------------

def _fake_emoji_manager():
    mod = types.ModuleType("emoji_manager")

    def get_emoji_path(tag):
        return "/emoji/lib/kaixin.png" if tag == "开心" else None

    mod.get_emoji_path = get_emoji_path
    return mod


class TranslateEmojiTests(unittest.TestCase):

    def test_known_tag_converted_to_cq_image(self):
        with mock.patch.dict(sys.modules, {"emoji_manager": _fake_emoji_manager()}):
            self.assertEqual(brain.translate_emoji("哈哈[EMOJI:开心]"),
                             "哈哈[CQ:image,file=file:///emoji/lib/kaixin.png]")

    def test_unknown_tag_degrades_to_text(self):
        # W1 降级口径：下载兜底仍无图 → 降级纯文本"[表情: 标签]"，
        # 绝不返回未转换的 [EMOJI: 原文
        with mock.patch.dict(sys.modules, {"emoji_manager": _fake_emoji_manager()}):
            self.assertEqual(brain.translate_emoji("呜呜[EMOJI:大哭]"),
                             "呜呜[表情: 大哭]")

    def test_mixed_tags(self):
        with mock.patch.dict(sys.modules, {"emoji_manager": _fake_emoji_manager()}):
            self.assertEqual(
                brain.translate_emoji("A[EMOJI:开心]B[EMOJI:缺失]C"),
                "A[CQ:image,file=file:///emoji/lib/kaixin.png]B[表情: 缺失]C")

    def test_no_tag_unchanged(self):
        self.assertEqual(brain.translate_emoji("普通回复，没有标签。"),
                         "普通回复，没有标签。")

    def test_emoji_manager_missing_graceful(self):
        # sys.modules 置 None 使延迟导入稳定抛 ImportError → 安全封口转纯文本，
        # 绝不崩溃、绝不再返回未转换的 [EMOJI: 原文
        with mock.patch.dict(sys.modules, {"emoji_manager": None}):
            self.assertEqual(brain.translate_emoji("[EMOJI:开心]"), "[表情: 开心]")

    def test_get_emoji_path_crash_still_degrades_to_text(self):
        # 链路异常（get_emoji_path 抛错，如下载崩溃）→ 降级纯文本，绝不崩溃
        mod = types.ModuleType("emoji_manager")

        def boom(tag):
            raise RuntimeError("下载链路崩了")

        mod.get_emoji_path = boom
        with mock.patch.dict(sys.modules, {"emoji_manager": mod}):
            self.assertEqual(brain.translate_emoji("哈哈[EMOJI:开心]"),
                             "哈哈[表情: 开心]")

    def test_wired_into_smart_ask_reply_chain(self):
        # 文档 §5 闭环口径：smart_ask 返回前调用 translate_emoji 转换
        with mock.patch.object(brain, "translate_emoji",
                               side_effect=lambda r: r.replace(
                                   "[EMOJI:开心]", "[已转换]")) as mtrans, \
                mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("带[EMOJI:开心]的回复")
            result = brain.smart_ask("你好", [])

        mtrans.assert_called_once_with("带[EMOJI:开心]的回复")
        # 表情先转换再包装：普通闲聊回复同样注入默认占位符
        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>带[已转换]的回复",
             "🏠 本地"))

    def test_emoji_translated_end_to_end_with_fake_library(self):
        # 假表情库：正常回复中的 [EMOJI:标签] 转成 CQ 码后随回复真正发出
        with mock.patch.dict(sys.modules, {"emoji_manager": _fake_emoji_manager()}), \
                mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("哈哈[EMOJI:开心]")
            result = brain.smart_ask("你好", [])

        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>"
             "哈哈[CQ:image,file=file:///emoji/lib/kaixin.png]", "🏠 本地"))

    def setUp(self):
        # 与机器状态/本地 .env 档位解耦：固定 high + 探测在线
        tp = mock.patch.object(brain, "_resolve_tier", return_value="high")
        tp.start()
        self.addCleanup(tp.stop)
        pp = mock.patch.object(brain, "probe_local", return_value=True)
        pp.start()
        self.addCleanup(pp.stop)

    def test_emoji_missing_library_degrades_gracefully(self):
        # emoji_manager 缺席 → 安全封口降级"[表情: 标签]"纯文本，不阻断回复链
        with mock.patch.dict(sys.modules, {"emoji_manager": None}), \
                mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("哈哈[EMOJI:开心]")
            result = brain.smart_ask("你好", [])

        self.assertEqual(
            result,
            (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>哈哈[表情: 开心]",
             "🏠 本地"))

    def test_tool_summary_reply_translated_too(self):
        # 工具汇总轮的回复同样过 translate_emoji
        raw = '{"tool": "list_files", "args": {}}'
        with mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool") as mexec, \
                mock.patch.object(brain, "translate_emoji",
                                  side_effect=lambda r: r.replace(
                                      "[EMOJI:开心]", "[图]")) as mtrans, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.side_effect = [_local_resp(raw),
                                   _local_resp("弄好啦[EMOJI:开心]")]
            mexec.return_value = "（工作区为空）"
            result = brain.smart_ask("帮我看看", [])

        # 表情先转换，再包 <think> 推理块（转换函数只见原文本，不见包装）
        self.assertEqual(
            result,
            (f"<think>{brain._tool_thinking_placeholder('list_files')}</think>弄好啦[图]",
             "🏠 本地 (工具)"))
        mtrans.assert_called_once_with("弄好啦[EMOJI:开心]")


# ---------------------------------------------------------------------------
# W1 核心功能接线：前情提要压缩（§10 #2）
# ---------------------------------------------------------------------------

class ContextCompressionWiringTests(unittest.TestCase):
    """smart_ask 前情提要压缩接线：>20 条 → compress_context 前情提要 +
    最近 10 条明细（替换硬截断口径）；缓存持久化（命中复用 / 历史变化失效
    重压）；压缩失败 / 降级摘要 / 缓存损坏降级不崩溃。compress_context 一律
    mock，全程离线；缓存文件一律注入临时目录。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="xiaoju3_brain_compress_")
        cp = mock.patch.object(brain, "CONTEXT_SUMMARY_FILE",
                               os.path.join(self.tmpdir, "context_summary.json"))
        cp.start()
        self.addCleanup(cp.stop)
        tp = mock.patch.object(brain, "_resolve_tier", return_value="high")
        tp.start()
        self.addCleanup(tp.stop)
        # 共享 fake 状态外置层归零：长期记忆注入不影响本类消息结构断言
        self.sm = _STATE_FAKE.state_manager
        self._reset_sm()
        # 位置上下文（2026-10-02 隐私口径）与本类无关：恒等旁路，消息结构
        # 断言保持原口径（其自身行为在 LocationAskTests 覆盖）
        lp = mock.patch.object(brain, "_inject_location_context",
                               side_effect=lambda m: m)
        lp.start()
        self.addCleanup(lp.stop)

    def _reset_sm(self):
        # MagicMock 的重置方法是 reset_mock（reset 会被当作子 mock 属性，清不掉）
        self.sm.reset_mock(return_value=True, side_effect=True)
        self.sm.get_recent_memories.return_value = []
        self.sm.save_memory.return_value = None

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        self._reset_sm()

    @staticmethod
    def _history(n):
        return [{"role": "user" if i % 2 == 0 else "assistant",
                 "content": f"历史消息{i}"} for i in range(n)]

    _SUMMARY = "【前情提要】：主人此前与小橘聊过小橘的功能与记忆机制。"

    def _compress_patch(self, summary=_SUMMARY):
        """把 plugins.context_manager.compress_context 换成可控假压缩。"""

        def fake_compress(messages, max_messages=20, keep_recent=10):
            return [messages[0],
                    {"role": "system", "content": summary},
                    *messages[-keep_recent:]]

        return mock.patch("plugins.context_manager.compress_context",
                          side_effect=fake_compress)

    def test_over_20_history_compresses_and_injects_summary(self):
        history = self._history(25)
        with self._compress_patch() as mcomp, \
                mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("好的呀")
            brain.smart_ask("当前问题", history)

        mcomp.assert_called_once()
        msgs = mr.post.call_args.kwargs["json"]["messages"]
        # 压缩形态：置顶系统提示词 + 前情提要 system 条目 + 最近 10 条明细
        self.assertEqual(msgs[0], prompts.SYSTEM_PROMPT)
        self.assertEqual(msgs[1]["role"], "system")
        self.assertTrue(msgs[1]["content"].startswith("【前情提要】"))
        self.assertIn(self._SUMMARY, msgs[1]["content"])
        self.assertEqual(len(msgs), 12)
        self.assertEqual(msgs[-1], {"role": "user", "content": "当前问题"})
        self.assertEqual(msgs[2]["content"], "历史消息16")   # 最近明细保留尾部
        # 替换硬截断口径：旧消息不再整段直送
        self.assertNotIn({"role": "user", "content": "历史消息0"}, msgs)

    def test_compress_failure_falls_back_to_existing_truncation(self):
        history = self._history(25)
        with self._compress_patch() as mcomp, \
                mock.patch.object(brain, "requests") as mr, _quiet():
            mcomp.side_effect = RuntimeError("双脑全挂")
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("好的呀")
            brain.smart_ask("当前问题", history)

        mcomp.assert_called_once()
        msgs = mr.post.call_args.kwargs["json"]["messages"]
        # 降级：既有口径原样直送（保存侧 50 条硬截断仍在下游生效），不崩溃
        self.assertEqual(len(msgs), 27)
        self.assertFalse(any(
            isinstance(m, dict)
            and str(m.get("content", "")).startswith("【前情提要】")
            for m in msgs))

    def test_degraded_summary_treated_as_failure(self):
        # compress_context 双脑不可用时返回降级摘要（不抛异常）——按失败处理
        history = self._history(25)
        summary = "【前情提要】：（由于系统原因，早期对话记忆已丢失）"
        with self._compress_patch(summary=summary) as mcomp, \
                mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("好的呀")
            brain.smart_ask("当前问题", history)

        mcomp.assert_called_once()
        msgs = mr.post.call_args.kwargs["json"]["messages"]
        self.assertEqual(len(msgs), 27)
        self.assertFalse(any(
            isinstance(m, dict)
            and str(m.get("content", "")).startswith("【前情提要】")
            for m in msgs))
        # 降级摘要不落缓存
        self.assertFalse(os.path.exists(brain.CONTEXT_SUMMARY_FILE))

    def test_cache_hit_skips_second_compress(self):
        history = self._history(25)
        with self._compress_patch() as mcomp, \
                mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("好的呀")
            brain.smart_ask("当前问题", history)
            mcomp.assert_called_once()
            # 第二轮：同一历史（指纹未变）→ 缓存命中，不再压缩
            brain.smart_ask("又来啦", history)
            mcomp.assert_called_once()

        # 缓存已持久化，两轮 payload 都注入前情提要
        self.assertTrue(os.path.exists(brain.CONTEXT_SUMMARY_FILE))
        payloads = [c.kwargs["json"]["messages"] for c in mr.post.call_args_list]
        self.assertEqual(len(payloads), 2)
        for msgs in payloads:
            self.assertTrue(msgs[1]["content"].startswith("【前情提要】"))

    def test_history_growth_invalidates_cache(self):
        history = self._history(25)
        with self._compress_patch() as mcomp, \
                mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("好")
            brain.smart_ask("第一问", history)
            mcomp.assert_called_once()
            # 新增消息 → 旧消息段指纹变化 → 自动失效重压
            history.append({"role": "user", "content": "新增消息"})
            brain.smart_ask("第二问", history)
            self.assertEqual(mcomp.call_count, 2)

    def test_corrupt_cache_file_recompresses(self):
        with open(brain.CONTEXT_SUMMARY_FILE, "w", encoding="utf-8") as f:
            f.write("{broken json")
        history = self._history(25)
        with self._compress_patch() as mcomp, \
                mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("好")
            brain.smart_ask("当前问题", history)

        # 持久化读失败/文件损坏 → 视为无缓存重新压缩，不崩溃
        mcomp.assert_called_once()
        msgs = mr.post.call_args.kwargs["json"]["messages"]
        self.assertTrue(msgs[1]["content"].startswith("【前情提要】"))

    def test_small_history_untouched(self):
        history = self._history(5)
        with self._compress_patch() as mcomp, \
                mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("好")
            brain.smart_ask("你好", history)

        mcomp.assert_not_called()
        msgs = mr.post.call_args.kwargs["json"]["messages"]
        self.assertEqual(len(msgs), 7)
        self.assertEqual(sum(1 for m in msgs if m["role"] == "system"), 1)

    def test_memory_injected_after_summary_when_compressed(self):
        # 集成形态：压缩与记忆注入并存 → 前情提要在前、长期记忆紧随其后
        self.sm.get_recent_memories.return_value = [("preference", "我喜欢蓝色")]
        history = self._history(25)
        with self._compress_patch() as mcomp, \
                mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("好的呀")
            brain.smart_ask("当前问题", history)

        mcomp.assert_called_once()
        msgs = mr.post.call_args.kwargs["json"]["messages"]
        self.assertTrue(msgs[1]["content"].startswith("【前情提要】"))
        self.assertTrue(msgs[2]["content"].startswith("以下是关于用户的长期记忆"))
        self.assertEqual(len(msgs), 13)


# ---------------------------------------------------------------------------
# W1 核心功能接线：长期记忆 SQLite（§10 #3）
# ---------------------------------------------------------------------------

class LongTermMemoryWiringTests(unittest.TestCase):
    """smart_ask 长期记忆接线：关键词规则落库（preference/event）、回答前
    get_recent_memories(5) 注入、SQLite 异常静默跳过、与 main 先行注入不
    重复。经 setUpModule 的进程内 fake 操控，不触碰真实 long_term.db。"""

    def setUp(self):
        self.sm = _STATE_FAKE.state_manager
        self._reset_sm()
        # 位置上下文（2026-10-02 隐私口径）与本类无关：恒等旁路，消息结构
        # 断言保持原口径（其自身行为在 LocationAskTests 覆盖）
        lp = mock.patch.object(brain, "_inject_location_context",
                               side_effect=lambda m: m)
        lp.start()
        self.addCleanup(lp.stop)
        tp = mock.patch.object(brain, "_resolve_tier", return_value="high")
        tp.start()
        self.addCleanup(tp.stop)

    def _reset_sm(self):
        # MagicMock 的重置方法是 reset_mock（reset 会被当作子 mock 属性，清不掉）
        self.sm.reset_mock(return_value=True, side_effect=True)
        self.sm.get_recent_memories.return_value = []
        self.sm.save_memory.return_value = None

    def tearDown(self):
        # 还原共享 fake 默认口径，避免影响其他用例类
        self._reset_sm()

    def _chat(self, message, history=None):
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("好的呀")
            result = brain.smart_ask(message, history or [])
        msgs = mr.post.call_args.kwargs["json"]["messages"]
        return result, msgs

    @staticmethod
    def _memory_blocks(msgs):
        return [m for m in msgs if isinstance(m, dict) and m.get("role") == "system"
                and str(m.get("content", "")).startswith("以下是关于用户的长期记忆")]

    # ---------- 关键词规则提取落库 ----------

    def test_preference_keyword_saves_memory(self):
        self._chat("我喜欢蓝色")
        self.sm.save_memory.assert_called_once_with("preference", "我喜欢蓝色")

    def test_dislike_keyword_saves_memory(self):
        self._chat("我讨厌下雨天")
        self.sm.save_memory.assert_called_once_with("preference", "我讨厌下雨天")

    def test_remember_keyword_saves_event(self):
        self._chat("请记住周三要开会")
        self.sm.save_memory.assert_called_once_with("event", "请记住周三要开会")

    def test_help_me_remember_saves_event(self):
        self._chat("帮我记住我的常用端口是5002")
        self.sm.save_memory.assert_called_once_with(
            "event", "帮我记住我的常用端口是5002")

    def test_keyword_extracts_matching_sentence_only(self):
        # 多句消息：提取命中规则的那一句，不是整条消息
        self._chat("今天天气不错。我讨厌下雨。")
        self.sm.save_memory.assert_called_once_with("preference", "我讨厌下雨")

    def test_no_keyword_no_save(self):
        self._chat("今天天气怎么样")
        self.sm.save_memory.assert_not_called()

    # ---------- 回答前注入 ----------

    def test_recent_memories_injected_into_model_messages(self):
        self.sm.get_recent_memories.return_value = [
            ("preference", "我喜欢蓝色"), ("user", "主人叫小张")]
        result, msgs = self._chat("我今天穿什么好？")

        blocks = self._memory_blocks(msgs)
        self.assertEqual(len(blocks), 1)
        self.assertIn("[preference] 我喜欢蓝色", blocks[0]["content"])
        self.assertIn("[user] 主人叫小张", blocks[0]["content"])
        self.assertEqual(msgs[0], prompts.SYSTEM_PROMPT)
        self.assertEqual(msgs[1], blocks[0])   # 紧随置顶提示词
        self.assertEqual(msgs[-1], {"role": "user", "content": "我今天穿什么好？"})
        self.assertEqual(result[1], "🏠 本地")

    def test_empty_memories_not_injected(self):
        result, msgs = self._chat("今天穿什么好？")
        self.assertEqual(self._memory_blocks(msgs), [])
        self.assertEqual(sum(1 for m in msgs if m["role"] == "system"), 1)
        self.assertEqual(result[1], "🏠 本地")

    def test_no_duplicate_injection_when_history_carries_block(self):
        # main 链路先行注入形态：历史已带同前缀条目 → 不重复注入
        block = {"role": "system",
                 "content": "以下是关于用户的长期记忆，回答时可以参考：\n· [user] 主人叫小张"}
        history = [block,
                   {"role": "user", "content": "之前的话"},
                   {"role": "assistant", "content": "好的"}]
        self.sm.get_recent_memories.return_value = [("preference", "我喜欢蓝色")]
        result, msgs = self._chat("继续", history)

        blocks = self._memory_blocks(msgs)
        self.assertEqual(len(blocks), 1)
        self.assertIn("[user] 主人叫小张", blocks[0]["content"])
        self.assertEqual(result[1], "🏠 本地")

    # ---------- SQLite / 模块异常静默 ----------

    def test_sqlite_read_error_skips_silently(self):
        self.sm.get_recent_memories.side_effect = Exception(
            "database disk image is malformed")
        result, msgs = self._chat("今天穿什么好？")
        self.assertEqual(result, (f"<think>{brain.CHAT_THINKING_PLACEHOLDER}"
                                  "</think>好的呀", "🏠 本地"))
        self.assertEqual(self._memory_blocks(msgs), [])

    def test_sqlite_save_error_skips_silently(self):
        self.sm.save_memory.side_effect = Exception("database is locked")
        result, msgs = self._chat("我喜欢蓝色")
        self.sm.save_memory.assert_called_once()          # 落库被调用
        self.assertEqual(result[1], "🏠 本地")            # 异常被吞，回复链正常
        self.assertEqual(self._memory_blocks(msgs), [])   # 无记忆 → 不注入

    def test_state_manager_missing_skips_silently(self):
        # 模块缺席（sys.modules 置 None → ImportError）→ 静默跳过不崩溃
        with mock.patch.dict(sys.modules, {"agent_state": None,
                                           "agent_state.state_manager": None}):
            result, msgs = self._chat("请记住带伞")
        self.assertEqual(result[1], "🏠 本地")
        self.sm.save_memory.assert_not_called()
        self.assertEqual(self._memory_blocks(msgs), [])


# ---------------------------------------------------------------------------
# 回复出口去重 + 历史轻量清洗（2026-10-02 用户口径，修复本地模型复读）
# ---------------------------------------------------------------------------

class ReplyDedupeTests(unittest.TestCase):
    """_dedupe_reply / _wrap_think ⑥ 出口去重 / _seal_bare_cot 透传收口。

    背景：本地模型（qwen2.5:7b）多相似消息后复读——实测 WRAPPED_TEXT 显示
    正文与 <think> 块内容完全相同（模型把回复原文同时塞进思考块与正文），
    网页上显示两遍。去重三原则：think==body 收敛为"占位卡+正文一份"、
    正文句级连续重复塌缩、去重后正文为空注入 DEDUPE_BODY_PLACEHOLDER。
    """

    def _seal(self, raw):
        with contextlib.redirect_stdout(io.StringIO()):
            return brain._seal_bare_cot(raw)

    def _wrap(self, thinking, body):
        with contextlib.redirect_stdout(io.StringIO()):
            return brain._wrap_think(thinking, body)

    def test_think_equals_body_collapsed(self):
        """模型自吐 <think>X</think>X（思考与正文完全相同）→ 占位卡 + 正文
        一份（用户实测例句，经 _seal_bare_cot 防重入透传收口）。"""
        raw = ("<think>我在呢，在呢，有啥需要帮忙的吗？😊</think>"
               "我在呢，在呢，有啥需要帮忙的吗？😊")
        sealed = self._seal(raw)
        self.assertEqual(
            sealed,
            "<think>" + brain.CHAT_THINKING_PLACEHOLDER + "</think>"
            + "我在呢，在呢，有啥需要帮忙的吗？😊")

    def test_body_consecutive_duplicate_sentences(self):
        """正文句级连续重复（同一句 3 遍）塌缩为一份。"""
        sealed = self._seal("在吗？在吗？在吗？")
        self.assertEqual(
            sealed,
            "<think>" + brain.CHAT_THINKING_PLACEHOLDER + "</think>在吗？")

    def test_emoji_tail_run_collapsed(self):
        """重复句之间被收尾表情（😊）隔断同样塌缩（粘连段 ≤4 字非文字）；
        第二份的收尾表情保留（重组后恰为单份原句形态）。"""
        raw = ("我在呢，在呢，有啥需要帮忙的吗？😊"
               "我在呢，在呢，有啥需要帮忙的吗？😊")
        sealed = self._seal(raw)
        self.assertEqual(
            sealed,
            "<think>" + brain.CHAT_THINKING_PLACEHOLDER + "</think>"
            + "我在呢，在呢，有啥需要帮忙的吗？😊")

    def test_plain_text_without_think_dedup(self):
        """退化形态（无成对 think 前缀的纯文本）：只做句级连续去重。"""
        self.assertEqual(brain._dedupe_reply("在吗？在吗？"), "在吗？")

    def test_recovery_form_not_collapsed(self):
        """设计形态零回退：正文回补"<think>[思考] X</think>X"（思考含标记
        前缀、比较保留标记差异）不命中 think==body 去重。"""
        out = self._wrap("[思考] 我在呢", "")
        self.assertEqual(out, "<think>[思考] 我在呢</think>我在呢")

    def test_no_duplicate_body_byte_identical(self):
        """无重复文本逐字节原样返回（零改动零回归）。"""
        text = "<think>[思考] 今天天气不错</think>适合出去散步，要一起吗？"
        self.assertEqual(brain._dedupe_reply(text), text)

    def test_card_only_form_preserved(self):
        """设计形态零回退：占位思考 + 空正文的"只有卡片"孤标签修复形态
        （_wrap_think ④ 既有设计）不被去重填占位，保持原样输出。"""
        with contextlib.redirect_stdout(io.StringIO()):
            out = brain._wrap_think(brain.CHAT_THINKING_PLACEHOLDER,
                                    "（操作已执行）")
        self.assertEqual(out, f"<think>{brain.CHAT_THINKING_PLACEHOLDER}</think>")
        # 空白正文的直喂同样保持原样（未被去重改动 → 逐字节返回）
        self.assertEqual(brain._dedupe_reply("<think>[思考] x</think>   "),
                         "<think>[思考] x</think>   ")

    def test_empty_body_after_dedupe_placeholder(self):
        """去重确实剥空正文 → 注入"我在呢～"占位（用户口径示例文案；
        用桩把句级塌缩模拟为剥空以直达该防御分支）。"""
        with mock.patch.object(brain, "_collapse_duplicate_sentences",
                               return_value=""):
            out = brain._dedupe_reply("<think>[思考] x</think>正文")
        self.assertEqual(out,
                         "<think>[思考] x</think>" + brain.DEDUPE_BODY_PLACEHOLDER)

    def test_none_input_safe(self):
        """None 输入按空串处理，原样返回不抛错。"""
        self.assertEqual(brain._dedupe_reply(None), "")


class SelfTalkStripTests(unittest.TestCase):
    """自说自话剥离（2026-10-02 用户口径，QQ 实测模型把心路历程写进正文）。

    用户实测："又是呼唤我，看来他挺关心我！这次我直接回应，别再问了！
    在呢在呢，有啥需要帮忙的吗？"——前两句是内心独白漏出，QQ 里像在
    自说自话；剥离后只留对用户说的话。
    """

    def test_user_example_stripped(self):
        """用户实测例句：开头连续心路历程句剥离，只留实际回复。"""
        body = ("又是呼唤我，看来他挺关心我！这次我直接回应，别再问了！"
                "在呢在呢，有啥需要帮忙的吗？")
        self.assertEqual(brain._strip_self_talk(body),
                         "在呢在呢，有啥需要帮忙的吗？")

    def test_full_pipeline_with_think(self):
        """端到端（防重入透传收口）：<think>块 + 自说自话正文 → 卡片保留、
        正文只留对用户说的话。"""
        raw = ("<think>用户又在呼唤我，直接回应即可。</think>"
               "又是呼唤我，看来他挺关心我！这次我直接回应，别再问了！"
               "在呢在呢，有啥需要帮忙的吗？")
        with contextlib.redirect_stdout(io.StringIO()):
            sealed = brain._seal_bare_cot(raw)
        self.assertEqual(
            sealed,
            "<think>用户又在呼唤我，直接回应即可。</think>"
            "在呢在呢，有啥需要帮忙的吗？")

    def test_each_marker_strips(self):
        """各句式逐个命中（任务清单列举 + 同族第三人称指代）。"""
        cases = [
            ("这次我直接回应，别再问了！在呢。", "在呢。"),
            ("看来他挺关心我！你好呀。", "你好呀。"),
            ("他问我怎么了。我回答了。", "我回答了。"),
            ("看来主人在忙。需要我做什么吗？", "需要我做什么吗？"),
            ("主人又在呼唤我。在呢。", "在呢。"),
        ]
        for body, expected in cases:
            with self.subTest(body=body):
                self.assertEqual(brain._strip_self_talk(body), expected)

    def test_no_self_talk_byte_identical(self):
        """无自说自话逐字节原样返回（零改动零回归）。"""
        body = "在呢在呢，有啥需要帮忙的吗？😊"
        self.assertEqual(brain._strip_self_talk(body), body)

    def test_mid_text_marker_untouched(self):
        """只剥开头连续段：正文中部的同字样（转述等场景）不误伤。"""
        body = "在呢在呢，有啥需要帮忙的吗？这次我记住了。"
        self.assertEqual(brain._strip_self_talk(body), body)

    def test_all_sentences_matching_kept_conservative(self):
        """全部句子都是心路历程（无法区分哪句是回复）→ 保守原样返回，
        绝不把真回复剥没。"""
        body = "又是呼唤我，看来他挺关心我！这次我直接回应，别再问了！"
        self.assertEqual(brain._strip_self_talk(body), body)

    def test_empty_and_none_safe(self):
        """空串/None 原样返回，不抛错。"""
        self.assertEqual(brain._strip_self_talk(""), "")
        self.assertIsNone(brain._strip_self_talk(None))


class HistoryCollapseTests(unittest.TestCase):
    """_collapse_repeated_user_history / _build_messages 接线（历史轻量清洗）。

    用户口径：连续 3 条及以上完全相同的用户消息（QQ 连发"@小橘3号 在吗"）
    只保留 1 条，防止模型被重复输入带偏复读；"连续"指用户消息序列相邻
    （中间可夹助手回复——连发场景每条之间实际都有回复）。
    """

    def _user_contents(self, messages):
        return [m["content"] for m in messages if m["role"] == "user"]

    def test_three_identical_collapsed_to_one(self):
        """连续 3 条相同用户消息（夹助手回复）只保留 1 条 + 当前消息。"""
        history = [{"role": "user", "content": "在吗"},
                   {"role": "assistant", "content": "我在"},
                   {"role": "user", "content": "在吗"},
                   {"role": "assistant", "content": "在的呢"},
                   {"role": "user", "content": "在吗"}]
        msgs = brain._build_messages("在吗", history)
        self.assertEqual(self._user_contents(msgs).count("在吗"), 2)

    def test_two_identical_kept(self):
        """仅 2 条相同不收敛（阈值 ≥3，保留用户有意的补充强调）。"""
        history = [{"role": "user", "content": "在吗"},
                   {"role": "assistant", "content": "我在"},
                   {"role": "user", "content": "在吗"}]
        msgs = brain._build_messages("睡了吗", history)
        self.assertEqual(self._user_contents(msgs).count("在吗"), 2)
        self.assertIn("睡了吗", self._user_contents(msgs))

    def test_different_user_messages_not_collapsed(self):
        """互不相同的用户消息原样保留，不受清洗影响。"""
        history = [{"role": "user", "content": "天气如何"},
                   {"role": "assistant", "content": "晴"},
                   {"role": "user", "content": "明天呢"},
                   {"role": "assistant", "content": "多云"},
                   {"role": "user", "content": "后天呢"}]
        msgs = brain._build_messages("那大后天呢", history)
        self.assertEqual(len(self._user_contents(msgs)), 4)

    def test_strictly_adjacent_run_collapsed(self):
        """连发无回复穿插的 3 条相同消息同样收敛；收敛后末条与当前消息
        相同时不重复追加（_build_messages 既有去重口径）。"""
        history = [{"role": "user", "content": "在吗"},
                   {"role": "user", "content": "在吗"},
                   {"role": "user", "content": "在吗"}]
        msgs = brain._build_messages("在吗", history)
        self.assertEqual(msgs, [brain.SYSTEM_PROMPT,
                                {"role": "user", "content": "在吗"}])

    def test_short_history_passthrough(self):
        """历史不足阈值原样返回（不清洗）。"""
        history = [{"role": "user", "content": "在吗"},
                   {"role": "assistant", "content": "我在"}]
        msgs = brain._build_messages("在吗", history)
        self.assertEqual(len(self._user_contents(msgs)), 2)

    def test_whitespace_only_difference_counts_as_same(self):
        """"完全相同"按去首尾空白比较（QQ 尾随空格连发同样命中）。"""
        history = [{"role": "user", "content": "在吗"},
                   {"role": "user", "content": "在吗 "},
                   {"role": "user", "content": " 在吗"}]
        msgs = brain._build_messages("在吗", history)
        self.assertEqual(len(msgs), 2)   # sys + 收敛后的 1 条（当前不再追加）

    def test_history_not_mutated(self):
        """清洗返回新列表，绝不改动调用方传入的 history（_build_messages 契约）。"""
        history = [{"role": "user", "content": "在吗"},
                   {"role": "user", "content": "在吗"},
                   {"role": "user", "content": "在吗"}]
        brain._build_messages("在吗", history)
        self.assertEqual(len(history), 3)

    def test_limit_constant(self):
        """阈值常量为 3（用户口径"连续 3 条以上"）。"""
        self.assertEqual(brain.REPEAT_USER_HISTORY_LIMIT, 3)


class LocationInjectTests(unittest.TestCase):
    """搜索指代消解（2026-10-02 用户口径）：裸地点词搜索补全配置位置。

    背景：QQ 群问"今天天气怎么样"，web_search 收到裸 query"今天天气"被
    搜索引擎随机定位（返回杭州余杭，用户实际在长沙天心）。
    """

    @classmethod
    def setUpClass(cls):
        # sys.modules 中 agent_state.state_manager 可能是并行测试模块注入的
        # fake（缺本批新增方法）——按真实路径重载（手法同 LocationAskTests）
        import importlib.util
        real_path = os.path.join(PROJECT_ROOT, "agent_state", "state_manager.py")
        spec = importlib.util.spec_from_file_location(
            "agent_state.state_manager", real_path)
        cls.real_sm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.real_sm)

    def test_bare_weather_query_rewritten_with_city(self):
        """任务口径用例①："今天天气" + USER_CITY=长沙 → 精准天气 query
        （2026-10-02 精度增强口径：规范化为"城市 今日天气预报 气温 降水"）。"""
        with mock.patch.object(brain, "USER_CITY", "长沙"), \
                mock.patch.object(brain, "USER_DISTRICT", ""):
            self.assertEqual(brain._inject_location("今天天气"),
                             "长沙 今日天气预报 气温 降水")

    def test_query_with_city_untouched(self):
        """任务口径用例②："北京天气" 已含地点 → 不改写。"""
        with mock.patch.object(brain, "USER_CITY", "长沙"), \
                mock.patch.object(brain, "USER_DISTRICT", "天心区"):
            self.assertEqual(brain._inject_location("北京天气"), "北京天气")

    def test_bare_news_query_rewritten(self):
        """任务口径用例③："今天新闻" + USER_CITY=长沙 → 改写 + 追加"最新
        今日"精度词（2026-10-02 新闻类增强口径）。"""
        with mock.patch.object(brain, "USER_CITY", "长沙"), \
                mock.patch.object(brain, "USER_DISTRICT", ""):
            self.assertEqual(brain._inject_location("今天新闻"),
                             "长沙今天新闻 最新 今日")

    def test_unconfigured_keeps_original(self):
        """任务口径用例④：USER_CITY 未配置且无本地位置记忆 → 返回 None
        （2026-10-02 隐私口径：调用方不改写，由模型主动询问主人）。"""
        with mock.patch.object(brain, "USER_CITY", ""), \
                mock.patch.object(brain, "USER_DISTRICT", ""), \
                mock.patch.object(self.real_sm, "get_user_location",
                                  return_value=None), \
                mock.patch.dict(sys.modules,
                                {"agent_state.state_manager": self.real_sm}):
            self.assertIsNone(brain._inject_location("今天天气"))

    def test_non_location_query_untouched(self):
        """任务口径用例⑤：非天气/本地类 query"如何写Python" → 不改写。"""
        with mock.patch.object(brain, "USER_CITY", "长沙"), \
                mock.patch.object(brain, "USER_DISTRICT", "天心区"):
            self.assertEqual(brain._inject_location("如何写Python"),
                             "如何写Python")

    def test_city_and_district_both_injected(self):
        """城市+区县都配置 → 裸 query 规范化为"长沙天心区 今日天气预报
        气温 降水"（任务 2 示例口径）。"""
        with mock.patch.object(brain, "USER_CITY", "长沙"), \
                mock.patch.object(brain, "USER_DISTRICT", "天心区"):
            self.assertEqual(brain._inject_location("今天天气"),
                             "长沙天心区 今日天气预报 气温 降水")

    def test_configured_district_in_query_canonicalized(self):
        """query 已含配置的区县（"天心区下雨吗"）→ 天气类规范化为精准
        query（2026-10-02 精度口径：不再原样放行宽泛词组）。"""
        with mock.patch.object(brain, "USER_CITY", "长沙"), \
                mock.patch.object(brain, "USER_DISTRICT", "天心区"):
            self.assertEqual(brain._inject_location("天心区下雨吗"),
                             "长沙天心区 今日天气预报 气温 降水")

    def test_administrative_suffix_untouched(self):
        """词表外地名带行政区划后缀（"株洲市天气"）→ 视为已含地点不改写。"""
        with mock.patch.object(brain, "USER_CITY", "长沙"), \
                mock.patch.object(brain, "USER_DISTRICT", ""):
            self.assertEqual(brain._inject_location("株洲市天气"), "株洲市天气")

    def test_web_search_query_location_injected_before_execute(self):
        """接线：smart_ask 工具路径在 execute_tool 之前对 web_search 的
        query 做 _inject_location 改写（其余参数透传）。"""
        raw = ('[思考] 查天气需要联网。\n'
               '[计划] 调用搜索。\n'
               '[行动] {"tool": "web_search", "args": {"query": "今天天气"}}')
        with mock.patch.object(brain, "USER_CITY", "长沙"), \
                mock.patch.object(brain, "USER_DISTRICT", ""), \
                mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool",
                                  return_value="1. 长沙今天晴，25 度") as mexec, \
                mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.side_effect = [_local_resp(raw), _local_resp("今天长沙晴")]
            mcloud.return_value = "不会走到这"
            reply, source = brain.smart_ask("今天天气怎么样", [])
        called_args = mexec.call_args[0][1]
        self.assertEqual(called_args["query"], "长沙 今日天气预报 气温 降水")

    def test_prompts_search_rule_contains_location_constraint(self):
        """提示词约束（2026-10-02 用户口径）：联网搜索规则含地点条款。"""
        content = brain.SYSTEM_PROMPT["content"]
        self.assertIn("query 必须包含具体地点", content)
        self.assertIn("必须先问", content)
        self.assertIn("以主人新说的为准", content)
        self.assertIn("不含地点的裸词去搜索", content)


class LocationAskTests(unittest.TestCase):
    """位置隐私模式（2026-10-02）：AI 主动询问 + 本地记忆，不写 .env。

    位置三级来源：.env USER_CITY/USER_DISTRICT（可选）→ 本地位置记忆
    agent_state/user_location.json（gitignore，[LOCATION:] 标记 /
    /set_location 指令写入）→ 都没有则不改写、由模型主动询问主人。

    注意：sys.modules 中的 agent_state.state_manager 可能是并行测试模块
    注入的 fake（缺本批新增方法）——setUpClass 按真实路径重载一份，经
    mock.patch.dict 让 brain 的延迟导入绑定真实实现（test_heartbeat 的
    _ensure_real_modules 同款手法），文件断言也走真实模块、测试后清理。
    """

    @classmethod
    def setUpClass(cls):
        import importlib.util
        real_path = os.path.join(PROJECT_ROOT, "agent_state", "state_manager.py")
        spec = importlib.util.spec_from_file_location(
            "agent_state.state_manager", real_path)
        cls.real_sm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.real_sm)

    def setUp(self):
        self.real_sm.clear_user_location()   # 起点干净
        self.addCleanup(self.real_sm.clear_user_location)

    def _sm_ctx(self):
        """让 brain 的延迟导入在 patch.dict 生效期间绑定真实 state_manager。"""
        return mock.patch.dict(sys.modules,
                               {"agent_state.state_manager": self.real_sm})

    def test_no_location_anywhere_returns_none(self):
        """.env 未配置 + 本地位置记忆不存在 → _inject_location 返回 None
        （不改写搜索词，由模型侧主动询问主人）。"""
        with mock.patch.object(brain, "USER_CITY", ""),                 mock.patch.object(brain, "USER_DISTRICT", ""),                 mock.patch.object(self.real_sm, "get_user_location",
                                  return_value=None),                 self._sm_ctx():
            self.assertIsNone(brain._inject_location("今天天气"))

    def test_local_memory_location_rewrites(self):
        """.env 未配置 + user_location.json 记录"长沙天心区"→ 改写 query，
        位置来源日志标注 user_location.json。"""
        buf = io.StringIO()
        with mock.patch.object(brain, "USER_CITY", ""),                 mock.patch.object(brain, "USER_DISTRICT", ""),                 mock.patch.object(self.real_sm, "get_user_location",
                                  return_value={"city": "长沙",
                                                "district": "天心区"}),                 self._sm_ctx(), contextlib.redirect_stdout(buf):
            result = brain._inject_location("今天天气")
        self.assertEqual(result, "长沙天心区 今日天气预报 气温 降水")
        self.assertIn("user_location.json", buf.getvalue())

    def test_env_location_takes_priority_over_memory(self):
        """.env 与本地记忆同时存在 → .env 优先（不读、不叠加本地记忆）。"""
        buf = io.StringIO()
        with mock.patch.object(brain, "USER_CITY", "长沙"),                 mock.patch.object(brain, "USER_DISTRICT", "天心区"),                 mock.patch.object(self.real_sm, "get_user_location",
                                  return_value={"city": "北京",
                                                "district": "朝阳区"}) as mget,                 self._sm_ctx(), contextlib.redirect_stdout(buf):
            result = brain._inject_location("今天天气")
        self.assertEqual(result, "长沙天心区 今日天气预报 气温 降水")
        self.assertIn(".env", buf.getvalue())
        mget.assert_not_called()   # .env 命中即短路，不触达本地记忆

    def test_location_context_injection_known(self):
        """位置已知 → 系统上下文注入【主人位置】+ "直接使用"指示。"""
        msgs = [{"role": "system", "content": "sys"},
                {"role": "user", "content": "你好"}]
        with mock.patch.object(brain, "USER_CITY", "长沙"),                 mock.patch.object(brain, "USER_DISTRICT", "天心区"),                 self._sm_ctx():
            out = brain._inject_location_context(msgs)
        self.assertEqual(len(out), 3)
        self.assertIn("【主人位置】长沙天心区", out[1]["content"])
        self.assertIn("无需再询问", out[1]["content"])

    def test_location_context_injection_unknown(self):
        """位置未知 → 系统上下文注入"先询问主人 + [LOCATION:] 标记"指示。"""
        msgs = [{"role": "system", "content": "sys"},
                {"role": "user", "content": "你好"}]
        with mock.patch.object(brain, "USER_CITY", ""),                 mock.patch.object(brain, "USER_DISTRICT", ""),                 mock.patch.object(self.real_sm, "get_user_location",
                                  return_value=None),                 self._sm_ctx():
            out = brain._inject_location_context(msgs)
        self.assertIn("【主人位置】未知", out[1]["content"])
        self.assertIn("[LOCATION:城市-区县]", out[1]["content"])

    def test_smart_ask_injects_location_context(self):
        """端到端：smart_ask 的模型消息含【主人位置】系统上下文。"""
        with mock.patch.object(brain, "USER_CITY", "长沙"),                 mock.patch.object(brain, "USER_DISTRICT", ""),                 self._sm_ctx(),                 mock.patch.object(brain, "probe_local", return_value=True),                 mock.patch.object(brain, "ask_local",
                                  return_value="你好呀！很高兴见到你。") as mlocal,                 _quiet():
            brain.smart_ask("你好", [])
        msgs = mlocal.call_args[0][0]
        self.assertTrue(any(isinstance(m, dict) and m.get("role") == "system"
                            and str(m.get("content", "")).startswith("【主人位置】")
                            for m in msgs), msgs[:3])

    def test_location_marker_consumed_and_saved(self):
        """回复含 [LOCATION:长沙-天心区] → 写入本地位置记忆 + 回复里标记
        被剥离（对主人不可见）。写真实 agent_state/user_location.json，
        测试后清除（setUp/addCleanup 兜底）。"""
        with self._sm_ctx(), contextlib.redirect_stdout(io.StringIO()):
            out = brain._dedupe_reply(
                "<think>[思考] 记录位置。</think>"
                "好的，已记录！[LOCATION:长沙-天心区]")
        # 标记从正文剥离，<think> 包装原样保留
        self.assertEqual(out,
                         "<think>[思考] 记录位置。</think>好的，已记录！")
        self.assertEqual(self.real_sm.get_user_location(),
                         {"city": "长沙", "district": "天心区"})

    def test_location_marker_city_only(self):
        """[LOCATION:长沙]（主人只说了城市）→ 城市写入、区县为空。"""
        with self._sm_ctx(), contextlib.redirect_stdout(io.StringIO()):
            out = brain._dedupe_reply("好的！[LOCATION:长沙]")
        self.assertEqual(out, "好的！")
        self.assertEqual(self.real_sm.get_user_location(),
                         {"city": "长沙", "district": ""})

    def test_marker_only_reply_conservative(self):
        """整条回复只有标记（剥空口径）→ 保守返回原文，绝不下发空回复。"""
        with self._sm_ctx(), contextlib.redirect_stdout(io.StringIO()):
            out = brain._dedupe_reply("[LOCATION:长沙-天心区]")
        self.assertEqual(out, "[LOCATION:长沙-天心区]")

    def test_no_marker_zero_change(self):
        """无标记回复逐字节原样返回（消费逻辑零误伤）。"""
        text = "<think>[思考] 想想</think>今天天气不错。"
        with self._sm_ctx(), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(brain._dedupe_reply(text), text)

    def test_location_marker_variants(self):
        """四格式标记兼容（2026-10-02 加固口径）：城市/城市-区县/空格分隔/
        无分隔"市+区县"形态，落库城市统一剥"市"字尾。"""
        cases = (
            ("[LOCATION:长沙]", ("长沙", "")),
            ("[LOCATION:长沙-天心区]", ("长沙", "天心区")),
            ("[LOCATION:长沙 天心区]", ("长沙", "天心区")),
            ("[LOCATION:长沙市天心区]", ("长沙", "天心区")),
        )
        for marker, expected in cases:
            with self.subTest(marker=marker):
                self.real_sm.clear_user_location()
                with self._sm_ctx(), contextlib.redirect_stdout(io.StringIO()):
                    brain._consume_location_marker("好的。" + marker)
                got = self.real_sm.get_user_location()
                self.assertEqual((got["city"], got["district"]), expected)

    def test_prompt_contains_ask_and_marker_protocol(self):
        """提示词（2026-10-02 隐私口径）：包含"必须先问"与 [LOCATION:] 协议。"""
        content = brain.SYSTEM_PROMPT["content"]
        self.assertIn("必须先问", content)
        self.assertIn("你现在在哪个城市和区", content)
        self.assertIn("[LOCATION:城市-区县]", content)
        self.assertIn("对主人不可见", content)
        self.assertIn("不要再重复询问", content)
        self.assertIn("直接使用，不要再问", content)


class LocationHardBlockTests(unittest.TestCase):
    """位置未知硬拦截 + 位置回答兜底提取（2026-10-02 用户口径）。

    背景：本地小模型无视提示词"必须先问"约束、自己编了"杭州余杭区"直接
    调 web_search 返回杭州天气——关键行为必须代码层硬拦截；且用户用完整
    句式回答位置（"我要的是长沙市天心区的"）时模型漏带 [LOCATION:] 标记。
    """

    @classmethod
    def setUpClass(cls):
        # sys.modules 中的 agent_state.state_manager 可能是 fake——按真实
        # 路径重载（手法同 LocationAskTests）
        import importlib.util
        real_path = os.path.join(PROJECT_ROOT, "agent_state", "state_manager.py")
        spec = importlib.util.spec_from_file_location(
            "agent_state.state_manager", real_path)
        cls.real_sm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.real_sm)

    def setUp(self):
        self.real_sm.clear_user_location()
        self.addCleanup(self.real_sm.clear_user_location)

    def _sm_ctx(self):
        """让 brain 的延迟导入在 patch.dict 生效期间绑定真实 state_manager。"""
        return mock.patch.dict(sys.modules,
                               {"agent_state.state_manager": self.real_sm})

    def _run_web_search_flow(self, query, user_city="", user_district="",
                             user_message="今天天气怎么样",
                             unknown_location=True):
        """跑一条 web_search 工具流，返回 (reply, source, stdout, mexec)。"""
        raw = ('[思考] 查询需要联网。\n'
               '[计划] 调用搜索。\n'
               '[行动] {"tool": "web_search", "args": {"query": "%s"}}' % query)
        buf = io.StringIO()
        with self._sm_ctx(), \
                mock.patch.object(brain, "USER_CITY", user_city), \
                mock.patch.object(brain, "USER_DISTRICT", user_district), \
                mock.patch.object(self.real_sm, "get_user_location",
                                  return_value=None if unknown_location
                                  else {"city": "长沙",
                                        "district": "天心区"}), \
                mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool",
                                  return_value="1. 搜索结果摘要") as mexec, \
                mock.patch.object(brain, "ask_cloud") as mcloud, \
                contextlib.redirect_stdout(buf):
            mr.get.return_value = mock.Mock()
            mr.post.side_effect = [_local_resp(raw), _local_resp("汇总完成")]
            mcloud.return_value = "汇总完成"
            reply, source = brain.smart_ask(user_message, [])
        return reply, source, buf.getvalue(), mexec

    def test_location_unknown_blocks_search(self):
        """任务口径用例①：位置未知 + query="今天天气" → 不调 web_search，
        返回固定询问文案（🛑 日志、来源标签 📍 询问位置）。"""
        reply, source, out, mexec = self._run_web_search_flow("今天天气")
        mexec.assert_not_called()   # 拦截在 execute_tool 之前，工具绝不执行
        self.assertIn("我还不知道你在哪个城市和区", reply)
        self.assertIn("长沙天心区", reply)   # 固定文案含示例
        self.assertEqual(source, "📍 询问位置")
        self.assertIn("🛑 [搜索] 位置未知，拦截搜索请求", out)

    def test_non_location_query_passes(self):
        """任务口径用例②：位置未知 + query="如何写Python"（非地点敏感）
        → 正常调用 web_search，query 原样透传。"""
        reply, source, out, mexec = self._run_web_search_flow("如何写Python")
        mexec.assert_called_once()
        called_args = mexec.call_args[0][1]
        self.assertEqual(called_args["query"], "如何写Python")
        self.assertNotIn("🛑", out)

    def test_location_known_rewrites_and_calls(self):
        """任务口径用例③：位置已知（.env 配置长沙）+ query="今天天气"
        → 正常改写为"长沙今天天气"并调用 web_search。"""
        reply, source, out, mexec = self._run_web_search_flow(
            "今天天气", user_city="长沙", unknown_location=False)
        mexec.assert_called_once()
        called_args = mexec.call_args[0][1]
        self.assertEqual(called_args["query"], "长沙 今日天气预报 气温 降水")
        self.assertIn("📍 [搜索] 位置来源: .env", out)
        self.assertNotIn("🛑", out)

    def test_user_message_location_extracted(self):
        """任务口径用例④：用户完整句式回答"我要的是长沙市天心区的"
        → 自动提取"长沙-天心区"写入 user_location.json。"""
        buf = io.StringIO()
        with self._sm_ctx(), contextlib.redirect_stdout(buf):
            saved = brain._extract_location_from_user_message(
                "我要的是长沙市天心区的")
        self.assertTrue(saved)
        self.assertEqual(self.real_sm.get_user_location(),
                         {"city": "长沙", "district": "天心区"})
        self.assertIn("📍 [位置] 从用户消息提取: 长沙-天心区，已写入并生效",
                      buf.getvalue())

    def test_user_message_without_combo_not_saved(self):
        """普通消息（无城市+区县组合）不触发写入（零误伤）。"""
        with self._sm_ctx(), contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(brain._extract_location_from_user_message(
                "今天天气怎么样"))
        self.assertIsNone(self.real_sm.get_user_location())

    def test_known_city_with_district_extracted(self):
        """词表城市 + 区县组合（"我在长沙天心区"）同样提取。"""
        with self._sm_ctx(), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(brain._extract_location_from_user_message(
                "我在长沙天心区"))
        self.assertEqual(self.real_sm.get_user_location(),
                         {"city": "长沙", "district": "天心区"})

    def test_hard_block_reply_wrapped_with_think(self):
        """硬拦截回复同样过 _wrap_think（全对话强制包装口径不破坏）。"""
        reply, _source, _out, _mexec = self._run_web_search_flow("今天天气")
        self.assertTrue(reply.startswith("<think>"), reply)
        self.assertIn("</think>", reply)

    def test_history_location_not_trusted_when_no_record(self):
        """任务口径用例①（严格来源化回归锁）：模型 query 带着历史推断的
        "长沙市天心区"、json 不存在 → query/历史位置不作为来源，硬拦截
        询问（修复 /clear_location 后仍搜旧位置的 bug）。"""
        reply, source, out, mexec = self._run_web_search_flow(
            "长沙市天心区的天气", user_message="今天天气怎么样")
        mexec.assert_not_called()
        self.assertIn("我还不知道你在哪个城市和区", reply)
        self.assertEqual(source, "📍 询问位置")
        self.assertIn("🛑 [搜索] 位置未知，拦截搜索请求", out)

    def test_grace_period_after_clear_forces_ask(self):
        """任务口径用例②：历史里有位置 + 刚执行过 /clear_location → 静默
        期强制询问（🚿 日志、绝不采信历史位置）。"""
        brain.mark_location_cleared()
        self.addCleanup(setattr, brain, "_location_cleared_at", 0.0)
        reply, source, out, mexec = self._run_web_search_flow(
            "长沙市天心区的天气", user_message="今天天气怎么样")
        mexec.assert_not_called()
        self.assertIn("我还不知道你在哪个城市和区", reply)
        self.assertIn("📍 [位置] 已清除后处于静默期，忽略历史位置，强制询问",
                      out)

    def test_location_record_works_despite_grace(self):
        """任务口径用例③：历史里无位置 + user_location.json 存在（主人
        静默期内重新告知）→ 正常使用位置，静默期不误伤新写入的记录。"""
        brain.mark_location_cleared()
        self.addCleanup(setattr, brain, "_location_cleared_at", 0.0)
        reply, source, out, mexec = self._run_web_search_flow(
            "今天天气", unknown_location=False)
        mexec.assert_called_once()
        called_args = mexec.call_args[0][1]
        self.assertEqual(called_args["query"],
                         "长沙天心区 今日天气预报 气温 降水")
        self.assertNotIn("🛑", out)
        self.assertNotIn("强制询问", out)   # 静默期检查调试行常驻，断言看拦截语义

    def test_grace_expires_after_window(self):
        """静默期超时（5 分钟）自动失效：届时无位置仍走常规未知路径。"""
        import time as _time
        brain._location_cleared_at = _time.time() - 301   # 恰好超出窗口
        self.addCleanup(setattr, brain, "_location_cleared_at", 0.0)
        self.assertFalse(brain._location_in_clear_grace())

    def test_grace_blocks_immediately_after_clear(self):
        """任务口径用例①：mark_location_cleared() 后立刻 _inject_location
        （无 .env / 无 json）→ None，日志含"静默期"（含前置调试行）。"""
        buf = io.StringIO()
        with mock.patch.object(brain, "USER_CITY", ""), \
                mock.patch.object(brain, "USER_DISTRICT", ""), \
                mock.patch.object(self.real_sm, "get_user_location",
                                  return_value=None), \
                mock.patch.dict(sys.modules,
                                {"agent_state.state_manager": self.real_sm}), \
                contextlib.redirect_stdout(buf):
            brain.mark_location_cleared()
            self.assertIsNone(brain._inject_location("今天天气"))
        self.assertIn("📍 [位置] 静默期检查:", buf.getvalue())
        self.assertIn("在静默期内=True", buf.getvalue())
        self.assertIn("静默期", buf.getvalue())

    def test_grace_blocks_query_location_words(self):
        """任务口径用例②：静默期内 query 带完整位置词（模型从历史带回的
        "长沙市天心区的天气"）→ 同样 None，位置词不绕过静默期。"""
        buf = io.StringIO()
        with mock.patch.object(brain, "USER_CITY", ""), \
                mock.patch.object(brain, "USER_DISTRICT", ""), \
                mock.patch.object(self.real_sm, "get_user_location",
                                  return_value=None), \
                mock.patch.dict(sys.modules,
                                {"agent_state.state_manager": self.real_sm}), \
                contextlib.redirect_stdout(buf):
            brain.mark_location_cleared()
            self.assertIsNone(brain._inject_location("长沙市天心区的天气"))

    def test_grace_blocks_env_location(self):
        """本 bug 回归锁（2026-10-02 实测：/clear 后立刻问天气仍搜旧位置
        ——.env 配置位置绕过静默期）：静默期内 .env 有位置也强制 None
        询问（主人刚清除，明确表达位置不对/不要用）。"""
        buf = io.StringIO()
        with mock.patch.object(brain, "USER_CITY", "长沙"), \
                mock.patch.object(brain, "USER_DISTRICT", "天心区"), \
                contextlib.redirect_stdout(buf):
            brain.mark_location_cleared()
            self.assertIsNone(brain._inject_location("今天天气"))
        self.assertIn("静默期内忽略 .env 配置位置，强制询问", buf.getvalue())

    def test_grace_expired_env_location_resumes(self):
        """任务口径用例③：5 分钟后静默期已过 → 正常判定（.env 位置恢复
        改写为精准天气 query）。"""
        import time as _time
        brain._location_cleared_at = _time.time() - 301
        self.addCleanup(setattr, brain, "_location_cleared_at", 0.0)
        buf = io.StringIO()
        with mock.patch.object(brain, "USER_CITY", "长沙"), \
                mock.patch.object(brain, "USER_DISTRICT", "天心区"), \
                contextlib.redirect_stdout(buf):
            result = brain._inject_location("今天天气")
        self.assertEqual(result, "长沙天心区 今日天气预报 气温 降水")
        self.assertIn("在静默期内=False", buf.getvalue())

    def test_grace_allows_newly_told_json_location(self):
        """任务口径用例④：静默期内主人重新回答位置（user_location.json
        新写入）→ 新位置立即生效，不受静默期影响。"""
        buf = io.StringIO()
        with mock.patch.object(brain, "USER_CITY", ""), \
                mock.patch.object(brain, "USER_DISTRICT", ""), \
                mock.patch.object(self.real_sm, "get_user_location",
                                  return_value={"city": "长沙",
                                                "district": "天心区"}), \
                mock.patch.dict(sys.modules,
                                {"agent_state.state_manager": self.real_sm}), \
                contextlib.redirect_stdout(buf):
            brain.mark_location_cleared()
            result = brain._inject_location("今天天气")
        self.assertEqual(result, "长沙天心区 今日天气预报 气温 降水")
        self.assertNotIn("强制询问", buf.getvalue())

    def test_user_message_same_turn_rewrite(self):
        """任务口径用例①：用户消息"帮我搜一下长沙市天心区的天气" + 位置
        未知 → 提取写入 user_location.json + 当轮就改写 query 为精准天气
        词组（提取在 smart_ask 起步、工具路径现读文件，不等下一轮）。"""
        raw = ('[思考] 查询天气。\n[计划] 搜索。\n'
               '[行动] {"tool": "web_search", '
               '"args": {"query": "长沙市天心区的天气"}}')
        buf = io.StringIO()
        with self._sm_ctx(), \
                mock.patch.object(brain, "USER_CITY", ""), \
                mock.patch.object(brain, "USER_DISTRICT", ""), \
                mock.patch.object(brain, "requests") as mr, \
                mock.patch.object(brain, "execute_tool",
                                  return_value="1. 天气结果") as mexec, \
                mock.patch.object(brain, "ask_cloud") as mcloud, \
                contextlib.redirect_stdout(buf):
            mr.get.return_value = mock.Mock()
            mr.post.side_effect = [_local_resp(raw), _local_resp("汇总完成")]
            mcloud.return_value = "汇总完成"
            brain.smart_ask("帮我搜一下长沙市天心区的天气", [])
        called_args = mexec.call_args[0][1]
        self.assertEqual(called_args["query"],
                         "长沙天心区 今日天气预报 气温 降水")
        self.assertEqual(self.real_sm.get_user_location(),
                         {"city": "长沙", "district": "天心区"})
        self.assertIn("📍 [位置] 从用户消息提取: 长沙-天心区，已写入并生效",
                      buf.getvalue())

    def test_weather_results_filtered(self):
        """任务口径用例②：天气类结果含"旅游攻略/百科/介绍/历史"等 → 被
        白名单过滤，只留天气特征条目。"""
        import search_tools
        results = [
            {"title": "长沙旅游攻略", "snippet": "必去景点介绍", "url": "u1"},
            {"title": "长沙百科", "snippet": "长沙历史沿革", "url": "u2"},
            {"title": "长沙今日天气预报", "snippet": "气温 25 度 降水 0mm",
             "url": "u3"},
        ]
        kept = search_tools._filter_weather_results(results)
        self.assertEqual([r["url"] for r in kept], ["u3"])

    def test_weather_search_all_filtered_msg(self):
        """任务口径用例③：天气类结果全被过滤 → 返回"未找到相关天气信息，
        请稍后重试"。"""
        import search_tools
        noise = [{"title": "长沙旅游攻略", "snippet": "景点介绍", "url": "u1"}]
        with mock.patch.dict(os.environ, {"SEARCH_ENGINE": "bing"}), \
                mock.patch.dict(search_tools._ENGINES,
                                {"bing": lambda q, n: list(noise)}):
            out = search_tools.web_search("长沙天心区 今日天气预报 气温 降水")
        self.assertEqual(out, search_tools.NO_WEATHER_RESULT_MSG)

    def test_weather_search_keeps_weather_results(self):
        """天气类搜索：混合结果过滤后只留天气条目（既有清单格式返回）。"""
        import search_tools
        mixed = [
            {"title": "长沙旅游攻略", "snippet": "景点", "url": "u1"},
            {"title": "长沙天气预报", "snippet": "今天多云 18 度", "url": "u2"},
        ]
        with mock.patch.dict(os.environ, {"SEARCH_ENGINE": "bing"}), \
                mock.patch.dict(search_tools._ENGINES,
                                {"bing": lambda q, n: list(mixed)}):
            out = search_tools.web_search("长沙天心区 今日天气预报 气温 降水")
        self.assertIn("长沙天气预报", out)
        self.assertNotIn("旅游攻略", out)

    def test_non_weather_search_not_filtered(self):
        """任务口径用例④：非天气类搜索 → 不过滤（结果原样返回）。"""
        import search_tools
        results = [
            {"title": "Python 教程", "snippet": "入门介绍", "url": "u1"},
            {"title": "Python 官方文档", "snippet": "语法参考", "url": "u2"},
        ]
        with mock.patch.dict(os.environ, {"SEARCH_ENGINE": "bing"}), \
                mock.patch.dict(search_tools._ENGINES,
                                {"bing": lambda q, n: list(results)}):
            out = search_tools.web_search("如何写Python")
        self.assertIn("Python 教程", out)
        self.assertIn("Python 官方文档", out)


class AntiRepeatPromptTests(unittest.TestCase):
    """prompts.py 防复读约束（2026-10-02 用户口径：系统提示词末尾加一句）。"""

    def test_system_prompt_contains_anti_repeat_rule(self):
        content = brain.SYSTEM_PROMPT["content"]
        self.assertIn("【防复读规则】", content)
        self.assertIn("严禁重复同一句话或同一段话", content)
        self.assertIn("我刚才已经回复过了", content)
        # 心路历程约束（2026-10-02 用户口径）：正文只含对主人说的话 +
        # ❌/✅ 反例正例
        self.assertIn("不要把心路历程写进正文", content)
        self.assertIn("又是呼唤我，看来他挺关心我", content)   # 错误示例
        self.assertIn("<think>用户又在呼唤我，直接回应即可。</think>", content)  # 正确示例
        # 约束位于系统提示词末尾（用户口径"在系统提示词末尾加一句约束"）
        self.assertTrue(content.rstrip().endswith("有啥需要帮忙的吗？）"))


if __name__ == "__main__":
    unittest.main()
