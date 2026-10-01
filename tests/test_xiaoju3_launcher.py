# -*- coding: utf-8 -*-
"""统一启动器（xiaoju3_launcher）单元测试（全部离线）。

铁律：不真实拉起 main.py / xiaoju3_dashboard.py / heartbeat——Popen、
打印、sleep、atexit / signal 注册一律经构造参数注入 mock（每个用例
setUp 现造、用例间互不共享；patch 用上下文管理器自动还原）。

覆盖：
- 启动计划三模块齐全与顺序（main 先、dashboard 后，心跳 hosted 随 main）；
- ✅ 三行日志文案逐字断言；
- 子进程句柄管理：Ctrl+C / SIGTERM 模拟 → terminate 被调、超时 kill
  兜底、已退出跳过、shutdown 幂等（atexit 双保险不重复杀）；
- 心跳选型注释与实现一致性（hosted 条目 + 模块不持有 start_heartbeat）；
- parse_args 默认值与 --dry-run / --root。
"""
import io
import os
import signal
import subprocess
import unittest
from unittest import mock

import xiaoju3_launcher as xl

# 假项目根：仅作 cwd/cmd 字符串断言，从不真实执行
FAKE_ROOT = "xiaoju3_fake_root_dir"
FAKE_PY = "py3x"


def make_handle():
    """造一个假 Popen 句柄（默认存活、等待即返回 0）。"""
    h = mock.MagicMock()
    h.poll.return_value = None
    h.wait.return_value = 0
    return h


class LauncherFixtureMixin(object):
    """公共夹具：注入式 mock 的 launcher 工厂（无全局 patch，无需还原）。"""

    def make_launcher(self, plan=None, sleep=None):
        self.handles = []
        self.prints = []
        self.atexit_regs = []
        self.handlers = {}

        def fake_popen(cmd, cwd=None):
            h = make_handle()
            h.cmd = cmd
            self.handles.append(h)
            return h

        def fake_register_atexit(fn):
            self.atexit_regs.append(fn)

        def fake_register_signal(sig, handler):
            self.handlers[sig] = handler

        launcher = xl.XiaojuLauncher(
            plan if plan is not None else
            xl.build_launch_plan(python=FAKE_PY, root=FAKE_ROOT),
            popen=fake_popen,
            out=self.prints.append,
            sleep=sleep or (lambda _s: None),
            register_atexit=fake_register_atexit,
            register_signal=fake_register_signal,
        )
        return launcher


class TestBuildLaunchPlan(unittest.TestCase):
    """启动计划：三模块齐全、顺序与参数。"""

    def setUp(self):
        self.plan = xl.build_launch_plan(python=FAKE_PY, root=FAKE_ROOT)

    def test_three_modules_complete_and_order(self):
        names = [e["name"] for e in self.plan]
        self.assertEqual(names, ["qq", "heartbeat", "dashboard"])
        # main 先、dashboard 后（用户口径）；心跳 hosted 条目居中
        self.assertLess(names.index("qq"), names.index("dashboard"))
        self.assertEqual([e["kind"] for e in self.plan],
                         ["subprocess", "hosted", "subprocess"])

    def test_subprocess_cmds_target_two_entrypoints(self):
        by_name = {e["name"]: e for e in self.plan}
        qq, dash = by_name["qq"], by_name["dashboard"]
        self.assertEqual(qq["cmd"], [FAKE_PY, os.path.join(FAKE_ROOT, "main.py")])
        self.assertEqual(dash["cmd"],
                         [FAKE_PY, os.path.join(FAKE_ROOT, "xiaoju3_dashboard.py")])
        for e in (qq, dash):
            self.assertEqual(e["cwd"], FAKE_ROOT)
            self.assertIn("banner", e)

    def test_banner_texts_exact(self):
        """✅ 三行文案逐字断言（文案口径固定）。"""
        self.assertEqual(xl.BANNER_QQ, "✅ QQ 接入层已启动 (5002)")
        self.assertEqual(xl.BANNER_HEARTBEAT, "✅ 心跳已启动")
        self.assertEqual(xl.BANNER_DASHBOARD, "✅ 控制台已启动 (5003/console)")
        banners = [e["banner"] for e in self.plan]
        self.assertEqual(banners, [xl.BANNER_QQ, xl.BANNER_HEARTBEAT,
                                   xl.BANNER_DASHBOARD])

    def test_heartbeat_hosted_consistency(self):
        """心跳选型注释与实现一致性：hosted 随 qq 进程，launcher 不重复拉起。"""
        hb = {e["name"]: e for e in self.plan}["heartbeat"]
        self.assertEqual(hb["kind"], "hosted")
        self.assertEqual(hb["host"], "qq")
        self.assertNotIn("cmd", hb)  # 绝不单独 Popen 心跳
        for kw in ("start_heartbeat", "main.py", "双心跳"):
            self.assertIn(kw, hb["reason"])
        # 模块未 import heartbeat / 未持有 start_heartbeat → 实现确实不拉起
        self.assertFalse(hasattr(xl, "start_heartbeat"))
        self.assertFalse(hasattr(xl, "heartbeat_loop"))
        # 选型说明同时写进模块 docstring（注释与实现一致）
        self.assertIn("start_heartbeat", xl.__doc__)
        self.assertIn("双心跳", xl.__doc__)


class TestStartSequence(LauncherFixtureMixin, unittest.TestCase):
    """启动序列：Popen 调用、三行 ✅ 顺序、句柄与 atexit 注册。"""

    def test_start_spawns_two_and_prints_three_banners_in_order(self):
        launcher = self.make_launcher()
        procs = launcher.start()
        # 只 Popen 两次（main 先、dashboard 后）；hosted 心跳不单独拉起
        self.assertEqual(len(self.handles), 2)
        self.assertEqual([h.cmd for h in self.handles],
                         [[FAKE_PY, os.path.join(FAKE_ROOT, "main.py")],
                          [FAKE_PY, os.path.join(FAKE_ROOT, "xiaoju3_dashboard.py")]])
        self.assertEqual(len(procs), 2)
        # 三行 ✅ 按启动完成顺序：qq → 心跳（随 qq 进程）→ dashboard
        self.assertEqual(self.prints,
                         [xl.BANNER_QQ, xl.BANNER_HEARTBEAT, xl.BANNER_DASHBOARD])

    def test_handles_kept_and_atexit_double_insurance_registered(self):
        launcher = self.make_launcher()
        launcher.start()
        # Popen 句柄全程持有（供优雅终止）
        self.assertEqual([p for _, p in launcher.procs], self.handles)
        # atexit 双保险注册的正是 shutdown（幂等）
        self.assertEqual(self.atexit_regs, [launcher.shutdown])
        # SIGINT/SIGTERM 处理器已注册
        self.assertIn(signal.SIGINT, self.handlers)
        self.assertIn(signal.SIGTERM, self.handlers)

    def test_start_rejects_unknown_kind(self):
        bad = [{"name": "x", "kind": "teleport", "banner": "?"}]
        launcher = self.make_launcher(plan=bad)
        with self.assertRaises(ValueError):
            launcher.start()


class TestGracefulShutdown(LauncherFixtureMixin, unittest.TestCase):
    """优雅终止：Ctrl+C / SIGTERM 模拟 → terminate 被调；kill 兜底；幂等。"""

    def test_ctrlc_simulate_terminates_all_reverse_order(self):
        """Ctrl+C（KeyboardInterrupt）→ 逆启动序 terminate 全部子进程。"""
        def boom(_seconds):
            raise KeyboardInterrupt()
        launcher = self.make_launcher(sleep=boom)
        order = []
        self.assertEqual(len(self.handles), 0)
        launcher.start()
        h_qq, h_dash = self.handles[0], self.handles[1]
        h_qq.terminate.side_effect = lambda: order.append("qq")
        h_dash.terminate.side_effect = lambda: order.append("dashboard")

        self.assertEqual(launcher.run(), 0)

        # 先 dashboard 后 main（接入层最后退）
        self.assertEqual(order, ["dashboard", "qq"])
        for h in (h_qq, h_dash):
            h.terminate.assert_called_once_with()
        self.assertEqual(launcher.procs, [])  # 句柄清空，无孤儿

    def test_sigterm_handler_sets_stop_and_exits_cleanly(self):
        """SIGTERM 模拟（处理器置位）→ 主循环退出 → terminate 全部。"""
        launcher = self.make_launcher()
        launcher.start()

        def raise_sigterm(_seconds):
            self.handlers[signal.SIGTERM](signal.SIGTERM, None)
        launcher.sleep = raise_sigterm

        self.assertEqual(launcher.run(), 0)
        self.assertTrue(launcher._stop)
        for h in self.handles:
            h.terminate.assert_called_once_with()

    def test_kill_fallback_on_terminate_timeout(self):
        """terminate 超时 → kill 兜底（每句柄恰好一次）。"""
        launcher = self.make_launcher()
        launcher.start()
        for h in self.handles:
            h.wait.side_effect = [subprocess.TimeoutExpired(cmd="x", timeout=8), 0]

        launcher.shutdown()

        for h in self.handles:
            h.terminate.assert_called_once_with()
            h.kill.assert_called_once_with()
            self.assertEqual(h.wait.call_count, 2)

    def test_shutdown_skips_already_exited_and_is_idempotent(self):
        """已退出的子进程跳过；shutdown 幂等（atexit 二次入口不重复杀）。"""
        launcher = self.make_launcher()
        launcher.start()
        self.handles[0].poll.return_value = 1  # 已异常退出
        self.handles[1].poll.return_value = 0  # 已正常退出

        launcher.shutdown()
        launcher.shutdown()  # atexit 双保险再进一次

        for h in self.handles:
            h.terminate.assert_not_called()

    def test_shutdown_survives_single_proc_termination_error(self):
        """单个子进程终止异常不阻断其余子进程清理。"""
        launcher = self.make_launcher()
        launcher.start()
        self.handles[0].terminate.side_effect = OSError("boom")

        launcher.shutdown()  # 不抛异常

        self.handles[1].terminate.assert_called_once_with()


class TestPollChildren(LauncherFixtureMixin, unittest.TestCase):
    """退出码巡检：非 0 告警一次且不重启；0 静默；返回存活数。"""

    def test_nonzero_exit_warns_once_no_restart(self):
        launcher = self.make_launcher()
        launcher.start()
        self.handles[1].poll.return_value = 3  # dashboard 崩了

        self.assertEqual(launcher.poll_children(), 1)  # 只剩 main 存活
        warns = [p for p in self.prints if "exit=3" in p]
        self.assertEqual(len(warns), 1)
        self.assertIn("不自动重启", warns[0])
        self.assertIn("start.sh", warns[0])
        # 不自动重启：不会再次 Popen（handles 数不变），且巡检两次只告警一次
        launcher.poll_children()
        self.assertEqual(len(self.handles), 2)
        self.assertEqual(len([p for p in self.prints if "exit=3" in p]), 1)

    def test_zero_exit_is_silent(self):
        launcher = self.make_launcher()
        launcher.start()
        self.handles[0].poll.return_value = 0
        self.assertEqual(launcher.poll_children(), 1)
        self.assertFalse([p for p in self.prints if "exit=0" in p])

    def test_alive_count_when_all_running(self):
        launcher = self.make_launcher()
        launcher.start()
        self.assertEqual(launcher.poll_children(), 2)


class TestParseArgs(unittest.TestCase):
    """CLI 参数纯函数。"""

    def test_defaults(self):
        args = xl.parse_args([])
        self.assertIsNone(args.root)
        self.assertFalse(args.dry_run)

    def test_dry_run_and_root(self):
        args = xl.parse_args(["--dry-run", "--root", "some/dir"])
        self.assertTrue(args.dry_run)
        self.assertEqual(args.root, "some/dir")


class TestMainDryRun(unittest.TestCase):
    """--dry-run 全链路冒烟：零子进程、零副作用（离线）。"""

    def test_dry_run_prints_plan_without_spawning(self):
        # 双保险：即使实现误入 Popen 分支也当场失败（上下文管理器自动还原）
        with mock.patch("xiaoju3_launcher.subprocess.Popen",
                        side_effect=AssertionError("dry-run 不允许拉起子进程")):
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                code = xl.main(["--dry-run"])
        out = buf.getvalue()
        self.assertEqual(code, 0)
        for frag in ("main.py", "xiaoju3_dashboard.py", ":5003",
                     "dashboard", "start_heartbeat"):
            self.assertIn(frag, out)


if __name__ == "__main__":
    unittest.main()
