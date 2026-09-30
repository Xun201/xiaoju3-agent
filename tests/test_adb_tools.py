# -*- coding: utf-8 -*-
"""adb_tools / android_ui_tools / vision_tools 单元测试：全离线。

subprocess 与网络全部 mock：ADB 三原语命令行组装、uiautomator XML 解析
（text 命中 / content-desc 命中 / 找不到 / 中心点计算）、视觉流程
（未配置提示串、坐标解析与换算、tap 调用）。
"""
import importlib.util
import os
import sys
import unittest
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_real_modules(*names):
    """发现 sys.modules 中同名 fake（无 __file__，由并行测试模块注入）时
    按真实路径重载，保证被测模块与 mock 绑定对象一致。"""
    for name in names:
        real_path = os.path.join(_ROOT, f"{name}.py")
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "__file__", None) and                 os.path.normcase(os.path.abspath(mod.__file__)) == os.path.normcase(real_path):
            continue
        spec = importlib.util.spec_from_file_location(name, real_path)
        real = importlib.util.module_from_spec(spec)
        sys.modules[name] = real
        spec.loader.exec_module(real)


_ensure_real_modules("adb_tools", "android_ui_tools", "vision_tools")

import adb_tools
import android_ui_tools
import vision_tools


# ---------------------------------------------------------------------------
# adb_tools：三原语的命令行组装
# ---------------------------------------------------------------------------

class AdbToolsTests(unittest.TestCase):
    def test_adb_screenshot_command(self):
        with mock.patch.object(adb_tools.subprocess, "run") as mrun:
            result = adb_tools.adb_screenshot()
        mrun.assert_called_once_with(
            f"adb exec-out screencap -p > {adb_tools.SCREENSHOT_PATH}",
            shell=True, check=True)
        self.assertEqual(result, f"✅ 手机屏幕截图已保存至: {adb_tools.SCREENSHOT_PATH}")

    def test_adb_screenshot_failure(self):
        import subprocess as sp
        with mock.patch.object(adb_tools.subprocess, "run",
                             side_effect=sp.CalledProcessError(1, "adb")):
            result = adb_tools.adb_screenshot()
        self.assertTrue(result.startswith("❌ ADB 截图失败: "))

    def test_adb_tap_command(self):
        with mock.patch.object(adb_tools.subprocess, "run") as mrun:
            result = adb_tools.adb_tap(100, 200)
        mrun.assert_called_once_with("adb shell input tap 100 200", shell=True, check=True)
        self.assertEqual(result, "✅ 已模拟点击坐标: (100, 200)")

    def test_adb_tap_failure(self):
        import subprocess as sp
        with mock.patch.object(adb_tools.subprocess, "run",
                             side_effect=sp.CalledProcessError(1, "adb")):
            result = adb_tools.adb_tap(1, 2)
        self.assertTrue(result.startswith("❌ ADB 点击失败: "))

    def test_adb_swipe_command_default_duration(self):
        with mock.patch.object(adb_tools.subprocess, "run") as mrun:
            result = adb_tools.adb_swipe(500, 1500, 500, 500)
        mrun.assert_called_once_with(
            "adb shell input swipe 500 1500 500 500 300", shell=True, check=True)
        self.assertEqual(result, "✅ 已模拟滑动: 从(500,1500)到(500,500)")

    def test_adb_swipe_command_custom_duration(self):
        with mock.patch.object(adb_tools.subprocess, "run") as mrun:
            adb_tools.adb_swipe(0, 0, 1080, 2400, 800)
        mrun.assert_called_once_with(
            "adb shell input swipe 0 0 1080 2400 800", shell=True, check=True)

    def test_adb_swipe_failure(self):
        import subprocess as sp
        with mock.patch.object(adb_tools.subprocess, "run",
                             side_effect=sp.CalledProcessError(1, "adb")):
            result = adb_tools.adb_swipe(1, 2, 3, 4)
        self.assertTrue(result.startswith("❌ ADB 滑动失败: "))


# ---------------------------------------------------------------------------
# android_ui_tools：uiautomator XML 解析
# ---------------------------------------------------------------------------

SAMPLE_UI_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" content-desc="" checkable="false" bounds="[0,0][1080,2400]">
    <node index="1" text="设置" content-desc="" bounds="[100,200][300,400]"/>
    <node index="2" text="" content-desc="返回" bounds="[0,100][100,200]"/>
    <node index="3" text="天气小组件" content-desc="" bounds="[400,400][600,600]"/>
    <node index="4" text="" content-desc="" bounds="[0,0][1080,100]">
      <node index="5" text="嵌套按钮" content-desc="" bounds="[10,20][110,120]"/>
    </node>
  </node>
</hierarchy>
"""


class UiXmlParsingTests(unittest.TestCase):
    """纯解析测试：不触碰 subprocess，直接喂样例 XML。"""

    def test_match_by_text(self):
        self.assertEqual(
            android_ui_tools.find_element_center(SAMPLE_UI_XML, "设置"), (200, 300))

    def test_match_by_content_desc(self):
        self.assertEqual(
            android_ui_tools.find_element_center(SAMPLE_UI_XML, "返回"), (50, 150))

    def test_match_in_nested_node(self):
        self.assertEqual(
            android_ui_tools.find_element_center(SAMPLE_UI_XML, "嵌套按钮"), (60, 70))

    def test_element_not_found(self):
        self.assertIsNone(
            android_ui_tools.find_element_center(SAMPLE_UI_XML, "不存在的按钮"))

    def test_exact_match_no_substring(self):
        # "天气小组件" 不应被 "天气" 子串命中（参考实现为精确匹配口径）
        self.assertIsNone(android_ui_tools.find_element_center(SAMPLE_UI_XML, "天气"))

    def test_center_calculation_fullscreen(self):
        xml = '<hierarchy><node text="全屏" bounds="[0,0][1080,2400]"/></hierarchy>'
        self.assertEqual(android_ui_tools.find_element_center(xml, "全屏"), (540, 1200))

    def test_empty_and_invalid_xml(self):
        self.assertIsNone(android_ui_tools.find_element_center("", "设置"))
        self.assertIsNone(android_ui_tools.find_element_center(None, "设置"))
        self.assertIsNone(android_ui_tools.find_element_center("<hierarchy><node", "设置"))

    def test_first_match_in_document_order_wins(self):
        xml = ('<hierarchy>'
               '<node text="设置" bounds="[0,0][10,10]"/>'
               '<node text="设置" bounds="[100,100][200,200]"/>'
               '</hierarchy>')
        self.assertEqual(android_ui_tools.find_element_center(xml, "设置"), (5, 5))

    def test_parse_bounds(self):
        self.assertEqual(android_ui_tools.parse_bounds("[100,200][300,400]"), (100, 200, 300, 400))
        self.assertEqual(android_ui_tools.parse_bounds("[-10,0][10,20]"), (-10, 0, 10, 20))
        self.assertIsNone(android_ui_tools.parse_bounds("[1,2]"))
        self.assertIsNone(android_ui_tools.parse_bounds(""))
        self.assertIsNone(android_ui_tools.parse_bounds(None))


class UiTapElementTests(unittest.TestCase):
    """ui_tap_element 集成路径：dump/pull 命令组装 + 定位 + adb_tap。"""

    def setUp(self):
        # 预置本地 dump 文件（subprocess 被 mock，dump/pull 不真跑）
        with open(android_ui_tools.LOCAL_DUMP_PATH, "w", encoding="utf-8") as f:
            f.write(SAMPLE_UI_XML)

    def tearDown(self):
        try:
            os.remove(android_ui_tools.LOCAL_DUMP_PATH)
        except OSError:
            pass

    def test_tap_found_element(self):
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (200, 300)")
        with mock.patch.object(android_ui_tools.subprocess, "run") as mrun, \
             mock.patch.object(android_ui_tools, "adb_tap", tap):
            result = android_ui_tools.ui_tap_element("设置")

        # 命令行组装：dump → pull
        self.assertEqual(mrun.call_count, 2)
        dump_cmd = mrun.call_args_list[0].args[0]
        pull_cmd = mrun.call_args_list[1].args[0]
        self.assertIn("adb shell uiautomator dump /sdcard/window_dump.xml", dump_cmd)
        self.assertTrue(pull_cmd.startswith(
            f"adb pull /sdcard/window_dump.xml {android_ui_tools.LOCAL_DUMP_PATH}"))

        # 命中元素 → bounds 中心点点击
        tap.assert_called_once_with(200, 300)
        self.assertEqual(result, "✅ 已模拟点击坐标: (200, 300)")

    def test_tap_element_not_found(self):
        tap = mock.MagicMock()
        with mock.patch.object(android_ui_tools.subprocess, "run"), \
             mock.patch.object(android_ui_tools, "adb_tap", tap):
            result = android_ui_tools.ui_tap_element("不存在的按钮")
        # 明确失败串（供模型回退 vision_tap_element）
        self.assertEqual(
            result,
            "❌ UI 层级中未找到【不存在的按钮】，请确认它目前在屏幕上可见，或者它没有文本/描述标签。")
        tap.assert_not_called()

    def test_tap_empty_xml(self):
        with open(android_ui_tools.LOCAL_DUMP_PATH, "w", encoding="utf-8") as f:
            f.write("")
        with mock.patch.object(android_ui_tools.subprocess, "run"):
            result = android_ui_tools.ui_tap_element("设置")
        self.assertEqual(result, "❌ UI 解析失败：未获取到 XML 数据，请检查手机屏幕是否亮起。")

    def test_tap_subprocess_exception_wrapped(self):
        with mock.patch.object(android_ui_tools.subprocess, "run",
                             side_effect=Exception("adb not found")):
            result = android_ui_tools.ui_tap_element("设置")
        self.assertTrue(result.startswith("❌ UI 层级解析失败: "))


# ---------------------------------------------------------------------------
# vision_tools：云端视觉模型点击
# ---------------------------------------------------------------------------

def _png_bytes(width, height):
    """构造带 IHDR 头的 PNG 文件头（仅前 24 字节有效，供 _png_size 解析）。"""
    return (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
            + width.to_bytes(4, "big") + height.to_bytes(4, "big")
            + b"\x08\x06\x00\x00\x00" + b"\x00" * 8)


class VisionToolsTests(unittest.TestCase):
    """vision_tap_element：未配置提示串、坐标解析换算、tap 调用。"""

    def setUp(self):
        self._old_model = vision_tools.VISION_MODEL
        self._old_key = vision_tools.VISION_KEY
        vision_tools.VISION_MODEL = "qwen-vl-test"
        vision_tools.VISION_KEY = "test-vision-key"
        self._screenshot_exists = False

    def tearDown(self):
        vision_tools.VISION_MODEL = self._old_model
        vision_tools.VISION_KEY = self._old_key
        try:
            os.remove(vision_tools.SCREENSHOT_PATH)
        except OSError:
            pass

    def _write_screenshot(self, width=540, height=1200):
        with open(vision_tools.SCREENSHOT_PATH, "wb") as f:
            f.write(_png_bytes(width, height))

    def _mock_post(self, content):
        resp = mock.MagicMock()
        resp.json.return_value = {
            "choices": [{"message": {"content": content}}]}
        return resp

    def test_unconfigured_key_hint(self):
        vision_tools.VISION_KEY = ""
        self.assertEqual(
            vision_tools.vision_tap_element("设置"),
            "❌ 未配置视觉 API Key，无法使用视觉点击功能。")

    def test_unconfigured_model_hint(self):
        vision_tools.VISION_MODEL = ""
        self.assertEqual(
            vision_tools.vision_tap_element("设置"),
            "❌ 未配置视觉模型 VISION_MODEL，无法使用视觉点击功能。")

    def test_screenshot_failure_propagates(self):
        with mock.patch.object(vision_tools, "adb_screenshot",
                               return_value="❌ ADB 截图失败: device offline"):
            result = vision_tools.vision_tap_element("设置")
        self.assertEqual(result, "❌ ADB 截图失败: device offline")

    def test_missing_screenshot_file(self):
        with mock.patch.object(vision_tools, "adb_screenshot",
                               return_value="✅ 截图完成"):
            result = vision_tools.vision_tap_element("设置")
        self.assertEqual(result, "❌ 截图文件不存在，请检查 ADB 连接。")

    def test_full_flow_coordinate_conversion_and_tap(self):
        # 截图 540 宽 / 屏幕 1080 宽 → 缩放比 0.5
        self._write_screenshot(width=540, height=1200)
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (400, 600)")
        wm_size = mock.MagicMock(stdout="Physical size: 1080x2400")

        content = '好的，元素位置是 {"x1": 100, "y1": 200, "x2": 300, "y2": 400} 请查收'
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅ 截图完成"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run", return_value=wm_size), \
             mock.patch.object(vision_tools.requests, "post",
                             return_value=self._mock_post(content)) as mpost:
            result = vision_tools.vision_tap_element("设置")

        # 框中心 (200,300) ÷ 0.5 → 真实坐标 (400,600)，无裁剪偏移
        tap.assert_called_once_with(400, 600)
        self.assertEqual(result, "✅ 已模拟点击坐标: (400, 600)")

        # 请求组装：OpenAI 兼容 chat/completions + Bearer + base64 PNG + 模型名
        kwargs = mpost.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"],
                         f"Bearer {vision_tools.VISION_KEY}")
        self.assertEqual(kwargs["json"]["model"], vision_tools.VISION_MODEL)
        user_content = kwargs["json"]["messages"][0]["content"]
        self.assertIn("【设置】", user_content[0]["text"])
        image_url = user_content[1]["image_url"]["url"]
        self.assertTrue(image_url.startswith("data:image/png;base64,"))

    def test_scale_one_when_png_header_missing(self):
        # 非 PNG 头（解析失败）→ 缩放比回退 1.0
        with open(vision_tools.SCREENSHOT_PATH, "wb") as f:
            f.write(b"\x00\x01\x02not-a-png")
        tap = mock.MagicMock(return_value="ok")
        content = '{"x1": 100, "y1": 200, "x2": 300, "y2": 400}'
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")), \
             mock.patch.object(vision_tools.requests, "post",
                               return_value=self._mock_post(content)):
            vision_tools.vision_tap_element("设置")
        tap.assert_called_once_with(200, 300)

    def test_model_response_without_choices(self):
        self._write_screenshot()
        resp = mock.MagicMock()
        resp.json.return_value = {"error": {"message": "bad request"}}
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")), \
             mock.patch.object(vision_tools.requests, "post", return_value=resp):
            result = vision_tools.vision_tap_element("设置")
        self.assertTrue(result.startswith("❌ 视觉模型返回异常: "))

    def test_model_response_without_coordinates(self):
        self._write_screenshot()
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")), \
             mock.patch.object(vision_tools.requests, "post",
                             return_value=self._mock_post("抱歉，我找不到这个图标。")):
            result = vision_tools.vision_tap_element("设置")
        self.assertEqual(
            result, "❌ 视觉模型未能识别出坐标。回复内容：抱歉，我找不到这个图标。")

    def test_request_exception_wrapped(self):
        self._write_screenshot()
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")), \
             mock.patch.object(vision_tools.requests, "post",
                             side_effect=ConnectionError("network down")):
            result = vision_tools.vision_tap_element("设置")
        self.assertTrue(result.startswith("❌ 视觉模型调用失败: "))

    def test_get_screen_size_parses_and_falls_back(self):
        with mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")):
            self.assertEqual(vision_tools.get_screen_size(), (1080, 2400))
        with mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="error")):
            self.assertEqual(vision_tools.get_screen_size(), (1080, 2400))
        with mock.patch.object(vision_tools.subprocess, "run",
                               side_effect=Exception("no adb")):
            self.assertEqual(vision_tools.get_screen_size(), (1080, 2400))


if __name__ == "__main__":
    unittest.main()
