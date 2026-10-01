# -*- coding: utf-8 -*-
"""adb_tools / android_ui_tools / vision_tools 单元测试：全离线。

subprocess 与网络全部 mock：ADB 三原语命令行组装、uiautomator XML 解析
（text 命中 / content-desc 命中 / 找不到 / 中心点计算）、exec-out 单次
往返导出（噪声剥离 / 失败回退旧 dump+pull 两步法）、视觉流程（未配置
提示串、坐标解析与换算、tap 调用）、视觉端点动态解析（旧环境变量
VISION_URL 向后兼容覆盖 / 新配置 VISION_API_URL 拼 /chat/completions，
防双段丢段）与请求失败诊断（403/404 鉴权与模型错误的中文诊断块与
错误串指引、密钥脱敏；超时/连接重置等网络类失败默认不重试，控制台
仅一行简短提示、返回简短文案，重试骨架在调大 MAX_RETRIES 后可用；
404 模型不存在自动回退备用模型链——中途切换成功 / 全部耗尽诊断 /
403 不回退；中文屏幕友好提示词结构与全 -1 未找到约定；多格式坐标
解析容错 _extract_click_point（2026-10-01 用户指令：实测返回
{"x1": [69, 514, 312, 547]} 值为数组也能解析，另兼容 bounds 数组 /
直接 x+y / 标准框，畸形输入返回"未能识别"不崩溃）；解析前清洗链
_clean_json_candidates（markdown ```json 围栏剥离 / 纯数字引号串剥
引号 / 缺 "y" 键补键，针对用户实测 ```json 包裹的 {"x": 246, "531"}）
与解析失败时控制台两行 ⚠️ 诊断（原始返回内容 / 清洗后的 JSON 候选，
截断 300）；提示词禁代码块包裹与数字不加引号两条新约束；模型名预检
（VISION_MODEL 不含 vl 打一行 ⚠️ 警告但不阻断调用，含 vl/大小写混写
不警告）与全 -1 未找到串附加兜底排查引导（2026-10-01 用户指令）；
.env.example 的 VISION_MODEL 默认值 qwen-vl-max-latest 与"带 VL"
注释存在；缩放换算可见化（📏 单行全量日志四要素：模型原始坐标 /
截图分辨率 / 手机实际分辨率 / 换算后坐标；_png_size 解析失败按 1:1
换算的 ⚠️ 警告与"未知(按1:1)"标注；get_screen_size 走缺省 1080x2400
兜底的 ⚠️ 警告）；提示词末尾强化句（不包含 markdown 代码块 /
解释性文字，置于最末尾）；提示词严格匹配强化（严格匹配屏幕中文字符 /
定位到文字本身而非图标或搜索框 / 找不到务必全 -1 不瞎猜，紧随"忽略
状态栏"规则，2026-10-01 用户指令）与换算后坐标顶部 15% 区域误定位
⚠️ 警告（real_y < 0.15 × screen_height 时仅警告仍点击，中下部不
警告）；ADB 点击间隔与指令容错（2026-10-01 用户指令，组 D1）——
点击前 0.5 秒延迟（📏 日志后、adb_tap 前 sleep(0.5)）、adb_tap 返回
失败语义串（❌ 开头/含"失败"）→ ⚠️ USB 调试权限警告进终端且警告
语义并入返回串、首次明确失败不二次确认，二次确认点击
VISION_CONFIRM_RETAP（默认开，env 置 0 可关）——首次成功后 sleep 1
秒同坐标再点一次，tap 两次坐标一致、sleep 序列 [0.5, 1]、返回串注明
"已执行二次确认点击"；既有链路用例的 tap 断言已按二次确认同步为
两次。任务 2/3（2026-10-01 用户指令，组 E1）：提示词末尾观察-描述
前置强化（先仔细观察屏幕 / 先描述你看到了什么 / 找不到直接返回 -1
不要瞎猜，保留"JSON 本体只含坐标"口径）；顶部疑似区分级警告与
偏移策略修正（同日用户指令修正：<15% 屏高 → 强警告"极易误点到
账号或搜索框" + 15% 线提示 + 2% 屏高向下偏移；15%~40% → 仅
"请确认"警告、不偏移、保留模型原始坐标——修复用户找"蓝牙"
y=847/2712=31.2% 被强推到 y=982 误点"我的设备"的漂移；≥40% →
零警告零偏移；VISION_TOP_OFFSET 可关，关=连 15% 内也不偏移）；
点击前后变化检测（前后 MD5 一致 → 控制台一行简短原因说明 +
返回串整体替换为明确失败口径"❌ 视觉模型未点中目标，请尝试手动点击
或换个清晰的图标"（F3-2：替换原"（⚠️ 页面未发生变化，已尝试点击
2 次）"含糊附加段，返回串精确等于该 ❌ 文案、tap 仍恰两次无额外
重试点击），不一致 → "✅ 页面已变化，点击已生效"且返回串不含该
❌ 文案，MD5 失败静默降级不影响主流程，VISION_CONFIRM_RETAP=0 跳过
检测）；顶部疑似区误识别降级告知进返回串（F3-1：<15% 或 15%~40%
屏高两级疑似区 → 返回串追加"⚠️ 视觉模型可能识别到了顶部区域（如
账号/搜索框），建议手动确认。"，≥40% 不追加，单次点击（无二次确认）
路径同样追加）与 android_ui_tools.file_md5（stdlib hashlib，失败
返回 None）。
"""
import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

import requests

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
import openai
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


class StripXmlNoiseTests(unittest.TestCase):
    """exec-out 输出噪声剥离：首个 '<?xml' / '<?' 之前的内容一律截断。"""

    def test_strip_log_line_before_xml_declaration(self):
        # 典型噪声：设备把 "UI hierchary dumped to: ..." 一并打到 stdout
        noisy = ("UI hierchary dumped to: [/dev/tty]\r\n"
                 '<?xml version=\'1.0\' encoding="UTF-8"?><hierarchy/>')
        self.assertEqual(android_ui_tools.strip_xml_noise(noisy),
                         '<?xml version=\'1.0\' encoding="UTF-8"?><hierarchy/>')

    def test_strip_generic_declaration_marker(self):
        # 无 '<?xml' 完整声明时回退按 '<?' 定位（声明被设备截断的情形）
        noisy = "UI hierchary dumped to: [/dev/tty]\r\n<?"
        self.assertEqual(android_ui_tools.strip_xml_noise(noisy), "<?")

    def test_strip_bom_prefix_before_declaration(self):
        # 编码前缀（如误解码的 UTF-8 BOM）夹在声明之前 → 截断至 '<?xml'
        noisy = "\xef\xbb\xbf<?xml version='1.0'?><hierarchy/>"
        self.assertEqual(android_ui_tools.strip_xml_noise(noisy),
                         "<?xml version='1.0'?><hierarchy/>")

    def test_clean_output_unchanged(self):
        self.assertEqual(android_ui_tools.strip_xml_noise(SAMPLE_UI_XML), SAMPLE_UI_XML)

    def test_no_declaration_unchanged(self):
        # 部分设备直接吐 <hierarchy> 开头（无声明）→ 不截断
        xml = '<hierarchy><node text="A" bounds="[0,0][1,1]"/></hierarchy>'
        self.assertEqual(android_ui_tools.strip_xml_noise(xml), xml)

    def test_empty_and_none(self):
        self.assertEqual(android_ui_tools.strip_xml_noise(""), "")
        self.assertIsNone(android_ui_tools.strip_xml_noise(None))


class FileMd5Tests(unittest.TestCase):
    """android_ui_tools.file_md5：stdlib hashlib 计算文件 MD5（vision
    变化检测复用）；文件不存在/不可读等失败返回 None、不抛异常。"""

    def test_md5_matches_hashlib(self):
        import hashlib
        data = "hello 小橘3号".encode("utf-8")
        fd, path = tempfile.mkstemp(prefix="xiaoju3_md5_case_")
        os.close(fd)

        def _cleanup():
            try:
                os.remove(path)
            except OSError:
                pass
        self.addCleanup(_cleanup)
        with open(path, "wb") as f:
            f.write(data)
        self.assertEqual(android_ui_tools.file_md5(path),
                         hashlib.md5(data).hexdigest())

    def test_missing_file_returns_none(self):
        self.assertIsNone(android_ui_tools.file_md5(
            os.path.join(_ROOT, "no_such_file_for_md5_test.png")))

    def test_directory_returns_none(self):
        # 路径是目录：open 抛异常 → 捕获返回 None
        self.assertIsNone(android_ui_tools.file_md5(_ROOT))


class UiTapElementTests(unittest.TestCase):
    """ui_tap_element 集成路径：exec-out 单次往返（优先）+ 失败回退旧
    dump/pull 两步法 + 定位 + adb_tap。"""

    def setUp(self):
        # 预置本地 dump 文件：回退两步法时（subprocess 被 mock）直接读取
        with open(android_ui_tools.LOCAL_DUMP_PATH, "w", encoding="utf-8") as f:
            f.write(SAMPLE_UI_XML)

    def tearDown(self):
        try:
            os.remove(android_ui_tools.LOCAL_DUMP_PATH)
        except OSError:
            pass

    @staticmethod
    def _exec_out_result(stdout_bytes):
        """构造 exec-out 成功返回（stdout 为字节流）。"""
        res = mock.MagicMock()
        res.stdout = stdout_bytes
        return res

    def test_tap_found_element_exec_out_single_roundtrip(self):
        # stdout 带噪声行，验证剥离后仍能定位命中
        noisy = ("UI hierchary dumped to: [/dev/tty]\r\n".encode("utf-8")
                 + SAMPLE_UI_XML.encode("utf-8"))
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (200, 300)")
        with mock.patch.object(android_ui_tools.subprocess, "run",
                               return_value=self._exec_out_result(noisy)) as mrun, \
             mock.patch.object(android_ui_tools, "adb_tap", tap):
            result = android_ui_tools.ui_tap_element("设置")

        # 单次往返：仅一条 exec-out 命令，不再 dump+pull 两次通信
        mrun.assert_called_once_with(
            android_ui_tools.EXEC_OUT_DUMP_CMD,
            shell=True, check=True, capture_output=True)

        # 命中元素 → bounds 中心点点击
        tap.assert_called_once_with(200, 300)
        self.assertEqual(result, "✅ 已模拟点击坐标: (200, 300)")

    def test_exec_out_failure_falls_back_to_dump_pull(self):
        # exec-out 返回码非 0 → 自动回退旧版 dump+pull 两步法
        import subprocess as sp
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (200, 300)")
        with mock.patch.object(android_ui_tools.subprocess, "run",
                               side_effect=[sp.CalledProcessError(1, "adb"),
                                            mock.MagicMock(), mock.MagicMock()]) as mrun, \
             mock.patch.object(android_ui_tools, "adb_tap", tap):
            result = android_ui_tools.ui_tap_element("设置")

        # 首条 exec-out 失败 → 第 2/3 条为旧 dump 与 pull 命令
        self.assertEqual(mrun.call_count, 3)
        self.assertEqual(mrun.call_args_list[0].args[0],
                         android_ui_tools.EXEC_OUT_DUMP_CMD)
        self.assertIn("adb shell uiautomator dump /sdcard/window_dump.xml",
                      mrun.call_args_list[1].args[0])
        self.assertTrue(mrun.call_args_list[2].args[0].startswith(
            f"adb pull /sdcard/window_dump.xml {android_ui_tools.LOCAL_DUMP_PATH}"))

        # 回退后功能不退化：仍能定位并点击
        tap.assert_called_once_with(200, 300)
        self.assertEqual(result, "✅ 已模拟点击坐标: (200, 300)")

    def test_exec_out_without_xml_falls_back_to_dump_pull(self):
        # exec-out 返回 0 但 stdout 无 XML（设备报错串）→ 同样回退两步法
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (200, 300)")
        no_xml = self._exec_out_result(b"ERROR: could not get idle state.")
        with mock.patch.object(android_ui_tools.subprocess, "run",
                               side_effect=[no_xml, mock.MagicMock(),
                                            mock.MagicMock()]) as mrun, \
             mock.patch.object(android_ui_tools, "adb_tap", tap):
            result = android_ui_tools.ui_tap_element("设置")

        self.assertEqual(mrun.call_count, 3)
        self.assertIn("adb shell uiautomator dump", mrun.call_args_list[1].args[0])
        self.assertIn("adb pull", mrun.call_args_list[2].args[0])
        tap.assert_called_once_with(200, 300)
        self.assertEqual(result, "✅ 已模拟点击坐标: (200, 300)")

    def test_tap_element_not_found(self):
        tap = mock.MagicMock()
        with mock.patch.object(android_ui_tools.subprocess, "run",
                               return_value=self._exec_out_result(
                                   SAMPLE_UI_XML.encode("utf-8"))), \
             mock.patch.object(android_ui_tools, "adb_tap", tap):
            result = android_ui_tools.ui_tap_element("不存在的按钮")
        # 明确失败串（供模型回退 vision_tap_element）
        self.assertEqual(
            result,
            "❌ UI 层级中未找到【不存在的按钮】，请确认它目前在屏幕上可见，或者它没有文本/描述标签。")
        tap.assert_not_called()

    def test_tap_empty_xml(self):
        # exec-out 空输出 → 回退两步法 → 本地 dump 文件也为空 → 明确失败串
        with open(android_ui_tools.LOCAL_DUMP_PATH, "w", encoding="utf-8") as f:
            f.write("")
        with mock.patch.object(android_ui_tools.subprocess, "run",
                               side_effect=[self._exec_out_result(b""),
                                            mock.MagicMock(), mock.MagicMock()]):
            result = android_ui_tools.ui_tap_element("设置")
        self.assertEqual(result, "❌ UI 解析失败：未获取到 XML 数据，请检查手机屏幕是否亮起。")

    def test_tap_subprocess_exception_wrapped(self):
        # exec-out 与回退两步法双双抛异常 → 上层统一包装失败串
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


class ExtractClickPointTests(unittest.TestCase):
    """_extract_click_point 纯函数：多格式坐标解析容错（2026-10-01
    用户指令）。背景：视觉模型实测返回 {"x1": [69, 514, 312, 547]}
    （值是数组）导致旧正则解析报"未能识别出坐标"。"""

    def test_user_reported_array_x1_format(self):
        # 实测格式：值为数组 → 按用户口径取前两个元素作为 x 和 y
        self.assertEqual(
            vision_tools._extract_click_point('{"x1": [69, 514, 312, 547]}'),
            (69, 514))

    def test_bounds_array_center(self):
        self.assertEqual(
            vision_tools._extract_click_point(
                '{"bounds": [100, 200, 300, 400]}'),
            (200, 300))

    def test_direct_xy(self):
        self.assertEqual(
            vision_tools._extract_click_point('{"x": 150, "y": 250}'),
            (150, 250))

    def test_standard_box_center(self):
        # 标准框（既有行为保持）：中心点
        self.assertEqual(
            vision_tools._extract_click_point(
                '{"x1": 100, "y1": 200, "x2": 300, "y2": 400}'),
            (200, 300))

    def test_priority_order_bounds_over_xy_over_box(self):
        # 优先级：bounds 数组 > x1 数组 > 直接 x/y > 标准框
        self.assertEqual(
            vision_tools._extract_click_point(
                '{"bounds": [100, 200, 300, 400], "x": 999, "y": 999}'),
            (200, 300))
        self.assertEqual(
            vision_tools._extract_click_point(
                '{"x1": [69, 514, 312, 547], "x": 1, "y": 2}'),
            (69, 514))
        self.assertEqual(
            vision_tools._extract_click_point(
                '{"x": 1, "y": 2, "x1": 10, "y1": 20, "x2": 30, "y2": 40}'),
            (1, 2))

    def test_numeric_string_and_float_tolerated(self):
        # 数值容错：数字字符串与 float 均可
        self.assertEqual(
            vision_tools._extract_click_point('{"x": "150", "y": "250"}'),
            (150, 250))
        self.assertEqual(
            vision_tools._extract_click_point('{"x": 12.5, "y": 24.5}'),
            (12.5, 24.5))

    def test_not_found_signals_parse_to_minus_one(self):
        # 各格式的全 -1 均解析为 (-1, -1)，由调用方统一识别为"未找到"
        self.assertEqual(
            vision_tools._extract_click_point('{"x": -1, "y": -1}'),
            (-1, -1))
        self.assertEqual(
            vision_tools._extract_click_point(
                '{"x1": -1, "y1": -1, "x2": -1, "y2": -1}'),
            (-1, -1))

    def test_prose_wrapped_json(self):
        self.assertEqual(
            vision_tools._extract_click_point(
                '好的，要点击的坐标是 {"x": 150, "y": 250}，请查收。'),
            (150, 250))

    def test_user_reported_json_fence_with_missing_y_key(self):
        # 用户实测原串（2026-10-01）：```json 包裹 + {"x": 246, "531"}
        # 缺 "y" 键且数字带引号 → 围栏剥离 + 剥引号 + 补键后解析 (246, 531)
        self.assertEqual(
            vision_tools._extract_click_point(
                '```json\n{"x": 246, "531"}\n```'),
            (246, 531))
        # 行内围栏（首尾 ```json / ```）同样剥离
        self.assertEqual(
            vision_tools._extract_click_point(
                '看这里 ```json {"x": 1, "531"} ``` 完毕'),
            (1, 531))
        # 无围栏的裸数字缺 y 键形态（{"x": 246, 531}）同样修复
        self.assertEqual(
            vision_tools._extract_click_point('{"x": 246, 531}'),
            (246, 531))
        # 引号数字 + 缺 y 键：引号形态先剥引号再补键
        self.assertEqual(
            vision_tools._extract_click_point('{"x": "246", "531"}'),
            (246, 531))

    def test_clean_json_candidates_shared_by_parser_and_diagnostics(self):
        # 清洗函数（解析与诊断共用）：合法片段原样保留、畸形片段修复、
        # 修复无效保持原貌、空/非 str/无花括号返回空列表
        self.assertEqual(
            vision_tools._clean_json_candidates(
                '```json\n{"x": 246, "531"}\n```'),
            ['{"x": 246, "y": 531}'])
        self.assertEqual(
            vision_tools._clean_json_candidates('{"x": 150, "y": 250}'),
            ['{"x": 150, "y": 250}'])
        self.assertEqual(
            vision_tools._clean_json_candidates('{"x1": oops}'),
            ['{"x1": oops}'])
        self.assertEqual(vision_tools._clean_json_candidates(''), [])
        self.assertEqual(vision_tools._clean_json_candidates(None), [])
        self.assertEqual(
            vision_tools._clean_json_candidates('抱歉，找不到。'), [])

    def test_quoted_non_numeric_string_untouched(self):
        # 剥引号只针对纯数字引号串：含其他字符的字符串不碰（"12a" 原样
        # 保留 → x 非法 → 整体仍解析失败返回 None）
        self.assertIsNone(
            vision_tools._extract_click_point('{"x": "12a", "531"}'))

    def test_malformed_inputs_return_none(self):
        # 数组元素不足 / 非数字 / 空 JSON / 畸形 JSON / 无 JSON → None 不崩溃
        self.assertIsNone(
            vision_tools._extract_click_point('{"x1": [69]}'))   # 仅 1 个元素
        self.assertIsNone(
            vision_tools._extract_click_point('{"x1": []}'))
        self.assertIsNone(
            vision_tools._extract_click_point('{"x1": ["a", "b"]}'))
        self.assertIsNone(
            vision_tools._extract_click_point('{"x": "abc", "y": 1}'))
        self.assertIsNone(vision_tools._extract_click_point('{}'))  # 空 JSON
        self.assertIsNone(
            vision_tools._extract_click_point('{"x1": 100, "y1": 200'))  # 截断
        self.assertIsNone(
            vision_tools._extract_click_point('{"x1": oops}'))  # 非法 JSON
        self.assertIsNone(
            vision_tools._extract_click_point('抱歉，我找不到这个图标。'))
        self.assertIsNone(vision_tools._extract_click_point(''))
        self.assertIsNone(vision_tools._extract_click_point(None))


class VisionToolsTests(unittest.TestCase):
    """vision_tap_element：未配置提示串、坐标解析换算（多格式容错：
    标准框 / bounds 数组 / 实测 x1 数组值 / 直接 x+y）、tap 调用、
    SDK 快速失败（默认不重试）、403 诊断与 404 备用模型自动回退链
    （诊断块只进控制台、返回串极简不带指引，2026-09-30 用户指令）、
    中文屏幕友好提示词结构与全 -1 未找到约定（含附加兜底排查引导）、
    模型名预检警告（不含 vl 打一行 ⚠️ 但不阻断）、缩放换算可见化
    （📏 单行全量日志 / _png_size 失败警告 / wm size 兜底警告）、
    提示词严格匹配强化（严格匹配中文字符 / 定位文字本身而非图标或
    搜索框 / 找不到务必全 -1 不瞎猜）与顶部 15% 区域误定位 ⚠️ 警告
    （仅警告仍点击，中下部不警告，2026-10-01 用户指令）；ADB 点击间隔
    与指令容错（组 D1，2026-10-01 用户指令）：点击前 0.5 秒延迟 /
    adb_tap 失败语义 ⚠️ 警告（打印 + 并入返回串，明确失败不二次确认）/
    二次确认点击 VISION_CONFIRM_RETAP（默认开，env 置 0 可关，tap 两次
    同坐标 + sleep 序列 [0.5, 1] + 返回串注明）；顶部疑似区分级警告与
    偏移策略修正（2026-10-01 用户指令修正——<15% 屏高：强警告"极易误点
    到账号或搜索框" + 15% 线提示 + 2% 屏高向下偏移；15%~40%：仅"请
    确认"警告、不偏移、保留模型原始坐标（修复"蓝牙"31.2% 被强推误点
    "我的设备"）；≥40%：零警告零偏移；VISION_TOP_OFFSET 可关）、顶部
    疑似区误识别降级告知进返回串（F3-1：两级疑似区 → 返回串追加
    "建议手动确认"文案，≥40% 不追加）与点击前后变化检测（F3-2：MD5
    一致 → 返回串精确替换为 ❌ 未点中文案、tap 恰两次无额外重试 /
    不一致打印已变化且返回串不含 ❌ 文案 / 失败静默降级 / 无二次点击
    跳过）。"""

    def setUp(self):
        self._old_model = vision_tools.VISION_MODEL
        self._old_key = vision_tools.VISION_KEY
        self._old_api_url = vision_tools.VISION_API_URL
        # 二次确认开关快照并强制开启：保证本类用例确定性（宿主机 env
        # 置 0 时不影响断言口径），tearDown 还原
        self._old_confirm_retap = vision_tools.VISION_CONFIRM_RETAP
        vision_tools.VISION_CONFIRM_RETAP = True
        # 顶部疑似区偏移开关快照并强制开启：保证偏移坐标断言确定性
        self._old_top_offset = vision_tools.VISION_TOP_OFFSET
        vision_tools.VISION_TOP_OFFSET = True
        vision_tools.VISION_MODEL = "qwen-vl-test"
        vision_tools.VISION_KEY = "test-vision-key"
        # 统一 patch 新配置 base（与生产形态一致：已含 /compatible-mode/v1）
        vision_tools.VISION_API_URL = "https://vision.test/compatible-mode/v1"
        # 环境变量快照：清除宿主机旧 VISION_URL，防止污染端点解析
        self._env_patcher = mock.patch.dict(os.environ)
        self._env_patcher.start()
        os.environ.pop("VISION_URL", None)
        # 重试退避不真等：patch 掉 time.sleep 并记录调用序列
        self._sleep_patch = mock.patch.object(vision_tools.time, "sleep")
        self._sleep = self._sleep_patch.start()   # start() 返回 mock 本体
        self._screenshot_exists = False

    def tearDown(self):
        self._sleep_patch.stop()
        self._env_patcher.stop()
        vision_tools.VISION_MODEL = self._old_model
        vision_tools.VISION_KEY = self._old_key
        vision_tools.VISION_API_URL = self._old_api_url
        vision_tools.VISION_CONFIRM_RETAP = self._old_confirm_retap
        vision_tools.VISION_TOP_OFFSET = self._old_top_offset
        try:
            os.remove(vision_tools.SCREENSHOT_PATH)
        except OSError:
            pass

    def _write_screenshot(self, width=540, height=1200):
        with open(vision_tools.SCREENSHOT_PATH, "wb") as f:
            f.write(_png_bytes(width, height))

    def _patch_client(self, content=None, side_effect=None):
        """构造假 OpenAI SDK：_OpenAIClient(...) 返回 fake 客户端，
        chat.completions.create 按需返回 content 或抛 side_effect 序列。
        返回 (create 的 mock, 客户端类的 mock) 供断言。"""
        fake_client = mock.MagicMock()
        create = fake_client.chat.completions.create
        if side_effect is not None:
            create.side_effect = side_effect
        else:
            resp = mock.MagicMock()
            resp.choices = [mock.MagicMock()]
            resp.choices[0].message.content = content
            create.return_value = resp
        cls_patch = mock.patch.object(vision_tools, "_OpenAIClient",
                                      return_value=fake_client)
        cls_mock = cls_patch.start()   # start() 返回替换用的 mock 本体
        self.addCleanup(cls_mock.stop)
        return create, cls_mock

    def _assert_tapped_twice_same_point(self, tap, x, y):
        """二次确认点击生效时的统一断言：tap 恰好两次且坐标完全一致。"""
        self.assertEqual(tap.call_count, 2)
        self.assertEqual([c.args for c in tap.call_args_list],
                         [(x, y), (x, y)])

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

    def test_non_vl_model_name_warns_but_proceeds(self):
        # 模型名预检（2026-10-01 用户指令）：纯文本模型名（不含 vl）填入
        # VISION_MODEL → 请求前打印一行 ⚠️ 警告；只警告不阻断，调用照常
        # 走完（背景：qwen3.5-122b-a10b 误填导致一直"未找到"）
        self._write_screenshot(width=1080, height=1200)
        # (150, 250) 落在 15% 线内（< 360）→ 强警告 + 2% 屏高（48px）
        # 下移 → (150, 298)
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (150, 298)")
        create, _cls = self._patch_client(content='{"x": 150, "y": 250}')
        buf = io.StringIO()
        vision_tools.VISION_MODEL = "qwen3.5-122b-a10b"
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("设置")
        out = buf.getvalue()
        # 警告恰好一行进控制台，含推荐模型名
        self.assertEqual(out.count("⚠️ 警告：当前模型可能不支持视觉"), 1)
        self.assertIn("推荐使用 qwen-vl-max-latest 或 qwen-vl-plus", out)
        # 不阻断：请求仍按配置模型发出并完成整个点击流程
        self.assertEqual(create.call_count, 1)
        self.assertEqual(create.call_args.kwargs["model"],
                         "qwen3.5-122b-a10b")
        # 二次确认点击（组 D1）：tap 两次同坐标；变化检测（任务 3 后半）
        # MD5 一致（页面未变化）→ F3-2 新口径：返回串整体替换为明确
        # 失败 ❌ 文案（替换原含糊附加段）
        self._assert_tapped_twice_same_point(tap, 150, 298)
        self.assertEqual(result, vision_tools.VISION_PAGE_UNCHANGED_FAIL)

    def test_vl_model_name_no_warning(self):
        # 名字含 vl（大小写不敏感）不触发预检警告
        self._write_screenshot()
        self._patch_client(content='{"x1": 0, "y1": 0, "x2": 10, "y2": 10}')
        for model in ("qwen-vl-test", "Qwen-VL-Plus"):
            vision_tools.VISION_MODEL = model
            buf = io.StringIO()
            with mock.patch.object(vision_tools, "adb_screenshot",
                                   return_value="✅"), \
                 mock.patch.object(vision_tools, "adb_tap",
                                   mock.MagicMock()), \
                 mock.patch.object(vision_tools.subprocess, "run",
                                   return_value=mock.MagicMock(
                                       stdout="Physical size: 1080x2400")), \
                 contextlib.redirect_stdout(buf):
                vision_tools.vision_tap_element("设置")
            self.assertNotIn("⚠️ 警告：当前模型可能不支持视觉",
                             buf.getvalue())

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
        # (400, 600) 落在 15%~40% 区间（360 ≤ 600 < 960）→ 仅"请确认"
        # 警告、不偏移，保留模型原始坐标执行
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (400, 600)")
        wm_size = mock.MagicMock(stdout="Physical size: 1080x2400")

        content = '好的，元素位置是 {"x1": 100, "y1": 200, "x2": 300, "y2": 400} 请查收'
        create, cls_mock = self._patch_client(content=content)
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅ 截图完成"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run", return_value=wm_size):
            result = vision_tools.vision_tap_element("设置")

        # 框中心 (200,300) ÷ 0.5 → 真实坐标 (400,600)，无裁剪偏移；
        # (400,600) 在 15%~40% 区间 → 不偏移、tap 原坐标；
        # 二次确认点击（组 D1）：tap 两次同坐标；页面未变化 → F3-2 新
        # 口径：返回串整体替换为明确失败 ❌ 文案
        self._assert_tapped_twice_same_point(tap, 400, 600)
        self.assertEqual(result, vision_tools.VISION_PAGE_UNCHANGED_FAIL)

        # SDK 客户端：base_url 不含 /chat/completions（客户端自动追加）、
        # api_key 与 5 秒快速超时正确传入
        cls_mock.assert_called_once_with(
            api_key="test-vision-key",
            base_url="https://vision.test/compatible-mode/v1",
            timeout=5.0)

        # 请求组装：模型名 + OpenAI 兼容消息（文本 + base64 PNG）
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["model"], vision_tools.VISION_MODEL)
        self.assertEqual(kwargs["temperature"], 0.1)
        user_content = kwargs["messages"][0]["content"]
        self.assertIn("【设置】", user_content[0]["text"])
        image_url = user_content[1]["image_url"]["url"]
        self.assertTrue(image_url.startswith("data:image/png;base64,"))

    def test_full_flow_user_reported_array_format_taps_first_two(self):
        # 用户实测格式 {"x1": [69, 514, 312, 547]}：前两个元素作为点击点
        # (69, 514)，缩放比 0.5 换算 → (138, 1028)（旧解析对此报"未能识别"）
        self._write_screenshot(width=540, height=1200)
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (138, 1028)")
        self._patch_client(content='{"x1": [69, 514, 312, 547]}')
        with mock.patch.object(vision_tools, "adb_screenshot",
                               return_value="✅ 截图完成"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")):
            result = vision_tools.vision_tap_element("设置")
        self._assert_tapped_twice_same_point(tap, 138, 1028)
        self.assertEqual(result, vision_tools.VISION_PAGE_UNCHANGED_FAIL)

    def test_full_flow_user_reported_fence_missing_y_taps_scaled(self):
        # 用户实测原串（```json 围栏 + {"x": 246, "531"}）：清洗修复 →
        # (246, 531)，缩放比 0.5 换算 → (492, 1062)
        self._write_screenshot(width=540, height=1200)
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (492, 1062)")
        self._patch_client(content='```json\n{"x": 246, "531"}\n```')
        with mock.patch.object(vision_tools, "adb_screenshot",
                               return_value="✅ 截图完成"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")):
            result = vision_tools.vision_tap_element("设置")
        self._assert_tapped_twice_same_point(tap, 492, 1062)
        self.assertEqual(result, vision_tools.VISION_PAGE_UNCHANGED_FAIL)

    def test_full_flow_bounds_array_taps_center(self):
        # {"bounds": [100, 200, 300, 400]} → 中心 (200, 300)，缩放 0.5；
        # (400, 600) 在 15%~40% 区间 → 仅"请确认"警告、不偏移
        self._write_screenshot(width=540, height=1200)
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (400, 600)")
        self._patch_client(content='{"bounds": [100, 200, 300, 400]}')
        with mock.patch.object(vision_tools, "adb_screenshot",
                               return_value="✅ 截图完成"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")):
            vision_tools.vision_tap_element("设置")
        self._assert_tapped_twice_same_point(tap, 400, 600)

    def test_full_flow_direct_xy_taps_directly(self):
        # {"x": 150, "y": 250} → 直接作为点击点（截图与屏幕等宽 → 缩放比
        # 1.0）；(150, 250) 在 15% 线内（< 360）→ 强警告 + 2% 屏高
        # （48px）下移 → (150, 298)
        self._write_screenshot(width=1080, height=1200)
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (150, 298)")
        self._patch_client(content='{"x": 150, "y": 250}')
        with mock.patch.object(vision_tools, "adb_screenshot",
                               return_value="✅ 截图完成"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")):
            result = vision_tools.vision_tap_element("设置")
        self._assert_tapped_twice_same_point(tap, 150, 298)
        self.assertEqual(result, vision_tools.VISION_PAGE_UNCHANGED_FAIL)

    def test_direct_minus_one_xy_reports_not_found(self):
        # 提示词新约定：找不到输出 {"x": -1, "y": -1} → 明确未找到文案，
        # 不换算、不点击
        self._write_screenshot()
        tap = mock.MagicMock()
        self._patch_client(content='{"x": -1, "y": -1}')
        with mock.patch.object(vision_tools, "adb_screenshot",
                               return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")):
            result = vision_tools.vision_tap_element("设置")
        # 未找到串后附加兜底排查引导（2026-10-01 用户指令：亮屏/页面 +
        # VISION_MODEL 模型配置两手排查）
        self.assertEqual(
            result,
            "❌ 视觉模型在屏幕上未找到【设置】。 ⚠️ 请确认手机屏幕已亮屏"
            "且停留在目标页面，同时确认 .env 中的 VISION_MODEL 是真正的"
            "视觉模型（如 qwen-vl-max-latest）")
        tap.assert_not_called()

    def test_malformed_array_content_reports_unrecognized(self):
        # 数组值格式但元素不足（{"x1": [69]}）→ "未能识别" 文案，不崩溃
        self._write_screenshot()
        tap = mock.MagicMock()
        self._patch_client(content='{"x1": [69]}')
        with mock.patch.object(vision_tools, "adb_screenshot",
                               return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")):
            result = vision_tools.vision_tap_element("设置")
        self.assertTrue(
            result.startswith("❌ 视觉模型未能识别出坐标。回复内容："))
        tap.assert_not_called()

    def test_endpoint_join_no_double_or_lost_segment(self):
        # base 末尾带 / → rstrip 后拼接防双斜杠；/compatible-mode/v1 段不丢
        vision_tools.VISION_API_URL = "https://vision.test/compatible-mode/v1/"
        self.assertEqual(
            vision_tools._vision_endpoint(),
            "https://vision.test/compatible-mode/v1/chat/completions")
        vision_tools.VISION_API_URL = "https://vision.test/compatible-mode/v1"
        self.assertEqual(
            vision_tools._vision_endpoint(),
            "https://vision.test/compatible-mode/v1/chat/completions")

    def test_endpoint_already_full_not_duplicated(self):
        # base 被误填成完整端点 → 防双段：不再追加 /chat/completions
        vision_tools.VISION_API_URL = (
            "https://vision.test/compatible-mode/v1/chat/completions")
        self.assertEqual(
            vision_tools._vision_endpoint(),
            "https://vision.test/compatible-mode/v1/chat/completions")

    def test_client_base_url_strips_endpoint_suffix(self):
        # SDK base_url 必须剥掉 /chat/completions 尾段（客户端自己追加）
        vision_tools.VISION_API_URL = "https://vision.test/compatible-mode/v1"
        self.assertEqual(vision_tools._client_base_url(),
                         "https://vision.test/compatible-mode/v1")
        vision_tools.VISION_API_URL = (
            "https://vision.test/compatible-mode/v1/chat/completions")
        self.assertEqual(vision_tools._client_base_url(),
                         "https://vision.test/compatible-mode/v1")

    def test_legacy_vision_url_env_override(self):
        # 旧环境变量 VISION_URL（完整端点）向后兼容覆盖，原样使用
        os.environ["VISION_URL"] = "https://legacy.example/v1/chat/completions"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            endpoint = vision_tools._vision_endpoint()
        self.assertEqual(endpoint, "https://legacy.example/v1/chat/completions")
        # 覆盖行为在控制台有 ⚠️ 提示，便于发现残留旧变量遮蔽新域名
        self.assertIn("VISION_URL", buf.getvalue())

    def _fake_status_error(self, exc_cls, status_code, body):
        """构造 openai HTTP 状态类异常（403/404 等鉴权与模型错误）。"""
        return exc_cls(
            f"{status_code} error",
            response=mock.MagicMock(status_code=status_code),
            body=body)

    def test_http_403_diagnostics_reply_short_no_retry(self):
        # sk-ws- 新版 Key 配了老域名 → 403：返回串极简（无指引），诊断块只进
        # 控制台；鉴权类错误不重试（create 仅一次）
        self._write_screenshot()
        err = self._fake_status_error(
            openai.PermissionDeniedError, 403,
            '{"error":{"code":"AccessDenied","message":"InvalidApiKey"}}')
        buf = io.StringIO()
        create, _cls = self._patch_client(side_effect=err)
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("设置")

        self.assertEqual(create.call_count, 1)   # 403 不重试
        # 返回串：只报状态码 + 操作已中止，不带任何排查指引
        self.assertEqual(result, "❌ 视觉模型调用失败: HTTP 403，操作已中止。")
        for keyword in ("请检查", "VISION_API_URL", "VISION_KEY", "VISION_MODEL"):
            self.assertNotIn(keyword, result)

        # 控制台诊断块：完整 URL / 状态码 / 错误摘要 / 脱敏 Key / 排查指引
        out = buf.getvalue()
        self.assertIn(
            "请求 URL: https://vision.test/compatible-mode/v1/chat/completions", out)
        self.assertIn("HTTP 状态码: 403", out)
        self.assertIn("响应体摘要:", out)
        self.assertIn("AccessDenied", out)
        self.assertIn("test-v****", out)          # 密钥仅显示前 6 位 + 掩码
        self.assertNotIn("test-vision-key", out)  # 完整 Key 不得入日志
        self.assertIn("排查指引:", out)
        self.assertIn("sk-ws- 开头的新版 Key", out)

    def test_http_404_falls_back_to_next_model_succeeds(self):
        # 404 回退链：第一候选 404 → ⚠️ 切换备用模型 → 第二候选成功
        self._write_screenshot()
        err404 = self._fake_status_error(
            openai.NotFoundError, 404,
            '{"error":{"code":"model.not_found","message":"Model not found"}}')
        resp = mock.MagicMock()
        resp.choices = [mock.MagicMock()]
        resp.choices[0].message.content = \
            '{"x1": 100, "y1": 200, "x2": 300, "y2": 400}'
        # (400, 600) 在 15%~40% 区间 → 仅"请确认"警告、不偏移
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (400, 600)")
        buf = io.StringIO()
        create, _cls = self._patch_client(side_effect=[err404, resp])
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("设置")

        # create 共两次：第一次配置模型，第二次为第一个备用模型
        self.assertEqual(create.call_count, 2)
        self.assertEqual(
            create.call_args_list[0].kwargs["model"], vision_tools.VISION_MODEL)
        self.assertEqual(
            create.call_args_list[1].kwargs["model"],
            vision_tools.VISION_FALLBACK_MODELS[0])
        # ⚠️ 提示同时含失败模型与备用模型名
        out = buf.getvalue()
        self.assertIn("⚠️ 模型 qwen-vl-test 不存在（404），"
                      "自动切换备用模型: qwen-vl-plus", out)
        # 中途切换成功：无终态诊断块、返回串不带已尝试模型
        self.assertNotIn("排查指引", out)
        self.assertNotIn("已尝试模型", out)
        # 二次确认点击（组 D1，默认开）：tap 两次同坐标；页面未变化 →
        # F3-2 新口径：返回串整体替换为明确失败 ❌ 文案
        self.assertEqual(tap.call_args_list,
                         [mock.call(400, 600), mock.call(400, 600)])
        self.assertEqual(result, vision_tools.VISION_PAGE_UNCHANGED_FAIL)

    def test_http_404_all_models_exhausted_diagnostics(self):
        # 全部候选模型均 404：按回退顺序逐个尝试后输出诊断块（含已尝试
        # 模型列表），返回串保持极简口径（括号内补已尝试模型，无指引）
        self._write_screenshot()
        err = self._fake_status_error(
            openai.NotFoundError, 404,
            '{"error":{"code":"model.not_found","message":"Model not found"}}')
        buf = io.StringIO()
        create, _cls = self._patch_client(side_effect=err)
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("设置")

        candidates = vision_tools._model_candidates()
        self.assertEqual(create.call_count, len(candidates))
        self.assertEqual(
            [call.kwargs["model"] for call in create.call_args_list],
            candidates)
        tried = "/".join(candidates)
        self.assertEqual(
            result,
            f"❌ 视觉模型调用失败: HTTP 404，操作已中止。（已尝试模型: {tried}）")
        self.assertNotIn("请检查", result)          # 返回串仍极简、无指引
        out = buf.getvalue()
        self.assertIn("HTTP 状态码: 404", out)
        self.assertIn("model.not_found", out)
        self.assertIn(f"已尝试模型: {tried}", out)   # 诊断块列出已尝试模型
        self.assertIn("排查指引:", out)

    def test_model_candidates_dedup_preserves_order(self):
        # 尝试序列 = 配置模型 + 备用去重保序；配置模型本身在备用列表中
        # 时不重复尝试同名模型
        vision_tools.VISION_MODEL = "qwen-vl-test"
        self.assertEqual(
            vision_tools._model_candidates(),
            ["qwen-vl-test", "qwen-vl-plus", "qwen-vl-max",
             "qwen-vl-max-latest"])
        vision_tools.VISION_MODEL = "qwen-vl-max-latest"
        self.assertEqual(
            vision_tools._model_candidates(),
            ["qwen-vl-max-latest", "qwen-vl-plus", "qwen-vl-max"])

    def test_fallback_stops_on_non_404_status_error(self):
        # 404 切换备用模型后遇 403（Key/域名问题）：换模型无用，不回退、
        # 立即诊断返回，剩余备用模型不再尝试
        self._write_screenshot()
        err404 = self._fake_status_error(
            openai.NotFoundError, 404,
            '{"error":{"code":"model.not_found","message":"Model not found"}}')
        err403 = self._fake_status_error(
            openai.PermissionDeniedError, 403,
            '{"error":{"code":"AccessDenied","message":"InvalidApiKey"}}')
        buf = io.StringIO()
        create, _cls = self._patch_client(side_effect=[err404, err403])
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("设置")

        self.assertEqual(create.call_count, 2)   # 403 后不再尝试第 3/4 候选
        self.assertEqual(result, "❌ 视觉模型调用失败: HTTP 403，操作已中止。")
        self.assertNotIn("已尝试模型", result)
        self.assertIn("HTTP 状态码: 403", buf.getvalue())  # 403 诊断块进控制台

    def test_timeout_no_retry_short_message(self):
        # 超时属网络类错误：默认不重试（MAX_RETRIES=0），快速失败不拖慢响应；
        # 控制台仅一行简短提示，返回简短文案，无大段诊断块
        self._write_screenshot()
        err = openai.APITimeoutError(request=mock.MagicMock())
        buf = io.StringIO()
        create, _cls = self._patch_client(side_effect=err)
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("设置")

        self.assertEqual(create.call_count, 1)    # 不重试，create 仅调用 1 次
        self._sleep.assert_not_called()           # 无退避等待
        self.assertEqual(result, "❌ 视觉模型网络连接失败，操作已中止。")
        # 返回串极简：无任何指引 / 旧文案残留
        self.assertNotIn("请检查", result)
        self.assertNotIn("请稍后重试", result)
        out = buf.getvalue()
        # 控制台单行简短提示（含异常自身的简短原因）
        self.assertEqual(out.count("❌ 视觉模型网络连接失败"), 1)
        self.assertIn("❌ 视觉模型网络连接失败: Request timed out.", out)
        # 网络路径不再输出大段诊断块 / 重试提示
        self.assertNotIn("排查指引", out)
        self.assertNotIn("请求 URL", out)
        self.assertNotIn("重试", out)
        self.assertNotIn("HTTP 状态码", out)

    def test_connection_reset_no_retry_short_message(self):
        # ConnectionResetError(10054) 属网络类：不重试、一行简短提示、快速失败
        self._write_screenshot(width=540, height=1200)
        buf = io.StringIO()
        create, _cls = self._patch_client(
            side_effect=ConnectionResetError(10054))
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("设置")

        self.assertEqual(create.call_count, 1)    # 不重试，create 仅调用 1 次
        self._sleep.assert_not_called()           # 无退避等待
        self.assertEqual(result, "❌ 视觉模型网络连接失败，操作已中止。")
        self.assertNotIn("请检查", result)         # 返回串极简，无指引
        self.assertNotIn("请稍后重试", result)
        out = buf.getvalue()
        # 控制台单行简短提示，冒号后带简短原因
        lines = [ln for ln in out.splitlines()
                 if "❌ 视觉模型网络连接失败" in ln]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("❌ 视觉模型网络连接失败: "))
        self.assertTrue(lines[0].split(":", 1)[1].strip())
        # 网络路径不输出大段诊断块，且完整 Key 不泄漏
        self.assertNotIn("排查指引", out)
        self.assertNotIn("请求 URL", out)
        self.assertNotIn("HTTP 状态码", out)
        self.assertNotIn("test-vision-key", out)

    def test_retry_skeleton_restorable_when_constant_raised(self):
        # 重试循环骨架保留：把 VISION_MAX_RETRIES 调回 1 即恢复"失败后重试
        # 1 次"行为（指数退避 1s），未来想恢复重试只改常量、无需改代码
        self._write_screenshot(width=540, height=1200)
        # (400, 600) 在 15%~40% 区间 → 仅"请确认"警告、不偏移
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (400, 600)")
        content = '{"x1": 100, "y1": 200, "x2": 300, "y2": 400}'
        resp = mock.MagicMock()
        resp.choices = [mock.MagicMock()]
        resp.choices[0].message.content = content
        create, _cls = self._patch_client(
            side_effect=[ConnectionResetError(10054), resp])
        with mock.patch.object(vision_tools, "VISION_MAX_RETRIES", 1), \
             mock.patch.object(vision_tools, "adb_screenshot",
                               return_value="✅ 截图完成"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")):
            result = vision_tools.vision_tap_element("设置")

        self.assertEqual(create.call_count, 2)    # 失败 1 次 + 重试成功 1 次
        # sleep 序列：网络退避 1s → 点击前 0.5s → 二次确认前 1s
        self.assertEqual(
            [c.args[0] for c in self._sleep.call_args_list], [1, 0.5, 1])
        self.assertEqual(tap.call_args_list,
                         [mock.call(400, 600), mock.call(400, 600)])
        self.assertEqual(result, vision_tools.VISION_PAGE_UNCHANGED_FAIL)

    def test_scale_one_when_png_header_missing(self):
        # 非 PNG 头（解析失败）→ 缩放比回退 1.0，且不再静默：打印 ⚠️
        # 警告（2026-10-01 用户指令：静默错误 → 可见错误），📏 全量日志
        # 截图分辨率标注"未知(按1:1)"
        with open(vision_tools.SCREENSHOT_PATH, "wb") as f:
            f.write(b"\x00\x01\x02not-a-png")
        tap = mock.MagicMock(return_value="ok")
        content = '{"x1": 100, "y1": 200, "x2": 300, "y2": 400}'
        self._patch_client(content=content)
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            vision_tools.vision_tap_element("设置")
        out = buf.getvalue()
        # 解析失败警告恰好一行，含 1:1 换算与截图格式排查提示
        self.assertIn("⚠️ [视觉缩放] 截图分辨率解析失败，按 1:1 换算", out)
        self.assertIn("（点击若偏差请检查截图格式）", out)
        # 📏 全量日志：截图分辨率显示"未知(按1:1)"，其余三要素齐全
        self.assertIn("📏 [视觉缩放] 模型原始坐标: (200, 300)", out)
        self.assertIn("截图分辨率: 未知(按1:1)", out)
        self.assertIn("手机实际分辨率: 1080x2400", out)
        self.assertIn("换算后坐标: (200, 300)", out)
        # (200, 300) 在 15% 线内（< 360）→ 强警告 + 2% 屏高（48px）下移
        # → 实际点击 (200, 348)
        self.assertEqual(tap.call_args_list,
                         [mock.call(200, 348), mock.call(200, 348)])

    def test_scale_conversion_full_log_line(self):
        # 📏 单行全量日志（2026-10-01 用户指令）：四要素——模型原始坐标 /
        # 截图分辨率 / 手机实际分辨率 / 换算后坐标；旧 🎯 行不再出现
        self._write_screenshot(width=540, height=1200)
        tap = mock.MagicMock(return_value="ok")
        content = '{"x1": 100, "y1": 200, "x2": 300, "y2": 400}'
        self._patch_client(content=content)
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            vision_tools.vision_tap_element("设置")
        out = buf.getvalue()
        # 截图 540 宽 / 屏幕 1080 宽 → 缩放比 0.5：框中心 (200,300) →
        # 换算 (400,600)，四要素齐全
        self.assertIn("📏 [视觉缩放] 模型原始坐标: (200, 300)", out)
        self.assertIn("截图分辨率: 540x1200", out)
        self.assertIn("手机实际分辨率: 1080x2400", out)
        self.assertIn("换算后坐标: (400, 600)", out)
        self.assertNotIn("🎯", out)
        # 换算发生在 adb_tap 之前：📏 行展示换算坐标 (400, 600)；该点在
        # 15%~40% 区间 → 仅"请确认"警告、不偏移，tap 两次收到原坐标
        self.assertEqual(tap.call_args_list,
                         [mock.call(400, 600), mock.call(400, 600)])

    def test_model_response_without_choices(self):
        self._write_screenshot()
        create, _cls = self._patch_client()
        resp = mock.MagicMock()
        resp.choices = []
        create.return_value = resp
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")):
            result = vision_tools.vision_tap_element("设置")
        self.assertTrue(result.startswith("❌ 视觉模型返回异常: "))

    def test_model_response_without_coordinates(self):
        self._write_screenshot()
        self._patch_client(content="抱歉，我找不到这个图标。")
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")):
            result = vision_tools.vision_tap_element("设置")
        self.assertEqual(
            result, "❌ 视觉模型未能识别出坐标。回复内容：抱歉，我找不到这个图标。")

    def test_parse_failure_prints_diagnostics(self):
        # 解析失败诊断（2026-10-01 用户指令）：控制台两行 ⚠️（原始返回
        # 内容 / 清洗后的 JSON 候选，各截断 300），返回串保持既有口径
        self._write_screenshot()
        tap = mock.MagicMock()
        long_content = "前" * 300 + "后" * 100 + ' {"x": "abc"}'
        self._patch_client(content=long_content)
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("设置")
        out = buf.getvalue()
        self.assertIn("⚠️ [视觉坐标解析失败] 原始返回内容: ", out)
        self.assertIn("⚠️ [视觉坐标解析失败] 清洗后的 JSON 候选: ", out)
        # 原始内容截断 300：前 300 字保留，其后内容不进诊断（返回串除外）
        self.assertIn("前" * 300, out)
        self.assertNotIn("后" * 100, out)
        # 候选行给出清洗后的 JSON 候选（{"x": "abc"} 本身合法 → 原样保留）
        self.assertIn('{"x": "abc"}', out)
        # 返回串与点击行为不变：既有失败串 + 不点击
        self.assertTrue(
            result.startswith("❌ 视觉模型未能识别出坐标。回复内容："))
        tap.assert_not_called()

    def test_parse_failure_diagnostics_without_candidates(self):
        # 无任何 JSON 候选（纯 prose 回复）：第二行给占位说明，两行诊断
        # 仍然齐全
        self._write_screenshot()
        self._patch_client(content="抱歉，我找不到这个图标。")
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("设置")
        out = buf.getvalue()
        self.assertIn(
            "⚠️ [视觉坐标解析失败] 原始返回内容: 抱歉，我找不到这个图标。", out)
        self.assertIn(
            "⚠️ [视觉坐标解析失败] 清洗后的 JSON 候选: （无 JSON 候选）", out)
        self.assertEqual(
            result, "❌ 视觉模型未能识别出坐标。回复内容：抱歉，我找不到这个图标。")

    def test_minus_one_coords_reports_not_found(self):
        # 模型按约定输出全 -1（未找到信号）→ 明确失败文案，不换算、不点击
        self._write_screenshot()
        tap = mock.MagicMock()
        self._patch_client(content='{"x1": -1, "y1": -1, "x2": -1, "y2": -1}')
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")):
            result = vision_tools.vision_tap_element("设置")
        # 未找到串后附加兜底排查引导（2026-10-01 用户指令），与上一用例
        # （直接 x+y 格式）共同覆盖两种全 -1 解析路径
        self.assertEqual(
            result,
            "❌ 视觉模型在屏幕上未找到【设置】。 ⚠️ 请确认手机屏幕已亮屏"
            "且停留在目标页面，同时确认 .env 中的 VISION_MODEL 是真正的"
            "视觉模型（如 qwen-vl-max-latest）")
        tap.assert_not_called()

    def test_prompt_structure_chinese_screen_friendly(self):
        # 提示词结构（中文屏幕识别友好）：截图语境 + 中文名优先 + 忽略
        # 状态栏/小组件 + 应用列表/文件夹逐屏排查 + 强制点击点 JSON 输出
        # （2026-10-01 用户指令）与 {"x": -1, "y": -1} 未找到约定
        self._write_screenshot()
        create, _cls = self._patch_client(
            content='{"x1": 0, "y1": 0, "x2": 10, "y2": 10}')
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", mock.MagicMock()), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")):
            vision_tools.vision_tap_element("微信")
        text = create.call_args.kwargs["messages"][0]["content"][0]["text"]
        for keyword in ("屏幕截图", "【微信】", "中文名称", "忽略", "状态栏",
                        "小组件", "应用列表", "文件夹",
                        "请务必只输出 JSON 格式", "屏幕绝对坐标",
                        '"x"', '"y"', "-1",
                        # 严格匹配强化（2026-10-01 用户指令，用户口径）
                        "严格匹配", "中文字符", "不要定位图标或搜索框",
                        "不要瞎猜"):
            self.assertIn(keyword, text)
        # 输出格式段统一为新口径：强制 {"x": 数字, "y": 数字}，未找到
        # 信号改为 {"x": -1, "y": -1}（旧 Bounding Box 指令不再出现）
        self.assertIn('{"x": 数字, "y": 数字}', text)
        self.assertIn('{"x": -1, "y": -1}', text)
        self.assertNotIn('"x1"', text)
        self.assertNotIn('"y2"', text)

    def test_prompt_forbids_code_fence_and_requires_keyed_numbers(self):
        # 提示词补强（2026-10-01 用户指令）：直接输出 JSON 本体禁 ```json
        # 等代码块包裹 + "x"/"y" 每个值必须带键名、数字不加引号（附正例）
        self._write_screenshot()
        create, _cls = self._patch_client(
            content='{"x1": 0, "y1": 0, "x2": 10, "y2": 10}')
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", mock.MagicMock()), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")):
            vision_tools.vision_tap_element("设置")
        text = create.call_args.kwargs["messages"][0]["content"][0]["text"]
        self.assertIn("直接输出 JSON 本体", text)
        self.assertIn("不要用 ```json 等代码块包裹", text)
        self.assertIn('"x" 与 "y" 每个值都必须带键名', text)
        self.assertIn("数字不要加引号", text)
        self.assertIn('{"x": 246, "y": 531}', text)
        # 末尾强化句（2026-10-01 用户指令）：置于提示词末尾段——任务 2
        # 观察描述段追加后不再位于最末尾；"不要包含任何解释性文字"与
        # "先描述你看到了什么"直接冲突，按任务 2 口径改为约束 JSON 本体
        self.assertIn("不要包含 markdown 代码块", text)
        self.assertNotIn("不要包含任何解释性文字", text)
        self.assertIn("JSON 本体只含", text)
        self.assertIn('示例：{"x": 100, "y": 200}。', text)

    def test_prompt_strict_match_reinforcement_adjacent_to_status_bar_rule(self):
        # 提示词严格匹配强化（2026-10-01 用户指令，用户口径）：背景是
        # qwen3-vl-flash 找屏幕中下方的"WLAN"文字时误点顶部搜索框——
        # 强化规则须与"忽略状态栏/小组件"规则相邻（其后）、"逐屏排查"
        # 规则之前；关键要素：严格匹配中文字符 / 定位到文字本身而非图标
        # 或搜索框 / 找不到务必全 -1 不瞎猜；既有输出格式与 -1 约定保留
        self._write_screenshot()
        create, _cls = self._patch_client(
            content='{"x1": 0, "y1": 0, "x2": 10, "y2": 10}')
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", mock.MagicMock()), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")):
            vision_tools.vision_tap_element("WLAN")
        text = create.call_args.kwargs["messages"][0]["content"][0]["text"]
        for keyword in ("严格匹配", "中文字符", "不要定位图标或搜索框",
                        "不要瞎猜", "返回全 -1 坐标"):
            self.assertIn(keyword, text)
        # 位置：紧跟"忽略状态栏"规则（其后）、"逐屏排查"规则之前
        self.assertLess(text.index("忽略顶部状态栏"), text.index("严格匹配"))
        self.assertLess(text.index("严格匹配"), text.index("逐屏仔细排查"))
        # 既有输出格式与 -1 约定保留
        self.assertIn('{"x": -1, "y": -1}', text)

    def test_top_region_coordinate_warns_but_still_taps(self):
        # 顶部区域合理性检查（2026-10-01 用户指令）+ F3-1 降级告知进
        # 返回串：截图 540x1200、屏幕 1080x2400 → 缩放比 0.5，模型返回
        # y=150 换算 real_y=300 < 360（0.15 × 2400，顶部 15% 通常是
        # 状态栏/搜索框位置）→ adb_tap 前打印一行 ⚠️ 警告；real_y=300
        # 同时 < 15% 强警告线 → "极易误点"强警告（另有专项用例）
        self._write_screenshot(width=540, height=1200)
        # 第二次截图（变化检测重截图）改写文件 → 页面已变化，返回串走
        # 成功口径，F3-1 顶部降级告知附加段由此断言
        reshot_calls = {"count": 0}

        def _fake_screenshot():
            reshot_calls["count"] += 1
            if reshot_calls["count"] >= 2:
                with open(vision_tools.SCREENSHOT_PATH, "wb") as f:
                    f.write(_png_bytes(541, 1200))
            return "✅"

        # real_y=300 落在 15% 线内（两行警告都打印，文案不同不去重）
        # → 2% 屏高（48px）下移 → 实际执行 (992, 348)
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (992, 348)")
        self._patch_client(content='{"x": 496, "y": 150}')
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "adb_screenshot",
                               side_effect=_fake_screenshot), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("WLAN")
        out = buf.getvalue()
        self.assertIn(
            "⚠️ 视觉坐标可能定位到搜索框或状态栏，请检查目标文字位置", out)
        self.assertEqual(out.count("视觉坐标可能定位到搜索框或状态栏"), 1)
        # 15% 线内强警告同屏打印（与 15% 提示并存，文案不同不去重）
        self.assertIn("⚠️ 目标位于屏幕上部，极易误点到账号或搜索框", out)
        self.assertIn("实际执行坐标: (992, 348)", out)
        # 换算 (496, 150) ÷ 0.5 → (992, 300)，15% 线内下移 48px →
        # 实际点击 (992, 348)（二次确认默认开：两次同坐标）
        self.assertEqual(tap.call_args_list,
                         [mock.call(992, 348), mock.call(992, 348)])
        # F3-1：页面已变化 → 无 ❌ 未点中文案；成功串后追加顶部降级
        # 告知（聊天框可见，<15% 强警告区命中）
        self.assertNotIn(vision_tools.VISION_PAGE_UNCHANGED_FAIL, result)
        self.assertEqual(
            result,
            "✅ 已模拟点击坐标: (992, 348)（已执行二次确认点击）"
            " ⚠️ 视觉模型可能识别到了顶部区域（如账号/搜索框），"
            "建议手动确认。")

    def test_mid_lower_coordinate_no_top_region_warning(self):
        # 反例：换算后 real_y 落在屏幕中下部（1062 ≥ 15%/40% 两级阈值，
        # 1062 ≥ 0.4 × 2400 = 960）
        # → 不打印顶部误定位警告、无 40% 严重警告与向下偏移，其余输出
        # （📏 缩放日志等）保持既有形态
        self._write_screenshot(width=540, height=1200)
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (492, 1062)")
        self._patch_client(content='{"x": 246, "y": 531}')
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("WLAN")
        self.assertNotIn("视觉坐标可能定位到搜索框或状态栏", buf.getvalue())
        # 中下部（1062 ≥ 0.4×2400）不触发任何上部警告、无向下偏移
        self.assertNotIn("极易误点到账号或搜索框", buf.getvalue())
        self.assertNotIn("目标位于屏幕上部", buf.getvalue())
        self.assertNotIn("实际执行坐标", buf.getvalue())
        self.assertIn("📏 [视觉缩放]", buf.getvalue())   # 其余日志不受影响
        self.assertEqual(tap.call_args_list,
                         [mock.call(492, 1062), mock.call(492, 1062)])
        # ≥40% 正常坐标 + 页面未变化 → F3-2 新口径：返回串精确等于 ❌
        # 文案；F3-1 顶部降级告知不追加（≥40% 不命中）
        self.assertNotIn("建议手动确认", result)
        self.assertEqual(result, vision_tools.VISION_PAGE_UNCHANGED_FAIL)

    def test_prompt_observe_and_describe_before_coordinates(self):
        # 任务 2（2026-10-01 用户指令，用户原文）：提示词末尾强势追加
        # "先仔细观察屏幕 / 先描述你看到了什么 / 找不到直接返回 -1 坐标
        # 不要瞎猜"；同时保留"JSON 本体只含坐标"口径（描述允许在 JSON
        # 之前，解析端 _extract_click_point 对 prose 包裹已容错）
        self._write_screenshot()
        create, _cls = self._patch_client(
            content='我看屏幕上是设置页面。{"x": 150, "y": 250}')
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", mock.MagicMock()), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")):
            vision_tools.vision_tap_element("设置")
        text = create.call_args.kwargs["messages"][0]["content"][0]["text"]
        for keyword in ("先仔细观察屏幕", "先描述你看到了什么",
                        "如果找不到目标文字，请直接返回 -1 坐标",
                        "不要瞎猜", "JSON 本体只含"):
            self.assertIn(keyword, text)
        # 新增强化段置于提示词最末尾（强势追加）
        self.assertTrue(text.rstrip().endswith("不要瞎猜。"))

    def test_zone_15_to_40_percent_warns_only_no_offset(self):
        # 修正后口径（2026-10-01 偏移策略修正）：real_y 落在 15%~40% 区间
        # （500，≥ 360 且 < 960）→ 只打"⚠️ 目标位于屏幕上部，请确认"警告，
        # 不偏移、保留模型原始坐标执行 → tap (200, 500)；15% 线提示与
        # "极易误点"强警告均不出现（设置列表正常元素也落此区间，杜绝
        # "蓝牙→我的设备"式漂移的关键口径）
        self._write_screenshot(width=540, height=1200)
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (200, 500)")
        self._patch_client(content='{"x": 100, "y": 250}')
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("账号")
        out = buf.getvalue()
        # 仅"请确认"警告恰好一行；强警告 / 15% 提示 / 偏移日志均不出现
        self.assertEqual(out.count("⚠️ 目标位于屏幕上部，请确认"), 1)
        self.assertNotIn("极易误点到账号或搜索框", out)
        self.assertNotIn("视觉坐标可能定位到搜索框或状态栏", out)
        self.assertNotIn("实际执行坐标", out)
        self.assertIn("换算后坐标: (200, 500)", out)   # 📏 日志展示原坐标
        self._assert_tapped_twice_same_point(tap, 200, 500)
        # 15%~40% 疑似区 + 页面未变化 → F3-2 新口径：返回串整体替换为
        # 明确失败 ❌ 文案（顶部降级告知只改成功串形态，此处被失败口径
        # 覆盖）
        self.assertEqual(result, vision_tools.VISION_PAGE_UNCHANGED_FAIL)

    def test_top_offset_env_disabled_warns_only(self):
        # VISION_TOP_OFFSET 关（env VISION_TOP_OFFSET=0 的模块常量形态）：
        # 语义不变——关=连 15% 内也不偏移：real_y=300（< 360 强警告线）
        # 仍打 15% 提示 + "极易误点"强警告，但不下移——tap 原坐标、
        # 无"实际执行坐标"行
        self._write_screenshot(width=540, height=1200)
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (200, 300)")
        self._patch_client(content='{"x": 100, "y": 150}')
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "VISION_TOP_OFFSET", False), \
             mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("账号")
        out = buf.getvalue()
        self.assertIn("⚠️ 目标位于屏幕上部，极易误点到账号或搜索框", out)
        self.assertIn("视觉坐标可能定位到搜索框或状态栏", out)
        self.assertNotIn("实际执行坐标", out)
        self._assert_tapped_twice_same_point(tap, 200, 300)
        self.assertEqual(result, vision_tools.VISION_PAGE_UNCHANGED_FAIL)

    def test_user_scenario_31_percent_warns_only_keeps_model_y(self):
        # 用户场景复现（2026-10-01 偏移策略修正的关键用例）：屏高 2712、
        # 模型给 y=847 → 31.2%——设置列表中"蓝牙"的正常元素位置。此前
        # 40% 区 5% 强推下移把它推到 y=982、点击漂移到"我的设备"（好心
        # 办坏事）；修正后 15%~40% 区间只警告、不偏移，y 保持 847 执行。
        # 截图与屏幕等宽 → 缩放比 1.0，换算后仍 (540, 847)；31.2% ≥ 15%
        # （406.8）→ 只有"请确认"警告一行
        self._write_screenshot(width=1080, height=2712)
        # 第二次截图（变化检测重截图）改写文件 → 页面已变化，返回串走
        # 成功口径，F3-1 顶部降级告知（15%~40% 疑似区命中）由此断言
        reshot_calls = {"count": 0}

        def _fake_screenshot():
            reshot_calls["count"] += 1
            if reshot_calls["count"] >= 2:
                with open(vision_tools.SCREENSHOT_PATH, "wb") as f:
                    f.write(_png_bytes(1081, 2712))
            return "✅"

        # 常量口径断言：偏移量收窄至 2%（0.02 × 2712 = 54.24，int 截断
        # 为 54），偏移线 0.15、警告上限 0.40
        self.assertEqual(
            int(vision_tools.VISION_TOP_OFFSET_RATIO * 2712), 54)
        self.assertEqual(vision_tools.VISION_TOP_STRONG_RATIO, 0.15)
        self.assertEqual(vision_tools.VISION_TOP_ZONE_RATIO, 0.40)
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (540, 847)")
        self._patch_client(content='{"x": 540, "y": 847}')
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "adb_screenshot",
                               side_effect=_fake_screenshot), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2712")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("蓝牙")
        out = buf.getvalue()
        # "请确认"警告恰好一行；强警告 / 15% 提示 / 偏移日志均不出现
        self.assertEqual(out.count("⚠️ 目标位于屏幕上部，请确认"), 1)
        self.assertNotIn("极易误点到账号或搜索框", out)
        self.assertNotIn("视觉坐标可能定位到搜索框或状态栏", out)
        self.assertNotIn("实际执行坐标", out)
        # 📏 缩放日志展示换算后原坐标；模型 y=847 原样执行（不漂移）
        self.assertIn("换算后坐标: (540, 847)", out)
        self._assert_tapped_twice_same_point(tap, 540, 847)
        # F3-1（用户"蓝牙→账号"误点场景）：页面已变化 → 成功串后追加
        # 顶部降级告知（15%~40% 疑似区同样命中），无 ❌ 未点中文案
        self.assertNotIn(vision_tools.VISION_PAGE_UNCHANGED_FAIL, result)
        self.assertEqual(
            result,
            "✅ 已模拟点击坐标: (540, 847)（已执行二次确认点击）"
            " ⚠️ 视觉模型可能识别到了顶部区域（如账号/搜索框），"
            "建议手动确认。")

    def test_below_15_percent_strong_zone_offsets_2_percent(self):
        # <15% 强警告区（14% 用户场景）：屏高 2712、模型 y=378（13.9%）
        # → 真状态栏/搜索框区 → 15% 提示 + 强警告 + 2% 屏高向下偏移
        # （int(0.02 × 2712) = 54 像素）→ 实际执行 (540, 432)
        self._write_screenshot(width=1080, height=2712)
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (540, 432)")
        self._patch_client(content='{"x": 540, "y": 378}')
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2712")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("搜索")
        out = buf.getvalue()
        # 15% 线内两行警告并存（15% 提示 + 强警告，文案不同不去重）
        self.assertIn("视觉坐标可能定位到搜索框或状态栏", out)
        self.assertIn("⚠️ 目标位于屏幕上部，极易误点到账号或搜索框", out)
        # 偏移量恰为 2% 屏高（54px）：378 + 54 = 432
        self.assertIn("已向下偏移 2% 屏高", out)
        self.assertIn("实际执行坐标: (540, 432)", out)
        self._assert_tapped_twice_same_point(tap, 540, 432)
        # <15% 强警告区 + 页面未变化 → F3-2 新口径：返回串整体替换为
        # 明确失败 ❌ 文案
        self.assertEqual(result, vision_tools.VISION_PAGE_UNCHANGED_FAIL)

    def test_just_below_40_percent_boundary_warns_only(self):
        # 40% 边界反例（下侧）：real_y=936 = 39% × 2400 < 960 → 只打
        # "请确认"警告、不偏移，tap 原坐标 (300, 936)；936 ≥ 360 →
        # 无 15% 提示、无强警告、无偏移日志
        self._write_screenshot(width=540, height=1200)
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (300, 936)")
        self._patch_client(content='{"x": 150, "y": 468}')
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            vision_tools.vision_tap_element("账号")
        out = buf.getvalue()
        self.assertEqual(out.count("⚠️ 目标位于屏幕上部，请确认"), 1)
        self.assertNotIn("极易误点到账号或搜索框", out)
        self.assertNotIn("视觉坐标可能定位到搜索框或状态栏", out)
        self.assertNotIn("实际执行坐标", out)
        self._assert_tapped_twice_same_point(tap, 300, 936)

    def test_just_above_40_percent_boundary_silent(self):
        # 40% 边界反例（上侧）：real_y=984 = 41% × 2400 ≥ 960 → 不警告
        # 不偏移，tap 原坐标 (300, 984)，无"实际执行坐标"行
        self._write_screenshot(width=540, height=1200)
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (300, 984)")
        self._patch_client(content='{"x": 150, "y": 492}')
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            vision_tools.vision_tap_element("账号")
        out = buf.getvalue()
        self.assertNotIn("目标位于屏幕上部", out)
        self.assertNotIn("极易误点到账号或搜索框", out)
        self.assertNotIn("视觉坐标可能定位到搜索框或状态栏", out)
        self.assertNotIn("实际执行坐标", out)
        self.assertIn("📏 [视觉缩放]", out)   # 其余日志不受影响
        self._assert_tapped_twice_same_point(tap, 300, 984)

    def test_change_detection_unchanged_reports_clear_failure(self):
        # 任务 3 后半 + F3-2 明确失败口径：重新截图与点击前留底 MD5 一致
        # （测试中 adb_screenshot 为 mock、不改写文件）→ 控制台一行简短
        # 原因说明 + 返回串精确等于 ❌ 未点中文案（替换原"（⚠️ 页面未
        # 发生变化，已尝试点击 2 次）"含糊附加段）；tap 仍恰两次——
        # 变化检测不做任何额外重试点击，adb_screenshot 恰两次（首次 +
        # 检测重截图）
        self._write_screenshot(width=540, height=1200)
        screenshot_mock = mock.MagicMock(return_value="✅")
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (492, 1062)")
        self._patch_client(content='{"x": 246, "y": 531}')
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "adb_screenshot",
                               screenshot_mock), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("WLAN")
        out = buf.getvalue()
        self.assertIn(
            "⚠️ 页面未发生变化，目标可能未点中，尝试滑动屏幕或重新寻找", out)
        self.assertNotIn("✅ 页面已变化", out)
        # 返回串精确等于新 ❌ 文案（锁死用户指定文案，不残留旧附加段）
        self.assertEqual(
            result,
            "❌ 视觉模型未点中目标，请尝试手动点击或换个清晰的图标")
        self.assertEqual(result, vision_tools.VISION_PAGE_UNCHANGED_FAIL)
        # tap 仍恰两次（无额外重试）；截图恰两次（首次 + 检测重截图）
        self._assert_tapped_twice_same_point(tap, 492, 1062)
        self.assertEqual(screenshot_mock.call_count, 2)

    def test_change_detection_page_changed_reports_effective_line(self):
        # 二次截图内容变化（第二次 adb_screenshot 重写截图文件）→ 打印
        # "✅ 页面已变化，点击已生效"，返回串不附加未变化段
        self._write_screenshot(width=540, height=1200)

        reshot_calls = {"count": 0}

        def _fake_screenshot():
            reshot_calls["count"] += 1
            if reshot_calls["count"] >= 2:
                # 与点击前留底内容不同 → MD5 变化
                with open(vision_tools.SCREENSHOT_PATH, "wb") as f:
                    f.write(_png_bytes(541, 1200))
            return "✅"

        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (492, 1062)")
        self._patch_client(content='{"x": 246, "y": 531}')
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "adb_screenshot",
                               side_effect=_fake_screenshot), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("WLAN")
        out = buf.getvalue()
        self.assertIn("✅ 页面已变化，点击已生效", out)
        self.assertNotIn("页面未发生变化", out)
        # F3-2 反例（测试 ③）：页面已变化 → 返回串不含 ❌ 未点中文案，
        # 保持成功口径；(492, 1062) ≥ 40% 屏高 → 顶部降级告知也不追加
        self.assertNotIn(vision_tools.VISION_PAGE_UNCHANGED_FAIL, result)
        self.assertNotIn("建议手动确认", result)
        self.assertEqual(
            result, "✅ 已模拟点击坐标: (492, 1062)（已执行二次确认点击）")

    def test_change_detection_md5_failure_keeps_main_flow(self):
        # MD5 计算失败（file_md5 返回 None）→ 检测静默降级：不崩溃、
        # 控制台与返回串均无检测结论，点击主流程结果不受影响
        self._write_screenshot(width=540, height=1200)
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (492, 1062)")
        self._patch_client(content='{"x": 246, "y": 531}')
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "file_md5", return_value=None), \
             mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("WLAN")
        out = buf.getvalue()
        self.assertNotIn("页面未发生变化", out)
        self.assertNotIn("页面已变化", out)
        self._assert_tapped_twice_same_point(tap, 492, 1062)
        self.assertEqual(
            result, "✅ 已模拟点击坐标: (492, 1062)（已执行二次确认点击）")

    def test_change_detection_skipped_when_confirm_retap_disabled(self):
        # VISION_CONFIRM_RETAP=0（无二次点击）：跳过变化检测——只点一次
        # 无从比对：不二次截图（adb_screenshot 共 1 次）、tap 一次、
        # 返回串无附加段
        self._write_screenshot(width=540, height=1200)
        screenshot_mock = mock.MagicMock(return_value="✅")
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (492, 1062)")
        self._patch_client(content='{"x": 246, "y": 531}')
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "VISION_CONFIRM_RETAP", False), \
             mock.patch.object(vision_tools, "adb_screenshot", screenshot_mock), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("WLAN")
        self.assertEqual(screenshot_mock.call_count, 1)
        tap.assert_called_once_with(492, 1062)
        self.assertEqual(result, "✅ 已模拟点击坐标: (492, 1062)")
        self.assertNotIn("页面未发生变化", buf.getvalue())

    def test_top_zone_note_appended_without_confirm_retap(self):
        # F3-1 补充：VISION_CONFIRM_RETAP=0（单次点击、跳过变化检测）
        # 时，顶部疑似区降级告知同样追加进返回串（聊天框可见）
        self._write_screenshot(width=1080, height=1200)
        screenshot_mock = mock.MagicMock(return_value="✅")
        tap = mock.MagicMock(return_value="✅ 已模拟点击坐标: (150, 298)")
        self._patch_client(content='{"x": 150, "y": 250}')
        buf = io.StringIO()
        with mock.patch.object(vision_tools, "VISION_CONFIRM_RETAP", False), \
             mock.patch.object(vision_tools, "adb_screenshot", screenshot_mock), \
             mock.patch.object(vision_tools, "adb_tap", tap), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(
                                   stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            result = vision_tools.vision_tap_element("WLAN")
        # 截图与屏幕等宽 → 缩放比 1.0；(150, 250) < 15% 线（360）→
        # 偏移 48px → (150, 298)；单次点击、无二次确认附加段
        tap.assert_called_once_with(150, 298)
        self.assertEqual(screenshot_mock.call_count, 1)
        self.assertEqual(
            result,
            "✅ 已模拟点击坐标: (150, 298) "
            "⚠️ 视觉模型可能识别到了顶部区域（如账号/搜索框），"
            "建议手动确认。")
        self.assertNotIn("页面未发生变化", buf.getvalue())

    def test_generic_exception_wrapped(self):
        # 非 SDK 分类的未知异常：不重试、原样包装（保持可排查）
        self._write_screenshot()
        create, _cls = self._patch_client(side_effect=ValueError("boom"))
        with mock.patch.object(vision_tools, "adb_screenshot", return_value="✅"), \
             mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")):
            result = vision_tools.vision_tap_element("设置")
        self.assertEqual(result, "❌ 视觉模型调用失败: boom")

    def test_get_screen_size_parses_and_falls_back(self):
        # 正常解析：返回解析值，无 ⚠️ 警告
        buf = io.StringIO()
        with mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="Physical size: 1080x2400")), \
             contextlib.redirect_stdout(buf):
            self.assertEqual(vision_tools.get_screen_size(), (1080, 2400))
        self.assertNotIn("⚠️ [视觉缩放]", buf.getvalue())

        # 输出无法解析 → 兜底 1080x2400 且不再静默：打印 ⚠️ 警告
        # （2026-10-01 用户指令：静默错误 → 可见错误）
        buf = io.StringIO()
        with mock.patch.object(vision_tools.subprocess, "run",
                               return_value=mock.MagicMock(stdout="error")), \
             contextlib.redirect_stdout(buf):
            self.assertEqual(vision_tools.get_screen_size(), (1080, 2400))
        self.assertIn("⚠️ [视觉缩放] 手机分辨率获取失败", buf.getvalue())
        self.assertIn("adb shell wm size", buf.getvalue())
        self.assertIn("1080x2400", buf.getvalue())

        # subprocess 异常 → 同样兜底 + ⚠️ 警告，不崩溃
        buf = io.StringIO()
        with mock.patch.object(vision_tools.subprocess, "run",
                               side_effect=Exception("no adb")), \
             contextlib.redirect_stdout(buf):
            self.assertEqual(vision_tools.get_screen_size(), (1080, 2400))
        self.assertIn("⚠️ [视觉缩放] 手机分辨率获取失败", buf.getvalue())


class EnvExampleVisionModelTests(unittest.TestCase):
    """.env.example：VISION_MODEL 默认值与紧邻注释（2026-10-01 用户指令）。

    背景：纯文本模型 qwen3.5-122b-a10b 被误填进 VISION_MODEL 导致视觉
    识别一直返回"未找到"——模板默认值改为 qwen-vl-max-latest，紧邻注释
    标注"必须使用带 VL 的视觉模型"。注意：模板默认值不影响代码缺省
    （xiaoju3.py 代码缺省保持空串，未配置仍走未配置提示，由
    test_unconfigured_model_hint 覆盖）。
    """

    def test_env_example_vision_model_default_and_comment(self):
        with open(os.path.join(_ROOT, ".env.example"),
                  "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("必须使用带 VL 的视觉模型", content)
        # VISION_MODEL= 恰好一行且为推荐视觉模型默认值（同时证明旧空值
        # 形态不再出现；splitlines 兼容 \n 与 \r\n）
        vision_lines = [ln.strip() for ln in content.splitlines()
                        if ln.strip().startswith("VISION_MODEL=")]
        self.assertEqual(vision_lines, ["VISION_MODEL=qwen-vl-max-latest"])


if __name__ == "__main__":
    unittest.main()
