# -*- coding: utf-8 -*-
"""prompts 单元测试：12 项工具协议（第二阶段 §10 #5 新增 web_search、
§7 权限新表新增 system_manage）、"只输出一行 JSON"约束、点击优先级规则
（ui_tap_element 优先，失败才 vision_tap_element）、联网搜索使用规则、
权限门禁拒绝口径、工作区路径注入，且不含任何内网地址。
"""
import unittest

import prompts
from xiaoju3 import WORKSPACE

TOOLS = [
    "list_files", "read_file", "write_file",
    "get_ha_devices", "control_ha_device",
    "adb_screenshot", "adb_tap", "adb_swipe",
    "vision_tap_element", "ui_tap_element",
    "web_search", "system_manage",
]


class PromptsTests(unittest.TestCase):

    def setUp(self):
        self.prompt = prompts.SYSTEM_PROMPT
        self.content = self.prompt["content"]

    def test_system_prompt_structure(self):
        self.assertEqual(self.prompt["role"], "system")
        self.assertIsInstance(self.content, str)
        self.assertTrue(self.content.strip())

    def test_contains_all_12_tool_names(self):
        for name in TOOLS:
            self.assertIn(name, self.content, name)

    def test_one_line_json_constraint(self):
        self.assertIn("必须且只输出一行 JSON", self.content)
        # f-string 渲染后示例 JSON 为真实单行格式
        self.assertIn('{"tool": "list_files", "args": {}}', self.content)

    def test_json_examples_cover_key_tools(self):
        for name in ("control_ha_device", "adb_screenshot",
                     "ui_tap_element", "vision_tap_element", "adb_swipe"):
            self.assertIn(f'{{"tool": "{name}"', self.content, name)

    def test_ui_tap_priority_rule(self):
        self.assertIn("必须优先使用 `ui_tap_element`", self.content)
        self.assertIn("回退使用 `vision_tap_element`", self.content)

    def test_web_search_protocol_and_usage_rule(self):
        # web_search 工具协议（编号 11，含参数说明）
        self.assertIn("11. web_search", self.content)
        self.assertIn("query", self.content)
        # 何时使用联网搜索的协议说明（§10 #5：实时/知识库外内容先检索）
        self.assertIn("【联网搜索规则】", self.content)
        self.assertIn("必须先用 `web_search` 联网检索", self.content)
        self.assertIn("绝对禁止在没搜过的情况下凭空编造实时数据", self.content)

    def test_system_manage_protocol_with_lv4_gate_note(self):
        # §7 权限新表：第 12 项 system_manage（仅 Lv.4，双因子 + 二次确认）
        self.assertIn("12. system_manage", self.content)
        self.assertIn("action", self.content)
        self.assertIn("component", self.content)
        self.assertIn("Lv.4", self.content)

    def test_permission_denial_wording(self):
        # §7 权限拒绝口径：如实转告拒绝原因与升级指引，禁止重试/伪造成功
        self.assertIn("【权限与拒绝口径】", self.content)
        self.assertIn("Lv.2", self.content)
        self.assertIn("逐次动态密码", self.content)
        self.assertIn("绝对不要反复重试同一被拒操作", self.content)
        self.assertIn("绝对不要伪造执行成功的结果", self.content)

    def test_workspace_path_injected(self):
        self.assertIn(WORKSPACE, self.content)

    def test_persona_present(self):
        self.assertIn("小橘3号", self.content)

    def test_no_private_addresses_or_paths(self):
        # 禁止内网地址与参考仓库的私有部署路径混入
        self.assertNotIn("192.168.", self.content)
        self.assertNotIn("/home/orangepi", self.content)

    def test_web_content_summary_rule(self):
        # 网页总结场景禁止输出工具 JSON（防误触发工具链）
        self.assertIn("绝对禁止输出任何 JSON 或工具调用代码", self.content)


if __name__ == "__main__":
    unittest.main()
