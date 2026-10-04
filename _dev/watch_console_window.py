# -*- coding: utf-8 -*-
"""常驻窗口监控（后台静默）——抓 DeepSeek 待办提取链路的偶发闪窗黑框。

背景（2026-10-04）：v8 冻结包抓取时黑框偶发（录屏不闪、EnumWindows 0.08s
采样也未捕获——竞态/极短存活）。本脚本改用 **SetWinEventHook 事件驱动**
（EVENT_OBJECT_SHOW，系统推送、零采样遗漏），常驻后台，命中即落盘留证。

过滤口径：
- 顶层可见窗口（GA_ROOT + IsWindowVisible），**不限窗口类名**（黑框未必是
  CONSOLE 类——上轮采样只盯 CONSOLE 类可能正是漏抓原因）；
- 进程归属 xiaoju3.exe 树（沿 ppid 上溯 ≤4 层；抓取链 node/chrome/conhost
  均在其中）——排除系统与其他软件噪音；
- 同一 hwnd 去抖（60 秒内重复 SHOW 不重记）。

日志：追加 xiaoju3_data/console_window_watch.log（UTF-8），每行：
  时间戳 | 类名 | pid | 进程名 | ppid | rect | 命令行(截断)
命中同时 print（前台运行时可观察）。

用法：
  python _dev/watch_console_window.py                 # 常驻（Ctrl+C 停）
  start "" pythonw _dev/watch_console_window.py       # 后台静默（无窗口）
  python _dev/watch_console_window.py --duration 600  # 限时 600 秒自退

不改核心代码；随仓维护的常驻观察工具（2026-10-04 收编，停止 = Ctrl+C 或按 PID 结束 pythonw）。
"""
import argparse
import datetime
import ctypes
import os
import sys
import time
import ctypes.wintypes as wt

import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import DATA_ROOT   # noqa: E402  日志落数据根（双根基建；dev=项目根，frozen=exe 目录）

LOG_FILE = os.path.join(DATA_ROOT, "xiaoju3_data", "console_window_watch.log")
EVENT_OBJECT_SHOW = 0x8002
WINEVENT_OUTOFCONTEXT = 0
WINEVENT_SKIPOWNTHREAD = 2
GA_ROOT = 2
DEDUP_WINDOW_SECONDS = 60.0
ROOT_PROC_NAME = "xiaoju3.exe"
MAX_CMDLINE_CHARS = 160

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
WinEventProc = ctypes.WINFUNCTYPE(
    None, ctypes.c_void_p, wt.DWORD, wt.HWND, wt.LONG, wt.LONG, ctypes.c_uint32, ctypes.c_uint32)


def log_line(text):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    line = f"{stamp} | {text}"
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"⚠️ 日志写入失败: {e}")
    print(line)


def proc_tree_contains(pid, root_name=ROOT_PROC_NAME, max_depth=4):
    """pid 是否位于 root_name 进程树内（沿 ppid 上溯 ≤max_depth 层）。"""
    current = pid
    for _ in range(max_depth):
        try:
            p = psutil.Process(current)
        except psutil.Error:
            return False
        if p.name() == root_name:
            return True
        try:
            current = p.ppid()
        except psutil.Error:
            return False
        if not current:
            return False
    return False


def make_callback(state):
    @WinEventProc
    def callback(hook, event, hwnd, id_object, id_child, thread_id, event_time):
        if id_object != 0:            # 只要 OBJID_WINDOW
            return
        try:
            if not user32.IsWindowVisible(hwnd):
                return
            if user32.GetAncestor(hwnd, GA_ROOT) != hwnd:
                return                # 只记顶层窗口
            now = time.time()
            seen = state["seen"]
            if hwnd in seen and now - seen[hwnd] < DEDUP_WINDOW_SECONDS:
                return                # 去抖：同窗短时重复 SHOW
            seen[hwnd] = now
            if len(seen) > 4096:      # 防长期驻留膨胀
                cutoff = now - DEDUP_WINDOW_SECONDS * 2
                for k in [k for k, v in seen.items() if v < cutoff]:
                    seen.pop(k, None)

            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            pid_val = pid.value
            if not proc_tree_contains(pid_val):
                return                # 不在 xiaoju3 树内：忽略
            buf = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(hwnd, buf, 128)
            rect = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            try:
                p = psutil.Process(pid_val)
                name, ppid = p.name(), p.ppid()
                cmdline = " ".join(p.cmdline())[:MAX_CMDLINE_CHARS]
            except (psutil.Error, psutil.AccessDenied):
                name, ppid, cmdline = "?", 0, ""
            log_line(f"{buf.value} | pid={pid_val} {name} ppid={ppid} | "
                     f"rect=({rect.left},{rect.top})-({rect.right},{rect.bottom}) | {cmdline}")
        except Exception:
            pass
    return callback


def pump_until(deadline):
    msg = wt.MSG()
    while time.time() < deadline:
        r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if r <= 0:
            break


def main():
    parser = argparse.ArgumentParser(description="常驻窗口监控（抓提取链偶发闪窗）")
    parser.add_argument("--duration", type=float, default=0,
                        help="运行秒数；0=常驻（Ctrl+C 停）")
    args = parser.parse_args()

    log_line(f"=== 监控启动 pid={kernel32.GetCurrentProcessId()} "
             f"duration={args.duration or '常驻'} ===")
    callback = make_callback({"seen": {}})
    hook = user32.SetWinEventHook(
        EVENT_OBJECT_SHOW, EVENT_OBJECT_SHOW, 0, callback, 0, 0,
        WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNTHREAD)
    if not hook:
        print("[FAIL] SetWinEventHook 失败")
        return 1
    print(f"监控已启动（EVENT_OBJECT_SHOW 事件驱动，日志: {LOG_FILE}）")

    deadline = time.time() + args.duration if args.duration > 0 else float("inf")
    try:
        pump_until(deadline)
    except KeyboardInterrupt:
        pass
    user32.UnhookWinEvent(hook)
    log_line("=== 监控停止 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
