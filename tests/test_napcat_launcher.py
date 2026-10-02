# -*- coding: utf-8 -*-
"""NapCat 静默拉起单元测试（2026-10-02，全部离线：popen/检测/身份全注入）。

覆盖：
- ensure_napcat 四分支：管理员拉起（cmd + CREATE_NO_WINDOW + DEVNULL）、
  非管理员 PowerShell runAs 隐藏路径、已运行跳过、launcher.bat 缺失跳过；
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
        self.bat = os.path.join(self.tmp, "launcher.bat")
        with open(self.bat, "w", encoding="utf-8") as f:
            f.write("@echo off\r\n")
        self.calls = []
        self.popen = lambda *a, **k: self.calls.append((a, k))
        self.out = []
        self.out_fn = self.out.append

    def _run(self, running=False, admin=True, os_name="nt",
             napcat_dir=None):
        return xl.ensure_napcat(
            napcat_dir=napcat_dir or self.tmp,
            popen=self.popen,
            out=self.out_fn,
            running_fn=lambda: running,
            is_admin_fn=lambda: admin,
            os_name=os_name,
        )

    def test_admin_launches_hidden_cmd(self):
        """管理员 + 未运行 → cmd /c 拉 launcher.bat（CREATE_NO_WINDOW +
        双 DEVNULL），日志为用户口径文案，返回 True。"""
        ok = self._run(running=False, admin=True)
        self.assertTrue(ok)
        self.assertEqual(len(self.calls), 1)
        args, kwargs = self.calls[0]
        self.assertEqual(args[0][:2], ["cmd", "/c"])
        self.assertIn("launcher.bat", args[0][2])
        if os.name == "nt":
            self.assertEqual(kwargs["creationflags"],
                             subprocess.CREATE_NO_WINDOW)
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertIn("✅ NapCat 已后台启动（无窗口）", self.out)

    def test_non_admin_uses_hidden_runas(self):
        """非管理员 → PowerShell Start-Process -Verb runAs -WindowStyle
        Hidden（launcher.bat 自带管理员自检，直接跑会弹可见黑框）。"""
        ok = self._run(running=False, admin=False)
        self.assertTrue(ok)
        args, kwargs = self.calls[0]
        self.assertEqual(args[0][0], "powershell")
        self.assertIn("-Verb runAs", args[0][3])
        self.assertIn("-WindowStyle Hidden", args[0][3])
        self.assertIn("UAC", " ".join(self.out))

    def test_running_skips(self):
        """已在运行 → 跳过（用户口径文案），不 Popen，返回 False。"""
        ok = self._run(running=True, admin=True)
        self.assertFalse(ok)
        self.assertEqual(self.calls, [])
        self.assertIn("ℹ️ NapCat 已在运行，跳过", self.out)

    def test_missing_bat_skips(self):
        """launcher.bat 缺失 → 跳过并提示路径，不 Popen。"""
        ok = self._run(napcat_dir=os.path.join(self.tmp, "nope"))
        self.assertFalse(ok)
        self.assertEqual(self.calls, [])
        self.assertTrue(any("未找到" in line for line in self.out))

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
        with mock.patch.object(xl, "ensure_napcat") as mensure, \
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
