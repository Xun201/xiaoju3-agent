# -*- coding: utf-8 -*-
"""小橘3号 · 桌面软件化主入口（pywebview 原生桌面窗口，desktop_launcher.py）。

用户口径："像 exe 一样的本地独立桌面窗口"——双击/启动小橘3号.bat 拉起本模块：
  ① subprocess 后台拉起统一启动器 xiaoju3_launcher.py（S2 交付：拉起
    xiaoju3_dashboard.py(:5003——QQ webhook/onebot、指令族、心跳引擎已全部宿主其中)）；
    若 :5003 已监听则跳过拉起，提示复用现有进程；
  ② pywebview 打开原生窗口（标题"小橘3号 · 控制台"，1200x800，可最小化/
    可关闭，无地址栏），加载本机回环内置服务的 /console 页面——
    **绝对禁止加载任何外网 URL**。

【窗口加载方案（沿用 M4 既有机制，零回退）】
  webview 启动一个仅绑定 127.0.0.1 回环地址的内置线程服务（复用
  xiaoju3_dashboard.app，端口默认随机 :0），窗口加载
  http://127.0.0.1:<port>/console。前端 fetch 全部为相对路径（已核实
  console.js），同源直达内置服务，/api/* 既有路由原样复用——不碰前端
  三件套（console.js / index.html / desktop-pet.js）。
  --serve-port 参数保留（M4 兼容）：显式指定内置服务端口，缺省随机。

【离线优先通信（不改任何既有链路，仅核实）】
  - 本地 Ollama 聊天 / 本地文件读取本就离线可用（brain 既有链路）；
  - 断网时 brain.smart_ask 返回 "❌ 大脑连接失败，请检查网络。..." 回复文案
    （brain.py 既有降级，前端气泡照常上屏、不白屏）；
  - /api/balance 请求失败回退 0.0 + 错误提示（xiaoju3_dashboard 既有口径）。

【后台进程生命周期（桌面软件化新增）】
  启动（ensure_backend_services）：
    :5003 在线 → 复用现有进程，不重复拉起；否则后台 Popen
    拉起 xiaoju3_launcher.py。子进程 stdin/out/err 全部 DEVNULL（pythonw
    下无控制台句柄也稳，杜绝 print 崩溃与管道缓冲死锁）；Windows
    creationflags=CREATE_NO_WINDOW 防闪黑窗；POSIX start_new_session=True
    独立成组便于整组回收；解释器为 pythonw 无窗口形态（2026-10-02 用户
    指令：pythonw 场景原样用 sys.executable，控制台场景解析同目录孪生
    pythonw.exe，缺席回退原解释器——全程无黑框）。
  关闭（窗口关闭 → 自动停止全部后台进程，finally 兜底）：
    先停本进程内置服务线程（M4 既有 stop_local_server，防僵尸端口驻留），
    再整树终止 xiaoju3_launcher.py（stop_backend_launcher）：优先 psutil
    （白名单依赖，已装则进程树 terminate→超时 kill）；psutil 未装则
    Windows 用 `taskkill /T /F /PID`（/T 连子进程整树）、POSIX 用
    os.killpg 向进程组发 SIGTERM（跨平台写法均保留，零新依赖）；最后
    proc.kill()/wait() 回收自身 spawn 的句柄。proc 为 None（复用现有
    进程 / 脚本缺失 / 拉起失败）时不做任何事——绝不误杀非本模块拉起的
    进程。关闭窗口即停全部，无孤儿进程驻留。

【启动探测】
  控制台（:5003）未在线且后台启动器缺位（脚本缺失/拉起失败）时，
  打印（并注入窗口标题）"主程序未启动，聊天功能受限"——窗口仍可打开界面
  （状态/历史等仪表盘功能不受影响）；自拉启动器途中不打该过时提示。

用法：
  python desktop_launcher.py                  # 内置服务端口随机
  python desktop_launcher.py --serve-port 5900  # 指定内置服务端口

【打包规划（文档标记，暂不实施）】
  pyinstaller -F -w desktop_launcher.py 打包为单文件免终端 exe → 🔜 规划中
  （届时需把 xiaoju3_launcher.py / xiaoju3_dashboard.py 等作为
  随包数据一并处理）。
"""
import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time

from werkzeug.serving import make_server

import paths  # 双根路径锚（方案 §1）：frozen 分支按 RESOURCE/DATA_ROOT 分流
from xiaoju3_dashboard import app   # 复用全部既有路由（/console、/api/*）

WINDOW_TITLE = "小橘3号 · 控制台"      # 桌面窗口标题（用户口径）
WINDOW_WIDTH = 1200                   # 窗口尺寸（用户口径 1200x800）
WINDOW_HEIGHT = 800
DEFAULT_HOST = "127.0.0.1"           # 内置服务只听回环地址（离线红线）
# 控制台固定端口（5003——QQ webhook/onebot 已宿主其中），用于启动探测/复用检测
DASHBOARD_APP_PORT = 5003
# xiaoju3_dashboard.py 控制台固定端口，用于后台服务复用检测
DASHBOARD_PORT = 5003
# xiaoju3_launcher.py 的解释器（后台子树口径，2026-10-02 用户指令：pythonw
# 无窗口形态）——见 _windowless_python()
LAUNCHER_SCRIPT = "xiaoju3_launcher.py"
# spawn-self 角色标志（方案 §2.1）：exe 单一入口按 argv 分流三角色——
# 无标志=桌面主进程（缺省，双击形态）。与 xiaoju3_launcher.ROLE_DASHBOARD_FLAG
# 保持字面一致（测试锁定）。
ROLE_LAUNCHER_FLAG = "--xj3-role=launcher"
ROLE_DASHBOARD_FLAG = "--xj3-role=dashboard"
# Windows creationflags：CREATE_NO_WINDOW（防闪黑窗；POSIX 无此常量，回退同值）
_WIN_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

MAIN_NOT_RUNNING_HINT = "⚠️ 主程序未启动，聊天功能受限（界面仍可打开）"
LAUNCHER_REUSE_HINT = "ℹ️ 控制台(5003)已在运行，复用现有进程"
LAUNCHER_MISSING_HINT = ("ℹ️ 未找到 " + LAUNCHER_SCRIPT +
                         "，跳过后台服务拉起（仅打开控制台窗口）")
MISSING_WEBVIEW_HINT = (
    "未检测到 pywebview，无法打开离线桌面窗口。\n"
    "请先安装依赖后重试：pip install pywebview==6.2.1"
)


def _print(msg, err=False):
    """安全打印：pythonw 下 sys.stdout/stderr 为 None，直接 print 会崩。"""
    stream = sys.stderr if err else sys.stdout
    if stream is None:
        return
    try:
        print(msg, file=stream)
    except Exception:
        pass


def parse_args(argv=None):
    """解析命令行参数：--serve-port <port> 指定内置服务端口（默认随机）。"""
    parser = argparse.ArgumentParser(
        description="小橘3号 · 桌面控制台（pywebview 主入口）")
    parser.add_argument("--serve-port", type=int, default=None,
                        help="内置本地服务端口（缺省由系统随机分配）")
    return parser.parse_args(argv)


def start_local_server(port=None, host=DEFAULT_HOST):
    """启动仅绑定 host（默认 127.0.0.1 回环）的内置线程服务。

    port 为 None/0 时由系统随机分配可用端口（make_server 绑定完成后
    server.server_port 即真实端口，pywebview 据此拼 URL）；threaded=True
    支撑前端 2s 状态轮询与聊天的并发请求。服务线程为 daemon。

    返回 (server, thread)：server 含 server_port / shutdown() /
    server_close()；stop_local_server 消费同一对对象完成关闭清理。
    """
    server = make_server(host, port or 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever,
                              name="xiaoju3-console-local", daemon=True)
    thread.start()
    return server, thread


def stop_local_server(server, thread=None):
    """关闭清理：shutdown() 停 serve_forever 循环 → join 线程 →
    server_close() 释放端口（webview 窗口关闭后调用，防僵尸驻留）。

    注意 shutdown() 必须从 serve_forever 之外线程调用（本函数调用方为
    主线程/测试线程）；各步骤容错，保证清理流程走到释放端口为止。
    """
    try:
        server.shutdown()
    except Exception:
        pass
    if thread is not None:
        thread.join(timeout=5)
    try:
        server.server_close()
    except Exception:
        pass


def _is_port_listening(port, timeout=1.0):
    """探测本机回环端口是否已监听（纯 socket 连接，无 HTTP 副作用）。"""
    try:
        with socket.create_connection((DEFAULT_HOST, port), timeout=timeout):
            return True
    except OSError:
        return False


def _is_main_running(port=DASHBOARD_APP_PORT, timeout=1.0):
    """探测控制台服务（:5003）是否在线（复用 _is_port_listening）。"""
    return _is_port_listening(port, timeout=timeout)


def wait_for_dashboard_ready(timeout_s=15.0, interval_s=0.5,
                             check_fn=None, sleep_fn=None):
    """轮询等待 :5003 就绪（端口修复设计 docs/DESKTOP_PORT_FIX.md §1，P1）。

    纯函数式时序：check_fn 缺省复用 _is_port_listening（纯 socket connect，
    无 HTTP 副作用）；sleep_fn 可注入使单测零真实等待。就绪返回 True，
    超时返回 False（调用方决定超时后的窗口/提示行为）。
    """
    check = check_fn or _is_port_listening
    sleep = sleep_fn or time.sleep
    deadline = time.monotonic() + float(timeout_s)
    while True:
        try:
            if check(DASHBOARD_APP_PORT):
                return True
        except Exception:
            pass   # 探针异常按"本轮未就绪"处理，继续轮询
        if time.monotonic() >= deadline:
            return False
        sleep(interval_s)


def _windowless_python():
    """后台子进程用解释器（2026-10-02 用户口径：pythonw 无窗口形态）。

    pythonw 场景（双击 bat 主链路，sys.executable 即 pythonw）直接原样使用
    ——xiaoju3_launcher.py 内部以 sys.executable 拉起 xiaoju3_dashboard.py，
    pythonw 形态沿子树自动传导，全程无控制台；控制台 python 场景（开发者
    CLI 跑 python desktop_launcher.py）解析同目录 pythonw.exe 孪生，孪生
    缺席（精简发行版等）时回退 sys.executable——此时子进程仍有
    CREATE_NO_WINDOW 兜底防黑窗。"""
    exe = sys.executable or "python"
    if not os.path.basename(exe).lower().startswith("pythonw"):
        twin = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.isfile(twin):
            return twin
    return exe


def route_argv(argv):
    """角色分流（纯函数，方案 §2.1）：返回 "launcher" / "dashboard" / "desktop"。

    exe（frozen）单一入口按 argv 标志把三种角色分流到对应主函数；
    无标志 = 桌面主进程（缺省，双击形态）。首个命中的标志生效，
    标志串与写入格式严格一致（大小写敏感）。
    """
    for a in argv or []:
        if a == ROLE_LAUNCHER_FLAG:
            return "launcher"
        if a == ROLE_DASHBOARD_FLAG:
            return "dashboard"
    return "desktop"


def start_backend_launcher():
    """subprocess 后台拉起统一启动器 xiaoju3_launcher.py。

    它再拉起控制台服务 xiaoju3_dashboard.py(:5003——QQ webhook/心跳宿主其中)。
    返回 Popen 句柄（供窗口关闭后整树终止）；脚本缺失/拉起失败返回 None
    （仅打开控制台窗口，不报错中断）。

    frozen 分支（方案 §2）：exe 以 launcher 角色 spawn 自身——无 .py 脚本
    可查（跳过存在性检查），解释器即 exe 自身，cwd 取数据根（可写持久）。
    """
    if paths.FROZEN:
        cmd = [sys.executable, ROLE_LAUNCHER_FLAG]
        kwargs = {"cwd": paths.DATA_ROOT,
                  "stdin": subprocess.DEVNULL,
                  "stdout": subprocess.DEVNULL,
                  "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = _WIN_CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        try:
            proc = subprocess.Popen(cmd, **kwargs)
        except OSError as e:
            _print(f"⚠️ 后台服务拉起失败（exe spawn-self）: {e}", err=True)
            return None
        _print(f"🚀 已后台拉起启动器角色（PID {proc.pid}）："
               "心跳/主程序/控制台启动中…")
        return proc
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          LAUNCHER_SCRIPT)
    if not os.path.isfile(script):
        _print(LAUNCHER_MISSING_HINT)
        return None
    # stdio 全部 DEVNULL：pythonw 链路下子进程无控制台句柄也稳（print 不崩）
    kwargs = {"cwd": os.path.dirname(script),
              "stdin": subprocess.DEVNULL,
              "stdout": subprocess.DEVNULL,
              "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = _WIN_CREATE_NO_WINDOW   # 防闪黑窗
    else:
        # POSIX：独立进程组，关闭时 killpg 整组回收（见 stop_backend_launcher）
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen([_windowless_python(), script], **kwargs)
    except OSError as e:
        _print(f"⚠️ 后台服务拉起失败（{LAUNCHER_SCRIPT}）: {e}", err=True)
        return None
    _print(f"🚀 已后台拉起 {LAUNCHER_SCRIPT}（PID {proc.pid}）："
           "心跳/主程序/控制台启动中…")
    return proc


def ensure_backend_services():
    """后台服务决策：:5003 已监听 → 复用现有进程（跳过拉起）；
    否则后台拉起 xiaoju3_launcher.py。返回 Popen 句柄或 None。"""
    if _is_port_listening(DASHBOARD_APP_PORT):
        _print(LAUNCHER_REUSE_HINT)
        return None
    return start_backend_launcher()


def stop_backend_launcher(proc, timeout=5):
    """窗口关闭 → 整树终止后台启动器 xiaoju3_launcher.py（含其全部子进程）。

    终止策略（零新依赖，跨平台写法均保留）：
    - psutil 已装（白名单依赖）：进程树 terminate → 超时 kill 兜底；
    - psutil 未装 + Windows：`taskkill /T /F /PID`（/T 连整棵进程树）；
    - psutil 未装 + POSIX：os.killpg 向独立进程组发 SIGTERM（进程组由
      启动时 start_new_session=True 保证；启动器的 SIGTERM 处理器会
      优雅收尾子进程）。
    最后 proc.kill()/wait() 兜底回收自身 spawn 的句柄，杜绝孤儿进程与
    僵尸句柄。proc 为 None 或已自行退出时不做任何事（不误杀他人进程）。
    """
    if proc is None:
        return
    try:
        if proc.poll() is not None:      # 已自行退出，无需清理
            return
        try:
            import psutil                # 白名单依赖：装了就整树优雅终止
        except ImportError:
            psutil = None
        if psutil is not None:
            try:
                parent = psutil.Process(proc.pid)
                procs = [parent] + parent.children(recursive=True)
                for p in procs:
                    try:
                        p.terminate()
                    except psutil.NoSuchProcess:
                        pass
                _, alive = psutil.wait_procs(procs, timeout=timeout)
                for p in alive:
                    try:
                        p.kill()
                    except psutil.NoSuchProcess:
                        pass
            except psutil.Error:         # 进程已消失等竞态：忽略
                pass
        elif os.name == "nt":
            # 无 psutil 的 Windows：taskkill /T 连子进程整树强杀
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, check=False)
        else:
            # POSIX：向启动时独立成组的进程组发 SIGTERM（组内含全部子进程）
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                proc.terminate()
        # 兜底：等待退出并回收自身 spawn 的句柄（超时强杀再回收）
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=timeout)
    except Exception:
        pass   # 清理尽力而为：任何异常不阻塞窗口关闭与主进程退出


def _supervise_backend(state, stop_event, respawn_fn, out=None,
                       poll_interval=2.0, max_restarts=3, window=60.0):
    """后台服务监督线程（2026-10-02，restart_service 复活链 Windows 形态）。

    窗口存活期间 launcher 进程意外退出（含 restart_service 受理后的
    2 秒自尽）→ 自动 respawn；60 秒窗口内最多 max_restarts 次防循环；
    stop_event 置位（正常关窗清理路径最先置位）即退出，绝不与手动关闭
    竞争。state 为 {"proc": Popen|None} 共享字典，respawn 后回写。
    """
    out = out or (lambda msg: None)
    restarts = []
    while not stop_event.is_set():
        proc = state.get("proc")
        if proc is not None and proc.poll() is not None:
            now = time.time()
            restarts = [t for t in restarts if now - t < window]
            if len(restarts) >= max_restarts:
                out("⚠️ 后台服务连续异常退出（60 秒内 3 次），已停止自动重启。")
                return
            restarts.append(now)
            out("🔁 后台服务意外退出，自动重启（restart_service 受理/异常恢复）...")
            state["proc"] = respawn_fn()
        stop_event.wait(poll_interval)


def main(argv=None):
    """入口：缺 pywebview 中文提示退出；拉后台服务 → 开窗口 → 关闭全清理。

    返回退出码：0 正常（窗口关闭并清理完成）；1 环境不满足（缺 pywebview /
    端口不可用）。
    """
    from xiaoju3_launcher import _redirect_stdio  # 延迟导入：非 frozen 依赖面零变化
    _redirect_stdio("desktop")  # frozen 入口重定向（步 3）；非 frozen 空操作
    try:
        import webview   # 延迟导入：缺库时清晰中文提示退出，不甩 traceback
    except Exception:
        _print(MISSING_WEBVIEW_HINT, err=True)
        return 1

    args = parse_args(argv)

    # ① 后台服务：:5003 已监听则复用现有进程，否则后台拉起统一启动器
    launcher_proc = ensure_backend_services()
    # 🔁 监督线程（2026-10-02）：窗口存活期间后台服务意外退出自动重启
    # （restart_service 复活链 Windows 形态）；正常关窗时 finally 最先
    # 置位 stop_event，监督线程随即退出，不与手动清理竞争
    backend_state = {"proc": launcher_proc}
    stop_event = threading.Event()
    if launcher_proc is not None:
        threading.Thread(
            target=_supervise_backend,
            args=(backend_state, stop_event, ensure_backend_services, _print),
            daemon=True).start()

    # ② 启动探测：主程序未在线且没有启动器在拉起途中 → 提示"聊天功能受限"
    #   （自拉启动器时主程序数秒后就绪，不打过时提示；窗口仍可打开界面）
    main_ok = _is_main_running()
    main_hint = not main_ok and launcher_proc is None
    if main_hint:
        _print(MAIN_NOT_RUNNING_HINT)

    try:
        server, thread = start_local_server(args.serve_port)
    except OSError as e:
        _print(f"内置本地服务启动失败（端口 {args.serve_port or '随机'}）: {e}",
               err=True)
        stop_backend_launcher(launcher_proc)   # 失败退出也回收已拉起的子进程
        return 1

    url = f"http://{DEFAULT_HOST}:{server.server_port}/console"
    # 原生桌面窗口：无地址栏，可最小化/可关闭（pywebview 默认能力）
    window = webview.create_window(WINDOW_TITLE, url,
                                   width=WINDOW_WIDTH, height=WINDOW_HEIGHT)

    def _on_loaded(*_):
        # 窗口内可见且非阻塞的提示：标题后缀（不用 alert，避免卡 GUI 线程）
        if main_hint:
            try:
                window.evaluate_js(
                    "document.title += '（主程序未启动，聊天功能受限）'")
            except Exception:
                pass

    try:
        window.events.loaded += _on_loaded
    except Exception:
        pass   # 个别后端事件系统不可用时静默跳过（终端已有打印提示）

    try:
        webview.start()   # 阻塞至窗口关闭
    finally:
        # 关闭清理：先停内置服务线程（M4 既有，防僵尸端口），再整树终止
        # xiaoju3_launcher.py（含心跳/main/dashboard 子进程）——关窗口即
        # 停全部后台进程，无孤儿驻留
        stop_event.set()   # 先停监督线程：正常关窗不再触发自动重启
        stop_local_server(server, thread)
        stop_backend_launcher(backend_state["proc"])
    return 0


if __name__ == "__main__":
    import multiprocessing
    # PyInstaller 冻结形态安全阀（方案 §2.2）：onefile 子进程引导必需
    multiprocessing.freeze_support()
    # spawn-self 角色分流（方案 §2.1）：exe 单一入口，按 argv 标志进三角色。
    # launcher/dashboard 角色延迟 import——非 frozen 桌面形态依赖面零变化。
    role = route_argv(sys.argv[1:])
    if role == "launcher":
        import xiaoju3_launcher
        rest = [a for a in sys.argv[1:] if a != ROLE_LAUNCHER_FLAG]
        sys.exit(xiaoju3_launcher.main(rest, frozen=True))
    if role == "dashboard":
        import xiaoju3_dashboard
        xiaoju3_dashboard.serve()
        sys.exit(0)
    sys.exit(main())
