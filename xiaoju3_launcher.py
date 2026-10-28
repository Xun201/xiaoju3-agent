# -*- coding: utf-8 -*-
"""小橘3号 · 统一启动器：一条命令拉起全栈（5003 一个进程承载一切）。

用法：
    python xiaoju3_launcher.py             # 前台运行，Ctrl+C 优雅停止全部
    python xiaoju3_launcher.py --dry-run   # 只打印启动计划，不实际拉起

【架构合并（2026-10-01，用户口径：彻底废弃 5002 端口，全部迁入 5003）】
main.py 已模块化为纯 QQ 业务逻辑（不再监听任何端口），launcher 只拉起
xiaoju3_dashboard.py 一个子进程：QQ webhook（POST /onebot）、网页控制台
（/console）与心跳线程全部宿主于该 5003 进程。

启动日志（✅ 三行 + ⚠️ 提醒，按打印顺序）：
1. ✅ QQ 接入层已启动 (5003)      —— subprocess: python xiaoju3_dashboard.py
2. ✅ 心跳已启动                  —— 宿主于 5003 进程（选型见下）
3. ✅ 控制台已启动 (5003/console) —— 与 QQ 接入层同一 5003 进程（:5003/console 路由）
4. ⚠️ QQ webhook 已迁移至 5003：请将 LLOneBot 的 HTTP 上报地址改为
   http://127.0.0.1:5003/onebot，否则 QQ 会断连（关键提示必须写入启动日志）

【心跳选型（读码定论）】heartbeat.py 提供两种形态（独立运行入口 /
start_heartbeat() daemon 线程），而 xiaoju3_dashboard.py 的 __main__ 已无条件
经 main.start_background_services() 内嵌 start_heartbeat()——5003 进程一启动，
心跳即宿主其中。launcher 若再拉第二条心跳（进程内线程或独立进程皆然）会形成
双心跳：两份快照各自 diff，同一环境变化触发两次大模型决策与两次设备控制
（重复控灯、双倍 token，甚至互相打架）。故 launcher 不重复拉起心跳，仅在
dashboard 启动后打印确认行。

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

import paths  # 双根路径锚（方案 §1）：资源根=程序自带文件基准，数据根=可写运行数据

# spawn-self 角色标志（方案 §2.1）：exe 单一入口按 argv 分流三角色；
# 与 desktop_launcher.ROLE_DASHBOARD_FLAG 保持字面一致（测试锁定）
ROLE_DASHBOARD_FLAG = "--xj3-role=dashboard"

# ✅ 三行确认日志 + ⚠️ 改址提醒（文案口径固定，测试断言）
BANNER_QQ = "✅ QQ 接入层已启动 (5003)"
BANNER_HEARTBEAT = "✅ 心跳已启动"
BANNER_DASHBOARD = "✅ 控制台已启动 (5003/console)"
QQ_WEBHOOK_MIGRATION_HINT = ("⚠️ QQ webhook 已迁移至 5003：请将 LLOneBot 的 HTTP 上报地址改为 "
                             "http://127.0.0.1:5003/onebot，否则 QQ 会断连")

# 心跳选型说明（随计划条目携带，供测试断言"注释与实现一致性"）
HEARTBEAT_REASON = (
    "heartbeat 为线程形态（start_heartbeat daemon 线程），且 xiaoju3_dashboard.py "
    "的 __main__ 已内嵌 main.start_background_services()（内部调用 start_heartbeat()）"
    "——python xiaoju3_dashboard.py 一启动心跳即宿主于 5003 进程；launcher 再拉第二条"
    "会双心跳（同一变化两次决策、两次控设备、双倍 token），故不单独拉起。"
)

# ==================== NapCat 后台拉起（2026-10-02 用户口径） ====================
# 目标：一个命令拉起全部——QQ（NapCat）也随 launcher 静默启动，无黑框；
# NapCat 是常驻服务形态：launcher 退出不杀它（不纳入 shutdown 进程树，
# 用户口径"关掉任何窗口 NapCat 仍继续运行"）。
# Windows-only：香橙派（POSIX）NapCat 由部署侧另行管理，launcher 静默跳过。

NAPCAT_STARTED_HINT = "✅ NapCat 已后台启动（无窗口）"
NAPCAT_RUNNING_HINT = "ℹ️ NapCat 已在运行，跳过"


def _napcat_running():
    """探测 NapCat 是否已在运行：psutil 可用则按进程名扫描（napcat 大小写
    不敏感，覆盖 NapCatWinBootMain.exe / NapCat.Shell.exe 等），psutil 缺席
    或扫描异常回退探测 WebUI 端口 6099；仍不可判定按未运行处理。"""
    try:
        import psutil
        for proc in psutil.process_iter(["name"]):
            name = str((proc.info or {}).get("name") or "").lower()
            if "napcat" in name:
                return True
    except Exception:
        pass
    try:
        import socket
        with socket.create_connection(("127.0.0.1", 6099), timeout=0.5):
            return True
    except OSError:
        return False


# ==================== fire 日志 + QQ 三态探测（#305 F3/F2，2026-10-11） ====================
# 背景：实机 20+ NapCatWinBootMain.exe 幽灵 + QQ(4) 僵尸树（设计稿
# _dev/design_305_napcat_ghost.md）。三病根=DEVNULL 零可观测 / 裸 QQ
# 探测盲区（进程名扫只认 napcat 子串，QQ.exe 不含）/ bat 末尾 pause 挂尸。
# 本段落 F3（fire 输出落盘留证）+ F2（三态探测，只杀 NapCat 副本）；
# F1（绕 bat 直呼 BootMain 根除 pause 挂尸）=批次 2，等批次 1 观察期。

NAPCAT_FIRE_LOG_KEEP = 10            # fire 日志轮换保留数（与 LOG_KEEP 口径统一）
NAPCAT_QQ_LOCK_GRACE_SECONDS = 10.0  # QQ 强杀后单实例锁残留宽限（E3 实锤：10s 内秒崩）


def _napcat_fire_log_dir():
    """fire 日志目录 = agent_state。优先 xiaoju3.AGENT_STATE_DIR（frozen 路径
    陷阱铁律：一律 import xiaoju3 取数据目录，禁 __file__ fallback——onedir
    下 __file__ 误落解包目录，生产三 db 曾误建 dev 仓 c6dc178 实锤）；
    xiaoju3 缺席回退 paths.DATA_ROOT/agent_state（launcher 日志 LOG_DIR 同源）。"""
    try:
        from xiaoju3 import AGENT_STATE_DIR as state_dir
        if state_dir:
            return state_dir
    except Exception:
        pass
    return os.path.join(paths.DATA_ROOT, "agent_state")


def _napcat_fire_log_path(log_dir=None, now=None):
    """带时间戳的 fire 日志路径：agent_state/napcat_fire_YYYYMMDD_HHMMSS.log
    （命名对齐 timestamped_log_path 口径：每次 fire 独占一文件）。"""
    ts = time.strftime("%Y%m%d_%H%M%S",
                       time.localtime(now if now is not None else time.time()))
    return os.path.join(log_dir or _napcat_fire_log_dir(),
                        f"napcat_fire_{ts}.log")


def prune_napcat_fire_logs(keep=NAPCAT_FIRE_LOG_KEEP, log_dir=None):
    """napcat_fire_*.log 轮换：按 mtime 保留最近 keep 个（prune_dashboard_logs
    同款口径；独立实现——fire 日志在 agent_state，不在 xiaoju3_data）。
    返回 (保留数, 删除数)；目录缺失/删除失败静默（日志清理绝不影响拉起）。"""
    log_dir = log_dir or _napcat_fire_log_dir()
    try:
        names = os.listdir(log_dir)
    except OSError:
        return 0, 0
    files = [os.path.join(log_dir, n) for n in names
             if n.startswith("napcat_fire_") and n.endswith(".log")]
    files.sort(key=os.path.getmtime, reverse=True)
    removed = files[keep:]
    removed_total = 0
    for path in removed:
        try:
            os.remove(path)
            removed_total += 1
        except OSError:
            pass
    return len(files) - len(removed), removed_total


def _classify_qq_processes(napcat_dir=None, iter_fn=None):
    """在跑 QQ.exe 按可执行路径二分（#305 F2 核心探针，2026-10-11 用户拍板：
    按【路径】区分不按进程名——NapCat 目录下的 QQ.exe = NapCat Shell 副本
    （裸 NapCat QQ，可杀可换）；NapCat 目录之外的 QQ.exe（D:\\Ruanjian\\QQ
    等日常安装）= 用户日常 QQ，绝不动）。

    返回 (plain, other_count)：plain=裸态 QQ 进程对象列表（供 KillQQ）；
    other_count=目录外 QQ.exe 数（含 exe 读取失败者——宁少杀不误杀，且按
    锁占用保守处理阻止 fire）。psutil 缺席/枚举异常 → ([], 0)：探测失效
    按"无 QQ 在跑"走 legacy fire（探测不可用宁可放行也不瞎杀）。
    iter_fn(attrs=["name", "exe"]) 可注入（测试零真实进程）。
    """
    if iter_fn is None:
        try:
            import psutil
        except ImportError:
            return [], 0
        iter_fn = psutil.process_iter
    base = os.path.normcase(os.path.normpath(napcat_dir or "")) + os.sep
    plain, other = [], 0
    try:
        for proc in iter_fn(attrs=["name", "exe"]):
            try:
                info = proc.info or {}
                if str(info.get("name") or "").lower() != "qq.exe":
                    continue
                exe = info.get("exe") or ""
                if exe and os.path.normcase(
                        os.path.normpath(exe)).startswith(base):
                    plain.append(proc)
                else:
                    other += 1
            except Exception:
                other += 1   # 单进程属性读取失败：归 other 保守（宁少杀+阻止 fire）
    except Exception:
        return [], 0
    return plain, other


def _qq_plain_running(napcat_dir=None, iter_fn=None):
    """裸 NapCat QQ 是否在跑（_classify_qq_processes 布尔门面，锚/快照用）。"""
    plain, _ = _classify_qq_processes(napcat_dir, iter_fn)
    return bool(plain)


def _kill_qq_plain(plain, out=None, wait_timeout=3.0):
    """终止裸 NapCat QQ 进程列表（#305 F2）：terminate → 等 wait_timeout →
    存活者 kill 兜底。返回 (已终止数, 仍存活数)；单进程异常不阻断其余收尾。
    只吃 _classify_qq_processes 判定的裸态列表——用户日常 QQ 永不进本函数。"""
    out = out or (lambda msg: None)
    killed, alive = 0, 0
    for proc in plain:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=wait_timeout)
            except Exception:
                proc.kill()
                try:
                    proc.wait(timeout=wait_timeout)
                except Exception:
                    pass
            killed += 1
        except Exception:
            alive += 1
    if plain:
        out(f"🛑 裸态 QQ 终止完成（killed={killed} alive={alive}）")
    return killed, alive


def ensure_napcat(napcat_dir=None, popen=None, out=None, running_fn=None,
                  os_name=None, qq_iter_fn=None, sleep=None,
                  fire_log_dir=None):
    """拉起 NapCat（Windows-only，幂等可重复调用）。返回是否执行了拉起。

    - 已在运行 / launcher-user.bat 缺失 / 非 Windows（香橙派部署侧自管）：
      跳过；
    - 三态判定（#305 F2，2026-10-11 用户拍板：按【路径】区分不按进程名）：
      ① NapCat 在跑（napcat 名进程/6099）→ 跳过；
      ② 裸 NapCat QQ 在跑（QQ.exe 且 exe 位于 NapCat 目录副本下，即
         D:\\NapCat\\QQ.exe Shell 形态）→ 只杀副本（用户日常 QQ 绝不动）
         + 锁释放宽限（NAPCAT_QQ_LOCK_GRACE_SECONDS）→ 拉起；若 NapCat
         目录之外还有 QQ.exe（用户日常）→ 副本终止后仍跳过拉起（锁被
         日常 QQ 占用，硬拉=锁冲突僵尸树——昨晚幽灵同型）；
      ③ 仅用户日常 QQ 在跑（NapCat 目录之外）→ 不干预，跳过拉起；
      ④ 全无 → 拉起。
    - 统一经 cmd /c 拉 **launcher-user.bat**（NapCat 官方免提权变体，无
      net session 自检段）+ CREATE_NO_WINDOW 全程无黑框——2026-10-08
      方案 E 去提权化：QQ 装在用户可写目录，注入/patch 写权限普通用户
      已具备，提权零收益且被火绒「隐藏执行 PowerShell」规则拦截；
    - fire 输出落 agent_state/napcat_fire_<ts>.log（#305 F3：首行探测
      快照留证+保留最近 NAPCAT_FIRE_LOG_KEEP 份轮换；日志创建失败回退
      DEVNULL 绝不影响拉起——DEVNULL 时代 NapCat 输出全丢、锁冲突挂死
      零痕迹的教训）；
    - Popen 句柄刻意不返回/不纳入 launcher 生命周期：NapCat 常驻后台，
      launcher 退出后继续运行。
    全部依赖可注入（popen/out/running_fn/os_name/qq_iter_fn/sleep/
    fire_log_dir），离线可测。
    """
    popen = popen or subprocess.Popen
    out = out or print
    running_fn = running_fn or _napcat_running
    sleep = sleep or time.sleep
    if os_name is None:
        os_name = os.name
    if os_name != "nt":
        return False   # POSIX（香橙派）：NapCat 由部署侧管理，静默跳过
    if napcat_dir is None:
        try:
            from xiaoju3 import NAPCAT_DIR as napcat_dir
        except Exception:
            napcat_dir = "D:\\NapCat"
    bat = os.path.join(napcat_dir, "launcher-user.bat")
    if running_fn():
        out(NAPCAT_RUNNING_HINT)
        return False
    if not os.path.isfile(bat):
        out(f"ℹ️ 未找到 {bat}，跳过 NapCat 拉起")
        return False
    # 三态判定（#305 F2）：QQ.exe 按可执行路径二分——NapCat 目录副本（裸态，
    # 可杀可换）vs 用户日常（NapCat 目录之外，绝不动）
    plain, other = _classify_qq_processes(napcat_dir, iter_fn=qq_iter_fn)
    snapshot = (f"napcat_running=False plain_napcat_qq={len(plain)} "
                f"other_qq={other}")
    branch = "直接fire"
    if plain:
        branch = "杀副本后fire"
        out(f"🛑 检测到 NapCat 副本 QQ（裸态）×{len(plain)}，终止后重新拉起"
            "（用户日常 QQ 不受影响）")
        _kill_qq_plain(plain, out=out)
        if other:
            out("⚠️ 用户日常 QQ 在跑（不干预）——单实例锁可能被占，"
                "跳过本次 NapCat 拉起（硬拉=锁冲突僵尸树）")
            return False
        sleep(NAPCAT_QQ_LOCK_GRACE_SECONDS)   # 锁释放宽限（E3 实锤 10s 残留）
    elif other:
        out("ℹ️ 用户日常 QQ 在跑但 NapCat 未运行（不干预），跳过 NapCat 拉起")
        return False
    # cwd 参数形态（2026-10-09 E3 轮 1 引号 bug 修复）：勿回退
    # 'cd /d "<dir>" && bat' 字符串拼接——list2cmdline+cmd 引号解析会损坏
    # （报「文件名目录名语法不正确」，bat 从未执行，对照实验 5 连定案）
    fire_path = _napcat_fire_log_path(log_dir=fire_log_dir)
    fh = None
    stream = subprocess.DEVNULL
    try:
        os.makedirs(os.path.dirname(fire_path), exist_ok=True)
        fh = open(fire_path, "a", buffering=1, encoding="utf-8",
                  errors="replace")
        fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🔍 fire 探测快照: "
                 f"{snapshot} 分支={branch} bat={bat}\n")
        stream = fh   # fire 输出（含 NapCat 运行日志）落盘留证（#305 F3）
    except OSError:
        stream = subprocess.DEVNULL   # 日志失败绝不影响拉起（老形态兜底）
    try:
        popen(["cmd", "/c", "launcher-user.bat"],
              cwd=napcat_dir,
              creationflags=subprocess.CREATE_NO_WINDOW,
              stdout=stream, stderr=subprocess.STDOUT)
    finally:
        if fh is not None:
            fh.close()   # 子进程已继承句柄续写，Python 侧即收（防句柄泄漏）
    out(NAPCAT_STARTED_HINT)
    prune_napcat_fire_logs(log_dir=fire_log_dir)
    return True


# ==================== 单实例防重 + 日志轮换（2026-10-02 稳定性排查·方案 a/b） ====================
# 排查结论：并发启动的 pair 经 werkzeug SO_REUSEADDR 在 Windows 静默抢绑 5003，
# 败者 exit=1、固定日志文件被多写者混写。对策：
# - 方案 b：启动前探测 5003 已被监听 → 取消本次启动（exit 0 不报错）；
# - 方案 a：日志文件名带启动时间戳（每次启动独占一个文件，杜绝截断与混写），
#   并自动清理旧日志只留最近 10 个。

DASHBOARD_PORT = 5003
ALREADY_RUNNING_HINT = ("⚠️ 小橘3号已在运行（5003 已被占用），本次启动取消。"
                        "如需重启，请先停止现有进程。")
LOG_DIR = os.path.join(paths.DATA_ROOT, "xiaoju3_data")
# 日志前缀族（方案步 3）：spawn-self 三角色各自成档——每次启动独占一文件
# （方案 a）× 每角色一文件（步 3）= 三进程零共写。dashboard 键保名兼容旧口径。
LOG_FILE_PREFIXES = {
    "launcher": "launcher_live_",
    "dashboard": "dashboard_live_",
    "desktop": "desktop_live_",
}
LOG_FILE_PREFIX = LOG_FILE_PREFIXES["dashboard"]
LOG_KEEP = 10


def is_port_in_use(port=DASHBOARD_PORT, host="127.0.0.1", check_fn=None):
    """探测端口是否已被监听（TCP connect_ex==0 即有实例在跑）。
    check_fn(host, port) -> bool 可注入（离线测试 mock）；探测异常按未占用
    处理（宁可让后续绑定报错给出真实原因，也不误报"已在运行"挡住启动）。"""
    import socket
    if check_fn is None:
        def check_fn(h, p):
            with socket.socket() as s:
                return s.connect_ex((h, p)) == 0
    try:
        return bool(check_fn(host, port))
    except OSError:
        return False


def timestamped_log_path(now=None, role="dashboard"):
    """带启动时间戳的日志路径：xiaoju3_data/<role>_live_YYYYMMDD_HHMMSS.log。
    每次启动独占一个文件——杜绝固定路径的截断与多写者混写（方案 a）；
    role 前缀族（步 3）：launcher/dashboard/desktop 各自成档，缺省 dashboard
    保持现行为（restart_clean.bat 的 python -c 调用零改动）。"""
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(
        now if now is not None else time.time()))
    return os.path.join(LOG_DIR, LOG_FILE_PREFIXES[role] + ts + ".log")


def prune_dashboard_logs(keep=LOG_KEEP, log_dir=None):
    """清理旧启动日志：三角色前缀族（launcher/dashboard/desktop_live_*.log）
    各自按修改时间排序保留最近 keep 个。返回 (保留总数, 删除总数)（聚合值，
    restart_clean.bat 取删除数打印的口径不变）；目录缺失/删除失败静默兜底
    （日志清理失败绝不能影响启动主流程）。"""
    log_dir = log_dir or LOG_DIR
    try:
        names = os.listdir(log_dir)
    except OSError:
        return 0, 0
    kept_total = removed_total = 0
    for prefix in set(LOG_FILE_PREFIXES.values()):
        files = [os.path.join(log_dir, n) for n in names
                 if n.startswith(prefix) and n.endswith(".log")]
        files.sort(key=os.path.getmtime, reverse=True)
        removed = files[keep:]
        for path in removed:
            try:
                os.remove(path)
            except OSError:
                pass
        kept_total += len(files) - len(removed)
        removed_total += len(removed)
    return kept_total, removed_total


class _RotatingStream:
    """10MB 自动轮转日志流（防爆盘 2026-10-28）：写前查大小，超限顺序位移
    （base→.1→.2，最多保留 3 份）。stdout/stderr 代用品——write/flush/
    close/reconfigure/isatty/writable 透传，reconfigure 供 dashboard 行
    缓冲设置。单进程独占单文件（per-launch 时间戳档），零共写竞争。"""

    MAX_BYTES = 10 * 1024 * 1024
    KEEP = 3

    def __init__(self, path):
        self._path = path
        self._file = open(path, "a", buffering=1,
                          encoding="utf-8", errors="replace")

    def _rotate_if_needed(self):
        try:
            if self._file.tell() < self.MAX_BYTES:
                return
            self._file.close()
            for i in range(self.KEEP - 2, 0, -1):   # .2→.3 无（KEEP-1 份位移）
                src = f"{self._path}.{i}"
                dst = f"{self._path}.{i + 1}"
                if os.path.exists(src):
                    os.replace(src, dst)
            os.replace(self._path, f"{self._path}.1")
        except OSError:
            pass    # 轮转失败不致命：继续追加（最坏单文件超限，下轮再试）
        try:
            self._file = open(self._path, "a", buffering=1,
                              encoding="utf-8", errors="replace")
        except OSError:
            pass    # 重开失败：保留旧句柄继续写（静默兜底）

    def write(self, s):
        self._rotate_if_needed()
        return self._file.write(s)

    def flush(self):
        self._file.flush()

    def close(self):
        self._file.close()

    def reconfigure(self, **kw):
        try:
            self._file.reconfigure(**kw)
        except Exception:
            pass

    def isatty(self):
        return False

    def writable(self):
        return True


def _redirect_stdio(role):
    """frozen 入口重定向（方案步 3，B 路线）：stdout/stderr → 角色专属日志。

    - frozen：开 LOG_DIR/<role>_live_<时间戳>.log（追加、行缓冲、UTF-8、
      errors=replace）替换 sys.stdout/stderr，并写角色启动横幅——exe(-w) 下
      sys.stdout 为 None 与子进程 stdio=DEVNULL 两类丢失一并兜住；行缓冲把
      硬杀丢面压到半行，进程退出由解释器统一 flush。三进程各写各档
      （timestamped_log_path 前缀族），零共写。
      防爆盘（2026-10-28）：流带 10MB 自动轮转（顺序位移保留 3 份）——
      常驻运行数月单文件不再无界膨胀。
    - 非 frozen：空操作返回 None——控制台 print 照旧上屏，restart_clean.bat
      的进程外重定向（fd 层）照旧生效，行为逐字节不变。
    返回日志路径（非 frozen 返回 None）。
    """
    if not paths.FROZEN:
        return None
    log_path = timestamped_log_path(role=role)
    try:
        # exe 首跑目录可能尚无 xiaoju3_data/（数据根惰性创建不覆盖日志路径）
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        stream = _RotatingStream(log_path)
    except OSError:
        # 重定向失败绝不影响启动主流程（与 prune 同口径）：退化为不重定向
        return None
    sys.stdout = stream
    sys.stderr = stream
    stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} "
                 f"[{role}] 启动（pid {os.getpid()}）\n")
    return log_path


def build_launch_plan(python=None, root=None, frozen=False):
    """构造统一启动计划（纯函数，离线可测）。

    条目字段：
    - kind="subprocess"：独立子进程，launcher 持 Popen 句柄管理生命周期；
    - kind="hosted"：随 5003 宿主进程内部承载（不单独 Popen，仅打印确认行）。
    顺序（用户口径）：QQ 接入层行先、心跳次之、控制台行最后，三行 ✅ 按此
    顺序打印——三者实为同一 5003 子进程（subprocess 条目 Popen 一次，
    hosted 条目只打印）。

    frozen=True（exe 形态，方案 §2）：spawn-self——server 条目 cmd 为
    [exe 自身, --xj3-role=dashboard]，cwd 取 exe 所在目录（数据根，可写）；
    缺省 frozen=False 走现行 .py 路径，行为逐字节不变。
    """
    py = python or sys.executable or "python"
    base = root or paths.RESOURCE_ROOT
    if frozen:
        server_cmd = [py, ROLE_DASHBOARD_FLAG]
        server_cwd = os.path.dirname(os.path.abspath(py))
    else:
        server_cmd = [py, os.path.join(base, "xiaoju3_dashboard.py")]
        server_cwd = base
    return [
        {
            "name": "server",
            "kind": "subprocess",
            "cmd": server_cmd,
            "cwd": server_cwd,
            "banner": BANNER_QQ,
            "desc": "统一服务进程（:5003：QQ webhook /onebot + 心跳宿主；5002 已废弃）",
        },
        {
            "name": "heartbeat",
            "kind": "hosted",
            "host": "server",
            "banner": BANNER_HEARTBEAT,
            "desc": "主动服务心跳（60s 轮询 HA，宿主于 5003 进程 daemon 线程）",
            "reason": HEARTBEAT_REASON,
        },
        {
            "name": "console",
            "kind": "hosted",
            "host": "server",
            "banner": BANNER_DASHBOARD,
            "desc": "新版控制台（:5003/console，与 QQ 接入层同一 5003 进程承载）",
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

        子进程继承本进程控制台（不接管管道，避免缓冲死锁）。✅ 三行按启动
        完成顺序打印：QQ 接入层（5003 子进程）→ 心跳（随该进程）→ 控制台
        （同进程 :5003/console）；随后打印 ⚠️ LLOneBot 改址提醒（关键提示
        必须写入启动日志，用户口径）。
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
        self.out(QQ_WEBHOOK_MIGRATION_HINT)
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

        架构合并后仅一个 5003 统一服务子进程（接入层/控制台/心跳全在其中，
        收尾即整栈退出）：terminate → 等 timeout 秒 → 超时 kill 兜底；
        已退出的直接跳过（send_signal 对已死进程安全）。"""
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


def main(argv=None, frozen=False):
    """入口：--dry-run 只打印计划（零副作用）；否则前台拉起并守护。

    frozen=True（exe spawn-self，方案 §2）：由 desktop_launcher 分流调用，
    启动计划生成 exe 自 spawn 形态；缺省 False 走现行 .py 拉起，行为不变。

    非 dry-run 时按序执行三步前置：
    1. 单实例防重（方案 b）：探测 5003 已被监听 → 打印提示并以 0 优雅退出
       （在 ensure_napcat 之前——取消时连 NapCat 也不动）；
    2. ensure_napcat() 无黑框拉起 QQ 接入层（NapCat，Windows-only、幂等）；
    3. prune_dashboard_logs() 清理旧启动日志（方案 a，只留最近 10 个）。
    """
    _redirect_stdio("launcher")  # frozen 入口重定向（步 3）；非 frozen 空操作
    args = parse_args(argv)
    plan = build_launch_plan(root=args.root, frozen=frozen)
    if args.dry_run:
        print("📋 小橘3号启动计划（--dry-run，未实际拉起）：")
        for entry in plan:
            target = entry.get("cmd") or f"(宿主于 {entry['host']} 进程)"
            print(f"  - {entry['name']}: {target}")
            print(f"      {entry.get('reason') or entry.get('desc', '')}")
        print(QQ_WEBHOOK_MIGRATION_HINT)
        return 0
    if is_port_in_use():
        print(ALREADY_RUNNING_HINT)
        return 0
    ensure_napcat()
    prune_dashboard_logs()
    launcher = XiaojuLauncher(plan)
    return launcher.run()


if __name__ == "__main__":
    import multiprocessing
    # PyInstaller 冻结形态安全阀（方案 §2.2）：onefile 子进程引导必需
    multiprocessing.freeze_support()
    sys.exit(main())
