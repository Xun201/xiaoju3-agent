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
  同样包装；普通聊天/URL 总结/熔断剥夺路径不包装；CoT 花括号内容不干扰
  JSON 提取（贪婪正则失败回退逐 { raw_decode 扫描）；[CoT] 终端日志
  （兜底占位符注入 / 模型原生思考输出各一条，redirect_stdout 捕获）；
- URL 输入触发网页抓取（script/style 被剔除）；
- MAX_MESSAGES=50 截断；translate_emoji 转换正确且已接入 smart_ask 回复链；
- smart_ask 返回二元组与来源标签（🏠 本地 / ☁️ 云端 / (工具) / ⛔ 熔断）正确；
- _build_messages 前缀白名单：最近设备操作记录 system 条目保留注入，
  既有【前情提要】/长期记忆前缀不回退。

外部模块（home_tools / adb_tools / vision_tools / android_ui_tools）由并行
开发负责，与 tests/test_tools.py 相同：在 import brain（→ tools）之前向
sys.modules 注入 mock；emoji_manager 用 patch.dict 按需注入。
"""
import contextlib
import io
import json
import os
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

        self.assertEqual(result, ("你好呀，我是小橘！", "🏠 本地"))
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

        self.assertEqual(result, ("云端回答", "☁️ 云端"))
        args, _ = mr.post.call_args
        self.assertEqual(args[0], xiaoju3.CLOUD_URL)

    def test_local_exception_hot_switch_to_cloud(self):
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()          # 探测成功
            mr.post.side_effect = [ConnectionError("本地挂了"), _cloud_resp("云端回答")]
            result = brain.smart_ask("你好", [])

        self.assertEqual(result, ("云端回答", "☁️ 云端"))
        self.assertEqual(mr.post.call_count, 2)

    def test_both_brains_down_error_message(self):
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.side_effect = OSError("探测失败")
            mr.post.side_effect = Exception("network down")
            reply, source = brain.smart_ask("你好", [])

        self.assertTrue(reply.startswith("❌ 大脑连接失败，请检查网络。错误："), reply)
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
        self.assertEqual(sum(1 for m in msgs if m["role"] == "system"), 1)
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
        self.assertEqual(sum(1 for m in msgs if m["role"] == "system"), 1)
        self.assertEqual([m["content"] for m in msgs[1:]],
                         ["昨天聊到哪了", "聊到记忆压缩", "那继续"])

    def test_history_with_pre_appended_user_message_dedup(self):
        # 参考实现口径：调用方先把用户消息 append 进 history 再调用 → 去重
        history = [{"role": "user", "content": "你好"}]
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("你好呀")
            brain.smart_ask("你好", history)

        msgs = mr.post.call_args.kwargs["json"]["messages"]
        self.assertEqual(len(msgs), 2)  # system + 去重后的 user
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
        self.assertEqual(result, ("抱歉，小橘3号刚才脑袋短路了，请再说一遍吧。", "🏠 本地"))

    def test_result_is_always_tuple_of_two(self):
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("好")
            self.assertEqual(brain.smart_ask("你好", []), ("好", "🏠 本地"))
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
        self.assertEqual(result, (raw, "🏠 本地"))
        mexec.assert_not_called()
        mcloud.assert_not_called()

    def test_tool_outside_whitelist_rejected(self):
        raw = '{"tool": "format_disk", "args": {}}'
        result, mexec, mcloud, _ = _run_tool_flow(raw)
        # 白名单外：不执行工具，按普通文本回复处理
        mexec.assert_not_called()
        mcloud.assert_not_called()
        self.assertEqual(result, (raw, "🏠 本地"))

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
    - 无工具调用（普通聊天/解析失败/白名单外/URL 总结/熔断剥夺）→ 不包装；
    - CoT 文本里混入花括号内容不得干扰工具 JSON 提取（先提取 JSON 再裁思考）。
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

    def test_plain_chat_reply_never_wrapped(self):
        # 普通聊天零影响：无工具调用绝不加包装
        with mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("今天天气不错哦～")
            result = brain.smart_ask("你好", [])
        self.assertEqual(result, ("今天天气不错哦～", "🏠 本地"))
        self.assertNotIn("<think>", result[0])

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

    def test_braces_in_cot_without_tool_json_stays_plain(self):
        # 有思考、有花括号，但没有合法工具 JSON → 按普通回复处理，不加包装
        raw = '[思考] 我先想想 {看看} 再说。'
        result, mexec, mcloud, _ = _run_tool_flow(raw)
        self.assertEqual(result, (raw, "🏠 本地"))
        mexec.assert_not_called()
        mcloud.assert_not_called()

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

    def test_url_summary_not_wrapped(self):
        # URL 总结路径无工具调用 → 不加 <think> 包装
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
        self.assertEqual(result, ("这是网页总结", "☁️ 云端 (总结)"))
        self.assertNotIn("<think>", result[0])


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
        self.assertEqual(result, (self.RAW, "🏠 本地"))

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
        self.assertEqual(result, ("这是网页总结", "☁️ 云端 (总结)"))

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

        self.assertEqual(result, ("这是网页总结", "🏠 本地 (总结)"))
        web_msg = mr.post.call_args.kwargs["json"]["messages"][-1]["content"]
        self.assertIn("已为你抓取好网页，请直接总结，不要输出任何 JSON！", web_msg)
        self.assertIn("这是正文内容，包含关键信息。", web_msg)
        self.assertIn("第二段正文", web_msg)
        self.assertNotIn("SECRET_SCRIPT", web_msg)
        self.assertNotIn("color: red", web_msg)
        self.assertNotIn("<p>", web_msg)

    def test_fetch_failure_returns_error(self):
        result, mcloud = self._run(probe_ok=True, get_error=OSError("timed out"))
        self.assertEqual(result, ("❌ 抓取网页失败: timed out", "❌ 失败"))
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
        self.assertEqual(result, ("云端回答", "☁️ 云端"))
        args, _kwargs = mr.post.call_args
        self.assertEqual(args[0], xiaoju3.CLOUD_URL)

    def test_medium_uses_small_model(self):
        """medium 档：探测本地并用小模型（LOCAL_MODEL_SMALL）。"""
        self._tier("medium")
        with mock.patch.object(brain, "requests") as mr,                 mock.patch.object(brain, "ask_cloud") as mcloud, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("小模型回答")
            result = brain.smart_ask("你好", [])
        self.assertEqual(result, ("小模型回答", "🏠 本地"))
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
        self.assertEqual(result, ("云端回答", "☁️ 云端"))

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
        self.assertEqual(result, ("小模型回答", "🏠 本地"))
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

    def test_unknown_tag_removed(self):
        with mock.patch.dict(sys.modules, {"emoji_manager": _fake_emoji_manager()}):
            self.assertEqual(brain.translate_emoji("呜呜[EMOJI:大哭]"), "呜呜")

    def test_mixed_tags(self):
        with mock.patch.dict(sys.modules, {"emoji_manager": _fake_emoji_manager()}):
            self.assertEqual(
                brain.translate_emoji("A[EMOJI:开心]B[EMOJI:缺失]C"),
                "A[CQ:image,file=file:///emoji/lib/kaixin.png]BC")

    def test_no_tag_unchanged(self):
        self.assertEqual(brain.translate_emoji("普通回复，没有标签。"),
                         "普通回复，没有标签。")

    def test_emoji_manager_missing_graceful(self):
        # sys.modules 置 None 使延迟导入稳定抛 ImportError → 原样返回
        with mock.patch.dict(sys.modules, {"emoji_manager": None}):
            self.assertEqual(brain.translate_emoji("[EMOJI:开心]"), "[EMOJI:开心]")

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
        self.assertEqual(result, ("带[已转换]的回复", "🏠 本地"))

    def test_emoji_translated_end_to_end_with_fake_library(self):
        # 假表情库：正常回复中的 [EMOJI:标签] 转成 CQ 码后随回复真正发出
        with mock.patch.dict(sys.modules, {"emoji_manager": _fake_emoji_manager()}), \
                mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("哈哈[EMOJI:开心]")
            result = brain.smart_ask("你好", [])

        self.assertEqual(result,
                         ("哈哈[CQ:image,file=file:///emoji/lib/kaixin.png]",
                          "🏠 本地"))

    def setUp(self):
        # 与机器状态/本地 .env 档位解耦：固定 high + 探测在线
        tp = mock.patch.object(brain, "_resolve_tier", return_value="high")
        tp.start()
        self.addCleanup(tp.stop)
        pp = mock.patch.object(brain, "probe_local", return_value=True)
        pp.start()
        self.addCleanup(pp.stop)

    def test_emoji_missing_library_degrades_gracefully(self):
        # emoji_manager 缺席 → [EMOJI:] 原样保留，不阻断回复链
        with mock.patch.dict(sys.modules, {"emoji_manager": None}), \
                mock.patch.object(brain, "requests") as mr, _quiet():
            mr.get.return_value = mock.Mock()
            mr.post.return_value = _local_resp("哈哈[EMOJI:开心]")
            result = brain.smart_ask("你好", [])

        self.assertEqual(result, ("哈哈[EMOJI:开心]", "🏠 本地"))

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


if __name__ == "__main__":
    unittest.main()
