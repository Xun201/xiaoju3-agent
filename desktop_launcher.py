# -*- coding: utf-8 -*-
"""小橘3号 · 桌面软件化主入口（pywebview 原生桌面窗口，desktop_launcher.py）。

用户口径："像 exe 一样的本地独立桌面窗口"——双击/启动小橘3号.bat 拉起本模块：
  ① subprocess 后台拉起统一启动器 xiaoju3_launcher.py（S2 交付：拉起
    xiaoju3_dashboard.py(:5003——QQ webhook/onebot、指令族、心跳引擎已全部宿主其中)）；
    若 :5003 已监听则跳过拉起，提示复用现有进程；
  ② pywebview 打开原生窗口（标题"小橘3号 · 控制台"，1200x800，可最小化/
    可关闭，无地址栏），窗口先显示"正在启动主程序…"占位页，就绪后
    导航到 http://127.0.0.1:5003/console——
    **绝对禁止加载任何外网 URL**。

【窗口加载方案（端口修复 2bed65b 前身 d9551cf，2026-10-03 定稿）】
  旧形态（已退役）：desktop 进程自起随机端口本地服务——
  随机端口可能抽中 Chromium ERR_UNSAFE_PORT 黑名单（真机 6697 实锤），
  窗口直接白屏。
  新形态：desktop **不再起任何本地服务**——先建占位窗（PLACEHOLDER_HTML），
  经 webview.start(回调) 在 GUI 就绪后后台轮询 wait_for_dashboard_ready()
  （复用 _is_port_listening 探 :5003），就绪即 window.load_url 到
  http://127.0.0.1:5003/console。前端 fetch 全部为相对路径（已核实
  console.js），同源直达 5003 主服务，/api/* 既有路由原样复用——不碰前端
  三件套（console.js / index.html / desktop-pet.js）。显式端口参数随
  内置服务一并退役（从未被 bat/自启/exe 使用）。

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
    整树终止 xiaoju3_launcher.py（stop_backend_launcher）：优先 psutil
    （白名单依赖，已装则进程树 terminate→超时 kill）；psutil 未装则
    Windows 用 `taskkill /T /F /PID`（/T 连子进程整树）、POSIX 用
    os.killpg 向进程组发 SIGTERM（跨平台写法均保留，零新依赖）；最后
    proc.kill()/wait() 回收自身 spawn 的句柄。proc 为 None（复用现有
    进程 / 脚本缺失 / 拉起失败）时不做任何事——绝不误杀非本模块拉起的
    进程。关闭窗口即停全部，无孤儿进程驻留。
    （旧"先停内置服务线程"步骤随内置服务退役一并移除。）

【启动探测】
  新形态：launcher 已自拉 → wait_for_dashboard_ready 轮询 :5003（15s 上限）；
  launcher 缺位且 :5003 不在线（无人会拉起）→ 跳过等待直接导航（错误页 +
  标题提示）。超时/缺位两条路径都仍创建窗口——窗口是唯一 UI 出口。

用法：
  python desktop_launcher.py                  # 占位窗 → 就绪后自动进控制台

【打包规划（已实施：xiaoju3.spec + build_exe.bat，见 docs/EXE_PACKAGING_PLAN.md；
  spawn-self 三角色由 argv 标志分流，route_argv/ROLE_* 常量）】
"""
import glob
import json
import os
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

import paths  # 双根路径锚（方案 §1）：frozen 分支按 RESOURCE/DATA_ROOT 分流
# xiaoju3_dashboard 不再顶层 import（2026-10-04 启动优化拍板②）：全链
# ≈1.1s 曾把占位窗拖到 ≈3.8s 才出现。收录职责由 xiaoju3.spec hiddenimports
# 静态承担（xiaoju3_dashboard/main 等显式在列）；运行时唯一引用点 =
# __main__ 的 dashboard 角色分流（本就函数内延迟导入）。防回流锚：
# tests/test_desktop_launcher.py（ast 断言模块体顶层零 dashboard import）。

# 白屏缓解（2026-10-07 拍板：低风险快改）：最小化时 WebView2 渲染器不再被
# 挂起/后台化——恢复窗口即现，无整页白闪重绘。必须在 WebView2 环境创建
# （webview 懒导入于 main）之前生效，故放模块导入期；setdefault 允许 env 覆盖。
# 2026-10-13 补强（最小化恢复白屏 3-5s 实锤）：
# - --disable-features=CalculateNativeWinOcclusion：Windows 原生遮挡
#   计算把最小化判为"完全遮挡"→合成器冻结出帧→恢复需 3-5s 重建；
#   前两个参数管后台优先级，管不到这条 feature 机制（真机复现实锤）
# - --disable-background-timer-throttling：后台定时器节流（前端 2s
#   状态轮询/15s 终端刷新在最小化期被降频，恢复时积压滞后）
# - msWebOOUI/msPdfOOUI/msSmartScreenProtection：WebView2 常规推荐
#   组合（UI 部件特性+SmartScreen 对本地回环误标）
# 代价（如实记录）：渲染进程最小化期不释放——内存/CPU 代价一条
# 渲染进程，桌面主窗常驻场景可接受。
os.environ.setdefault(
    "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
    "--disable-backgrounding-occluded-windows --disable-renderer-backgrounding "
    "--disable-background-timer-throttling "
    "--disable-features=CalculateNativeWinOcclusion,msWebOOUI,msPdfOOUI,"
    "msSmartScreenProtection")

# 单实例互斥体（#263）：**模块导入期即持锁**——2026-10-07 真机双开实锤：
# 互斥体若在 main() 里才建，onedir 初始化期（登录风暴下 186MB 依赖导入
# 10-30 秒）就是双开空窗（自启实例与用户双击双双过门）。导入期建锁后
# 空窗缩到进程创建的亚秒级。main() 读 _SI_ALREADY 旗标做"唤起+退出"UX。
_SI_MUTEX = "Local\\Xiaoju3_Desktop_SingleInstance"
_SI_HANDLE = None
_SI_ALREADY = False
if os.name == "nt" and not any(
        a.startswith("--xj3-role=") for a in sys.argv[1:]):
    # 方案 A 角色守卫（v23 冒烟实锤）：仅桌面角色建锁。exe 单一入口=
    # 本模块，launcher/dashboard 角色启动同样加载它——此前无差别持锁
    # 把后到的桌面窗 _SI_ALREADY 污染成 True → 登录链桌面窗被门误杀
    # （"窗口启动中"+return 0 永无窗）；后端持锁还使门 or 短路，掩盖
    # 5003 探测分支（连带 NameError 藏至 v21 车才炸）。
    import ctypes
    _SI_HANDLE = ctypes.windll.kernel32.CreateMutexW(None, False, _SI_MUTEX)
    _SI_ALREADY = bool(
        ctypes.windll.kernel32.GetLastError() == 183)   # ERROR_ALREADY_EXISTS

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
# 控制台页完整 URL（端口修复 P2：窗口直接挂 5003 主服务，随机内置服务已退役）
CONSOLE_URL = f"http://{DEFAULT_HOST}:{DASHBOARD_APP_PORT}/console"
# 占位页（先出窗后导航：create_window 先显示，就绪后 load_url 切控制台）。
# 品牌化骨架（2026-10-04 启动优化拍板②/A 增强 2）：深色底 + 橘色主体 +
# 三步进度文案——静态版（真实进度需 JS 桥接 launcher 轮询，按设计稿
# "纯静态文案亦可"口径落地，视觉素材后续可替换）
PLACEHOLDER_HTML = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<style>body{font-family:system-ui,sans-serif;background:#101828;"
    "color:#e8eefc;display:flex;align-items:center;justify-content:center;"
    "height:100vh;margin:0}div{text-align:center}"
    "h2{margin:0 0 10px;font-size:26px}.accent{color:#ff9a3c}"
    "p{opacity:.65;margin:4px 0;font-size:14px}"
    ".steps{margin:14px 0 0;font-size:13px;opacity:.85;letter-spacing:1px}"
    "</style></head><body><div>"
    "<h2>🍊 <span class='accent'>小橘3号</span> 正在醒来…</h2>"
    "<div class='steps'>① 准备资源　→　② 启动服务　→　③ 打开界面</div>"
    "<p>首次启动约需数秒，窗口将自动进入控制台</p></div></body></html>"
)

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


def _another_instance_serving(port=DASHBOARD_APP_PORT, timeout=1.0):
    """跨版本双开探测（#263 L1，2026-10-07）：5003 已被监听 = 已有实例在
    跑——**不分正式/测试通道**（真机双开实锤：桌面快捷方式历史上指向测试
    版旧车，旧车无互斥体代码，同版本互斥体门对其失明）。端口探测是跨版本
    通吃的兜底。测试经 mock 关闭。"""
    return _is_port_listening(port, timeout=timeout)


def wait_for_dashboard_ready(timeout_s=60.0, interval_s=0.5,
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


def _backend_warming_up():
    """探测后端是否已在拉起途中（方案 A 自启改造，2026-10-08）：5003 已
    监听（就绪）或存在其他 xiaoju3.exe 进程（自启任务直启的 launcher 角色
    初始化中）→ True；全无 → False（真没人拉，走 spawn-self 双击兜底）。"""
    if _is_port_listening(DASHBOARD_APP_PORT):
        return True
    try:
        import psutil
        me = os.getpid()
        return any((p.info.get("name") or "").lower() == "xiaoju3.exe"
                   and p.info.get("pid") != me
                   for p in psutil.process_iter(["pid", "name"]))
    except Exception:
        return False


def ensure_backend_services():
    """后台服务决策（方案 A 改造，2026-10-08）：:5003 已监听 → 复用；
    未监听但探测到后端在拉起途中（自启任务直启的 launcher 初始化中）→
    返回 None 等待复用（开机链路零 spawn-self，火绒对 exe 自我复制敏感
    ——2026-10-08 拦截实锤）；全无 → spawn-self（双击场景兜底）。"""
    if _is_port_listening(DASHBOARD_APP_PORT):
        _print(LAUNCHER_REUSE_HINT)
        return None
    if _backend_warming_up():
        _print("ℹ️ 后端已在拉起途中（自启任务直启），等待复用不重复拉起")
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
            # （黑框普查③：补 CREATE_NO_WINDOW——兜底路径原样闪控制台）
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, check=False,
                           creationflags=_WIN_CREATE_NO_WINDOW)
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
        elif proc is None and not _is_main_running():
            # 复用态监督（方案 A 监督真空修复，2026-10-09）：复用分支无
            # 句柄可 poll——改为监视 5003 存活：消失（后端死且无人在拉）
            # → respawn（ensure 重新探测：真死 spawn / 途中复用回写），
            # 同窗限防循环。E3 轮 1 实锤：复用态 launcher/dashboard 被
            # 杀后 130 秒无人重生（QQ 通道死）。
            now = time.time()
            restarts = [t for t in restarts if now - t < window]
            if len(restarts) >= max_restarts:
                out("⚠️ 复用态后端连续消失（60 秒内 3 次），已停止自动重启。")
                return
            restarts.append(now)
            out("🔁 复用态后端消失，自动重启（监督真空修复）...")
            state["proc"] = respawn_fn()
        stop_event.wait(poll_interval)


# 旧 _MEI 残留清理阈值（秒，2026-10-04 启动优化拍板③：30 分钟——双开安全
# 余量比 10 分钟更大；目录 mtime 30 分钟内动过就绝不判残留）
MEI_STALE_SECONDS = 30 * 60


def _dir_size_quiet(path):
    """目录字节数（os.walk 求和，仅用于清理日志）；任何失败按 0 计。"""
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def _has_other_own_instance():
    """存在其它本应用冻结实例运行中（进程可执行文件与当前同名且非本
    pid）→ True。双开第一保险：mtime 只能防"新并行实例"，防不了"长驻
    实例仍在用"（长驻 >30 分钟的解包目录 mtime 必然过期）——只要有同名
    实例活着就整体跳过本轮清理（卫生项机会主义，宁漏勿误）。psutil 未装
    或枚举失败返回 False（退回 mtime 单判，不阻塞）。"""
    try:
        import psutil
    except ImportError:
        return False
    try:
        me = os.getpid()
        image = os.path.basename(sys.executable).lower()
        for proc in psutil.process_iter(["pid", "exe"]):
            info = proc.info
            if info.get("pid") == me:
                continue
            exe = info.get("exe")
            if exe and os.path.basename(exe).lower() == image:
                return True
    except Exception:
        return False
    return False


def _meipass_in_use(path):
    """单目录存活探测：任一进程的可执行文件位于 path 下 → True（本应用
    崩溃后 playwright node 驱动等子进程可能滞留，仍握着旧解包目录）。
    psutil 未装/枚举失败返回 False（退回 mtime 单判）。"""
    try:
        import psutil
    except ImportError:
        return False
    try:
        norm = os.path.normcase(os.path.normpath(path)) + os.sep
        for proc in psutil.process_iter(["exe"]):
            exe = proc.info.get("exe")
            if exe and os.path.normcase(os.path.normpath(exe)).startswith(norm):
                return True
    except Exception:
        return False
    return False


def _cleanup_stale_meipass():
    """清理 Temp 下历史残留的 _MEI* 解包目录（2026-10-04 启动优化拍板③；
    frozen 才执行，main() 最早期调用）。正常退出 PyInstaller 自清，强杀/
    崩溃残留（实测 10 代 5 目录 868MB）。安全序：① 其它同名实例存活 →
    整体跳过（防长驻实例的解包目录被 mtime 误判）；② 跳过自身
    sys._MEIPASS 与非目录项；③ 30 分钟内动过的不碰（MEI_STALE_SECONDS）；
    ④ 仍有进程握着该目录（_meipass_in_use）的跳过；⑤ 删除静默容错
    （rmtree ignore_errors——Explorer/杀软句柄占用不报错不阻塞），只对
    删净的目录计释放量并打一行 🧹 日志。对启动耗时无直接收益（onefile
    每次新解包不复用），纯磁盘卫生项；任何异常静默吞掉，绝不影响启动。"""
    if not getattr(sys, "frozen", False):
        return
    try:
        if _has_other_own_instance():
            return
        own = os.path.normcase(os.path.normpath(
            getattr(sys, "_MEIPASS", "")))
        cutoff = time.time() - MEI_STALE_SECONDS
        stale = []
        for path in glob.glob(os.path.join(tempfile.gettempdir(), "_MEI*")):
            if not os.path.isdir(path):
                continue
            if own and os.path.normcase(os.path.normpath(path)) == own:
                continue
            try:
                if os.path.getmtime(path) > cutoff:
                    continue
            except OSError:
                continue
            if _meipass_in_use(path):
                continue
            stale.append(path)
        if not stale:
            return
        freed = 0
        cleaned = 0
        for path in stale:
            size = _dir_size_quiet(path)
            shutil.rmtree(path, ignore_errors=True)
            if not os.path.exists(path):
                cleaned += 1
                freed += size
        if cleaned:
            _print(f"🧹 已清理 {cleaned} 处历史解包残留，"
                   f"释放 {freed / (1024 * 1024):.0f} MB")
    except Exception:
        pass   # 卫生项：任何异常（tempdir 不可用等）静默，绝不影响启动


# ==================== 单实例门（#263，2026-10-07） ====================
_SINGLE_INSTANCE_MUTEX = "Local\\Xiaoju3_Desktop_SingleInstance"
_ERROR_ALREADY_EXISTS = 183


def _acquire_single_instance_lock(name=_SINGLE_INSTANCE_MUTEX):
    """命名互斥体单实例门：返回 (句柄, 是否已有实例)。

    句柄刻意不闭——随进程存活即持锁，进程退出由 OS 回收（无残留）；
    main() 正常收尾时经 _release_single_instance_lock 主动释放（测试
    同进程可重复进出）。name 可注入（测试用唯一名防同进程互扰）。
    非 Windows 回退 (None, False)。
    """
    if os.name != "nt":
        return None, False
    import ctypes
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, name)
    already = ctypes.windll.kernel32.GetLastError() == _ERROR_ALREADY_EXISTS
    return handle, already


def _release_single_instance_lock(handle):
    """释放单实例互斥体（main 收尾用；None/已闭句柄安全跳过）。"""
    if handle:
        import ctypes
        ctypes.windll.kernel32.CloseHandle(int(handle))


def _activate_existing_window():
    """枚举顶层窗口找已有实例（WINDOW_TITLE 前缀）：最小化则恢复、置前台。

    返回 True=已唤起；找不到=False——此时已有实例尚在启动期，其窗口稍后
    自现，第二实例静默退出即 #263 期望的"跳过"语义（闪任务栏需窗口句柄，
    第二实例自身无窗，不适用）。"""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    prefix = WINDOW_TITLE.split("·")[0].strip()   # "小橘3号"
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum_cb(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value.startswith(prefix):
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(_enum_cb, 0)
    if not found:
        return False
    hwnd = found[0]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)   # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return True


# ==================== 退出模式（#264 B2d④） ====================
# mode 语义（用户拍板双方法）：'backend_only'=只退窗口（后端+NapCat 继续跑）/
# 'full_exit'=完全退出（前端+后端+NapCat 全关）/ 'legacy'=前端未就绪时的旧
# 语义直退（关窗清后端，NapCat 留）/ 'ask'=未决（弹窗询问）。
# 记住选择持久化=agent_state/ui_pref.json——**绝不用 localStorage**（pywebview
# 每窗独立 user_data_folder 且关窗 rmtree，跨启动即焚，设计稿第五节铁律）。

UI_PREF_MODES = ("ask", "backend_only", "full_exit")
UI_PREF_DEFAULT = {"exit": "ask"}


def _ui_pref_path():
    """ui_pref.json 路径：xiaoju3.AGENT_STATE_DIR 优先（frozen 路径陷阱
    铁律，禁 __file__ fallback），缺席回退 paths.DATA_ROOT/agent_state。"""
    try:
        from xiaoju3 import AGENT_STATE_DIR as state_dir
        if state_dir:
            return os.path.join(state_dir, "ui_pref.json")
    except Exception:
        pass
    return os.path.join(paths.DATA_ROOT, "agent_state", "ui_pref.json")


def _load_ui_pref(path=None):
    """读 UI 偏好全量 KV（#264 B2c 泛化：exit 之外新增 dev_unlocked/
    dev_mode_on）。exit 缺失/非法 → 缺省 ask（最保守=每次询问）；
    其余键原样透传（未知键不丢——多特性共文件互不覆盖）。"""
    p = path or _ui_pref_path()
    data = {}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception:
        data = {}
    mode = data.get("exit")
    out = dict(data)
    out["exit"] = mode if mode in UI_PREF_MODES else UI_PREF_DEFAULT["exit"]
    return out


def _save_ui_pref(data, path=None):
    """写 UI 偏好（tmp+replace 原子写；目录惰性创建）。#264 B2c 泛化：
    接收全量 dict（调用方负责读改写合并，避免多特性互覆盖）。"""
    p = path or _ui_pref_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, p)


def _kill_napcat_all(out=None, psutil_mod=None, wait_procs=None):
    """全退 NapCat（#264 B2d④『完全退出』路径；主人主动断链语义，与
    #305 F2『只杀副本』区分）：NapCat* 全列 + QQ.exe 全列 + cmd(命令行含
    launcher-user.bat) 全列 terminate→超时 kill 兜底。psutil 缺席 → 静默
    跳过（退出主流程不被阻塞）。返回命中数。"""
    out = out or (lambda msg: None)
    try:
        import psutil
    except ImportError:
        out("ℹ️ psutil 缺席，跳过 NapCat/QQ 清理")
        return 0
    psutil_mod = psutil_mod or psutil
    wait_fn = wait_procs or psutil_mod.wait_procs
    targets = []
    for proc in psutil_mod.process_iter(["name", "cmdline"]):
        try:
            info = proc.info or {}
            name = str(info.get("name") or "").lower()
            cmdline = " ".join(info.get("cmdline") or []).lower()
            if (name.startswith("napcat") or name == "qq.exe"
                    or (name == "cmd.exe" and "launcher-user.bat" in cmdline)):
                targets.append(proc)
        except Exception:
            continue
    for proc in targets:
        try:
            proc.terminate()
        except Exception:
            pass
    _, alive = wait_fn(targets, timeout=3)
    for proc in alive:
        try:
            proc.kill()
        except Exception:
            pass
    out(f"🛑 全退清理：NapCat/QQ 相关进程终止 {len(targets)} 个")
    return len(targets)


class QuitBridge:
    """退出桥（#264 B2d④，js_api）：前端统一退出弹窗的 Python 侧。

    - get_exit_pref/set_exit_pref：ui_pref.json 读写（记住选择持久化）；
    - quit_app(mode, remember)：可选记住 → 置退出态 → destroy 主窗 →
      closing 放行 → webview.start 返回 → main() finally 按 mode 清理
      （full_exit 追加 NapCat 全杀；backend_only 跳过后端终止）。
    window 经 window_getter 惰性取（桥先于 create_window 构造）。
    """

    def __init__(self, window_getter, quit_state, out=None, pref_path=None,
                 napcat_killer=None):
        self._window_getter = window_getter
        self._state = quit_state
        self._out = out or (lambda msg: None)
        self._pref_path = pref_path
        self._napcat_killer = napcat_killer

    def get_exit_pref(self):
        return _load_ui_pref(self._pref_path).get("exit", "ask")

    def dev_audit(self, detail=""):
        """开发者模式事件审计（#264 B2c a：连点触发写 settings_log）。
        复用 settings_api._audit（同写 trace.db settings_log 表，跨进程
        SQLite 短写）；失败静默（审计绝不阻塞前端交互）。"""
        try:
            from settings_api import _audit
            _audit({"action": "dev_mode", "detail": str(detail)[:200]})
            return {"ok": True}
        except Exception as e:
            self._out(f"⚠️ dev_audit 失败: {e}")
            return {"ok": False}

    def set_exit_pref(self, mode):
        if mode not in UI_PREF_MODES:
            return {"ok": False, "error": "invalid_mode"}
        cur = _load_ui_pref(self._pref_path)   # 读改写合并：不覆盖 dev 字段
        cur["exit"] = mode
        _save_ui_pref(cur, self._pref_path)
        self._out(f"💾 退出偏好已保存：{mode}")
        return {"ok": True, "exit": mode}

    def get_dev_pref(self):
        """开发者模式偏好（#264 B2c）：unlocked=暗入口已解锁（开关行显示）；
        mode_on=开发者模式开（🛠️ 徽标+审计挂它）。"""
        data = _load_ui_pref(self._pref_path)
        return {"unlocked": bool(data.get("dev_unlocked")),
                "mode_on": bool(data.get("dev_mode_on"))}

    def set_dev_pref(self, unlocked=None, mode_on=None):
        """写开发者模式偏好（读改写合并；两键独立可只写其一）。"""
        cur = _load_ui_pref(self._pref_path)
        if unlocked is not None:
            cur["dev_unlocked"] = bool(unlocked)
        if mode_on is not None:
            cur["dev_mode_on"] = bool(mode_on)
        _save_ui_pref(cur, self._pref_path)
        self._out(f"💾 开发者模式偏好已保存：unlocked={cur.get('dev_unlocked')} "
                  f"mode_on={cur.get('dev_mode_on')}")
        return {"ok": True, "unlocked": bool(cur.get("dev_unlocked")),
                "mode_on": bool(cur.get("dev_mode_on"))}

    def quit_app(self, mode="backend_only", remember=False):
        if mode not in ("backend_only", "full_exit"):
            return {"ok": False, "error": "invalid_mode"}
        if remember:
            cur = _load_ui_pref(self._pref_path)
            cur["exit"] = mode
            _save_ui_pref(cur, self._pref_path)
        self._state["quitting"] = mode
        self._out(f"🛑 退出受理：mode={mode} remember={bool(remember)}")
        # 🌌 灵魂回写兜底 flush（#319 批 3-b 退出链，2026-10-17）：退出前
        # 强制补投 outbox（sync=True 内带 10s 上限，超时放行退出不卡关机；
        # 未配置 SOUL_CORE 时 outbox 空=零成本直过；异常全吞不阻塞退出）。
        try:
            import soul_sync
            _flushed = soul_sync.process_outbox(sync=True, total_timeout=10)
            if _flushed:
                self._out(f"🌌 [灵魂回写] 退出前补投 {_flushed} 件")
        except Exception as e:
            self._out(f"⚠️ [灵魂回写] 退出 flush 异常（放行退出）: {e}")
        try:
            self._window_getter().destroy()
        except Exception as e:
            self._out(f"⚠️ destroy 异常: {e}")
        return {"ok": True, "mode": mode}


def main(argv=None):
    """入口：缺 pywebview 中文提示退出；拉后台服务 → 占位窗 → 就绪导航 →
    关闭全清理（端口修复 P2：内置随机服务退役，窗口直挂 :5003）。

    返回退出码：0 正常（窗口关闭并清理完成）；1 环境不满足（缺 pywebview）。
    argv 参数保留兼容既有调用形态（launcher.main([])），当前不消费。
    """
    _cleanup_stale_meipass()   # 🧹 上代 _MEI 残留清理（拍板③）：frozen 才执行，静默不阻塞
    from xiaoju3_launcher import _redirect_stdio  # 延迟导入：非 frozen 依赖面零变化
    _redirect_stdio("desktop")  # frozen 入口重定向（步 3）；非 frozen 空操作
    try:
        import webview   # 延迟导入：缺库时清晰中文提示退出，不甩 traceback
    except Exception:
        _print(MISSING_WEBVIEW_HINT, err=True)
        return 1

    # ⓪ 单实例门（#263 L1）：①互斥体（同版本，模块导入期已持锁——见
    #   模块顶部）②5003 端口（跨版本：桌面快捷方式历史指向测试版旧车，
    #   旧车无互斥体代码，同版本门对其失明——2026-10-07 双版本双开实锤）。
    #   任一命中 → 唤起已有窗口 + return 0（先于 ensure：退出路径不重复拉
    #   后端）。方案 A 精化（v22 冒烟实锤）：5003 被占但唤不到窗口 = 只有
    #   后端角色在跑（Run 键/自启任务先直启 launcher 的登录链标准态）→
    #   本进程是第一个桌面窗，正常出窗复用后端，不退出（否则登录后永无窗）。
    if _SI_ALREADY or _another_instance_serving():
        activated = _activate_existing_window()
        if activated or _SI_ALREADY:
            _print("ℹ️ 小橘3号已在运行"
                   + ("，已唤起已有窗口" if activated else "，窗口启动中"))
            return 0
        _print("ℹ️ 后端已在运行，复用后端启动控制台窗口")

    # ① 后台服务：:5003 已监听则复用现有进程，否则后台拉起统一启动器
    launcher_proc = ensure_backend_services()
    # 方案 A 监督真空修复（2026-10-09 E3 轮 1 实锤）：复用态（等待后端
    # 起途/后端由他人直启）也纳入监督——此前 launcher_proc=None 时监督
    # 线程不启动，后端死后无人重生（QQ 通道死 130s+）
    backend_pending = (launcher_proc is None and _backend_warming_up())
    # 🔁 监督线程（2026-10-02）：窗口存活期间后台服务意外退出自动重启
    # （restart_service 受理/异常恢复）；正常关窗时 finally 最先
    # 置位 stop_event，监督线程随即退出，不与手动清理竞争
    backend_state = {"proc": launcher_proc}
    stop_event = threading.Event()
    if launcher_proc is not None or backend_pending:
        threading.Thread(
            target=_supervise_backend,
            args=(backend_state, stop_event, ensure_backend_services, _print),
            daemon=True).start()

    # ② 启动探测：主程序未在线且没有启动器在拉起途中 → 提示"聊天功能受限"
    #   （无人会拉起主程序时等待无意义，导航线程跳过等待直接进错误页路径）；
    #   方案 A 等待复用态：backend_pending 已在 ① 前算好（监督启动条件
    #   与等待判定共用同一事实）
    main_ok = _is_main_running()
    main_hint = not main_ok and launcher_proc is None and not backend_pending
    need_wait = (launcher_proc is not None) or main_ok or backend_pending
    if main_hint:
        _print(MAIN_NOT_RUNNING_HINT)

    # ③ 占位窗先行（先出窗后导航，端口修复 P2）：create_window 先显示
    #   "正在启动主程序…"，GUI 就绪后由 webview.start 回调在后台线程
    #   轮询 :5003，就绪即 load_url 切控制台。
    #   js_api=退出桥（#264 B2d④）：前端统一退出弹窗经此受理（window 经
    #   lambda 惰性取，桥先于窗口构造）。
    quit_state = {"quitting": None}
    bridge = QuitBridge(lambda: window, quit_state, out=_print)
    window = webview.create_window(WINDOW_TITLE, html=PLACEHOLDER_HTML,
                                   width=WINDOW_WIDTH, height=WINDOW_HEIGHT,
                                   js_api=bridge,
                                   background_color="#f4f6f9")
    # background_color（2026-10-25 放大白屏闪烁）：窗口放大/最大化时 WebView2
    # 合成层重排的瞬间露出**窗体原生 BackColor**（pywebview 缺省纯白——CSS
    # body 底色管不到这层），设为主题灰 #f4f6f9（--color-bg 同值）后闪白
    # 变闪灰，肉眼接近无感。--disable-gpu/transparent 不采用：前者全局降
    # 渲染性能，后者是 #311-b 评估的闪烁风险位。

    def _apply_composited_style():
        """窗口原生双缓冲（2026-10-25 白屏终极方案 A）：给 HWND 加
        WS_EX_COMPOSITED 扩展样式——窗口尺寸突变时原生层自底向上双缓冲
        绘制，消除撕裂/露底。与 background_color/CSS 方案正交叠加。

        hwnd 获取：FindWindowW 按标题直找——window.native.Handle 跨线程
        （回调线程≠GUI 线程）隐性失败实锤（COMPOSITED=False 直查），
        WinForms Invoke 依赖 pythonnet 线程封送，FindWindow 零依赖最稳。
        注入态可复核：GetWindowLongW(hwnd,-20) & 0x02000000。"""
        import ctypes
        import time as _time
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_COMPOSITED = 0x02000000
        for _ in range(10):   # 窗口创建竞态重试（最多 10s）
            hwnd = user32.FindWindowW(None, WINDOW_TITLE)
            if hwnd:
                break
            _time.sleep(1)
        if not hwnd:
            _print("[白屏终极方案A] FindWindow 未找到主窗口（方案B兜底）")
            return
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                              style | WS_EX_COMPOSITED)
        _print(f"[白屏终极方案A] WS_EX_COMPOSITED 已注入 (hwnd={hwnd})", flush=True)

    def _navigate_when_ready():
        """后台导航（webview.start 回调）：等 :5003 就绪 → load_url 控制台。
        超时/缺位也仍导航（WebView2 自显示连接失败页，稍后服务起来刷新即
        恢复）——窗口是唯一 UI 出口，不能没有内容；同时标题追加提示。"""
        _apply_composited_style()   # GUI 就绪即注入（先于导航）
        timed_out = False
        if need_wait:
            timed_out = not wait_for_dashboard_ready()
        try:
            window.load_url(CONSOLE_URL)
        except Exception as e:
            _print(f"⚠️ 控制台导航失败：{e}", err=True)
            return
        if timed_out or main_hint:
            try:
                window.evaluate_js(
                    f"document.title += '{MAIN_NOT_RUNNING_HINT}'")
            except Exception:
                pass

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

    def _on_closing():
        # #264 B2d④：X → 与桌宠菜单「退出」统一弹窗（双方法+记住选择）。
        # ⚠️ pywebview 事件返回值语义（winforms on_closing 源码实锤）：
        #   should_cancel = closing.set() —— **handler 返回 False=取消关闭，
        #   返回 True=放行**（Event.set 聚合：任一 handler False→取消）。
        #   坑库 #18：凭直觉写反曾致 X 直接关窗、弹窗永不出现。
        # ① 记住过（pref≠ask）→ 直接按记住的方法退出，不弹；
        # ② 未记住 → 起线程 evaluate_js 唤前端弹窗（GUI 线程内不可同步
        #    evaluate），本次默认关闭取消；
        # ③ 前端未就绪（占位页阶段，console.js 未加载）→ 退回旧语义直退。
        try:
            if quit_state.get("quitting"):
                return True   # quit_app/legacy 已受理（destroy 再入），放行关闭
            pref = _load_ui_pref().get("exit", "ask")

            def _decide():
                try:
                    if pref in ("backend_only", "full_exit"):
                        quit_state["quitting"] = pref
                        window.destroy()
                        return
                    window.evaluate_js(
                        "window.__xiaoju3OpenQuitDialog && window.__xiaoju3OpenQuitDialog()")
                except Exception:
                    # 前端未就绪：旧语义直退（关窗清后端，NapCat 留）
                    quit_state["quitting"] = "legacy"
                    try:
                        window.destroy()
                    except Exception:
                        pass

            threading.Thread(target=_decide, daemon=True).start()
            return False   # 取消本次默认关闭（决定线程随后弹窗或 destroy）
        except Exception:
            return True   # handler 任何异常：放行关闭（绝不卡死用户关窗）

    try:
        window.events.closing += _on_closing
    except Exception:
        pass

    try:
        webview.start(_navigate_when_ready)   # GUI 启动后执行导航回调，阻塞至窗口关闭
    finally:
        # 关闭清理（#264 B2d④ 按退出模式分派）：
        # - full_exit：整树终止后端 + NapCat/QQ 全杀（主人主动断链）
        # - backend_only：只退窗口——后端+NapCat 保持运行（跳过后端终止）
        # - legacy/None：旧语义（关窗清后端，NapCat 留）
        # 三种均先停监督线程（正常关窗不再触发自动重启）并释放单实例互斥体。
        mode = quit_state.get("quitting")
        stop_event.set()   # 先停监督线程：正常关窗不再触发自动重启
        if mode == "backend_only":
            _print("ℹ️ 仅退窗口：后端与 NapCat 按你的选择保持运行")
        else:
            stop_backend_launcher(backend_state["proc"])
            if mode == "full_exit":
                _kill_napcat_all(_print)
        _release_single_instance_lock(_SI_HANDLE)   # 单实例互斥体随窗关闭释放
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
