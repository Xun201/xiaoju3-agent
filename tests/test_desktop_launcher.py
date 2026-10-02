# -*- coding: utf-8 -*-
"""桌面软件化主入口（desktop_launcher）单元测试（全部离线）。

覆盖（S3 桌面软件化任务口径；pywebview 真窗口不自动化测试——无头环境不可行，
以纯函数 + 静态断言 + mock webview/subprocess/psutil 覆盖）：
- 缺 pywebview（sys.modules 置 None）→ main 中文提示退出，返回码 1；
- --serve-port 参数解析：缺省 None（随机端口）、显式端口正确解析（M4 兼容）；
- 后台启动器拉起：:5002/:5003 未监听时经 subprocess.Popen 后台拉起
  xiaoju3_launcher.py（命令行含该脚本名、stdio 全 DEVNULL）；两端口均已
  监听 → 跳过拉起并提示"复用现有进程"；脚本缺失/拉起失败 → 跳过不报错；
- 关闭清理：webview.start 返回（窗口关闭）后 stop_local_server（M4 既有）
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
import signal
import socket
import subprocess
import sys
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


class ParseArgsTests(unittest.TestCase):
    """--serve-port 参数解析（任务口径：缺省随机、可显式指定；M4 兼容）。"""

    def test_default_port_is_none_random(self):
        args = launcher.parse_args([])
        self.assertIsNone(args.serve_port)

    def test_explicit_serve_port(self):
        args = launcher.parse_args(["--serve-port", "5099"])
        self.assertEqual(args.serve_port, 5099)


class MissingWebviewTests(unittest.TestCase):
    """缺 pywebview：中文提示退出，不让 import 崩溃。"""

    def test_missing_webview_prints_chinese_and_returns_1(self):
        err = io.StringIO()
        with _fake_webview(None), contextlib.redirect_stderr(err):
            rc = launcher.main([])
        self.assertEqual(rc, 1)
        self.assertIn("pywebview", err.getvalue())
        self.assertIn("离线桌面", err.getvalue())   # 中文提示

    def test_missing_webview_no_window_no_server(self):
        """缺库快速失败：不拉后台服务、不创建窗口、不启动内置服务、不探测。"""
        err = io.StringIO()
        with _fake_webview(None), contextlib.redirect_stderr(err), \
                mock.patch.object(launcher, "ensure_backend_services") as me, \
                mock.patch.object(launcher, "start_local_server") as ms, \
                mock.patch.object(launcher, "_is_main_running") as mp:
            rc = launcher.main([])
        self.assertEqual(rc, 1)
        me.assert_not_called()
        ms.assert_not_called()
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

    def _run_main(self, main_running=True, serve_port=None, spawn_proc=None):
        """注入伪 webview + 伪内置服务跑 main()，返回（rc, 桩集合, stdout）。"""
        fake_webview = mock.MagicMock()
        fake_server = mock.MagicMock()
        fake_server.server_port = 45677
        fake_thread = mock.MagicMock()

        out = io.StringIO()
        with _fake_webview(fake_webview), \
                mock.patch.object(launcher, "ensure_backend_services",
                                  return_value=spawn_proc) as mspawn, \
                mock.patch.object(launcher, "_is_main_running",
                                  return_value=main_running), \
                mock.patch.object(launcher, "start_local_server",
                                  return_value=(fake_server,
                                                fake_thread)) as ms, \
                mock.patch.object(launcher, "stop_local_server") as mstop, \
                mock.patch.object(launcher, "stop_backend_launcher") as mkill, \
                contextlib.redirect_stdout(out):
            rc = launcher.main([] if serve_port is None
                               else ["--serve-port", str(serve_port)])
        stubs = types.SimpleNamespace(fake_webview=fake_webview, mspawn=mspawn,
                                      ms=ms, mstop=mstop, mkill=mkill,
                                      server=fake_server, thread=fake_thread)
        return rc, stubs, out.getvalue()

    def test_window_title_size_and_loopback_console_url(self):
        """窗口形态：标题"小橘3号 · 控制台"、1200x800、回环 /console URL
        （离线红线：无外网 URL）；先拉后台服务再开窗。"""
        rc, s, _ = self._run_main()
        self.assertEqual(rc, 0)
        s.fake_webview.create_window.assert_called_once_with(
            launcher.WINDOW_TITLE, "http://127.0.0.1:45677/console",
            width=1200, height=800)
        self.assertEqual(launcher.WINDOW_TITLE, "小橘3号 · 控制台")
        self.assertEqual((launcher.WINDOW_WIDTH, launcher.WINDOW_HEIGHT),
                         (1200, 800))
        s.fake_webview.start.assert_called_once()   # 入口阻塞至窗口关闭
        s.ms.assert_called_once_with(None)          # 未指定端口 → 随机
        s.mspawn.assert_called_once_with()          # 开窗前先拉后台服务

    def test_serve_port_forwarded_to_server(self):
        """--serve-port 透传给内置服务（M4 兼容零回退）。"""
        _, s, _ = self._run_main(serve_port=5900)
        s.ms.assert_called_once_with(5900)

    def test_spawned_launcher_killed_on_window_close(self):
        """关闭清理：窗口关闭后整树终止自拉的 xiaoju3_launcher.py 进程。"""
        proc = mock.MagicMock()
        _, s, _ = self._run_main(spawn_proc=proc)
        s.mkill.assert_called_once_with(proc)
        s.mstop.assert_called_once_with(s.server, s.thread)   # M4 清理零回退

    def test_reuse_mode_cleanup_still_invoked_but_noop(self):
        """复用现有进程（未自拉）：清理照常走 None 分支（不误杀他人进程；
        "复用现有进程"提示由 EnsureBackendServicesTests 覆盖）。"""
        _, s, _ = self._run_main(spawn_proc=None)
        s.mkill.assert_called_once_with(None)
        s.mstop.assert_called_once_with(s.server, s.thread)

    def test_cleanup_runs_even_if_start_raises(self):
        """webview.start 异常（后端崩溃）照常上抛，但 finally 里两段清理
        必达——防僵尸端口与孤儿进程。"""
        fake_webview = mock.MagicMock()
        fake_webview.start.side_effect = RuntimeError("gui boom")
        fake_server, fake_thread = mock.MagicMock(), mock.MagicMock()
        fake_server.server_port = 45678
        proc = mock.MagicMock()
        with _fake_webview(fake_webview), \
                mock.patch.object(launcher, "ensure_backend_services",
                                  return_value=proc), \
                mock.patch.object(launcher, "_is_main_running",
                                  return_value=True), \
                mock.patch.object(launcher, "start_local_server",
                                  return_value=(fake_server, fake_thread)), \
                mock.patch.object(launcher, "stop_local_server") as mstop, \
                mock.patch.object(launcher, "stop_backend_launcher") as mkill, \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):
                launcher.main([])
        mstop.assert_called_once_with(fake_server, fake_thread)
        mkill.assert_called_once_with(proc)

    def test_server_failure_cleans_spawned_launcher(self):
        """内置服务启动失败退出码 1：已拉起的启动器进程也被回收。"""
        proc = mock.MagicMock()
        with _fake_webview(mock.MagicMock()), \
                mock.patch.object(launcher, "ensure_backend_services",
                                  return_value=proc), \
                mock.patch.object(launcher, "_is_main_running",
                                  return_value=True), \
                mock.patch.object(launcher, "start_local_server",
                                  side_effect=OSError("port busy")), \
                mock.patch.object(launcher, "stop_backend_launcher") as mkill, \
                contextlib.redirect_stdout(io.StringIO()):
            rc = launcher.main([])
        self.assertEqual(rc, 1)
        mkill.assert_called_once_with(proc)

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


class LocalServerLifecycleTests(unittest.TestCase):
    """真实内置服务（127.0.0.1 回环，离线）：绑定、HTTP 可达与关闭清理
    （M4 机制零回退）。"""

    def _free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def test_start_random_port_binds_loopback(self):
        server, thread = launcher.start_local_server(None)
        try:
            self.assertGreater(server.server_port, 0)      # 随机分配了真实端口
            self.assertEqual(server.server_address[0], "127.0.0.1")
            self.assertTrue(thread.daemon)
            self.assertTrue(thread.is_alive())
        finally:
            launcher.stop_local_server(server, thread)

    def test_start_explicit_port(self):
        port = self._free_port()
        server, thread = launcher.start_local_server(port)
        try:
            self.assertEqual(server.server_port, port)
        finally:
            launcher.stop_local_server(server, thread)

    def test_console_reachable_via_loopback_http(self):
        """窗口加载形态冒烟：内置服务上 GET /console 经回环 HTTP 200 可达。"""
        server, thread = launcher.start_local_server(None)
        try:
            url = f"http://127.0.0.1:{server.server_port}/console"
            with urllib.request.urlopen(url, timeout=5) as resp:
                body = resp.read().decode("utf-8")
            self.assertEqual(resp.status, 200)
            self.assertIn("小橘3号", body)
        finally:
            launcher.stop_local_server(server, thread)

    def test_stop_terminates_thread_and_releases_port(self):
        """关闭清理冒烟：stop 后服务线程终止，端口 HTTP 请求失败（已释放）。"""
        server, thread = launcher.start_local_server(None)
        port = server.server_port
        launcher.stop_local_server(server, thread)
        self.assertFalse(thread.is_alive())   # serve_forever 循环已退出
        time.sleep(0.3)                       # 等内核回收监听 socket
        url = f"http://127.0.0.1:{port}/console"
        with self.assertRaises(OSError):
            urllib.request.urlopen(url, timeout=2)


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
        self.assertIn("webview.create_window(WINDOW_TITLE, url", self.src)
        self.assertIn("width=WINDOW_WIDTH, height=WINDOW_HEIGHT", self.src)
        self.assertIn("webview.start()", self.src)
        self.assertIn('if __name__ == "__main__":', self.src)

    def test_window_constants_user_spec(self):
        """窗口常量与用户口径一致：标题"小橘3号 · 控制台"、1200x800。"""
        self.assertIn('WINDOW_TITLE = "小橘3号 · 控制台"', self.src)
        self.assertIn("WINDOW_WIDTH = 1200", self.src)
        self.assertIn("WINDOW_HEIGHT = 800", self.src)

    def test_close_cleanup_in_finally(self):
        """关闭清理位于 finally：内置服务（M4）+ 后台启动器整树终止都兜底。"""
        self.assertIn("finally:", self.src)
        self.assertIn("stop_local_server(server, thread)", self.src)
        self.assertIn("stop_backend_launcher(launcher_proc)", self.src)

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

    def test_pyinstaller_plan_marked_in_docstring(self):
        """可选任务（文档标记，不实施）：pyinstaller 单 exe → 🔜 规划中。"""
        self.assertIn("pyinstaller", self.src.lower())
        self.assertIn("🔜 规划中", self.src)


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
