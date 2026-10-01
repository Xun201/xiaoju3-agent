# -*- coding: utf-8 -*-
"""统一启动器（xiaoju3_launcher）单元测试（全部离线）。

铁律：不真实拉起 xiaoju3_dashboard.py / heartbeat——Popen、打印、sleep、
atexit / signal 注册一律经构造参数注入 mock（每个用例 setUp 现造、用例间
互不共享；patch 用上下文管理器自动还原）。

【架构合并（2026-10-01：5002 废弃，5003 一个进程承载一切）后的覆盖面】
- 启动计划三行条目（server 子进程 + 心跳/控制台 hosted 随 5003 进程）；
- ✅ 三行日志文案逐字断言 + ⚠️ LLOneBot 改址提醒写入启动日志；
- 子进程句柄管理：Ctrl+C / SIGTERM 模拟 → terminate 被调、超时 kill
  兜底、已退出跳过、shutdown 幂等（atexit 双保险不重复杀）；
- 心跳选型注释与实现一致性（hosted 随 5003 进程，模块不持有
  start_heartbeat）；
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
    """启动计划：三行条目（一个子进程 + 两个 hosted）与顺序。"""

    def setUp(self):
        self.plan = xl.build_launch_plan(python=FAKE_PY, root=FAKE_ROOT)

    def test_three_entries_complete_and_order(self):
        names = [e["name"] for e in self.plan]
        self.assertEqual(names, ["server", "heartbeat", "console"])
        # QQ 接入层行先、心跳居中、控制台行最后（用户口径）；后两行 hosted
        self.assertEqual([e["kind"] for e in self.plan],
                         ["subprocess", "hosted", "hosted"])
        self.assertEqual([e.get("host") for e in self.plan],
                         [None, "server", "server"])

    def test_single_subprocess_targets_dashboard_only(self):
        """架构合并：只 Popen 一个 5003 统一服务子进程，main.py 不再被拉起。"""
        subprocess_entries = [e for e in self.plan if e["kind"] == "subprocess"]
        self.assertEqual(len(subprocess_entries), 1)
        server = subprocess_entries[0]
        self.assertEqual(server["cmd"],
                         [FAKE_PY, os.path.join(FAKE_ROOT, "xiaoju3_dashboard.py")])
        self.assertEqual(server["cwd"], FAKE_ROOT)
        self.assertIn("banner", server)
        for entry in self.plan:   # 旧 main.py 入口彻底退出启动计划
            for cmd_part in (entry.get("cmd") or []):
                self.assertNotIn("main.py", cmd_part)

    def test_banner_texts_exact(self):
        """✅ 三行 + ⚠️ 改址提醒文案逐字断言（文案口径固定）。"""
        self.assertEqual(xl.BANNER_QQ, "✅ QQ 接入层已启动 (5003)")
        self.assertEqual(xl.BANNER_HEARTBEAT, "✅ 心跳已启动")
        self.assertEqual(xl.BANNER_DASHBOARD, "✅ 控制台已启动 (5003/console)")
        self.assertEqual(
            xl.QQ_WEBHOOK_MIGRATION_HINT,
            "⚠️ QQ webhook 已迁移至 5003：请将 LLOneBot 的 HTTP 上报地址改为 "
            "http://127.0.0.1:5003/onebot，否则 QQ 会断连")
        banners = [e["banner"] for e in self.plan]
        self.assertEqual(banners, [xl.BANNER_QQ, xl.BANNER_HEARTBEAT,
                                   xl.BANNER_DASHBOARD])

    def test_heartbeat_hosted_consistency(self):
        """心跳选型注释与实现一致性：hosted 随 5003 进程，launcher 不重复拉起。"""
        hb = {e["name"]: e for e in self.plan}["heartbeat"]
        self.assertEqual(hb["kind"], "hosted")
        self.assertEqual(hb["host"], "server")
        self.assertNotIn("cmd", hb)  # 绝不单独 Popen 心跳
        for kw in ("start_heartbeat", "xiaoju3_dashboard.py", "双心跳"):
            self.assertIn(kw, hb["reason"])
        # 模块未 import heartbeat / 未持有 start_heartbeat → 实现确实不拉起
        self.assertFalse(hasattr(xl, "start_heartbeat"))
        self.assertFalse(hasattr(xl, "heartbeat_loop"))
        # 选型说明同时写进模块 docstring（注释与实现一致）
        self.assertIn("start_heartbeat", xl.__doc__)
        self.assertIn("双心跳", xl.__doc__)


class TestStartSequence(LauncherFixtureMixin, unittest.TestCase):
    """启动序列：Popen 调用、三行 ✅ + ⚠️ 提醒顺序、句柄与 atexit 注册。"""

    def test_start_spawns_one_and_prints_banners_plus_hint_in_order(self):
        launcher = self.make_launcher()
        procs = launcher.start()
        # 只 Popen 一次（5003 统一服务进程）；hosted 心跳/控制台不单独拉起
        self.assertEqual(len(self.handles), 1)
        self.assertEqual(self.handles[0].cmd,
                         [FAKE_PY, os.path.join(FAKE_ROOT, "xiaoju3_dashboard.py")])
        self.assertEqual(len(procs), 1)
        # 三行 ✅ 按启动完成顺序：QQ 接入层 → 心跳（随该进程）→ 控制台；
        # 随后打印 ⚠️ LLOneBot 改址提醒（关键提示必须写入启动日志）
        self.assertEqual(self.prints,
                         [xl.BANNER_QQ, xl.BANNER_HEARTBEAT, xl.BANNER_DASHBOARD,
                          xl.QQ_WEBHOOK_MIGRATION_HINT])

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

    def test_ctrlc_simulate_terminates_the_server_process(self):
        """Ctrl+C（KeyboardInterrupt）→ terminate 5003 统一服务子进程。"""
        def boom(_seconds):
            raise KeyboardInterrupt()
        launcher = self.make_launcher(sleep=boom)
        terminated = []
        self.assertEqual(len(self.handles), 0)
        launcher.start()
        self.handles[0].terminate.side_effect = lambda: terminated.append("server")

        self.assertEqual(launcher.run(), 0)

        self.assertEqual(terminated, ["server"])
        self.handles[0].terminate.assert_called_once_with()
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

        launcher.shutdown()
        launcher.shutdown()  # atexit 双保险再进一次

        for h in self.handles:
            h.terminate.assert_not_called()

    def test_shutdown_survives_single_proc_termination_error(self):
        """单个子进程终止异常不阻断其余子进程清理（异常被吞、不抛出）。"""
        launcher = self.make_launcher()
        launcher.start()
        self.handles[0].terminate.side_effect = OSError("boom")

        launcher.shutdown()  # 不抛异常


class TestPollChildren(LauncherFixtureMixin, unittest.TestCase):
    """退出码巡检：非 0 告警一次且不重启；0 静默；返回存活数。"""

    def test_nonzero_exit_warns_once_no_restart(self):
        launcher = self.make_launcher()
        launcher.start()
        self.handles[0].poll.return_value = 3  # 5003 统一服务进程崩了

        self.assertEqual(launcher.poll_children(), 0)  # 无存活子进程
        warns = [p for p in self.prints if "exit=3" in p]
        self.assertEqual(len(warns), 1)
        self.assertIn("不自动重启", warns[0])
        self.assertIn("start.sh", warns[0])
        # 不自动重启：不会再次 Popen（handles 数不变），且巡检两次只告警一次
        launcher.poll_children()
        self.assertEqual(len(self.handles), 1)
        self.assertEqual(len([p for p in self.prints if "exit=3" in p]), 1)

    def test_zero_exit_is_silent(self):
        launcher = self.make_launcher()
        launcher.start()
        self.handles[0].poll.return_value = 0
        self.assertEqual(launcher.poll_children(), 0)
        self.assertFalse([p for p in self.prints if "exit=0" in p])

    def test_alive_count_when_running(self):
        launcher = self.make_launcher()
        launcher.start()
        self.assertEqual(launcher.poll_children(), 1)


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
        for frag in ("xiaoju3_dashboard.py", ":5003", "console",
                     "start_heartbeat", "127.0.0.1:5003/onebot"):
            self.assertIn(frag, out)
        self.assertNotIn("main.py", out)   # 旧 5002 入口不再出现在计划中


if __name__ == "__main__":
    unittest.main()
