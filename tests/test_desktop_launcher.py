# -*- coding: utf-8 -*-
"""桌面软件化主入口（desktop_launcher）单元测试（全部离线）。

覆盖（S3 桌面软件化任务口径；pywebview 真窗口不自动化测试——无头环境不可行，
以纯函数 + 静态断言 + mock webview/subprocess/psutil 覆盖）：
- 缺 pywebview（sys.modules 置 None）→ main 中文提示退出，返回码 1；
- 角色分流 route_argv（步 A4a）：无标志=desktop，--xj3-role=* 归位；
- 后台启动器拉起：:5002/:5003 未监听时经 subprocess.Popen 后台拉起
  xiaoju3_launcher.py（命令行含该脚本名、stdio 全 DEVNULL）；两端口均已
  监听 → 跳过拉起并提示"复用现有进程"；脚本缺失/拉起失败 → 跳过不报错；
- 关闭清理：webview.start 返回（窗口关闭）后 stop_backend_launcher 整树终止
  与 stop_backend_launcher 均被调用；stop_backend_launcher 内部
  psutil 进程树 terminate / 无 psutil 时 Windows taskkill /T /F、POSIX
  killpg、proc.kill 兜底回收句柄；proc 为 None 时绝不误杀；
- 窗口形态：标题"小橘3号 · 控制台"、1200x800、加载本机回环 /console
  （绝不出现外网 URL）；
- 启动探测：main.py（:5002）未运行且启动器缺位 → 打印"主程序未启动，
  聊天功能受限"，窗口仍照常创建；自拉启动器途中不打过时提示；在线不提示；
- _is_main_running / _is_port_listening：socket 连接探测（mock 子进程级
  副作用）；
- 真实内置服务（127.0.0.1 回环，离线）：随机端口绑定成功、/console 经
  HTTP 200 可达（loopback 非外网）；stop 后服务线程终止、端口释放
  （M4 机制零回退）。

mock 注意：webview / psutil 走 sys.modules 注入（patch.dict 自动还原）；
socket / subprocess / os.path / 服务启停全部 mock.patch 还原，绝不污染
真实环境、不真拉起任何进程。
"""
import contextlib
import io
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import types
import unittest
import urllib.request
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import desktop_launcher as launcher  # noqa: E402
import paths  # noqa: E402  # frozen 分流用例需 mock 双根标志


@contextlib.contextmanager
def _fake_webview(module):
    """向 sys.modules 注入伪 webview 模块（patch.dict 结束自动还原）。"""
    with mock.patch.dict(sys.modules, {"webview": module}):
        yield module


def _no_psutil():
    """sys.modules 注入 psutil=None：强制 `import psutil` 走 ImportError 分支。"""
    return mock.patch.dict(sys.modules, {"psutil": None})


class ServePortRetiredTests(unittest.TestCase):
    """--serve-port/内置服务退役反向锚（端口修复 P2）：形态不得回流。"""

    def test_serve_port_and_builtin_server_retired(self):
        src = open(os.path.join(PROJECT_ROOT, "desktop_launcher.py"),
                   encoding="utf-8").read()
        self.assertNotIn("--serve-port", src)
        self.assertNotIn("start_local_server", src)
        self.assertNotIn("make_server", src)


class MissingWebviewTests(unittest.TestCase):
    """缺 pywebview：中文提示退出，不让 import 崩溃。"""

    def test_missing_webview_prints_chinese_and_returns_1(self):
        err = io.StringIO()
        with _fake_webview(None), contextlib.redirect_stderr(err):
            rc = launcher.main([])
        self.assertEqual(rc, 1)
        self.assertIn("pywebview", err.getvalue())
        self.assertIn("离线桌面", err.getvalue())   # 中文提示

    def test_missing_webview_no_window_no_probe(self):
        """缺库快速失败：不拉后台服务、不创建窗口、不探测。"""
        err = io.StringIO()
        with _fake_webview(None), contextlib.redirect_stderr(err),                 mock.patch.object(launcher, "ensure_backend_services") as me,                 mock.patch.object(launcher, "wait_for_dashboard_ready") as mw,                 mock.patch.object(launcher, "_is_main_running") as mp:
            rc = launcher.main([])
        self.assertEqual(rc, 1)
        me.assert_not_called()
        mw.assert_not_called()
        mp.assert_not_called()


class EnsureBackendServicesTests(unittest.TestCase):
    """后台服务决策：端口已监听跳过、未监听 Popen 拉启动器、脚本缺失跳过。"""

    def _patch_script_exists(self, exists):
        return mock.patch.object(launcher.os.path, "isfile",
                                 return_value=exists)

    def test_both_ports_listening_skips_and_reuses(self):
        """:5002/:5003 已监听 → 跳过拉起，提示复用现有进程（绝不 Popen）。"""
        out = io.StringIO()
        with mock.patch.object(launcher, "_is_port_listening",
                               return_value=True), \
                mock.patch.object(launcher.subprocess, "Popen") as mp, \
                contextlib.redirect_stdout(out):
            proc = launcher.ensure_backend_services()
        self.assertIsNone(proc)
        mp.assert_not_called()
        self.assertIn("复用现有进程", out.getvalue())

    def test_ports_down_spawns_launcher_via_popen(self):
        """端口未监听 → Popen 命令行含 xiaoju3_launcher.py，stdio 全 DEVNULL。"""
        fake_proc = mock.MagicMock()
        fake_proc.pid = 4321
        out = io.StringIO()
        with mock.patch.object(launcher, "_is_port_listening",
                               return_value=False), \
                self._patch_script_exists(True), \
                mock.patch.object(launcher.subprocess, "Popen",
                                  return_value=fake_proc) as mp, \
                contextlib.redirect_stdout(out):
            proc = launcher.ensure_backend_services()
        self.assertIs(proc, fake_proc)
        args, kwargs = mp.call_args
        self.assertEqual(len(args[0]), 2)
        self.assertTrue(str(args[0][1]).endswith("xiaoju3_launcher.py"))
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        if os.name == "nt":
            self.assertEqual(kwargs["creationflags"],
                             launcher._WIN_CREATE_NO_WINDOW)  # 防闪黑窗
        else:
            self.assertTrue(kwargs["start_new_session"])     # 独立进程组
        self.assertIn("xiaoju3_launcher.py", out.getvalue())
        self.assertIn("4321", out.getvalue())

    def test_windowless_python_prefers_pythonw(self):
        """后台子树解释器（2026-10-02 用户口径：pythonw 无窗口形态）：
        pythonw 场景原样返回（bat 主链路 sys.executable 即 pythonw，无窗口
        形态沿子树传导）；控制台 python 场景解析同目录 pythonw.exe 孪生；
        孪生缺席回退 sys.executable（CREATE_NO_WINDOW 仍防黑窗）。"""
        fake_pyw = os.path.join("some", "dir", "pythonw.exe")
        fake_py = os.path.join("some", "dir", "python.exe")
        with mock.patch.object(launcher.sys, "executable", fake_pyw):
            self.assertEqual(launcher._windowless_python(), fake_pyw)
        with mock.patch.object(launcher.sys, "executable", fake_py), \
                mock.patch.object(launcher.os.path, "isfile",
                                  return_value=True):
            self.assertEqual(launcher._windowless_python(), fake_pyw)
        with mock.patch.object(launcher.sys, "executable", fake_py), \
                mock.patch.object(launcher.os.path, "isfile",
                                  return_value=False):
            self.assertEqual(launcher._windowless_python(), fake_py)

    def test_script_missing_skips_launch(self):
        """xiaoju3_launcher.py 缺失：提示跳过，不 Popen、返回 None 不报错。"""
        out = io.StringIO()
        with mock.patch.object(launcher, "_is_port_listening",
                               return_value=False), \
                self._patch_script_exists(False), \
                mock.patch.object(launcher.subprocess, "Popen") as mp, \
                contextlib.redirect_stdout(out):
            proc = launcher.ensure_backend_services()
        self.assertIsNone(proc)
        mp.assert_not_called()
        self.assertIn("未找到 xiaoju3_launcher.py", out.getvalue())

    def test_popen_oserror_returns_none(self):
        """Popen 系统级失败（OSError）：中文提示、返回 None，不让窗口崩。"""
        err = io.StringIO()
        with mock.patch.object(launcher, "_is_port_listening",
                               return_value=False), \
                self._patch_script_exists(True), \
                mock.patch.object(launcher.subprocess, "Popen",
                                  side_effect=OSError("boom")), \
                contextlib.redirect_stderr(err):
            proc = launcher.ensure_backend_services()
        self.assertIsNone(proc)
        self.assertIn("后台服务拉起失败", err.getvalue())


class StopBackendLauncherTests(unittest.TestCase):
    """窗口关闭 → 整树终止启动器：psutil 优先 / taskkill 兜底 / 句柄回收。"""

    def _fake_psutil(self):
        """构造伪 psutil 模块：Error 必须为真异常类（供 except 捕获）。"""
        parent, child = mock.MagicMock(), mock.MagicMock()
        parent.children.return_value = [child]
        mod = mock.MagicMock()
        mod.Error = type("FakePsutilError", (Exception,), {})
        mod.NoSuchProcess = type("FakeNoSuchProcess", (Exception,), {})
        mod.Process.return_value = parent
        mod.wait_procs.return_value = ([parent, child], [])  # 全部优雅退出
        return mod, parent, child

    def test_none_proc_noop(self):
        """复用现有进程/脚本缺失（proc=None）：绝不误杀任何进程。"""
        with mock.patch.object(launcher.subprocess, "run") as mrun:
            launcher.stop_backend_launcher(None)
        mrun.assert_not_called()

    def test_already_exited_noop(self):
        """启动器已自行退出：不 taskkill、不 kill，直接返回。"""
        proc = mock.MagicMock()
        proc.poll.return_value = 0
        with _no_psutil(), mock.patch.object(launcher.os, "name", "nt"), \
                mock.patch.object(launcher.subprocess, "run") as mrun:
            launcher.stop_backend_launcher(proc)
        mrun.assert_not_called()
        proc.kill.assert_not_called()

    def test_psutil_tree_terminate_and_handle_reap(self):
        """psutil 路径：进程树（父+子）terminate，句柄 wait 回收，无需强杀。"""
        mod, parent, child = self._fake_psutil()
        proc = mock.MagicMock()
        proc.poll.return_value = None
        proc.pid = 111
        with mock.patch.dict(sys.modules, {"psutil": mod}):
            launcher.stop_backend_launcher(proc)
        mod.Process.assert_called_once_with(111)
        parent.terminate.assert_called_once()
        child.terminate.assert_called_once()
        parent.kill.assert_not_called()      # 全部退出，kill 兜底未触发
        proc.wait.assert_called()            # 自身句柄已回收

    def test_no_psutil_windows_uses_taskkill_tree(self):
        """psutil 未装 + Windows：taskkill /T /F /PID 整树强杀。"""
        proc = mock.MagicMock()
        proc.poll.return_value = None
        proc.pid = 2222
        with _no_psutil(), mock.patch.object(launcher.os, "name", "nt"), \
                mock.patch.object(launcher.subprocess, "run") as mrun:
            launcher.stop_backend_launcher(proc)
        argv = mrun.call_args[0][0]
        self.assertEqual(argv[:4], ["taskkill", "/T", "/F", "/PID"])
        self.assertEqual(argv[4], "2222")
        proc.wait.assert_called()            # 兜底回收句柄

    def test_no_psutil_posix_killpg_process_group(self):
        """psutil 未装 + POSIX：killpg 向独立进程组发 SIGTERM。"""
        proc = mock.MagicMock()
        proc.poll.return_value = None
        proc.pid = 3333
        with _no_psutil(), mock.patch.object(launcher.os, "name", "posix"), \
                mock.patch.object(launcher.os, "getpgid", create=True,
                                  return_value=4444), \
                mock.patch.object(launcher.os, "killpg", create=True) as mkillpg:
            launcher.stop_backend_launcher(proc)
        mkillpg.assert_called_once_with(4444, signal.SIGTERM)
        proc.wait.assert_called()

    def test_wait_timeout_fallback_kill(self):
        """兜底：wait 超时 → 强杀自身并再回收句柄（僵尸句柄零残留）。"""
        proc = mock.MagicMock()
        proc.poll.return_value = None
        proc.pid = 5555
        proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="x", timeout=1),
                                 0]
        with _no_psutil(), mock.patch.object(launcher.os, "name", "nt"), \
                mock.patch.object(launcher.subprocess, "run") as mrun:
            launcher.stop_backend_launcher(proc, timeout=1)
        mrun.assert_called_once()            # taskkill 已先行整树终止
        proc.kill.assert_called_once()       # 句柄强杀兜底
        self.assertEqual(proc.wait.call_count, 2)


class MainFlowTests(unittest.TestCase):
    """main 主流程：窗口形态、后台服务拉起、启动探测提示与关闭清理
    （全 mock，无真窗口、不真拉起进程）。"""

    def _run_main(self, main_running=True, ready=True, spawn_proc=None):
        """注入伪 webview + 伪探测跑 main()，返回（rc, 桩集合, stdout）。

        fake webview.start 同步执行导航回调（真机为 GUI 启动后异步执行），
        使 load_url/标题提示可在离线单测中断言。
        """
        fake_webview = mock.MagicMock()
        # 单实例门（#263）在测试环境强制放行：真互斥体随模块导入创建，
        # 生产实例在跑时同进程 _SI_ALREADY 恒 True，会把所有 main 流程
        # 用例绊在门上——流程测试显式压 False（门本身由门锚单测覆盖）。
        gate_patch = mock.patch.object(launcher, "_SI_ALREADY", False)
        gate_patch.start()
        self.addCleanup(gate_patch.stop)
        gate_handle_patch = mock.patch.object(
            launcher, "_SI_HANDLE", None)
        gate_handle_patch.start()
        self.addCleanup(gate_handle_patch.stop)

        def fake_start(fn=None, *args, **kwargs):
            if fn:
                fn()
            return None

        fake_webview.start.side_effect = fake_start
        window = fake_webview.create_window.return_value

        out = io.StringIO()
        with _fake_webview(fake_webview),                 mock.patch.object(launcher, "_SI_ALREADY", False),                 mock.patch.object(launcher, "_SI_HANDLE", None),                 mock.patch.object(launcher, "_acquire_single_instance_lock",
                                  return_value=(None, False)),                 mock.patch.object(launcher, "_another_instance_serving",
                                  return_value=False),                 mock.patch.object(launcher, "ensure_backend_services",
                                  return_value=spawn_proc) as mspawn,                 mock.patch.object(launcher, "_is_main_running",
                                  return_value=main_running) as mp,                 mock.patch.object(launcher, "wait_for_dashboard_ready",
                                  return_value=ready) as mwait,                 mock.patch.object(launcher, "stop_backend_launcher") as mkill,                 contextlib.redirect_stdout(out):
            rc = launcher.main([])
        stubs = types.SimpleNamespace(fake_webview=fake_webview, mspawn=mspawn,
                                      mwait=mwait, mkill=mkill, window=window)
        return rc, stubs, out.getvalue()

    def test_placeholder_window_then_navigate_to_5003(self):
        """新主线（端口修复 P2）：占位窗（html=PLACEHOLDER_HTML）先行，
        就绪后 load_url 切 http://127.0.0.1:5003/console——随机内置服务退役。"""
        rc, s, _ = self._run_main()
        self.assertEqual(rc, 0)
        kwargs = s.fake_webview.create_window.call_args[1]
        self.assertEqual(kwargs.get("html"), launcher.PLACEHOLDER_HTML)
        self.assertEqual((kwargs.get("width"), kwargs.get("height")),
                         (1200, 800))
        s.window.load_url.assert_called_once_with(launcher.CONSOLE_URL)
        s.mspawn.assert_called_once_with()          # 开窗前先拉后台服务
        s.fake_webview.start.assert_called_once()   # 导航回调经 start 执行

    def test_timeout_still_navigates_and_hints_title(self):
        """探测超时：窗口照常导航 :5003（WebView2 错误页兜底，稍后刷新即恢复）
        + 标题追加"主程序未启动"提示；关窗仍回收自拉进程。"""
        proc = mock.MagicMock()
        rc, s, _ = self._run_main(main_running=False, ready=False,
                                  spawn_proc=proc)
        self.assertEqual(rc, 0)
        s.window.load_url.assert_called_once_with(launcher.CONSOLE_URL)
        title_js = s.window.evaluate_js.call_args[0][0]
        self.assertIn("主程序未启动", title_js)
        s.mkill.assert_called_once_with(proc)

    def test_spawned_launcher_killed_on_window_close(self):
        """关闭清理：窗口关闭后整树终止自拉的 xiaoju3_launcher.py 进程。"""
        proc = mock.MagicMock()
        _, s, _ = self._run_main(spawn_proc=proc)
        s.mkill.assert_called_once_with(proc)

    def test_reuse_mode_cleanup_still_invoked_but_noop(self):
        """复用现有进程（未自拉）：清理照常走 None 分支（不误杀他人进程；
        "复用现有进程"提示由 EnsureBackendServicesTests 覆盖）。"""
        _, s, _ = self._run_main(spawn_proc=None)
        s.mkill.assert_called_once_with(None)

    def test_cleanup_runs_even_if_start_raises(self):
        """webview.start 异常（后端崩溃）照常上抛，但 finally 里整树终止
        必达——防孤儿进程。"""
        fake_webview = mock.MagicMock()
        fake_webview.start.side_effect = RuntimeError("gui boom")
        proc = mock.MagicMock()
        with _fake_webview(fake_webview),                 mock.patch.object(launcher, "_SI_ALREADY", False),                 mock.patch.object(launcher, "_SI_HANDLE", None),                 mock.patch.object(launcher, "_another_instance_serving",
                                  return_value=False),                 mock.patch.object(launcher, "_acquire_single_instance_lock",
                                  return_value=(None, False)),                 mock.patch.object(launcher, "ensure_backend_services",
                                  return_value=proc),                 mock.patch.object(launcher, "_is_main_running",
                                  return_value=True),                 mock.patch.object(launcher, "stop_backend_launcher") as mkill,                 contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):
                launcher.main([])   # 导航回调未执行（start 即抛），清理仍必达
        mkill.assert_called_once_with(proc)

    def test_no_launcher_no_wait_navigates_immediately(self):
        """启动器缺位（proc=None）且主程序未运行：跳过等待直接导航
        （无人会拉起，等待无意义），窗口仍创建 + 打印受限提示。"""
        rc, s, stdout = self._run_main(main_running=False, ready=False,
                                       spawn_proc=None)
        self.assertEqual(rc, 0)
        self.assertIn("主程序未启动，聊天功能受限", stdout)
        s.mwait.assert_not_called()                  # 无人拉起 → 不空等
        s.window.load_url.assert_called_once_with(launcher.CONSOLE_URL)
        s.fake_webview.create_window.assert_called_once()

    def test_main_not_running_hint_and_window_still_opens(self):
        """启动器缺位（proc=None）且 main.py 未运行：打印"主程序未启动，
        聊天功能受限"，窗口仍创建（界面仍可打开）。"""
        rc, s, stdout = self._run_main(main_running=False, spawn_proc=None)
        self.assertEqual(rc, 0)
        self.assertIn("主程序未启动，聊天功能受限", stdout)
        s.fake_webview.create_window.assert_called_once()

    def test_spawn_path_no_stale_hint(self):
        """自拉启动器途中不打"主程序未启动"过时提示（主程序数秒后就绪）。"""
        proc = mock.MagicMock()
        _, s, stdout = self._run_main(main_running=False, spawn_proc=proc)
        self.assertNotIn("主程序未启动", stdout)
        s.fake_webview.create_window.assert_called_once()

    def test_main_running_no_hint(self):
        """main.py 在线：不打印受限提示。"""
        _, _, stdout = self._run_main(main_running=True)
        self.assertNotIn("主程序未启动", stdout)


class IsMainRunningTests(unittest.TestCase):
    """_is_main_running / _is_port_listening：socket 连接探测（纯连接无
    HTTP 副作用；:5002 探测口径不变）。"""

    def test_connect_success_returns_true(self):
        with mock.patch.object(launcher.socket, "create_connection") as mc:
            mc.return_value = mock.MagicMock()   # 支持 with 的连接桩
            self.assertTrue(launcher._is_main_running())
        mc.assert_called_once_with(("127.0.0.1", launcher.DASHBOARD_APP_PORT),
                                   timeout=1.0)

    def test_connect_refused_returns_false(self):
        with mock.patch.object(launcher.socket, "create_connection",
                               side_effect=OSError("connection refused")):
            self.assertFalse(launcher._is_main_running())

    def test_main_port_constant_retired_after_merge(self):
        """架构合并（2026-10-01）：5002 彻底废弃，探测常量改为控制台 5003。"""
        self.assertEqual(launcher.DASHBOARD_APP_PORT, 5003)
        self.assertFalse(hasattr(launcher, "MAIN_APP_PORT"))

    def test_dashboard_port_constant_matches_dashboard(self):
        """复用检测的控制台端口常量与 xiaoju3_dashboard.py 一致（5003）。"""
        self.assertEqual(launcher.DASHBOARD_PORT, 5003)

    def test_is_main_running_delegates_to_port_probe(self):
        """_is_main_running 复用 _is_port_listening（探测逻辑单点）。"""
        with mock.patch.object(launcher, "_is_port_listening",
                               return_value=True) as mp:
            self.assertTrue(launcher._is_main_running())
        mp.assert_called_once_with(launcher.DASHBOARD_APP_PORT, timeout=1.0)

    def test_port_listening_probe_dashboard(self):
        with mock.patch.object(launcher.socket, "create_connection") as mc:
            mc.return_value = mock.MagicMock()
            self.assertTrue(launcher._is_port_listening(5003))
        mc.assert_called_once_with(("127.0.0.1", 5003), timeout=1.0)


class StaticContractTests(unittest.TestCase):
    """静态断言（真窗口不自动化测试的补充）：离线红线与入口形态。"""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(PROJECT_ROOT, "desktop_launcher.py"),
                  "r", encoding="utf-8") as f:
            cls.src = f.read()

    def test_no_external_urls(self):
        """离线红线：源码不含任何 https:// 外链；http:// 仅用于回环 URL 构造。"""
        self.assertNotIn("https://", self.src)
        self.assertIn('f"http://{DEFAULT_HOST}:', self.src)   # 回环 URL 构造点

    def test_entrypoint_shape(self):
        """入口形态：先拉后台服务 → create_window(1200x800) → start →
        __main__ 守卫。"""
        self.assertIn("ensure_backend_services()", self.src)
        self.assertIn(
            "webview.create_window(WINDOW_TITLE, html=PLACEHOLDER_HTML",
            self.src)
        self.assertIn("width=WINDOW_WIDTH, height=WINDOW_HEIGHT", self.src)
        self.assertIn("webview.start(_navigate_when_ready)", self.src)
        self.assertIn('if __name__ == "__main__":', self.src)

    def test_window_constants_user_spec(self):
        """窗口常量与用户口径一致：标题"小橘3号 · 控制台"、1200x800。"""
        self.assertIn('WINDOW_TITLE = "小橘3号 · 控制台"', self.src)
        self.assertIn("WINDOW_WIDTH = 1200", self.src)
        self.assertIn("WINDOW_HEIGHT = 800", self.src)

    def test_close_cleanup_in_finally(self):
        """关闭清理位于 finally：内置服务（M4）+ 后台启动器整树终止都兜底。"""
        self.assertIn("finally:", self.src)
        self.assertNotIn("stop_local_server", self.src)
        self.assertIn('stop_backend_launcher(backend_state["proc"])', self.src)
        self.assertIn("wait_for_dashboard_ready()", self.src)

    def test_launcher_spawn_shape(self):
        """主入口职责：subprocess Popen 拉起 xiaoju3_launcher.py；端口复用
        检测（5002/5003）；taskkill /T 整树终止兜底。"""
        self.assertIn('LAUNCHER_SCRIPT = "xiaoju3_launcher.py"', self.src)
        self.assertIn("subprocess.Popen([_windowless_python(), script]", self.src)
        self.assertIn("_is_port_listening(DASHBOARD_APP_PORT)", self.src)
        self.assertIn("_is_port_listening(DASHBOARD_APP_PORT)", self.src)
        self.assertIn('"taskkill", "/T", "/F", "/PID"', self.src)

    def test_pywebview_lazy_import_with_chinese_hint(self):
        """缺 pywebview：延迟导入 + 中文提示退出（红线：不让 import 崩溃）。"""
        self.assertIn("import webview", self.src)               # 函数内延迟导入
        self.assertIn("请先安装依赖后重试", self.src)

    def test_pyinstaller_plan_implemented(self):
        """打包已实施（步 4）：spec 引用 + spawn-self 常量在源。"""
        self.assertIn("pyinstaller", self.src.lower())
        self.assertIn("ROLE_LAUNCHER_FLAG", self.src)


class TestSpawnSelfRouting(unittest.TestCase):
    """frozen spawn-self 分流（方案 §2）：route_argv 纯函数 + frozen 拉起分支。

    mock 注意：paths.FROZEN/DATA_ROOT 与 sys.executable 全部 mock.patch，
    绝不真拉起进程；非 frozen 缺省行为由既有用例锁定，此处只测新分支。
    """

    def test_route_argv_three_roles(self):
        """三角色分流：无标志=desktop（缺省），两标志各归其位，首个命中生效。"""
        self.assertEqual(launcher.route_argv([]), "desktop")
        self.assertEqual(launcher.route_argv(None), "desktop")
        self.assertEqual(launcher.route_argv(["--xj3-role=launcher"]), "launcher")
        self.assertEqual(launcher.route_argv(["--xj3-role=dashboard"]), "dashboard")
        self.assertEqual(
            launcher.route_argv(["--xj3-role=launcher", "--other"]), "launcher")

    def test_route_argv_unrelated_args_stay_desktop(self):
        """无关参数（如 --serve-port）不影响缺省桌面角色。"""
        self.assertEqual(launcher.route_argv(["--serve-port", "5900"]), "desktop")

    def test_role_flag_literals_locked(self):
        """角色标志字面锁定：desktop 侧与 xiaoju3_launcher 侧必须一致。"""
        import xiaoju3_launcher as xl
        self.assertEqual(launcher.ROLE_LAUNCHER_FLAG, "--xj3-role=launcher")
        self.assertEqual(launcher.ROLE_DASHBOARD_FLAG, "--xj3-role=dashboard")
        self.assertEqual(launcher.ROLE_DASHBOARD_FLAG, xl.ROLE_DASHBOARD_FLAG)

    def test_frozen_start_backend_spawns_self(self):
        """frozen：exe 以 launcher 角色 spawn 自身；cwd=数据根；stdio 全 DEVNULL。"""
        fake_exe = r"C:\Apps\xiaoju3\xiaoju3.exe"
        with mock.patch.object(paths, "FROZEN", True), \
             mock.patch.object(paths, "DATA_ROOT", r"C:\Apps\xiaoju3"), \
             mock.patch.object(sys, "executable", fake_exe), \
             mock.patch.object(subprocess, "Popen") as popen, \
             mock.patch.object(sys, "stdout", new=io.StringIO()):
            popen.return_value = mock.MagicMock(pid=4321)
            proc = launcher.start_backend_launcher()
        args, kwargs = popen.call_args
        self.assertEqual(args[0], [fake_exe, launcher.ROLE_LAUNCHER_FLAG])
        self.assertEqual(kwargs["cwd"], r"C:\Apps\xiaoju3")
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertIsNotNone(proc)

    def test_non_frozen_start_backend_skips_frozen_branch(self):
        """非 frozen（FROZEN=False）：不触发 spawn-self——cmd 仍为
        [解释器, xiaoju3_launcher.py]，不含角色标志（原路径回归锚）。"""
        with mock.patch.object(paths, "FROZEN", False), \
             mock.patch.object(subprocess, "Popen") as popen, \
             mock.patch.object(sys, "stdout", new=io.StringIO()):
            popen.return_value = mock.MagicMock(pid=1)
            launcher.start_backend_launcher()
        args = popen.call_args[0][0]
        self.assertTrue(str(args[1]).endswith("xiaoju3_launcher.py"))
        self.assertNotIn(launcher.ROLE_LAUNCHER_FLAG, args)


if __name__ == "__main__":
    unittest.main()


class WaitForDashboardReadyTests(unittest.TestCase):
    """端口修复 P1：wait_for_dashboard_ready 三态（check/sleep 全注入，零真等）。"""

    def test_first_check_ready_returns_true(self):
        """首轮即就绪（复用模式：服务已在）→ True，且不再 sleep。"""
        sleeps = []
        self.assertTrue(launcher.wait_for_dashboard_ready(
            timeout_s=15, interval_s=0.5,
            check_fn=lambda p: True, sleep_fn=sleeps.append))
        self.assertEqual(sleeps, [])

    def test_ready_after_n_rounds(self):
        """第 N 轮就绪 → True：前两轮 False，第三轮 True（验证轮询推进）。"""
        seq = iter([False, False, True])
        sleeps = []
        self.assertTrue(launcher.wait_for_dashboard_ready(
            timeout_s=15, interval_s=0.5,
            check_fn=lambda p: next(seq), sleep_fn=sleeps.append))
        self.assertEqual(sleeps, [0.5, 0.5])   # 就绪前恰好 sleep 两轮

    def test_timeout_returns_false(self):
        """超时 → False：check 恒 False + 快速假 sleep，不真等。"""
        fast = mock.MagicMock()
        self.assertFalse(launcher.wait_for_dashboard_ready(
            timeout_s=1.0, interval_s=0.2,
            check_fn=lambda p: False, sleep_fn=fast))
        self.assertGreaterEqual(fast.call_count, 1)

    def test_check_exception_treated_as_not_ready(self):
        """探针抛异常按"本轮未就绪"处理（不炸轮询）。"""
        seq = iter([Exception("boom"), True])
        def flaky(_port):
            step = next(seq)
            if isinstance(step, Exception):
                raise step
            return step
        self.assertTrue(launcher.wait_for_dashboard_ready(
            timeout_s=15, interval_s=0.5, check_fn=flaky,
            sleep_fn=lambda _s: None))


class StartupUxTests(unittest.TestCase):
    """启动体验优化锚（2026-10-04 启动优化拍板②）：顶层 dashboard import
    退役（占位窗创建不再被 ≈1.1s 全链拖住，提前 ≈0.7-1.1s 见窗）+ 占位页
    品牌化三步进度文案。"""

    def test_no_top_level_dashboard_import(self):
        """ast 级防回流锚：desktop_launcher 模块体（顶层）零
        xiaoju3_dashboard 导入；__main__ 分支的函数内延迟导入（dashboard
        角色分流）不受限（ast 只看 Module 直接子节点，嵌套 Import 不算）。"""
        import ast
        src_path = os.path.join(os.path.dirname(launcher.__file__),
                                "desktop_launcher.py")
        with open(src_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        offenders = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and \
                    node.module == "xiaoju3_dashboard":
                offenders.append(node.lineno)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "xiaoju3_dashboard":
                        offenders.append(node.lineno)
        self.assertEqual(
            offenders, [],
            "desktop_launcher 顶层不得 import xiaoju3_dashboard，"
            f"行号: {offenders}")

    def test_placeholder_branded_three_step_copy(self):
        """占位页品牌化锚：橘色 accent + 三步进度文案 + 安抚行在位
        （视觉素材后续可替换，文案骨架先行锁定）。"""
        html = launcher.PLACEHOLDER_HTML
        self.assertIn("小橘3号", html)
        self.assertIn("#ff9a3c", html)          # 橘色 accent
        self.assertIn("① 准备资源", html)
        self.assertIn("② 启动服务", html)
        self.assertIn("③ 打开界面", html)
        self.assertIn("自动进入控制台", html)


class MeiCleanupTests(unittest.TestCase):
    """旧 _MEI 残留清理（2026-10-04 启动优化拍板③，阈值 30 分钟）：
    frozen 才执行 / 跳过自身 _MEIPASS / 30 分钟内动过绝不判残留 / 其它
    同名实例存活整体跳过（防长驻实例误删）/ 仍有进程握着的目录跳过 /
    非 frozen 零副作用。存活探测一律 mock（测试不依赖宿主机进程表），
    Temp 重定向到独立沙箱目录（绝不触碰真实 Temp\\_MEI*）。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="xj3_mei_test_")
        redirect = mock.patch.object(launcher.tempfile, "gettempdir",
                                     return_value=self._tmp)
        redirect.start()
        self.addCleanup(redirect.stop)
        self.addCleanup(
            lambda: shutil.rmtree(self._tmp, ignore_errors=True))
        probe = mock.patch.object(launcher, "_meipass_in_use",
                                  return_value=False)
        probe.start()
        self.addCleanup(probe.stop)
        other = mock.patch.object(launcher, "_has_other_own_instance",
                                  return_value=False)
        other.start()
        self.addCleanup(other.stop)

    def _make(self, name, age_s):
        """造一个假 _MEI 目录（含 1KB payload），目录 mtime 拨回 age_s
        秒前（os.utime，判定走的是目录 mtime 而非内部文件）。"""
        path = os.path.join(self._tmp, name)
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "payload.bin"), "wb") as f:
            f.write(b"x" * 1024)
        old = time.time() - age_s
        os.utime(path, (old, old))
        return path

    def _frozen(self, own_meipass=None):
        """注入 frozen 形态（sys.frozen + sys._MEIPASS，测试进程本无此
        二属性，create=True；mock 自动还原）。"""
        fp = mock.patch.object(launcher.sys, "frozen", True, create=True)
        fp.start()
        self.addCleanup(fp.stop)
        mp = mock.patch.object(
            launcher.sys, "_MEIPASS",
            own_meipass or os.path.join(self._tmp, "_MEIown"), create=True)
        mp.start()
        self.addCleanup(mp.stop)

    def test_stale_removed_recent_and_own_kept(self):
        """核心安全约束：1 小时前残留删净；1 分钟内目录（新并行实例）与
        自身 _MEIPASS（即便 mtime 过期）绝不碰。"""
        stale = self._make("_MEI1111", age_s=3600)
        recent = self._make("_MEI2222", age_s=60)
        own = self._make("_MEIown", age_s=3600)
        self._frozen(own_meipass=own)
        launcher._cleanup_stale_meipass()
        self.assertFalse(os.path.exists(stale))
        self.assertTrue(os.path.exists(recent))
        self.assertTrue(os.path.exists(own))

    def test_threshold_30min_boundary(self):
        """拍板阈值 30 分钟边界：29 分钟（双开安全余量内）保留、31 分钟
        判残留清理。"""
        keep = self._make("_MEIkeep", age_s=29 * 60)
        gone = self._make("_MEIgone", age_s=31 * 60)
        self._frozen()
        launcher._cleanup_stale_meipass()
        self.assertTrue(os.path.exists(keep))
        self.assertFalse(os.path.exists(gone))

    def test_not_frozen_noop(self):
        """非 frozen（开发态 python 直跑）零副作用：不枚举不删除。"""
        target = self._make("_MEI3333", age_s=3600)
        fp = mock.patch.object(launcher.sys, "frozen", False, create=True)
        fp.start()
        self.addCleanup(fp.stop)
        launcher._cleanup_stale_meipass()
        self.assertTrue(os.path.exists(target))

    def test_other_instance_alive_skips_all(self):
        """双开第一保险：其它同名实例存活 → 本轮整体跳过（长驻实例的
        解包目录 mtime 必然过期，mtime 单判防不住，宁漏勿误）。"""
        target = self._make("_MEI4444", age_s=3600)
        self._frozen()
        with mock.patch.object(launcher, "_has_other_own_instance",
                               return_value=True):
            launcher._cleanup_stale_meipass()
        self.assertTrue(os.path.exists(target))

    def test_in_use_probe_skips_that_dir(self):
        """单目录存活探测：仍有进程握着的目录跳过，同批其它残留照常
        清理（崩溃后 node 驱动滞留场景）。"""
        used = self._make("_MEI5555", age_s=3600)
        stale = self._make("_MEI6666", age_s=3600)
        self._frozen()

        def probe(path):
            return os.path.normcase(path) == os.path.normcase(used)

        with mock.patch.object(launcher, "_meipass_in_use",
                               side_effect=probe):
            launcher._cleanup_stale_meipass()
        self.assertTrue(os.path.exists(used))
        self.assertFalse(os.path.exists(stale))

    def test_cleanup_wired_into_main_early(self):
        """接线锚：main() 体最早期调用 _cleanup_stale_meipass()（在
        _redirect_stdio 之前），防接线被误删回退。"""
        src_path = os.path.join(os.path.dirname(launcher.__file__),
                                "desktop_launcher.py")
        with open(src_path, "r", encoding="utf-8") as f:
            src = f.read()
        main_at = src.index("def main(argv=None):")
        call_at = src.index("_cleanup_stale_meipass()", main_at)
        redirect_at = src.index('_redirect_stdio("desktop")', main_at)
        self.assertLess(call_at, redirect_at)


class SingleInstanceGateTests(unittest.TestCase):
    """单实例门（#263，2026-10-07）：互斥体已存在 → 唤起已有窗 + return 0，
    不开第二窗不重复拉后端；白屏缓解 env（WEBVIEW2_ADDITIONAL_BROWSER_
    ARGUMENTS）在模块导入期生效。"""

    def test_env_browser_args_setdefault(self):
        """白屏快改锚：desktop_launcher 导入期即设 WebView2 附加参数
        （禁最小化挂起/后台化——恢复窗口无整页白闪），setdefault 允许 env 覆盖。"""
        val = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
        self.assertIn("--disable-backgrounding-occluded-windows", val)
        self.assertIn("--disable-renderer-backgrounding", val)

    def test_mutex_fresh_then_held(self):
        """互斥体语义锚（唯一名防同进程互扰）：首取 fresh；持有时再取 →
        already=True；释放后可重取（main 收尾释放/测试可重复进出）。"""
        unique = f"Local\\Xiaoju3_test_{os.getpid()}"
        handle, already = launcher._acquire_single_instance_lock(name=unique)
        self.assertIsNotNone(handle)
        self.assertFalse(already)                       # 首取 fresh
        if os.name != "nt":
            return
        launcher._release_single_instance_lock(handle)
        handle2, already2 = launcher._acquire_single_instance_lock(name=unique)
        self.assertFalse(already2)                  # 已释放 → 可重取
        launcher._release_single_instance_lock(handle2)

    def test_gate_second_instance_exits_zero(self):
        """门行为锚（#263 同版本）：互斥体旗标已置（模拟已有实例）→ main
        返回 0 + 提示已在运行 + 已唤起窗口 + 不创建第二窗 + 不重复拉后端。"""
        activated = mock.MagicMock(return_value=True)
        fake_webview = mock.MagicMock()
        out = io.StringIO()
        with _fake_webview(fake_webview), \
                mock.patch.object(launcher, "_SI_ALREADY", True), \
                mock.patch.object(launcher, "_another_instance_serving",
                                  return_value=False), \
                mock.patch.object(launcher, "_activate_existing_window",
                                  activated), \
                contextlib.redirect_stdout(out):
            rc = launcher.main([])
        self.assertEqual(rc, 0)
        self.assertIn("已在运行", out.getvalue())
        activated.assert_called_once()
        fake_webview.create_window.assert_not_called()   # 不开第二窗

    def test_gate_cross_version_5003_guard(self):
        """跨版本兜底锚（#263 L1，2026-10-07）：5003 被占（如测试版旧车，
        无互斥体代码）→ 同样唤起+return 0——端口探测跨版本通吃，
        双版本双开（真机实锤）由此拦住。"""
        activated = mock.MagicMock(return_value=True)
        fake_webview = mock.MagicMock()
        out = io.StringIO()
        with _fake_webview(fake_webview), \
                mock.patch.object(launcher, "_SI_ALREADY", False), \
                mock.patch.object(launcher, "_another_instance_serving",
                                  return_value=True), \
                mock.patch.object(launcher, "_activate_existing_window",
                                  activated), \
                contextlib.redirect_stdout(out):
            rc = launcher.main([])
        self.assertEqual(rc, 0)
        self.assertIn("已在运行", out.getvalue())
        activated.assert_called_once()
        fake_webview.create_window.assert_not_called()


if __name__ == "__main__":
    unittest.main()
