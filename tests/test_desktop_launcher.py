# -*- coding: utf-8 -*-
"""离线桌面控制台壳（desktop_launcher）单元测试（全部离线）。

覆盖（任务 3 测试口径；pywebview 真窗口不自动化测试——无头环境不可行，
以纯函数 + 静态断言 + mock webview 覆盖）：
- 缺 pywebview（sys.modules 置 None）→ main 中文提示退出，返回码 1；
- --serve-port 参数解析：缺省 None（随机端口）、显式端口正确解析；
- main 主流程（mock webview + mock 内置服务）：窗口标题与加载 URL 为
  本机回环 /console（绝不出现外网 URL）；webview.start 被调用；窗口关闭
  （start 返回）后 stop_local_server 被调用（关闭清理，防僵尸端口驻留）；
- 启动探测：main.py（:5002）未运行时打印"主程序未启动，聊天功能受限"，
  窗口仍照常创建（界面仍可打开）；在线时不打印提示；
- _is_main_running：socket 连接成功 True / 失败 False（mock 子进程级副作用）；
- 真实内置服务（127.0.0.1 回环，离线）：随机端口绑定成功、/console 经
  HTTP 200 可达（loopback 非外网）；stop 后服务线程终止、端口释放。

mock 注意：webview 走 sys.modules 注入 MagicMock（patch.dict 自动还原）；
socket / 服务启停全部走 mock.patch 还原，绝不污染真实环境。
"""
import contextlib
import io
import os
import socket
import sys
import time
import unittest
import urllib.request
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import desktop_launcher as launcher  # noqa: E402


@contextlib.contextmanager
def _fake_webview(module):
    """向 sys.modules 注入伪 webview 模块（patch.dict 结束自动还原）。"""
    with mock.patch.dict(sys.modules, {"webview": module}):
        yield module


class ParseArgsTests(unittest.TestCase):
    """--serve-port 参数解析（任务口径：缺省随机、可显式指定）。"""

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
        """缺库快速失败：不创建窗口、不启动内置服务、不探测主程序。"""
        err = io.StringIO()
        with _fake_webview(None), contextlib.redirect_stderr(err), \
                mock.patch.object(launcher, "start_local_server") as ms, \
                mock.patch.object(launcher, "_is_main_running") as mp:
            rc = launcher.main([])
        self.assertEqual(rc, 1)
        ms.assert_not_called()
        mp.assert_not_called()


class MainFlowTests(unittest.TestCase):
    """main 主流程：窗口 URL、启动探测提示与关闭清理（全 mock，无真窗口）。"""

    def _run_main(self, main_running=True, serve_port=None):
        """注入伪 webview + 伪内置服务跑 main()，返回（rc, 桩, stdout）。"""
        fake_webview = mock.MagicMock()
        fake_server = mock.MagicMock()
        fake_server.server_port = 45677
        fake_thread = mock.MagicMock()

        out = io.StringIO()
        with _fake_webview(fake_webview), \
                mock.patch.object(launcher, "_is_main_running",
                                  return_value=main_running), \
                mock.patch.object(launcher, "start_local_server",
                                  return_value=(fake_server, fake_thread)) as ms, \
                mock.patch.object(launcher, "stop_local_server") as mstop, \
                contextlib.redirect_stdout(out):
            rc = launcher.main([] if serve_port is None
                               else ["--serve-port", str(serve_port)])
        return rc, fake_webview, ms, mstop, fake_server, fake_thread, out.getvalue()

    def test_window_title_and_loopback_console_url(self):
        """窗口标题与 URL：本机回环 + /console（离线红线：无外网 URL）。"""
        rc, fake_webview, ms, _, _, _, _ = self._run_main()
        self.assertEqual(rc, 0)
        fake_webview.create_window.assert_called_once_with(
            launcher.WINDOW_TITLE, "http://127.0.0.1:45677/console")
        self.assertEqual(launcher.WINDOW_TITLE, "小橘3号 · 离线控制台")
        fake_webview.start.assert_called_once()   # 入口阻塞至窗口关闭
        ms.assert_called_once_with(None)          # 未指定端口 → 随机

    def test_serve_port_forwarded_to_server(self):
        """--serve-port 透传给内置服务启动。"""
        _, _, ms, _, _, _, _ = self._run_main(serve_port=5900)
        ms.assert_called_once_with(5900)

    def test_close_cleanup_stops_server_after_start_returns(self):
        """关闭清理：webview.start 返回（窗口关闭）后 stop_local_server
        以 (server, thread) 被调用——防僵尸端口驻留。"""
        _, _, _, mstop, fake_server, fake_thread, _ = self._run_main()
        mstop.assert_called_once_with(fake_server, fake_thread)

    def test_cleanup_runs_even_if_start_raises(self):
        """webview.start 异常（后端崩溃）异常照常上抛，但 finally 里的
        关闭清理必达——防僵尸端口驻留。"""
        fake_webview = mock.MagicMock()
        fake_webview.start.side_effect = RuntimeError("gui boom")
        fake_server, fake_thread = mock.MagicMock(), mock.MagicMock()
        fake_server.server_port = 45678
        with _fake_webview(fake_webview), \
                mock.patch.object(launcher, "_is_main_running",
                                  return_value=True), \
                mock.patch.object(launcher, "start_local_server",
                                  return_value=(fake_server, fake_thread)), \
                mock.patch.object(launcher, "stop_local_server") as mstop, \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):
                launcher.main([])
        mstop.assert_called_once_with(fake_server, fake_thread)

    def test_main_not_running_hint_and_window_still_opens(self):
        """main.py 未运行：打印"主程序未启动，聊天功能受限"，窗口仍创建。"""
        rc, fake_webview, _, _, _, _, stdout = self._run_main(main_running=False)
        self.assertEqual(rc, 0)
        self.assertIn("主程序未启动，聊天功能受限", stdout)
        fake_webview.create_window.assert_called_once()   # 窗口仍可打开界面

    def test_main_running_no_hint(self):
        """main.py 在线：不打印受限提示。"""
        _, _, _, _, _, _, stdout = self._run_main(main_running=True)
        self.assertNotIn("主程序未启动", stdout)


class IsMainRunningTests(unittest.TestCase):
    """_is_main_running：socket 连接探测（:5002，纯连接无 HTTP 副作用）。"""

    def test_connect_success_returns_true(self):
        with mock.patch.object(launcher.socket, "create_connection") as mc:
            mc.return_value = mock.MagicMock()   # 支持 with 的连接桩
            self.assertTrue(launcher._is_main_running())
        mc.assert_called_once_with(("127.0.0.1", launcher.MAIN_APP_PORT),
                                   timeout=1.0)

    def test_connect_refused_returns_false(self):
        with mock.patch.object(launcher.socket, "create_connection",
                               side_effect=OSError("connection refused")):
            self.assertFalse(launcher._is_main_running())

    def test_main_port_constant_matches_main_py(self):
        """探测端口常量与 main.py 实际监听端口一致（5002）。"""
        self.assertEqual(launcher.MAIN_APP_PORT, 5002)


class LocalServerLifecycleTests(unittest.TestCase):
    """真实内置服务（127.0.0.1 回环，离线）：绑定、HTTP 可达与关闭清理。"""

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
        """入口形态：webview.create_window + webview.start + __main__ 守卫。"""
        self.assertIn("webview.create_window(WINDOW_TITLE, url)", self.src)
        self.assertIn("webview.start()", self.src)
        self.assertIn('if __name__ == "__main__":', self.src)

    def test_close_cleanup_called_in_finally(self):
        """关闭清理位于 finally（webview.start 返回/异常两态都兜底）。"""
        self.assertIn("finally:", self.src)
        self.assertIn("stop_local_server(server, thread)", self.src)

    def test_pywebview_lazy_import_with_chinese_hint(self):
        """缺 pywebview：延迟导入 + 中文提示退出（红线：不让 import 崩溃）。"""
        self.assertIn("import webview", self.src)               # 函数内延迟导入
        self.assertIn("请先安装依赖后重试", self.src)


if __name__ == "__main__":
    unittest.main()
