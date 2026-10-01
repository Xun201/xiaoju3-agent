# -*- coding: utf-8 -*-
"""xiaoju3 统一配置契约与终端 CLI 行为测试（全部离线）。

- 配置常量存在性与默认值合理性：用子进程探测（隔离本进程环境变量）；
- env 覆盖生效：子进程注入环境变量后探测（环境变量优先于 .env）；
- import 零副作用：以子进程 import 且 stdin 关闭，若 REPL 意外启动会
  因 EOF 报错退出；
- CLI 平行双脑（ask_local / ask_cloud 3 次重试 / smart_ask）、内置文件
  工具沙箱、菜单渲染与 REPL 循环：mock 网络与文件副作用后离线验证。
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import xiaoju3  # noqa: E402

# 统一配置契约要求的键（BUILD_BRIEF §3）
CONFIG_KEYS = [
    "LOCAL_URL", "LOCAL_PROBE_URL", "LOCAL_MODEL", "LOCAL_TIMEOUT",
    "CLOUD_URL", "CLOUD_MODEL", "CLOUD_KEY", "CLOUD_BALANCE_URL",
    "VISION_MODEL", "VISION_KEY",
    "WORKSPACE", "MAX_MESSAGES", "AGENT_STATE_DIR", "WEB_API_KEY",
    "HA_URL", "HA_TOKEN", "HEARTBEAT_INTERVAL", "DASHBOARD_PORT",
    "PROJECT_ROOT", "TRIGGER_WORDS",
]

# 与 env 覆盖测试相关的键（子进程探测前从环境剔除，排除外部干扰）
CONFIG_ENV_KEYS = [
    "LOCAL_URL", "LOCAL_PROBE_URL", "LOCAL_MODEL", "LOCAL_TIMEOUT",
    "CLOUD_URL", "CLOUD_MODEL", "MAX_MESSAGES", "WORKSPACE",
    "AGENT_STATE_DIR", "WEB_API_KEY", "HA_URL", "HA_TOKEN",
    "VISION_MODEL", "VISION_KEY", "CLI_LOCAL_TIMEOUT",
]

PROBE_CODE = (
    "import json, sys; sys.path.insert(0, r'{root}'); import xiaoju3; "
    "print(json.dumps({{"
    "'LOCAL_MODEL': xiaoju3.LOCAL_MODEL, "
    "'MAX_MESSAGES': xiaoju3.MAX_MESSAGES, "
    "'WORKSPACE': xiaoju3.WORKSPACE, "
    "'LOCAL_URL': xiaoju3.LOCAL_URL, "
    "'CLOUD_URL': xiaoju3.CLOUD_URL, "
    "'PROJECT_ROOT': xiaoju3.PROJECT_ROOT"
    "}}))"
).format(root=PROJECT_ROOT)


def probe_config(extra_env=None):
    """子进程探测 xiaoju3 配置值（剔除相关 env 后即为默认值口径）。"""
    env = {k: v for k, v in os.environ.items() if k not in CONFIG_ENV_KEYS}
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run([sys.executable, "-c", PROBE_CODE],
                          capture_output=True, text=True, env=env, timeout=120)
    if proc.returncode != 0:
        raise AssertionError(f"配置探测子进程失败：{proc.stderr}")
    return json.loads(proc.stdout)


def _quiet():
    return contextlib.redirect_stdout(io.StringIO())


class ConfigContractTest(unittest.TestCase):
    """配置常量存在性与默认值合理性（BUILD_BRIEF §3）。"""

    def test_all_config_keys_exist(self):
        for key in CONFIG_KEYS:
            self.assertTrue(hasattr(xiaoju3, key), f"缺少配置键: {key}")

    @unittest.skipIf(os.path.exists(os.path.join(PROJECT_ROOT, ".env"))
                     or os.path.exists(os.path.join(PROJECT_ROOT, "xiaoju3_data", ".env")),
                     "项目存在本地 .env，默认值可能被其覆盖")
    def test_default_values(self):
        cfg = probe_config()
        self.assertEqual(cfg["LOCAL_MODEL"], "qwen2.5:7b")
        self.assertEqual(cfg["MAX_MESSAGES"], 50)
        # 本地 Ollama 默认指向本机中立地址，不得复制参考实现内网 IP
        self.assertTrue(cfg["LOCAL_URL"].startswith("http://127.0.0.1:11434"))
        self.assertEqual(cfg["CLOUD_URL"], "https://api.deepseek.com/chat/completions")
        # WORKSPACE 默认指向项目根 workspace/
        self.assertEqual(os.path.normpath(cfg["WORKSPACE"]),
                         os.path.normpath(os.path.join(cfg["PROJECT_ROOT"], "workspace")))

    def test_env_override_takes_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = probe_config({
                "LOCAL_MODEL": "qwen2.5:14b",
                "MAX_MESSAGES": "77",
                "WORKSPACE": tmp,
            })
        self.assertEqual(cfg["LOCAL_MODEL"], "qwen2.5:14b")
        self.assertEqual(cfg["MAX_MESSAGES"], 77)  # int 类型转换生效
        self.assertEqual(os.path.normpath(cfg["WORKSPACE"]), os.path.normpath(tmp))

    def test_import_has_zero_side_effect(self):
        """import xiaoju3 不得启动 REPL：stdin 关闭时若意外执行 input() 会
        抛 EOFError 使子进程非零退出。"""
        code = f"import sys; sys.path.insert(0, r'{PROJECT_ROOT}'); import xiaoju3; print('IMPORT_OK')"
        proc = subprocess.run([sys.executable, "-c", code], stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("IMPORT_OK", proc.stdout)


class VisionApiUrlPrefixToleranceTests(unittest.TestCase):
    """VISION_API_URL 前缀自动容错（2026-09-30 用户指令）：值 strip 后不以
    http:// 或 https:// 开头（大小写不敏感）→ 自动补 https:// 前缀；
    空值（含纯空白）仍回退缺省 DashScope 地址。子进程探测隔离宿主环境
    变量（env 优先级高于 .env，探测结果确定）。"""

    _PROBE_CODE = (
        "import sys; sys.path.insert(0, r'{root}'); import xiaoju3; "
        "print(xiaoju3.VISION_API_URL)"
    ).format(root=PROJECT_ROOT)

    def _probe_vision_url(self, value):
        """子进程设置 VISION_API_URL 后探测清洗结果（先剔除宿主同名变量）。"""
        env = {k: v for k, v in os.environ.items() if k != "VISION_API_URL"}
        env["VISION_API_URL"] = value
        proc = subprocess.run([sys.executable, "-c", self._PROBE_CODE],
                              capture_output=True, text=True, env=env, timeout=120)
        if proc.returncode != 0:
            raise AssertionError(f"VISION_API_URL 探测子进程失败：{proc.stderr}")
        return proc.stdout.strip()

    def test_bare_probe_domain_gets_https_prefix(self):
        # 不带前缀的试探地址（如 qwen 开头裸域名）→ 自动补 https://
        url = self._probe_vision_url(
            "qwen-probe.maas.aliyuncs.com/compatible-mode/v1")
        self.assertTrue(url.startswith("https://"), url)
        self.assertEqual(
            url, "https://qwen-probe.maas.aliyuncs.com/compatible-mode/v1")

    def test_value_stripped_before_prefix_added(self):
        # 两侧空白先 strip 再补前缀
        url = self._probe_vision_url("  vision.test/compatible-mode/v1  ")
        self.assertEqual(url, "https://vision.test/compatible-mode/v1")

    def test_existing_https_prefix_kept_as_is(self):
        # 已带 https:// → 原样保留，不二次补前缀
        url = self._probe_vision_url("https://vision.test/compatible-mode/v1")
        self.assertEqual(url, "https://vision.test/compatible-mode/v1")

    def test_uppercase_http_prefix_detected_case_insensitive(self):
        # HTTP:// 大写前缀：大小写不敏感识别，原样保留不重复补前缀
        url = self._probe_vision_url("HTTP://vision.test/compatible-mode/v1")
        self.assertEqual(url, "HTTP://vision.test/compatible-mode/v1")

    def test_empty_value_falls_back_to_default_dashscope(self):
        # 空值仍走缺省 DashScope 地址
        url = self._probe_vision_url("")
        self.assertEqual(
            url, "https://dashscope.aliyuncs.com/compatible-mode/v1")


class CliBrainTest(unittest.TestCase):
    """终端 CLI 平行双脑：ask_local / ask_cloud / smart_ask（mock 网络）。"""

    def _fake_response(self, payload, status_ok=True):
        resp = mock.Mock()
        resp.raise_for_status = mock.Mock()
        if status_ok:
            resp.json.return_value = payload
        else:
            resp.json.side_effect = ValueError("bad json")
        return resp

    def test_ask_local_posts_ollama_payload(self):
        resp = self._fake_response({"message": {"content": "本地回答"}})
        with mock.patch.object(xiaoju3.requests, "post", return_value=resp) as post:
            reply = xiaoju3.ask_local([{"role": "user", "content": "hi"}])
        self.assertEqual(reply, "本地回答")
        args, kwargs = post.call_args
        self.assertEqual(args[0], xiaoju3.LOCAL_URL)
        self.assertEqual(kwargs["json"]["model"], xiaoju3.LOCAL_MODEL)
        self.assertFalse(kwargs["json"]["stream"])

    def test_ask_cloud_returns_choices_content(self):
        resp = self._fake_response({"choices": [{"message": {"content": "云端回答"}}]})
        with mock.patch.object(xiaoju3.requests, "post", return_value=resp) as post:
            reply = xiaoju3.ask_cloud([{"role": "user", "content": "hi"}])
        self.assertEqual(reply, "云端回答")
        args, kwargs = post.call_args
        self.assertEqual(args[0], xiaoju3.CLOUD_URL)
        self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {xiaoju3.CLOUD_KEY}")
        self.assertEqual(kwargs["json"]["model"], xiaoju3.CLOUD_MODEL)

    def test_ask_cloud_surfaces_api_error_detail(self):
        resp = self._fake_response({"error": {"message": "余额不足"}})
        with mock.patch.object(xiaoju3.requests, "post", return_value=resp):
            with _quiet():
                reply = xiaoju3.ask_cloud([{"role": "user", "content": "hi"}])
        self.assertEqual(reply, "⚠️ API返回错误：余额不足")

    def test_ask_cloud_retries_three_times_then_graceful(self):
        with mock.patch.object(xiaoju3.requests, "post", side_effect=OSError("断网")) as post, \
                mock.patch.object(xiaoju3.time, "sleep") as sleep, \
                _quiet():
            reply = xiaoju3.ask_cloud([{"role": "user", "content": "hi"}])
        self.assertEqual(reply, "⚠️ 云端大脑开小差了，请稍后再试~")
        self.assertEqual(post.call_count, 3)   # 云端最多 3 次重试
        self.assertEqual(sleep.call_count, 2)  # 前两次失败后各歇 2 秒

    def test_smart_ask_local_success(self):
        with mock.patch.object(xiaoju3, "ask_local", return_value="本地回复"), _quiet():
            reply, source = xiaoju3.smart_ask([{"role": "user", "content": "hi"}])
        self.assertEqual((reply, source), ("本地回复", "🏠 本地"))

    def test_smart_ask_hot_switch_to_cloud(self):
        with mock.patch.object(xiaoju3, "ask_local", side_effect=OSError("本地挂了")), \
                mock.patch.object(xiaoju3, "ask_cloud", return_value="云端回复") as cloud, \
                _quiet():
            reply, source = xiaoju3.smart_ask([{"role": "user", "content": "hi"}])
        self.assertEqual((reply, source), ("云端回复", "☁️ 云端"))
        self.assertEqual(cloud.call_count, 1)

    def test_smart_ask_tool_interception(self):
        tool_json = '{"tool": "list_files", "args": {}}'
        with mock.patch.object(xiaoju3, "ask_local",
                               side_effect=[tool_json, "工作区里有 a.txt"]), \
                mock.patch.object(xiaoju3, "execute_tool", return_value="a.txt") as exec_tool, \
                _quiet():
            messages = [{"role": "user", "content": "看看工作区"}]
            reply, source = xiaoju3.smart_ask(messages)
        self.assertEqual((reply, source), ("工作区里有 a.txt", "🏠 本地 (工具)"))
        exec_tool.assert_called_once_with("list_files", {})
        # 工具 JSON 与结果按参考实现喂回消息列表
        self.assertEqual(messages[1], {"role": "assistant", "content": tool_json})
        self.assertIn("工具执行结果：a.txt", messages[2]["content"])

    def test_smart_ask_malformed_json_treated_as_reply(self):
        bad = "{不是合法json}"
        with mock.patch.object(xiaoju3, "ask_local", return_value=bad), _quiet():
            reply, source = xiaoju3.smart_ask([{"role": "user", "content": "hi"}])
        self.assertEqual((reply, source), (bad, "🏠 本地"))


class CliBuiltinToolTest(unittest.TestCase):
    """内置文件工具三件套：沙箱校验 / 截断 / 列目录。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._ws_patch = mock.patch.object(xiaoju3, "WORKSPACE", self._tmp.name)
        self._ws_patch.start()
        self.addCleanup(self._ws_patch.stop)

    def test_read_write_roundtrip_and_truncation(self):
        self.assertEqual(xiaoju3._builtin_execute_tool(
            "write_file", {"filename": "a.txt", "content": "x" * 1200}),
            "✅ 文件 a.txt 写入成功！")
        content = xiaoju3._builtin_execute_tool("read_file", {"filename": "a.txt"})
        self.assertEqual(content, "x" * 1000)  # read_file 截断 1000 字符
        self.assertIn("不存在", xiaoju3._builtin_execute_tool("read_file", {"filename": "ghost.txt"}))

    def test_sandbox_rejects_outside_workspace(self):
        for tool, args in [("read_file", {"filename": "../secret.txt"}),
                           ("write_file", {"filename": "../evil.txt", "content": "x"})]:
            result = xiaoju3._builtin_execute_tool(tool, args)
            self.assertTrue(result.startswith("❌ 安全拒绝"), result)

    def test_list_files(self):
        self.assertEqual(xiaoju3._builtin_execute_tool("list_files", {}), "（工作区为空）")
        with open(os.path.join(self._tmp.name, "b.txt"), "w", encoding="utf-8") as f:
            f.write("hi")
        self.assertEqual(xiaoju3._builtin_execute_tool("list_files", {}), "b.txt")

    def test_unknown_tool(self):
        self.assertEqual(xiaoju3._builtin_execute_tool("nope", {}), "未知工具")


class CliMenuAndReplTest(unittest.TestCase):
    """/help 菜单渲染与 REPL 循环（/exit、/gen_log、对话）。"""

    def test_help_menu_fallback_when_plugin_missing(self):
        with mock.patch.dict(sys.modules, {"plugins.help_menu": None}):
            menu = xiaoju3._get_help_menu()
        self.assertIn("/gen_log", menu)
        self.assertIn("/exit", menu)
        self.assertIn("Lv.", menu)

    def test_help_menu_delegates_to_plugin(self):
        fake = types.ModuleType("plugins.help_menu")
        fake.get_help_menu = mock.Mock(return_value="MENU-FROM-PLUGIN")
        with mock.patch.dict(sys.modules, {"plugins.help_menu": fake}):
            menu = xiaoju3._get_help_menu()
        self.assertEqual(menu, "MENU-FROM-PLUGIN")
        fake.get_help_menu.assert_called_once()
        level = fake.get_help_menu.call_args[0][0]
        self.assertTrue(str(level).startswith("Lv."))

    def _run_repl(self, inputs, extra_patches=None):
        out = io.StringIO()
        saved = []
        with contextlib.redirect_stdout(out), contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("builtins.input", side_effect=inputs))
            stack.enter_context(mock.patch.object(
                xiaoju3, "load_memory", return_value=[{"role": "system", "content": "S"}]))
            stack.enter_context(mock.patch.object(
                xiaoju3, "save_memory", side_effect=saved.append))
            stack.enter_context(mock.patch.object(
                xiaoju3, "_get_help_menu", return_value="MENU"))
            stack.enter_context(mock.patch.object(
                xiaoju3, "smart_ask", return_value=("回复", "🏠 本地")))
            for p in (extra_patches or []):
                stack.enter_context(p)
            xiaoju3.main()
        return out.getvalue(), saved

    def test_repl_chat_exit_and_memory_saved(self):
        out, saved = self._run_repl(["你好", "/exit"])
        self.assertIn("🤖 小橘3号 [🏠 本地]: 回复", out)
        self.assertIn("💾 记忆已保存。", out)
        self.assertEqual(len(saved), 2)  # 每轮对话后 + 退出时各保存一次

    def test_repl_menu_words(self):
        for word in ("/help", "菜单", "帮助", "指令"):
            out, _ = self._run_repl([word, "/exit"])
            self.assertIn("MENU", out)

    def test_repl_gen_log_invalid_url(self):
        out, _ = self._run_repl(["/gen_log", "/exit"])
        self.assertIn("⚠️ 请提供正确的 DeepSeek 分享链接", out)

    def test_repl_gen_log_delegates_to_run_link_log(self):
        fake = types.ModuleType("run_link_log")
        recorded = []
        fake.run_link_log = lambda url, data_dir=None: recorded.append(url) or "日志正文"
        with mock.patch.dict(sys.modules, {"run_link_log": fake}):
            out, _ = self._run_repl(["/gen_log https://chat.deepseek.com/share/abc", "/exit"])
        self.assertEqual(recorded, ["https://chat.deepseek.com/share/abc"])

    def test_repl_eof_saves_memory(self):
        # Ctrl+C / EOF 亦走保存退出路径（input 在 EOF 时抛 EOFError）
        out, saved = self._run_repl(["你好", EOFError])
        self.assertIn("💾 记忆已保存。", out)
        self.assertEqual(len(saved), 2)  # 每轮对话后 + EOF 退出时各保存一次


class CliMemoryTest(unittest.TestCase):
    """CLI 会话记忆：读写往返 + system 提示词 + MAX_MESSAGES 截断。"""

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem_file = os.path.join(tmp, "history_cli.json")
            with mock.patch.object(xiaoju3, "CLI_MEMORY_FILE", mem_file), _quiet():
                messages = [{"role": "system", "content": "S"},
                            {"role": "user", "content": "hi"},
                            {"role": "assistant", "content": "hello"}]
                xiaoju3.save_memory(messages)
                self.assertTrue(os.path.exists(mem_file))
                loaded = xiaoju3.load_memory()
        self.assertEqual(loaded[0]["role"], "system")           # system 提示词在最前
        self.assertEqual([m["content"] for m in loaded[1:]], ["hi", "hello"])

    def test_save_truncates_to_max_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem_file = os.path.join(tmp, "history_cli.json")
            with mock.patch.object(xiaoju3, "CLI_MEMORY_FILE", mem_file), _quiet():
                messages = [{"role": "system", "content": "S"}]
                messages += [{"role": "user", "content": f"m{i}"}
                             for i in range(xiaoju3.MAX_MESSAGES + 10)]
                xiaoju3.save_memory(messages)
                with open(mem_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
        self.assertEqual(len(saved), xiaoju3.MAX_MESSAGES)
        self.assertEqual(saved[-1]["content"], f"m{xiaoju3.MAX_MESSAGES + 9}")


class HardwareAdaptiveConfigTests(unittest.TestCase):
    """硬件自适应路由配置键（DEVICE_TIER / LOCAL_MODEL_SMALL）。"""

    @unittest.skipIf(os.path.exists(os.path.join(PROJECT_ROOT, ".env"))
                     or os.path.exists(os.path.join(PROJECT_ROOT, "xiaoju3_data", ".env")),
                     "项目存在本地 .env，DEVICE_TIER 可能被其覆盖")
    def test_config_keys_exist(self):
        import importlib
        cfg = importlib.import_module("xiaoju3")
        self.assertEqual(cfg.DEVICE_TIER, "auto")
        self.assertEqual(cfg.LOCAL_MODEL_SMALL, "qwen2.5:0.5b")

    def test_env_override(self):
        import subprocess
        code = (
            "import xiaoju3 as c;"
            "print(c.DEVICE_TIER, c.LOCAL_MODEL_SMALL)"
        )
        import os
        env = dict(os.environ)
        env["DEVICE_TIER"] = "low"
        env["LOCAL_MODEL_SMALL"] = "tiny-model"
        out = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, env=env,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.assertEqual(out.stdout.strip(), "low tiny-model")


if __name__ == "__main__":
    unittest.main()
