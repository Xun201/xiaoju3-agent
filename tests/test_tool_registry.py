# -*- coding: utf-8 -*-
"""tool_registry 统一工具登记表测试（2026-10-04 model_tool 合并钩子，
docs/ARCHITECTURE_BOUNDARY.md §3.3）：声明唯一真相——tools/brain/prompts
三处派生一致、旧集合快照不变、"新增工具只改登记表一处"锚、插件分派
（handler 字符串 importlib 解析，缺库/异常中文 ❌ 串）。全离线。"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import tool_registry
import tools
import brain
import prompts

# 旧集合快照（2026-10-04 重构前的字面值，派生结果必须与之全等——
# 行为不变的硬保证，任何"顺手调整"都该在此处显式失败再拍板）
_LEGACY_WHITELIST = [
    "list_files", "read_file", "write_file", "get_ha_devices",
    "control_ha_device", "adb_tap", "adb_swipe", "adb_screenshot",
    "vision_tap_element", "ui_tap_element", "web_search", "system_manage",
    "read_core_memory", "restart_service", "extract_todos",
    "desktop_list_skills", "desktop_run_skill", "desktop_list_windows",
]
_LEGACY_LV2 = {"read_file", "list_files", "extract_todos"}
_LEGACY_LV3 = {"write_file"}
_LEGACY_LV4 = {"adb_screenshot", "adb_tap", "adb_swipe", "ui_tap_element",
               "vision_tap_element", "send_image", "restart_service",
               "desktop_list_skills", "desktop_run_skill", "desktop_list_windows"}
_LEGACY_DANGER = {"write_file", "adb_tap", "adb_swipe", "control_ha_device",
                  "desktop_run_skill"}
_LEGACY_ACTION = {"control_ha_device", "adb_tap", "adb_swipe", "desktop_run_skill"}

# 工具协议 15 行字面量快照（prompts.py 重构前原文，派生行必须逐字节一致）
_LEGACY_PROMPT_BLOCK = """1. list_files - 列出工作区内的所有文件。参数：无
2. read_file - 读取工作区内指定文件的内容。参数：filename
3. write_file - 在工作区内创建一个新文件并写入内容。参数：filename, content
4. get_ha_devices - 获取所有智能家居设备及其当前状态。参数：无
5. control_ha_device - 控制家中家电设备（灯/开关/空调/传感器/插座等）——凡是开灯、关灯、调温等家电请求必用此工具。参数：entity_id (设备ID), action (turn_on/turn_off/toggle/set_temperature), temperature (set_temperature 时的目标温度，数字，如 26)
6. adb_screenshot - 截取手机屏幕图片。参数：无
7. adb_tap - 点击手机屏幕坐标。参数：x (横坐标), y (纵坐标)
8. adb_swipe - 滑动手机屏幕。参数：x1, y1, x2, y2
9. ui_tap_element - 通过系统底层 UI 解析精准点击手机屏幕元素（仅限手机/平板界面，家电控制禁止用此工具）。参数：element_name (要点击的元素的文字，如 “设置”、“确认”)
10. vision_tap_element - 视觉识别点击（仅在 ui_tap_element 失效时备用，仅限手机屏幕）。参数：element_name
11. web_search - 联网搜索，检索互联网上的公开信息。参数：query (搜索关键词), max_results (可选，结果条数，默认 5)
12. system_manage - 一键安装/卸载系统组件（仅 Lv.4 主人级可用）。参数：action (install/uninstall), component (组件名，仅允许字母数字._-)
13. read_core_memory - 读取核心记忆库（仅 Lv.4 主人级可用）。参数：limit (可选，条数，默认 5)
14. restart_service - 重启小橘3号自身进程（LV4 主人级专属，重启后需等待守护进程拉起，期间会短暂离线）。参数：无
15. extract_todos - 提取 DeepSeek 分享链接里的待办事项并存入待办清单（后台处理，受理后立即返回）。参数：url（完整分享链接，须以 https://chat.deepseek.com/share/ 开头）。当主人发来分享链接并表达“记下待办/整理清单”类意图时使用。
16. desktop_list_skills - 列出已保存的桌面操作技能（录制回放，控制台 🧰 面板可录制）。参数：无
17. desktop_run_skill - 回放一个已保存的桌面操作技能（会真实执行录制时的鼠标键盘操作；敏感窗口自动拦截中止）。参数：name (技能名，先 desktop_list_skills 查询)
18. desktop_list_windows - 列出当前打开的桌面窗口标题（回放前确认目标窗口是否在场）。参数：无"""

# 模拟"新增插件模型工具"：一条登记 + handler 字符串（json:dumps 为
# 离线可执行的真实函数，dumps(obj=..) 形参对应 args 键）
_FAKE_PLUGIN_TOOL = {
    "name": "weather_probe", "desc": "探测天气", "params": "a, b",
    "level": 3, "dangerous": True, "is_action": True,
    "handler": "json:dumps", "module": "plugins.weather",
}
_EXTENDED = tool_registry.TOOL_MANIFEST + [_FAKE_PLUGIN_TOOL]


class ToolRegistrySnapshotTests(unittest.TestCase):
    """登记表派生值 == 重构前字面值快照（行为不变的硬保证）。"""

    def test_whitelist_matches_legacy(self):
        self.assertEqual(sorted(tool_registry.whitelist_names()),
                         sorted(_LEGACY_WHITELIST))
        self.assertEqual(len(tool_registry.whitelist_names()), 18)

    def test_permission_sets_match_legacy(self):
        self.assertEqual(tool_registry.level_set(2), _LEGACY_LV2)
        self.assertEqual(tool_registry.level_set(3), _LEGACY_LV3)
        self.assertEqual(tool_registry.level_set(4), _LEGACY_LV4)
        self.assertEqual(tool_registry.danger_set(), _LEGACY_DANGER)
        self.assertEqual(tool_registry.action_set(), _LEGACY_ACTION)

    def test_prompt_lines_match_legacy_block(self):
        self.assertEqual("\n".join(tool_registry.prompt_tool_lines()),
                         _LEGACY_PROMPT_BLOCK)

    def test_control_ha_device_exposes_set_temperature(self):
        # H1（2026-10-05）：温度设定暴露给模型——"空调调到26度"口径
        # （功能文档 §8.4），登记表 params 必须含 set_temperature/temperature
        entry = next(t for t in tool_registry.TOOL_MANIFEST
                     if t["name"] == "control_ha_device")
        self.assertIn("set_temperature", entry["params"])
        self.assertIn("temperature", entry["params"])

    def test_home_appliance_trigger_words_and_phone_scope(self):
        # #248（2026-10-05）：控灯误路由修复——C 腿双向描述改造：
        # control_ha_device 带家电触发词+必用话术；点击类工具标"仅限手机"
        ha = next(t for t in tool_registry.TOOL_MANIFEST
                  if t["name"] == "control_ha_device")
        self.assertIn("必用此工具", ha["desc"])
        self.assertIn("灯", ha["desc"])
        ui = next(t for t in tool_registry.TOOL_MANIFEST
                  if t["name"] == "ui_tap_element")
        vi = next(t for t in tool_registry.TOOL_MANIFEST
                  if t["name"] == "vision_tap_element")
        self.assertIn("仅限手机", ui["desc"])
        self.assertIn("家电控制禁止", ui["desc"])
        self.assertIn("仅限手机", vi["desc"])


class ThreeSitesDeriveFromRegistryTests(unittest.TestCase):
    """tools / brain / prompts 三处消费值全部来自登记表（合并钩子本体）。"""

    def test_tools_whitelist_derived(self):
        self.assertEqual(tools.TOOL_WHITELIST,
                         tool_registry.whitelist_names())

    def test_tools_permission_sets_derived(self):
        self.assertEqual(tools._LV2_TOOLS, tool_registry.level_set(2))
        self.assertEqual(tools._LV3_TOOLS, tool_registry.level_set(3))
        self.assertEqual(tools._LV4_TOOLS, tool_registry.level_set(4))
        self.assertEqual(tools.DANGER_TOOLS, tool_registry.danger_set())
        self.assertEqual(tools.ACTION_TOOLS, tool_registry.action_set())

    def test_brain_whitelist_is_tools_object(self):
        # #312 R1-a（2026-10-25）：brain from-import 快照退役（消费口=tools
        # 属性访问+直调），assertIs 同一对象锚随退役——相等性语义由上方
        # tools 派生锚与 test_brain 的 tools.TOOL_WHITELIST 引用共同覆盖。
        brain_src = open(os.path.join(PROJECT_ROOT, "brain.py"),
                         encoding="utf-8").read()
        self.assertNotIn("from tools import execute_tool, TOOL_WHITELIST",
                         brain_src)   # 快照形态禁回流
    def test_prompts_embeds_generated_block(self):
        content = prompts.SYSTEM_PROMPT["content"]
        self.assertIn("\n".join(tool_registry.prompt_tool_lines()), content)

    def test_prompts_source_has_no_literal_tool_block(self):
        # 源码级静态锚：15 行字面量已退役，占位符在位（防手写清单回流）
        src_path = os.path.join(PROJECT_ROOT, "prompts.py")
        with open(src_path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("{_TOOL_LINES}", src)
        self.assertNotIn("1. list_files", src)


class NewToolRegistryOnlyTests(unittest.TestCase):
    """核心锚：新增（插件）工具只改登记表一处——白名单/权限组/协议行/
    分派四俱全（传扩展 manifest 的纯函数验证，不污染真实登记）。"""

    def test_new_tool_appears_in_all_derivations(self):
        wl = tool_registry.whitelist_names(_EXTENDED)
        self.assertIn("weather_probe", wl)
        self.assertEqual(len(wl), 19)                     # 18 + 1
        self.assertIn("weather_probe", tool_registry.level_set(3, _EXTENDED))
        self.assertIn("weather_probe", tool_registry.danger_set(_EXTENDED))
        self.assertIn("weather_probe", tool_registry.action_set(_EXTENDED))
        lines = tool_registry.prompt_tool_lines(_EXTENDED)
        self.assertEqual(len(lines), 19)
        self.assertTrue(lines[-1].startswith("19. weather_probe - 探测天气"))
        self.assertIn("weather_probe",
                      tool_registry.plugin_tool_names(_EXTENDED))

    def test_new_tool_dispatch_via_handler(self):
        result = tool_registry.dispatch_plugin_tool(
            "weather_probe", {"obj": {"k": 1}}, manifest=_EXTENDED)
        self.assertEqual(result, '{"k": 1}')

    def test_dispatch_broken_handler_returns_chinese_fail(self):
        broken = tool_registry.TOOL_MANIFEST + [
            {"name": "ghost_tool", "handler": "no_such_mod_xyz:fn",
             "in_protocol": False}]
        result = tool_registry.dispatch_plugin_tool(
            "ghost_tool", {}, manifest=broken)
        self.assertTrue(result.startswith("❌"))
        self.assertIn("处理器加载失败", result)

    def test_dispatch_exception_returns_chinese_fail(self):
        boom = tool_registry.TOOL_MANIFEST + [
            {"name": "boom_tool", "handler": "json:loads",
             "in_protocol": False}]   # loads() 必缺参抛 TypeError
        result = tool_registry.dispatch_plugin_tool(
            "boom_tool", {}, manifest=boom)
        self.assertTrue(result.startswith("❌"))
        self.assertIn("执行失败", result)

    def test_unregistered_name_rejected(self):
        self.assertTrue(tool_registry.dispatch_plugin_tool(
            "never_registered", {}, manifest=_EXTENDED).startswith("❌"))

    def test_real_manifest_handler_set_is_desktop_only(self):
        # DA1（2026-10-31）：现网 handler 通道=desktop_* 三件（动态分派），
        # 核心工具仍走 execute_tool 既有分支——本锚防"老工具被误改成动态分派"
        self.assertEqual(sorted(tool_registry.plugin_tool_names()),
                         ["desktop_list_skills", "desktop_list_windows",
                          "desktop_run_skill"])


if __name__ == "__main__":
    unittest.main()
