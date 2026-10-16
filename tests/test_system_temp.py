# -*- coding: utf-8 -*-
"""系统温度读取锚（#系统温度一期：pynvml GPU 温度，2026-10-16）。
mock 全走，零硬件依赖（无 N 卡的 CI/机器同样可跑）。"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import xiaoju3_dashboard as dash


class NvmlTempTests(unittest.TestCase):
    """_temp_from_nvml：异常吞返回 None（不炸链）+成功读值。"""

    def test_nvml_exception_swallowed_returns_none(self):
        """pynvml init 抛异常（无驱动机器/未装包）→ None 落回原链，绝不炸。"""
        import types
        fake = types.ModuleType("pynvml")

        def _boom():
            raise RuntimeError("driver not loaded")
        fake.nvmlInit = _boom
        with mock.patch.dict(sys.modules, {"pynvml": fake}):
            self.assertIsNone(dash._temp_from_nvml())

    def test_nvml_success_returns_float(self):
        """正常路径：init→取句柄→读温度→shutdown 全链走通返回 float。"""
        import types
        fake = types.ModuleType("pynvml")
        fake.NVML_TEMPERATURE_GPU = 0
        fake.nvmlInit = lambda: None
        fake.nvmlDeviceGetHandleByIndex = lambda i: f"handle{i}"
        fake.nvmlDeviceGetTemperature = lambda h, t: 48
        fake.nvmlShutdown = lambda: None
        with mock.patch.dict(sys.modules, {"pynvml": fake}):
            self.assertEqual(dash._temp_from_nvml(), 48.0)

    def test_chain_prefers_nvml_when_available(self):
        """链首接线：nvml 有值时 get_cpu_temp 直接用它（WMI/sys 不再触达）。"""
        import types
        fake = types.ModuleType("pynvml")
        fake.NVML_TEMPERATURE_GPU = 0
        fake.nvmlInit = lambda: None
        fake.nvmlDeviceGetHandleByIndex = lambda i: "h"
        fake.nvmlDeviceGetTemperature = lambda h, t: 47
        fake.nvmlShutdown = lambda: None
        with mock.patch.dict(sys.modules, {"pynvml": fake}), \
                mock.patch.object(dash, "_temp_from_psutil", return_value=99.0), \
                mock.patch.object(dash, "_temp_from_wmi", return_value=98.0):
            self.assertEqual(dash.get_cpu_temp(), 47.0)

    def test_no_driver_falls_through_to_no_temp(self):
        """无驱动机器全链失败 → 仍回 "暂无温度"（负向锁：不炸、不返回 0.0）。"""
        import types
        fake = types.ModuleType("pynvml")

        def _boom():
            raise RuntimeError("no nvidia")
        fake.nvmlInit = _boom
        with mock.patch.dict(sys.modules, {"pynvml": fake}), \
                mock.patch.object(dash, "_temp_from_psutil", return_value=None), \
                mock.patch.object(dash, "_temp_from_wmi", return_value=None), \
                mock.patch.object(dash, "_temp_from_sys_thermal", return_value=None):
            self.assertEqual(dash.get_cpu_temp(), dash.NO_TEMP_TEXT)


if __name__ == "__main__":
    unittest.main()


class StripPollutionG1G2Tests(unittest.TestCase):
    """#322 对齐 G1/G2（2026-10-17）：未闭合标签行首剥+正文引用不误伤+
    空白变体剥+合法 CQ 码保留。"""

    def test_g1_unclosed_leading_stripped(self):
        """行首未闭合标签（无闭标签）→ 整段剥（半截污染形态）。"""
        from chain_of_thought import strip_pollution
        self.assertEqual(strip_pollution("[计划]先做A再做B"), "")
        self.assertEqual(strip_pollution("[think]只吐开头"), "")

    def test_g1_inline_reference_not_stripped(self):
        """正文引用 [计划] 字样（非行首）→ 不误伤（G1 行首锚防误伤）。"""
        from chain_of_thought import strip_pollution
        self.assertIn("[计划]", strip_pollution("与[计划]正常段聊"))
        self.assertIn("[CQ:image,x]", strip_pollution("看图[CQ:image,x]与[计划]段"))

    def test_g2_whitespace_variant_stripped(self):
        """标签内空白变体 [ think ]...[ /think ] → 剥（留正文）。"""
        from chain_of_thought import strip_pollution
        self.assertEqual(strip_pollution("好的[ think ]推理[ /think ]正文"), "好的正文")
