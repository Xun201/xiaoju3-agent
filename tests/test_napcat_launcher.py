# -*- coding: utf-8 -*-
"""NapCat 静默拉起单元测试（2026-10-02；2026-10-08 方案 E 去提权化重构）。

覆盖：
- ensure_napcat 分支：无窗口直拉 launcher-user.bat（NapCat 官方免提权
  变体，cmd + CREATE_NO_WINDOW + DEVNULL，零 PowerShell 零 UAC——
  火绒「隐藏执行 PowerShell」拦截实锤后的根治形态）、已运行跳过、
  脚本缺失跳过；
- 泛用动词锚：Popen 命令行绝不出现 powershell（防提权路径回潮）；
- POSIX（香橙派）静默跳过（部署侧自管 NapCat）；
- main() 非 dry-run 时调用 ensure_napcat（--dry-run 零副作用既有契约不破坏）。

NapCat 是常驻服务：launcher 退出不杀（句柄不纳入生命周期管理，测试锁定
"不返回句柄"语义）。
"""
import os
import subprocess
import tempfile
import unittest
from unittest import mock

import xiaoju3_launcher as xl


class EnsureNapcatTests(unittest.TestCase):
    """ensure_napcat 分支全覆盖（依赖全注入，零真实进程/零真实 UAC）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_napcat_")
        self.bat = os.path.join(self.tmp, "launcher-user.bat")
        with open(self.bat, "w", encoding="utf-8") as f:
            f.write("@echo off\r\n")
        self.calls = []
        self.popen = lambda *a, **k: self.calls.append((a, k))
        self.out = []
        self.out_fn = self.out.append

    def _run(self, running=False, os_name="nt", napcat_dir=None):
        return xl.ensure_napcat(
            napcat_dir=napcat_dir or self.tmp,
            popen=self.popen,
            out=self.out_fn,
            running_fn=lambda: running,
            os_name=os_name,
        )

    def test_launches_user_bat_no_elevation(self):
        """未运行 → cmd /c 拉 launcher-user.bat（NapCat 官方免提权变体；
        CREATE_NO_WINDOW + 双 DEVNULL），零 PowerShell 零 UAC——方案 E
        去提权化（2026-10-08）：QQ 目录用户可写，注入写权限普通用户已
        具备，旧 powershell runAs 分支被火绒「隐藏执行 PowerShell」拦截。"""
        ok = self._run(running=False)
        self.assertTrue(ok)
        self.assertEqual(len(self.calls), 1)
        args, kwargs = self.calls[0]
        self.assertEqual(args[0][:2], ["cmd", "/c"])
        self.assertIn("launcher-user.bat", args[0][2])
        self.assertNotIn("powershell", " ".join(args[0]).lower())
        # cwd 参数形态锚（E3 轮 1 引号 bug 修复）：经 cwd 传目录，命令行
        # 绝不含 cd&& 拼接（list2cmdline+cmd 引号解析会坏，勿回退）
        self.assertEqual(kwargs.get("cwd"), self.tmp)
        self.assertNotIn("cd /d", args[0][2])
        if os.name == "nt":
            self.assertEqual(kwargs["creationflags"],
                             subprocess.CREATE_NO_WINDOW)
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertIn("✅ NapCat 已后台启动（无窗口）", self.out)

    def test_running_skips(self):
        """已在运行 → 跳过（用户口径文案），不 Popen，返回 False。"""
        ok = self._run(running=True)
        self.assertFalse(ok)
        self.assertEqual(self.calls, [])
        self.assertIn("ℹ️ NapCat 已在运行，跳过", self.out)

    def test_missing_bat_skips(self):
        """launcher-user.bat 缺失 → 跳过并提示路径，不 Popen。"""
        ok = self._run(napcat_dir=os.path.join(self.tmp, "nope"))
        self.assertFalse(ok)
        self.assertEqual(self.calls, [])
        self.assertTrue(any("未找到" in line for line in self.out))

    def test_prefers_user_bat_over_admin_bat(self):
        """优先级锚（方案 E 核心选择，2026-10-08）：目录里同时存在管理员版
        launcher.bat 与免提权版 launcher-user.bat → 必拉 user 版（零提权
        零 UAC 零 PowerShell——火绒「隐藏执行 PowerShell」拦截实锤后的
        根治形态），绝不回退管理员版。"""
        with open(os.path.join(self.tmp, "launcher.bat"), "w",
                  encoding="utf-8") as f:
            f.write("@echo off\r\n")
        ok = self._run(running=False)
        self.assertTrue(ok)
        args, _ = self.calls[0]
        self.assertIn("launcher-user.bat", args[0][2])
        self.assertNotIn("launcher.bat", args[0][2].replace(
            "launcher-user.bat", ""))   # 除 user 版外不含管理员版名

    def test_posix_skips_silently(self):
        """POSIX（香橙派）：NapCat 由部署侧管理——静默跳过，零输出零 Popen。"""
        ok = self._run(os_name="posix")
        self.assertFalse(ok)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.out, [])


class NapcatDetectorTests(unittest.TestCase):
    """_napcat_running 探测：psutil 扫描与 6099 端口回退。"""

    def test_psutil_name_scan_hits_napcat(self):
        psutil = mock.MagicMock()
        psutil.process_iter.return_value = [
            mock.MagicMock(info={"name": "QQ.exe"}),
            mock.MagicMock(info={"name": "NapCatWinBootMain.exe"}),
        ]
        with mock.patch.dict("sys.modules", {"psutil": psutil}):
            self.assertTrue(xl._napcat_running())

    def test_psutil_no_hit_falls_back_to_port(self):
        psutil = mock.MagicMock()
        psutil.process_iter.return_value = [
            mock.MagicMock(info={"name": "QQ.exe"})]
        with mock.patch.dict("sys.modules", {"psutil": psutil}), \
                mock.patch("socket.create_connection",
                           side_effect=OSError("refused")):
            self.assertFalse(xl._napcat_running())

    def test_port_fallback_hits(self):
        import socket as real_socket
        with mock.patch.dict("sys.modules", {"psutil": None}), \
                mock.patch.object(real_socket, "create_connection",
                                  return_value=mock.MagicMock()):
            self.assertTrue(xl._napcat_running())


class MainHookTests(unittest.TestCase):
    """main() 集成点：非 dry-run 调 ensure_napcat；--dry-run 零副作用。"""

    def test_main_calls_ensure_napcat(self):
        # 单实例防重（方案 b）：探测空闲才走到 ensure_napcat（patch 掉真实端口探测，
        # 测试不依赖当前 5003 是否有服务在跑）
        with mock.patch.object(xl, "is_port_in_use", return_value=False), \
                mock.patch.object(xl, "ensure_napcat") as mensure, \
                mock.patch.object(xl.subprocess, "Popen"), \
                mock.patch.object(xl, "XiaojuLauncher") as mlauncher:
            mlauncher.return_value.run.return_value = 0
            code = xl.main([])
        self.assertEqual(code, 0)
        mensure.assert_called_once_with()

    def test_dry_run_skips_ensure_napcat(self):
        with mock.patch.object(xl, "ensure_napcat") as mensure, \
                mock.patch.object(xl.subprocess, "Popen",
                                  side_effect=AssertionError(
                                      "dry-run 不允许拉起子进程")):
            code = xl.main(["--dry-run"])
        self.assertEqual(code, 0)
        mensure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
