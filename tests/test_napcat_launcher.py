# -*- coding: utf-8 -*-
"""NapCat 静默拉起单元测试（2026-10-02；2026-10-08 方案 E 去提权化重构）。

覆盖：
- ensure_napcat 分支：无窗口直拉 launcher-user.bat（NapCat 官方免提权
  变体，cmd + CREATE_NO_WINDOW，零 PowerShell 零 UAC——火绒「隐藏执行
  PowerShell」拦截实锤后的根治形态）、已运行跳过、脚本缺失跳过；
- #305 F2 三态探测（2026-10-11）：QQ.exe 按可执行路径二分——NapCat 目录
  副本（裸态）杀后重拉；用户日常 QQ（目录外）绝不杀且阻止 fire（锁占用
  防僵尸树）；exe 读取失败保守归 other；
- #305 F3 fire 日志：napcat_fire_<ts>.log 落盘+首行探测快照+stderr 合流+
  创建失败回退 DEVNULL+N=10 轮换；
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


class _FakeQqProc:
    """psutil.Process 假体：info/terminate/kill/wait 最小面（#305 F2 测试）。"""

    def __init__(self, pid=1, exe=None, name="QQ.exe"):
        self.pid = pid
        self.info = {"name": name, "exe": exe}
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return 0


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
        self.sleeps = []
        self.sleep_fn = self.sleeps.append

    def _run(self, running=False, os_name="nt", napcat_dir=None,
             qq_iter=None, fire_log_dir=None):
        return xl.ensure_napcat(
            napcat_dir=napcat_dir or self.tmp,
            popen=self.popen,
            out=self.out_fn,
            running_fn=lambda: running,
            os_name=os_name,
            qq_iter_fn=lambda attrs=None: list(qq_iter or []),
            sleep=self.sleep_fn,
            fire_log_dir=fire_log_dir if fire_log_dir is not None
            else self.tmp,
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
        # #305 F3：fire 输出落 napcat_fire_<ts>.log（首行探测快照），stderr 合流
        self.assertTrue(hasattr(kwargs["stdout"], "write"))
        self.assertTrue(kwargs["stdout"].closed)   # Python 侧即收，子进程持继承句柄
        self.assertIn("napcat_fire_", os.path.basename(kwargs["stdout"].name))
        self.assertEqual(kwargs["stderr"], subprocess.STDOUT)
        self.assertIn("✅ NapCat 已后台启动（无窗口）", self.out)
        with open(kwargs["stdout"].name, encoding="utf-8") as f:
            first = f.readline()
        self.assertIn("🔍 fire 探测快照", first)
        self.assertIn("napcat_running=False", first)
        self.assertIn("plain_napcat_qq=0", first)
        self.assertIn("other_qq=0", first)
        self.assertIn("分支=直接fire", first)

    def test_plain_napcat_copy_qq_killed_then_fire(self):
        """#305 F2：裸 NapCat QQ（exe 在 NapCat 目录副本下）→ 只杀副本 +
        锁宽限（10s）+ 正常 fire；快照记 plain_napcat_qq=N（按路径判定
        非进程名——用户拍板 2026-10-11）。"""
        plain1 = _FakeQqProc(11, os.path.join(self.tmp, "QQ.exe"))
        plain2 = _FakeQqProc(12, os.path.join(self.tmp, "QQ.exe"))
        ok = self._run(qq_iter=[plain1, plain2])
        self.assertTrue(ok)
        self.assertTrue(plain1.terminated and plain2.terminated)
        self.assertEqual(self.sleeps, [xl.NAPCAT_QQ_LOCK_GRACE_SECONDS])
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(any("NapCat 副本 QQ（裸态）×2" in line
                            for line in self.out))
        self.assertTrue(any("裸态 QQ 终止完成" in line for line in self.out))
        _, kwargs = self.calls[0]
        with open(kwargs["stdout"].name, encoding="utf-8") as f:
            first = f.readline()
        self.assertIn("plain_napcat_qq=2", first)
        self.assertIn("分支=杀副本后fire", first)

    def test_daily_qq_outside_napcat_never_killed_blocks_fire(self):
        """#305 F2 核心安全锚：用户日常 QQ（exe 在 NapCat 目录之外，含 exe
        读取失败者）绝不进 kill 路径，且阻止 fire（锁被日常 QQ 占用，
        硬拉=锁冲突僵尸树——昨晚 20+ 幽灵同型）。"""
        daily = _FakeQqProc(21, "D:\\Ruanjian\\QQ\\QQ.exe")
        opaque = _FakeQqProc(22, None)   # exe 读取失败 → 保守归 other
        ok = self._run(qq_iter=[daily, opaque])
        self.assertFalse(ok)
        self.assertEqual(self.calls, [])
        self.assertFalse(daily.terminated)
        self.assertFalse(opaque.terminated)
        self.assertEqual(self.sleeps, [])   # 未进宽限分支
        self.assertTrue(any("不干预" in line for line in self.out))

    def test_plain_killed_but_daily_qq_blocks_fire(self):
        """#305 F2：副本与日常 QQ 并存 → 副本照杀、日常绝不动、不放 fire。"""
        plain = _FakeQqProc(31, os.path.join(self.tmp, "QQ.exe"))
        daily = _FakeQqProc(32, "D:\\Ruanjian\\QQ\\QQ.exe")
        ok = self._run(qq_iter=[plain, daily])
        self.assertFalse(ok)
        self.assertTrue(plain.terminated)    # 副本照杀
        self.assertFalse(daily.terminated)   # 日常绝不动
        self.assertEqual(self.calls, [])     # 但不放 fire
        self.assertEqual(self.sleeps, [])
        self.assertTrue(any("跳过本次 NapCat 拉起" in line
                            for line in self.out))

    def test_fire_log_fallback_devnull_on_oserror(self):
        """#305 F3 兜底锚：fire 日志创建失败（目录路径实为文件等 OSError）→
        回退 DEVNULL 形态，fire 照常执行绝不阻断。"""
        blocker = os.path.join(self.tmp, "not_a_dir")
        with open(blocker, "w", encoding="utf-8") as f:
            f.write("x")
        ok = self._run(fire_log_dir=blocker)
        self.assertTrue(ok)
        self.assertEqual(len(self.calls), 1)
        _, kwargs = self.calls[0]
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.STDOUT)

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


class NapcatFireLogTests(unittest.TestCase):
    """#305 F3：fire 日志目录锚 + 轮换。"""

    def test_fire_log_dir_default_endswith_agent_state(self):
        """fire 日志落 agent_state（xiaoju3.AGENT_STATE_DIR 优先，
        frozen 路径陷阱铁律——禁 __file__ fallback）。"""
        d = xl._napcat_fire_log_dir()
        self.assertTrue(d.replace("/", "\\").endswith("agent_state"))

    def test_prune_keeps_latest_ten(self):
        """napcat_fire_*.log 轮换：保留最近 NAPCAT_FIRE_LOG_KEEP 份，
        最旧被清（mtime 排序，与 prune_dashboard_logs 同款口径）。"""
        tmp = tempfile.mkdtemp(prefix="xiaoju3_firelog_")
        for i in range(12):
            p = os.path.join(tmp, f"napcat_fire_{i:02d}.log")
            with open(p, "w", encoding="utf-8") as f:
                f.write("x")
            os.utime(p, (1000000 + i * 10, 1000000 + i * 10))
        kept, removed = xl.prune_napcat_fire_logs(log_dir=tmp)
        self.assertEqual((kept, removed), (10, 2))
        remaining = sorted(n for n in os.listdir(tmp) if n.endswith(".log"))
        self.assertEqual(len(remaining), 10)
        self.assertNotIn("napcat_fire_00.log", remaining)   # 最旧被清
        self.assertNotIn("napcat_fire_01.log", remaining)
        self.assertIn("napcat_fire_11.log", remaining)      # 最新保留

    def test_prune_missing_dir_silent(self):
        """目录缺失 → (0, 0) 静默（清理绝不影响主流程）。"""
        self.assertEqual(xl.prune_napcat_fire_logs(
            log_dir=os.path.join(tempfile.mkdtemp(), "nope")), (0, 0))


class QqPlainProbeTests(unittest.TestCase):
    """#305 F2：_qq_plain_running / _classify_qq_processes 路径判定锚。"""

    def test_plain_running_true_for_napcat_dir_exe(self):
        """exe 位于 NapCat 目录下 → 判裸态（NapCat Shell 副本）。"""
        tmp = tempfile.mkdtemp(prefix="xiaoju3_plain_")
        plain = _FakeQqProc(1, os.path.join(tmp, "QQ.exe"))
        self.assertTrue(xl._qq_plain_running(
            napcat_dir=tmp, iter_fn=lambda attrs=None: [plain]))

    def test_plain_running_false_for_daily_qq(self):
        """exe 在 NapCat 目录之外（用户日常 D:\\Ruanjian\\QQ）→ 绝不判裸态。"""
        daily = _FakeQqProc(2, "D:\\Ruanjian\\QQ\\QQ.exe")
        plain, other = xl._classify_qq_processes(
            napcat_dir="D:\\NapCat", iter_fn=lambda attrs=None: [daily])
        self.assertEqual((plain, other), ([], 1))
        self.assertFalse(xl._qq_plain_running(
            napcat_dir="D:\\NapCat", iter_fn=lambda attrs=None: [daily]))

    def test_non_qq_names_ignored(self):
        """非 QQ.exe 名（BootMain 等）不进二分——napcat 名探测归
        running_fn 管，两探针职责分离。"""
        boot = _FakeQqProc(3, None, name="NapCatWinBootMain.exe")
        plain, other = xl._classify_qq_processes(
            napcat_dir="D:\\NapCat", iter_fn=lambda attrs=None: [boot])
        self.assertEqual((plain, other), ([], 0))


if __name__ == "__main__":
    unittest.main()
