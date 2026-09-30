# -*- coding: utf-8 -*-
"""hardware_profiler 硬件探测单元测试（全部离线，psutil/subprocess 打桩）。

覆盖（硬件自适应路由口径）：
- 独显检测：nvidia-smi 成功 → high；失败/异常 → 非独显路径；
- ARM 架构（aarch64/armv）→ low（开发板/云端优先）；
- 内存门槛：无独显 x86 时 ≥8GB → medium，<8GB → low；
- psutil 不可用 / 探测异常 → 降级 medium；
- total_ram_gb / has_discrete_gpu / is_arm 单元行为与阈值边界。
"""
import contextlib
import io
import os
import sys
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import hardware_profiler as hp


class RamTests(unittest.TestCase):
    def test_total_ram_gb_converts_bytes(self):
        with mock.patch.object(hp, "psutil") as mp:
            mp.virtual_memory.return_value.total = 8 * 1024 ** 3
            self.assertAlmostEqual(hp.total_ram_gb(), 8.0)

    def test_total_ram_gb_none_when_psutil_missing(self):
        with mock.patch.object(hp, "psutil", None):
            self.assertIsNone(hp.total_ram_gb())


class GpuTests(unittest.TestCase):
    def test_nvidia_smi_success_means_dgpu(self):
        with mock.patch("subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            self.assertTrue(hp.has_discrete_gpu())

    def test_nvidia_smi_failure_means_no_dgpu(self):
        with mock.patch("subprocess.run") as mrun:
            mrun.return_value.returncode = 1
            self.assertFalse(hp.has_discrete_gpu())

    def test_nvidia_smi_missing_means_no_dgpu(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            self.assertFalse(hp.has_discrete_gpu())

    def test_gpu_probe_has_short_timeout(self):
        with mock.patch("subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            hp.has_discrete_gpu()
            self.assertEqual(mrun.call_args.kwargs.get("timeout"), 2)


class ArchTests(unittest.TestCase):
    def test_aarch64_is_arm(self):
        with mock.patch.object(hp.platform, "machine", return_value="aarch64"):
            self.assertTrue(hp.is_arm())

    def test_armv7_is_arm(self):
        with mock.patch.object(hp.platform, "machine", return_value="ARMv7"):
            self.assertTrue(hp.is_arm())

    def test_x86_64_is_not_arm(self):
        with mock.patch.object(hp.platform, "machine", return_value="AMD64"):
            self.assertFalse(hp.is_arm())


class DetectTierTests(unittest.TestCase):
    """推荐规则：独显→high；ARM→low；无独显 x86 按 8GB 内存门槛分 medium/low。"""

    def _detect(self, gpu, ram, arch="AMD64"):
        with mock.patch.object(hp, "has_discrete_gpu", return_value=gpu), \
                mock.patch.object(hp, "total_ram_gb", return_value=ram), \
                mock.patch.object(hp, "is_arm", return_value=arch.startswith("aarch") or "armv" in arch):
            return hp.detect_tier()

    def test_dgpu_means_high(self):
        self.assertEqual(self._detect(gpu=True, ram=4), "high")

    def test_arm_means_low_even_with_big_ram(self):
        self.assertEqual(self._detect(gpu=False, ram=16, arch="aarch64"), "low")

    def test_x86_8gb_means_medium(self):
        self.assertEqual(self._detect(gpu=False, ram=8.0), "medium")

    def test_x86_16gb_means_medium(self):
        self.assertEqual(self._detect(gpu=False, ram=16.0), "medium")

    def test_x86_4gb_means_low(self):
        self.assertEqual(self._detect(gpu=False, ram=4.0), "low")

    def test_ram_unknown_degrades_medium(self):
        self.assertEqual(self._detect(gpu=False, ram=None), "medium")

    def test_probe_exception_degrades_medium(self):
        with mock.patch.object(hp, "has_discrete_gpu", side_effect=OSError("boom")), \
                mock.patch.object(hp, "total_ram_gb", side_effect=OSError("boom")), \
                mock.patch.object(hp, "is_arm", side_effect=OSError("boom")):
            self.assertEqual(hp.detect_tier(), "medium")


class PrintReportTests(unittest.TestCase):
    def test_print_report_returns_tier_and_prints(self):
        with mock.patch.object(hp, "has_discrete_gpu", return_value=False), \
                mock.patch.object(hp, "total_ram_gb", return_value=16.0), \
                mock.patch.object(hp, "is_arm", return_value=False):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                tier = hp.print_report()
        self.assertEqual(tier, "medium")
        self.assertIn("推荐档位：medium", buf.getvalue())
        self.assertIn("DEVICE_TIER=medium", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
