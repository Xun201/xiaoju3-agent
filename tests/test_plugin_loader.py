# -*- coding: utf-8 -*-
"""插件总线（#312 一期）测试：契约/隔离/卸载收回/合并视图/R1-a 消费口动态化。

隔离策略：external_dir() patch 到 tmp 目录 + 现场写临时插件，零碰真实
agent_state/plugins（验收样例 dice.py 留在原地作真机演示，不进测试断言）。
"""
import os
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import plugin_loader
import tool_registry
import tools
import intent_router

DICE = textwrap.dedent('''
    import random
    def extract_noargs(_message=None, _match=None):
        return {}

    _state = {"setup": False, "teardown": False}

    def setup(ctx):
        _state["setup"] = True
        _state["data_dir"] = ctx.get("data_dir", "")

    def teardown():
        _state["teardown"] = True

    def ping():
        return "pong"

    def reply(**_):
        return "意图命中"

    PLUGIN = {
        "name": "ttest", "version": "0.1.0", "desc": "测试插件", "level": 2,
        "tools": [
            {"name": "ext_ttest_ping", "desc": "回声测试", "params": "无",
             "handler": "agent_state_plugins_ttest:ping"},
        ],
        "intents": [
            {"name": "ext_ttest_intent", "desc": "测试意图",
             "patterns": [r"临时测试意图标记词"],
             "extractor": extract_noargs,
             "handler_name": "agent_state_plugins_ttest:reply"},
        ],
        "setup": setup, "teardown": teardown,
    }
''')


class PluginLoaderTests(unittest.TestCase):
    """总线六步生命周期 + 契约校验 + 隔离（tmp 插件目录，零碰真实样例）。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="xj3_plug_")
        self._orig_dir = plugin_loader.external_dir
        self._enter = patch.object(plugin_loader, "external_dir",
                                   lambda: self._tmp)
        self._enter.start()
        # 模块级缓存态清场（跨测试串扰防御）
        tool_registry.external_tools[:] = []
        tools.refresh_derived()
        intent_router.register_external_intents([])

    def tearDown(self):
        self._enter.stop()
        plugin_loader._loaded.clear()
        tool_registry.external_tools[:] = []
        tools.refresh_derived()
        intent_router.register_external_intents([])
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write(self, filename, content):
        path = os.path.join(self._tmp, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_load_validate_merge_full_cycle(self):
        """全周期：加载→白名单/意图/prompt 合并生效→卸载全收回→再载回。"""
        self._write("ttest.py", DICE)
        ok, fail = plugin_loader.load_all()
        self.assertEqual((ok, fail), (1, 0))
        self.assertIn("ext_ttest_ping", tools.TOOL_WHITELIST)          # 白名单合并
        self.assertNotIn("ext_ttest_ping", tool_registry.TOOL_MANIFEST and
                         [t["name"] for t in tool_registry.TOOL_MANIFEST])  # 内置表本体零污染
        r = intent_router.route("说一句 临时测试意图标记词 看看")
        self.assertIsNotNone(r)
        self.assertEqual(r.handler, "agent_state_plugins_ttest:reply")  # 意图合并
        # 卸载全收回
        plugin_loader.unload_all()
        self.assertNotIn("ext_ttest_ping", tools.TOOL_WHITELIST)
        self.assertIsNone(intent_router.route("说一句 临时测试意图标记词 看看"))
        # 再载回（幂等）
        ok, fail = plugin_loader.load_all()
        self.assertEqual((ok, fail), (1, 0))
        self.assertIn("ext_ttest_ping", tools.TOOL_WHITELIST)

    def test_setup_teardown_hooks_called(self):
        """生命周期钩子：setup 载入时调用（ctx 含 data_dir），teardown 卸载时调用。"""
        self._write("ttest.py", DICE)
        plugin_loader.load_all()
        rec = plugin_loader.loaded_plugins()["ttest"]
        self.assertTrue(rec["module"]._state["setup"])
        self.assertIn("ttest", rec["module"]._state["data_dir"])
        plugin_loader.unload_all()
        self.assertTrue(rec["module"]._state["teardown"])

    def test_broken_plugin_isolated(self):
        """隔离①加载期：语法坏插件跳过+计数 fail，好插件照常载入。"""
        self._write("broken.py", "PLUGIN = { 这是故意的语法错误 !!!")
        self._write("ttest.py", DICE)
        ok, fail = plugin_loader.load_all()
        self.assertEqual((ok, fail), (1, 1))
        self.assertIn("ttest", plugin_loader.loaded_plugins())

    def test_boom_dispatch_isolated(self):
        """隔离②执行期：插件工具抛异常 → dispatch 返回 ❌ 串，不抛不崩（既有
        双层 try/except 承担，本测锁合并视图下该语义仍成立）。"""
        self._write("ttest.py", DICE.replace(
            '"handler": "agent_state_plugins_ttest:ping"',
            '"handler": "agent_state_plugins_ttest:boom",\n'
            '         "extra": None'))
        self._write("ttest.py", DICE)
        # 直接写一个必抛插件（独立文件更直白）
        self._write("boomer.py", textwrap.dedent('''
            PLUGIN = {
                "name": "boomer", "version": "0.1.0", "desc": "必抛", "level": 2,
                "tools": [{"name": "ext_boom_now", "desc": "必抛", "params": "无",
                           "handler": "agent_state_plugins_boomer:boom"}],
            }
            def boom():
                raise RuntimeError("隔离演示")
        '''))
        plugin_loader.load_all()
        out = tool_registry.dispatch_plugin_tool("ext_boom_now", {})
        self.assertTrue(out.startswith("❌"))
        self.assertIn("ext_ttest_ping", tools.TOOL_WHITELIST)   # 其他插件照常

    def test_ext_prefix_and_level_cap_enforced(self):
        """D1/D2 落地：非 ext_ 前缀工具拒载；level 越权压回 Lv.3 并收录。"""
        self._write("bad_name.py", textwrap.dedent('''
            PLUGIN = {"name": "bad_name", "version": "0.1.0", "desc": "x", "level": 2,
                      "tools": [{"name": "no_prefix", "desc": "x", "params": "无",
                                 "handler": "agent_state_plugins_bad_name:f"}]}
            def f(): return "x"
        '''))
        self._write("overpower.py", textwrap.dedent('''
            PLUGIN = {"name": "overpower", "version": "0.1.0", "desc": "x", "level": 4,
                      "tools": [{"name": "ext_over", "desc": "x", "params": "无",
                                 "handler": "agent_state_plugins_overpower:f"}]}
            def f(): return "x"
        '''))
        plugin_loader.load_all()
        self.assertNotIn("bad_name", plugin_loader.loaded_plugins())   # 前缀违反拒载
        rec = plugin_loader.loaded_plugins()["overpower"]
        self.assertEqual(rec["plugin"]["level"], 3)                    # 越权压回 Lv.3
        self.assertIn("ext_over", tools.TOOL_WHITELIST)

    def test_no_plugin_declaration_skipped(self):
        """无 PLUGIN 声明的 .py 跳过（不误载普通脚本）。"""
        self._write("plain.py", "x = 1\n")
        ok, fail = plugin_loader.load_all()
        self.assertEqual((ok, fail), (0, 1))

    def test_r1a_consumers_are_dynamic(self):
        """R1-a 消费口动态化哨兵：tools 派生常量经 refresh_derived 重绑生效；
        brain/prompts 消费口为属性访问/直调（from-import 快照退役）。"""
        self._write("ttest.py", DICE)
        plugin_loader.load_all()
        self.assertIn("ext_ttest_ping", tools.TOOL_WHITELIST)   # refresh 后常量新集合
        brain_src = open(os.path.join(PROJECT_ROOT, "brain.py"),
                         encoding="utf-8").read()
        self.assertNotIn("from tools import execute_tool, TOOL_WHITELIST", brain_src)
        self.assertGreaterEqual(brain_src.count("tools.TOOL_WHITELIST"), 2)
        main_src = open(os.path.join(PROJECT_ROOT, "main.py"),
                        encoding="utf-8").read()
        self.assertIn("import prompts", main_src)               # 属性访问形态
        self.assertIn("def refresh_system_messages", main_src)
        loader_src = open(os.path.join(PROJECT_ROOT, "plugin_loader.py"),
                          encoding="utf-8").read()
        self.assertIn("importlib.reload(prompts)", loader_src)
        self.assertIn("main.refresh_system_messages()", loader_src)

    def test_builtin_plugins_not_scanned(self):
        """D5 双轨：总线只扫 agent_state/plugins，内置 plugins/ 目录不入扫描
        （内置 13 插件照旧手工表，零迁移零回归）。"""
        self.assertEqual([n for n, _, _ in plugin_loader.scan()], [])


if __name__ == "__main__":
    unittest.main()
