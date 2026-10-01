# -*- coding: utf-8 -*-
"""小橘3号 · 统一启动器：一条命令拉起全栈（心跳 + QQ 接入层 + 控制台）。

用法：
    python xiaoju3_launcher.py             # 前台运行，Ctrl+C 优雅停止全部
    python xiaoju3_launcher.py --dry-run   # 只打印启动计划，不实际拉起

拉起内容与顺序（三行 ✅ 按启动完成顺序打印）：
1. ✅ QQ 接入层已启动 (5002)      —— subprocess: python main.py
2. ✅ 心跳已启动                  —— 宿主于接入层进程（选型见下）
3. ✅ 控制台已启动 (5003/console) —— subprocess: python xiaoju3_dashboard.py

【心跳选型（读码定论）】heartbeat.py 提供两种形态（独立运行入口 /
start_heartbeat() daemon 线程），但 main.py 的 __main__ 已无条件内嵌
start_heartbeat()——python main.py 一启动，心跳即宿主于接入层进程内。
launcher 若再拉第二条心跳（进程内线程或独立进程皆然）会形成双心跳：
两份快照各自 diff，同一环境变化触发两次大模型决策与两次设备控制
（重复控灯、双倍 token，甚至互相打架）。故 launcher 不重复拉起心跳，
仅在 main.py 启动后打印确认行；若未来 main.py 移除内嵌心跳，把计划
中该条目改回 in-process 线程调用 start_heartbeat() 即可。

【进程管理边界】launcher 只负责"拉起 + 优雅终止 + 退出码警告"，
不做异常自动重启——守护循环（异常 2 秒拉起、stop.flag 安全退出）是
start.sh 的职责，两层边界不得混淆。

优雅终止路径（三路幂等，terminate → 超时 kill 兜底，杜绝孤儿进程）：
Ctrl+C（KeyboardInterrupt / SIGINT 处理器置位）、SIGTERM、atexit 收尾。
子进程不接管 stdio（继承本控制台），避免管道缓冲死锁；Ctrl+C 时同控制台
进程组一并收到中断，terminate/kill 兜底收编漏网者。Windows 下 terminate
即 TerminateProcess（无 SIGTERM 优雅语义），POSIX 下为 SIGTERM。

可测性：build_launch_plan / parse_args 为纯函数；subprocess、打印、sleep、
atexit / signal 注册一律构造参数注入，测试离线 mock、不真拉起任何服务。
"""
import argparse
import atexit
import os
import signal
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ✅ 三行确认日志文案（文案口径固定，测试断言）
BANNER_QQ = "✅ QQ 接入层已启动 (5002)"
BANNER_HEARTBEAT = "✅ 心跳已启动"
BANNER_DASHBOARD = "✅ 控制台已启动 (5003/console)"

# 心跳选型说明（随计划条目携带，供测试断言"注释与实现一致性"）
HEARTBEAT_REASON = (
    "heartbeat 为线程形态（start_heartbeat daemon 线程），且 main.py 的 "
    "__main__ 已内嵌 start_heartbeat()——python main.py 一启动心跳即宿主于"
    "接入层进程；launcher 再拉第二条会双心跳（同一变化两次决策、两次控设备、"
    "双倍 token），故不单独拉起。若未来 main.py 移除内嵌心跳，本条目改回 "
    "in-process 线程调用 start_heartbeat() 即可。"
)


def build_launch_plan(python=None, root=None):
    """构造统一启动计划（纯函数，离线可测）。

    条目字段：
    - kind="subprocess"：独立子进程，launcher 持 Popen 句柄管理生命周期；
    - kind="hosted"：随宿主子进程内部自启（不单独 Popen，仅打印确认行）。
    顺序（用户口径）：main 先、dashboard 后（dashboard 的 /api/chat 直连
    brain 与 main 无硬依赖，顺序为部署口径）；心跳随 main 进程，hosted
    条目排在 qq 之后、dashboard 之前，三行 ✅ 按此顺序打印。
    """
    py = python or sys.executable or "python"
    base = root or PROJECT_ROOT
    return [
        {
            "name": "qq",
            "kind": "subprocess",
            "cmd": [py, os.path.join(base, "main.py")],
            "cwd": base,
            "banner": BANNER_QQ,
            "desc": "QQ 接入层（:5002，webhook + API 网关，心跳宿主其中）",
        },
        {
            "name": "heartbeat",
            "kind": "hosted",
            "host": "qq",
            "banner": BANNER_HEARTBEAT,
            "desc": "主动服务心跳（60s 轮询 HA，宿主于接入层进程 daemon 线程）",
            "reason": HEARTBEAT_REASON,
        },
        {
            "name": "dashboard",
            "kind": "subprocess",
            "cmd": [py, os.path.join(base, "xiaoju3_dashboard.py")],
            "cwd": base,
            "banner": BANNER_DASHBOARD,
            "desc": "监控仪表盘 + 网络控制台（:5003，/console 同进程）",
        },
    ]


def parse_args(argv=None):
    """CLI 参数解析（纯函数，便于测试与 --dry-run 冒烟）。"""
    parser = argparse.ArgumentParser(
        prog="xiaoju3_launcher", description="小橘3号统一启动器")
    parser.add_argument("--root", default=None,
                        help="项目根目录（默认：launcher 所在目录）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印启动计划，不实际拉起子进程")
    return parser.parse_args(argv)


class XiaojuLauncher:
    """统一启动器：按计划拉起子进程、持句柄管理、三路幂等优雅终止。

    popen / out / sleep / register_atexit / register_signal 均可注入
    （离线单测 mock 用；测试侧 mock 经 addCleanup 自动还原）。
    """

    TERMINATE_TIMEOUT = 8  # terminate 后等待秒数，超时 kill 兜底

    def __init__(self, plan, popen=None, out=None, sleep=None,
                 register_atexit=None, register_signal=None):
        self.plan = plan
        self.popen = popen or subprocess.Popen
        self.out = out or print
        self.sleep = sleep or time.sleep
        self.register_atexit = register_atexit or atexit.register
        self.register_signal = register_signal or signal.signal
        self.procs = []            # [(entry, Popen 句柄)]，仅 kind=subprocess
        self._warned = set()       # 已告警过的退出子进程（告警只打一次）
        self._stop = False         # 信号置位标志（优雅退出主循环）
        self._shutdown_done = False  # atexit / 信号 / 主循环三路幂等护栏

    # ==================== 拉起 ====================

    def start(self):
        """按计划顺序拉起：subprocess 条目 Popen，hosted 条目仅打印确认行。

        子进程继承本进程控制台（不接管管道，避免缓冲死锁）。三行 ✅ 按
        启动完成顺序打印：qq → heartbeat（随 qq 进程）→ dashboard。
        """
        for entry in self.plan:
            kind = entry.get("kind")
            if kind == "subprocess":
                proc = self.popen(entry["cmd"], cwd=entry.get("cwd"))
                self.procs.append((entry, proc))
            elif kind == "hosted":
                pass  # 宿主形态：随宿主子进程内部自启，此处只打印确认行
            else:
                raise ValueError(f"未知启动形态: {kind!r}（{entry.get('name')}）")
            self.out(entry["banner"])
        # atexit 双保险：无论从哪条路径退出（主循环 return、信号、异常
        # 冒泡），解释器收尾时都再清一次子进程（shutdown 幂等，不重复杀）
        self.register_atexit(self.shutdown)
        self._install_signal_handlers()
        return self.procs

    def _install_signal_handlers(self):
        """SIGINT/SIGTERM → 置位优雅退出。Ctrl+C 常态由本处理器接住
        （KeyboardInterrupt 分支为注册失败时的兜底）；注册失败（如非主
        线程）静默跳过，atexit 仍兜底。"""
        def handler(signum, frame):
            self._stop = True
            self.out("🛑 收到退出信号，正在优雅停止全部子进程...")

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self.register_signal(sig, handler)
            except (ValueError, OSError, AttributeError):
                pass

    # ==================== 主循环 ====================

    def run(self, poll_interval=5):
        """前台主循环：拉起 → 巡检退出码 → 优雅收尾。返回退出码。

        退出路径：SIGINT/SIGTERM 置位、Ctrl+C（KeyboardInterrupt 兜底）、
        全部子进程已退出（launcher 无留守意义）。
        """
        self.start()
        self.out("🚀 小橘3号已整体拉起（Ctrl+C 优雅停止全部模块）")
        try:
            while not self._stop:
                if self.poll_children() == 0:
                    self.out("🛑 全部子进程已退出，launcher 随之退出。")
                    break
                self.sleep(poll_interval)
        except KeyboardInterrupt:
            self._stop = True
            self.out("🛑 收到 Ctrl+C，正在优雅停止全部子进程...")
        self.shutdown()
        return 0

    # ==================== 巡检 ====================

    def poll_children(self):
        """巡检子进程退出码：非 0 打印一次警告（不自动重启——重启属
        start.sh 守护职责，边界见模块 docstring）；0 为正常退出静默。
        返回存活子进程数。"""
        alive = 0
        for entry, proc in self.procs:
            code = proc.poll()
            if code is None:
                alive += 1
            elif code != 0 and entry["name"] not in self._warned:
                self._warned.add(entry["name"])
                self.out(f"⚠️ [{entry['name']}] 子进程已退出（exit={code}），"
                         "不自动重启（重启属 start.sh 守护职责）")
        return alive

    # ==================== 终止 ====================

    def shutdown(self, timeout=None):
        """优雅终止全部子进程（幂等，三路退出入口共用）。

        逆启动序收尾（先 dashboard 后 main，接入层最后退便于上游先断）：
        terminate → 等 timeout 秒 → 超时 kill 兜底；已退出的直接跳过
        （send_signal 对已死进程安全）。"""
        if self._shutdown_done:
            return
        self._shutdown_done = True
        if timeout is None:
            timeout = self.TERMINATE_TIMEOUT
        for entry, proc in reversed(self.procs):
            if proc.poll() is not None:
                continue  # 已退出，无需终止
            name = entry["name"]
            try:
                self.out(f"🛑 正在停止 {name}...")
                proc.terminate()
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    self.out(f"⚠️ [{name}] terminate 超时，kill 兜底")
                    proc.kill()
                    proc.wait(timeout=timeout)
                self.out(f"✅ [{name}] 已停止")
            except Exception as e:  # 单个收尾失败不阻断其余子进程清理
                self.out(f"⚠️ [{name}] 终止异常（忽略，继续收尾）: {e}")
        self.procs = []


def main(argv=None):
    """入口：--dry-run 只打印计划（零副作用）；否则前台拉起并守护。"""
    args = parse_args(argv)
    plan = build_launch_plan(root=args.root)
    if args.dry_run:
        print("📋 小橘3号启动计划（--dry-run，未实际拉起）：")
        for entry in plan:
            target = entry.get("cmd") or f"(宿主于 {entry['host']} 进程)"
            print(f"  - {entry['name']}: {target}")
            print(f"      {entry.get('reason') or entry.get('desc', '')}")
        return 0
    launcher = XiaojuLauncher(plan)
    return launcher.run()


if __name__ == "__main__":
    sys.exit(main())
