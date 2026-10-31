# -*- coding: utf-8 -*-
"""小橘3号 · 桌面技能录制回放（DA1 · 阶段一：技能录制回放）。

路线图：_dev/design_desktop_automation_roadmap.md（2026-10-31 队长拍板立项）。
设计已过 DeepSeek 秘书审查，四条致命点全采纳（见各函数标注）。

能力：
- 录制：自研 ctypes LL 钩子（WH_MOUSE_LL/WH_KEYBOARD_LL，零第三方依赖）
  捕获鼠标点击/键盘输入；点击落点经 uiautomation
  ControlFromPoint 解析 UIA 控件树生成"祖先定位链"（比裸坐标抗 DPI/布局漂移）；
  连续字符键合并 type_text；Ctrl/Alt/Win 组合按 vk 直取记 hotkey。
  合规批（2026-10-31）：pynput=LGPLv3 按队长最高红线移除，DeepSeek 秘书裁决
  路线 A（自研钩子）。
- **功能定位与防滥用（合规红线）**：本模块仅限"本地个人辅助"用途——
  帮助主人把本人手动演示过的操作变成可回放的技能；不做也不容忍：
  验证码绕过、批量注册、恶意爬虫、伪造点击流量等任何触犯《网络安全法》
  的能力；敏感进程/窗口/密码框一律拒录拒放。
- 回放：按窗口标题找顶层窗口 → 按定位链下钻 → 失败回退窗口内相对坐标
  （DPI 缩放比对不过则禁止回退、直接失败）；失败即停、诚实汇报已执行步数。
- 安全硬拦截（最高优先级，fail-closed）：
  1) 敏感窗口标题黑名单（默认 银行|支付|网银|密码|凭据|口令|password|credential|
     bank|wallet，env XIAOJU3_DESKTOP_TITLE_BLACKLIST 可覆盖）——录制跳过计数、
     回放直接中止；
  2) UIA IsPassword 控件（密码框官方信号）——拒录拒放，属性读不到按敏感处理；
  3) 全量审计 JSONL：agent_state/logs/desktop_audit.log。
- 权限：模型工具 desktop_* 全套 LV4（tool_registry level:4）；控制台面板直属
  主人（儿童锁口径：网页控制台视为成人设备）。

打包纪律（AGENTS.md 动态引用铁律）：本模块被 tool_registry 以
"desktop_tools:handler" 动态引用，必须显式列 xiaoju3.spec hiddenimports；
uiautomation(Apache-2.0)/comtypes(MIT，本地 LICENSE.txt 核实)/
pyautogui(BSD)/psutil(BSD-3) 进 hiddenimports。pynput(LGPLv3) 已按队长
最高红线移除——合规清单见路线图 §九。comtypes 的
gen 缓存目录启动期重定向到 agent_state（DeepSeek 审查：onedir 只读安装目录
下的最高频翻车点）。
"""
import json
import os
import re
import threading
import time
import queue as _queue

from xiaoju3 import AGENT_STATE_DIR

SKILLS_DIR = os.path.join(AGENT_STATE_DIR, "skills")
AUDIT_LOG = os.path.join(AGENT_STATE_DIR, "logs", "desktop_audit.log")

# ── 安全常量 ─────────────────────────────────────────────────────────
_TITLE_BLACKLIST_DEFAULT = (
    r"银行|支付|网银|密码|凭据|口令|验证|钱包|转账|"
    r"password|credential|bank|wallet|payment"
)
MAX_LOCATOR_DEPTH = 12       # 定位链最大深度（防病态树拖爆）
MIN_STEP_DELAY_MS = 150      # 回放步间最小间隔
MAX_STEP_DELAY_MS = 2000     # 回放步间最大间隔（录制发呆不拖慢回放）
MAX_TEXT_RUN = 200           # 单段 type_text 长度上限
RECORD_MAX_EVENTS = 2000     # 单次录制事件数保险丝
UIA_TIMEOUT_S = 1.5          # 单次 UIA 解析超时（150% DPI+UWP provider 实测冷启动 >0.8s）

_AUTO = None                 # uiautomation 模块缓存（lazy import）
_GEN_DIR_READY = False


# ── uiautomation / comtypes 基础设施 ────────────────────────────────
def _ensure_comtypes_gen_dir():
    """DeepSeek 审查②：comtypes 首跑要在包目录写 gen 缓存，onedir 装在
    只读目录即炸（最高频翻车点）。任何 UIA 使用前重定向到 agent_state。"""
    global _GEN_DIR_READY
    if _GEN_DIR_READY:
        return
    try:
        import comtypes
        import comtypes.client
        gen_dir = os.path.join(AGENT_STATE_DIR, "comtypes_gen")
        os.makedirs(gen_dir, exist_ok=True)
        try:
            comtypes.client.gen_dir = gen_dir
        except Exception:
            pass
    except Exception:
        pass
    _GEN_DIR_READY = True


def _get_auto():
    """lazy import uiautomation（缺席时给冻结包修复提示，绝不静默吞）。"""
    global _AUTO
    if _AUTO is None:
        _ensure_comtypes_gen_dir()
        try:
            import uiautomation as auto_mod
        except ImportError as e:
            raise RuntimeError(
                "uiautomation 不可用（%s）——冻结包请核对 xiaoju3.spec "
                "hiddenimports 是否含 uiautomation/comtypes。" % e)
        _AUTO = auto_mod
    return _AUTO


def _com_init():
    """COM 线程纪律（DeepSeek 审查）：每个用 COM 的线程自己 CoInitialize。"""
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass


def _dpi_scale():
    """系统 DPI 缩放比（96=1.0）。录制/回放各取一次，不一致禁用坐标回退。"""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        dpi = int(user32.GetDpiForSystem())
        if dpi <= 0:
            raise ValueError(dpi)
        return dpi / 96.0
    except Exception:
        try:  # Win7 及以下退路
            import ctypes
            hdc = ctypes.windll.user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
            ctypes.windll.user32.ReleaseDC(0, hdc)
            return dpi / 96.0
        except Exception:
            return 1.0


# ── 敏感拦截（实装硬拦截，fail-closed）───────────────────────────────
def _blacklist_pattern():
    env = (os.environ.get("XIAOJU3_DESKTOP_TITLE_BLACKLIST") or "").strip()
    return env if env else _TITLE_BLACKLIST_DEFAULT


def is_sensitive_title(title):
    """敏感窗口标题判定；正则坏掉按敏感处理（fail-closed）。"""
    if not title:
        return False
    try:
        return re.search(_blacklist_pattern(), title, re.IGNORECASE) is not None
    except re.error:
        return True


def is_password_control(ctrl):
    """UIA IsPassword（密码框官方信号）；读不到属性按敏感（fail-closed）。"""
    try:
        return bool(ctrl.IsPassword)
    except Exception:
        return True


# ── 定位链（UIA 祖先链，比裸坐标抗 DPI/布局漂移）────────────────────
def build_locator_chain(ctrl, max_depth=MAX_LOCATOR_DEPTH):
    """从命中控件向上走到顶层窗口，产出祖先定位链（顶窗在前，命中在后）。
    每节点只存稳定字段：type/name/cls/auto；name 是易变字段的最后防线，
    回放时 type 必须相等、其余空则通配。"""
    chain = []
    node = ctrl
    depth = 0
    while node is not None and depth <= max_depth:
        try:
            chain.append({
                "type": node.ControlTypeName or "",
                "name": node.Name or "",
                "cls": node.ClassName or "",
                "auto": node.AutomationId or "",
            })
        except Exception:
            break
        try:
            node = node.GetParentControl()
        except Exception:
            break
        depth += 1
    chain.reverse()
    return chain[:max_depth + 1]


# ── 技能库（agent_state/skills/，数据不出家门）──────────────────────
def _safe_name(name):
    if not isinstance(name, str) or not re.fullmatch(r"[\w\-\u4e00-\u9fff]{1,40}", name):
        return None
    return name


def _skill_path(name):
    return os.path.join(SKILLS_DIR, name + ".json")


def save_skill(name, trigger, steps, dpi=1.0):
    """落盘技能；schema 校验失败/非法名拒绝。"""
    name = _safe_name(name)
    if not name:
        return False, "❌ 技能名非法（限 1-40 位中英文/数字/-/_）。"
    if not isinstance(steps, list) or not steps:
        return False, "❌ 技能没有可保存的步骤。"
    os.makedirs(SKILLS_DIR, exist_ok=True)
    skill = {
        "version": 2,   # v2：窗口标题脱敏（proc+whash，秘书复审②）
        "name": name,
        "trigger": (trigger or "").strip()[:80],
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dpi": round(float(dpi), 3),
        "steps": steps,
    }
    try:
        with open(_skill_path(name), "w", encoding="utf-8") as f:
            json.dump(skill, f, ensure_ascii=False, indent=1)
    except OSError as e:
        return False, "❌ 技能保存失败：%s" % e
    _audit("skill_save", name, "%d 步" % len(steps))
    return True, "✅ 技能「%s」已保存（%d 步）。" % (name, len(steps))


def load_skill(name):
    """读技能；非法名/文件缺失/schema 不合法一律 None。"""
    name = _safe_name(name)
    if not name:
        return None
    try:
        with open(_skill_path(name), "r", encoding="utf-8") as f:
            skill = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(skill, dict) or not isinstance(skill.get("steps"), list):
        return None
    return skill


def list_skills():
    """技能清单（面板/模型共用）。"""
    out = []
    try:
        os.makedirs(SKILLS_DIR, exist_ok=True)
        for fn in sorted(os.listdir(SKILLS_DIR)):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(SKILLS_DIR, fn), "r", encoding="utf-8") as f:
                    s = json.load(f)
                out.append({
                    "name": s.get("name", fn[:-5]),
                    "trigger": s.get("trigger", ""),
                    "steps": len(s.get("steps", [])),
                    "created_at": s.get("created_at", ""),
                })
            except (OSError, ValueError):
                continue
    except OSError:
        pass
    return out


# ── 审计 ────────────────────────────────────────────────────────────
def _audit(action, skill="", detail=""):
    """全量审计 JSONL（失败静默——审计绝不拖垮主链）。"""
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "t": time.strftime("%Y-%m-%d %H:%M:%S"),
                "action": action, "skill": skill, "detail": str(detail)[:300],
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ── 事件后处理（纯函数，供单测）─────────────────────────────────────
def _postprocess_events(events):
    """原始事件流 → 步骤序列。

    DeepSeek 审查采纳：①事件时间戳取入队时刻（消费再慢节奏不失真）；
    ②敏感事件丢弃并计数；③连续字符合并 type_text（只挂窗口级，不挂具体
    控件——控件级挂接是会挂错的启发式，回放走焦点投递）；④步间延迟夹
    [MIN,MAX]。events 元素：
      {"kind":"click","t":ms,"x":,"y":,"window":,"locator":,"rel":,"sensitive":bool}
      {"kind":"char","t":ms,"ch":"a","window":,"sensitive":bool}
      {"kind":"hotkey","t":ms,"combo":"Ctrl+s","window":,"sensitive":bool}
    """
    steps = []
    blocked = 0
    last_t = None

    def _delay(cur_t):
        if last_t is None:
            return 0
        return max(MIN_STEP_DELAY_MS, min(MAX_STEP_DELAY_MS, int(cur_t - last_t)))

    i = 0
    n = len(events)
    while i < n:
        ev = events[i]
        if ev.get("sensitive"):
            blocked += 1
            i += 1
            continue
        t = ev.get("t", 0)
        kind = ev.get("kind")
        if kind == "click":
            steps.append({
                "type": "click", "proc": ev.get("proc", ""),
                "whash": ev.get("whash", ""),
                "locator": ev.get("locator"), "rel": ev.get("rel"),
                "xy": [ev.get("x"), ev.get("y")], "delay_ms": _delay(t),
            })
            last_t = t
            i += 1
        elif kind == "char":
            # 合并连续字符（≤MAX_TEXT_RUN）；窗口取最近一次 click 的窗口
            run = []
            proc = ev.get("proc", "")
            whash = ev.get("whash", "")
            j = i
            while j < n:
                e2 = events[j]
                if e2.get("sensitive"):
                    blocked += 1
                    j += 1
                    continue
                if e2.get("kind") != "char" or not e2.get("ch", "").isprintable():
                    break
                run.append(e2["ch"])
                proc = e2.get("proc", "") or proc
                whash = e2.get("whash", "") or whash
                j += 1
                if len(run) >= MAX_TEXT_RUN:
                    break
            steps.append({
                "type": "type_text", "proc": proc, "whash": whash,
                "text": "".join(run), "delay_ms": _delay(t),
            })
            last_t = events[j - 1].get("t", t) if j > i else t
            i = j
        elif kind == "hotkey":
            steps.append({
                "type": "hotkey", "proc": ev.get("proc", ""),
                "whash": ev.get("whash", ""),
                "combo": ev.get("combo", ""), "delay_ms": _delay(t),
            })
            last_t = t
            i += 1
        else:
            i += 1
    return steps, blocked


# ── hotkey：vk 直取 → uiautomation SendKeys 语法 ─────────────────────
# （2026-10-31 合规批：pynput=LGPLv3 按队长最高红线移除，录制层换自研
#   ctypes LL 钩子——DeepSeek 秘书裁决路线 A：零 LGPL 依赖、代码自有）
_UIA_MOD = {"Ctrl": "{Ctrl}", "Alt": "{Alt}", "Win": "{Win}", "Shift": "{Shift}"}
_UIA_KEY = {"Enter": "{Enter}", "Space": " ", "Tab": "{Tab}",
            "Backspace": "{Backspace}", "Delete": "{Delete}", "Esc": "{Esc}",
            "Up": "{Up}", "Down": "{Down}", "Left": "{Left}",
            "Right": "{Right}", "Home": "{Home}", "End": "{End}",
            "PageUp": "{PageUp}", "PageDown": "{PageDown}", "Insert": "{Insert}"}


def _vk_to_name(vk):
    """虚拟键码 → 键名（DeepSeek 审查：禁用 char 反推，vk 直取对布局/IME 稳）。"""
    if not vk:
        return None
    if 0x41 <= vk <= 0x5A:      # A-Z
        return chr(vk)
    if 0x30 <= vk <= 0x39:      # 0-9
        return chr(vk)
    if 0x60 <= vk <= 0x69:      # 小键盘 0-9
        return "Num%d" % (vk - 0x60)
    if 0x70 <= vk <= 0x87:      # F1-F24
        return "F%d" % (vk - 0x6F)
    return None


def combo_to_uia(combo):
    """"Ctrl+s" → "{Ctrl}s"；"Enter" → "{Enter}"。未知键原样（SendKeys 兜底）。"""
    parts = [p.strip() for p in str(combo).split("+") if p.strip()]
    out = ""
    for p in parts:
        if p in _UIA_MOD:
            out += _UIA_MOD[p]
        elif p in _UIA_KEY:
            out += _UIA_KEY[p]
        else:
            out += p
    return out


def _hash_title(title):
    """窗口标题脱敏哈希（秘书复审②：技能文件禁存明文标题）——
    sha256 前 12 位；回放按 进程名+标题哈希 两段式定位（不落明文）。"""
    import hashlib
    return hashlib.sha256((title or "").encode("utf-8", "ignore")).hexdigest()[:12]


def _norm_title(s):
    """窗口标题归一化：Win11 记事本未保存改动态会给标题加 `*` 前缀，
    录制态与回放态不一致会假失配（E2E 实锤）——统一去 * 去空白。"""
    return (s or "").strip().lstrip("*").strip()


def _foreground_title():
    """前台窗口标题（ctypes 直取，微秒级——钩子线程安全用，绝不碰 UIA）。
    秘书审查点④修复：键盘事件在钩子时归属前台窗口，敏感窗口里的按键
    在录制端即被丢弃，堵住"敏感窗口打字被录成无窗口事件绕过黑名单"的
    键记录缺口。已知漏判面（如实挂账）：无标题窗口 + IsPassword 控件内
    打字（钩子时做 UIA 查询代价过高）→ 由回放端硬拦截兜底。"""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        return _norm_title(buf.value)
    except Exception:
        return ""


_PROC_BLACKLIST_DEFAULT = r"keepass|bitwarden|1password|lastpass|dashlane|enpass"


def is_sensitive_proc(proc_name):
    """敏感进程判定（2026-10-31 合规批实装：密码管理器等凭据类进程
    整体禁录禁放）；env XIAOJU3_DESKTOP_PROC_BLACKLIST 可覆盖。"""
    if not proc_name:
        return False
    env = (os.environ.get("XIAOJU3_DESKTOP_PROC_BLACKLIST") or "").strip()
    pattern = env if env else _PROC_BLACKLIST_DEFAULT
    try:
        return re.search(pattern, proc_name, re.IGNORECASE) is not None
    except re.error:
        return True


def _pid_proc_name(hwnd):
    """句柄→进程名（小写）；任何异常返回 ""（不误拦）。"""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        import psutil
        return (psutil.Process(pid.value).name() or "").lower()
    except Exception:
        return ""


def _foreground_proc():
    """前台窗口的进程名（ctypes+psutil，毫秒级——键盘钩子安全用）。"""
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        return _pid_proc_name(hwnd) if hwnd else ""
    except Exception:
        return ""


# ── 自研 LL 钩子（合规批：pynput=LGPLv3 移除；DeepSeek 秘书裁决路线 A）──
# 工程铁律（秘书审查）：①钩子回调只做"读结构体+入队+立即 CallNextHookEx"，
# 绝不做 UIA/日志/锁竞争——不拖慢全系统输入；②停止顺序=先 UnhookWindowsHookEx
# 再 PostThreadMessage(WM_QUIT)，反序=钩子泄漏；③钩子必须装在有消息循环的线程。
import ctypes as _ct
from ctypes import wintypes as _wt

_HOOKPROC = _ct.WINFUNCTYPE(_ct.c_ssize_t, _ct.c_int, _ct.c_size_t, _ct.c_ssize_t)

# 64 位句柄纪律（E2E 实锤：默认 restype=c_int 把 GetModuleHandleW 的 64 位
# 句柄截断成 32 位 → SetWindowsHookExW 报 126 MOD_NOT_FOUND）——必须显式
# 声明 argtypes/restypes，句柄全程 c_void_p。
_user32 = _ct.windll.user32
_kernel32 = _ct.windll.kernel32
_kernel32.GetModuleHandleW.restype = _ct.c_void_p
_kernel32.GetModuleHandleW.argtypes = (_wt.LPCWSTR,)
_user32.SetWindowsHookExW.restype = _ct.c_void_p
_user32.SetWindowsHookExW.argtypes = (_ct.c_int, _HOOKPROC, _ct.c_void_p,
                                      _wt.DWORD)
_user32.UnhookWindowsHookEx.argtypes = (_ct.c_void_p,)
_user32.CallNextHookEx.restype = _ct.c_ssize_t
_user32.CallNextHookEx.argtypes = (_ct.c_void_p, _ct.c_int, _ct.c_size_t,
                                   _ct.c_ssize_t)


class _POINT(_ct.Structure):
    _fields_ = [("x", _ct.c_long), ("y", _ct.c_long)]


class _MSLLHOOKSTRUCT(_ct.Structure):
    _fields_ = [("pt", _POINT), ("mouseData", _wt.DWORD),
                ("flags", _wt.DWORD), ("time", _wt.DWORD),
                ("dwExtraInfo", _ct.c_size_t)]


class _KBDLLHOOKSTRUCT(_ct.Structure):
    _fields_ = [("vkCode", _wt.DWORD), ("scanCode", _wt.DWORD),
                ("flags", _wt.DWORD), ("time", _wt.DWORD),
                ("dwExtraInfo", _ct.c_size_t)]


_VK_MOD_NAME = {0x10: "Shift", 0x11: "Ctrl", 0x12: "Alt",
                0xA0: "Shift", 0xA1: "Shift", 0xA2: "Ctrl", 0xA3: "Ctrl",
                0xA4: "Alt", 0xA5: "Alt", 0x5B: "Win", 0x5C: "Win"}
_VK_SPECIAL_NAME = {0x0D: "Enter", 0x09: "Tab", 0x08: "Backspace",
                    0x1B: "Esc", 0x2E: "Delete", 0x25: "Left", 0x26: "Up",
                    0x27: "Right", 0x28: "Down", 0x24: "Home", 0x23: "End",
                    0x21: "PageUp", 0x22: "PageDown"}


def _vk_to_char(vk, scan, down_vks):
    """vk→字符（ToUnicodeEx 含 Shift 态）。已知限制：IME 合成键
    （VK_PROCESSKEY 0xE5）拿不到合成汉字——LL 钩子在输入法合成前触发，
    pynput 同理；录制捕获的是物理按键序列（对外表述按此口径）。"""
    try:
        user32 = _ct.windll.user32
        state = (_wt.BYTE * 256)()
        for k in down_vks:
            state[k] = 0x80
        # 规范修饰键位（探针实锤）：ToUnicodeEx 按 VK_SHIFT/CONTROL/MENU
        # 判状态——只置 VK_LSHIFT(0xA0) 不生效，必须同置规范位 0x10/0x11/0x12
        if down_vks & {0x10, 0xA0, 0xA1}:
            state[0x10] = 0x80
        if down_vks & {0x11, 0xA2, 0xA3}:
            state[0x11] = 0x80
        if down_vks & {0x12, 0xA4, 0xA5}:
            state[0x12] = 0x80
        buf = _ct.create_unicode_buffer(8)
        n = user32.ToUnicodeEx(vk, scan, state, buf, 8, 0,
                               user32.GetKeyboardLayout(0))
        if n == 1:
            return buf.value
    except Exception:
        pass
    return None


class _WinHook(object):
    """WH_MOUSE_LL(14)/WH_KEYBOARD_LL(13) 自研全局钩子（零第三方依赖）。"""

    def __init__(self, recorder):
        self._rec = recorder
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="xj3-winhook")
        self.thread_id = 0
        self.h_mouse = None
        self.h_kbd = None
        self.error = None
        self._ready = threading.Event()

    def start(self):
        self._thread.start()
        self._ready.wait(timeout=3)
        if self.error:
            return False
        return self.h_mouse is not None and self.h_kbd is not None

    def stop(self):
        user32 = _user32
        if self.h_mouse:
            user32.UnhookWindowsHookEx(self.h_mouse)
            self.h_mouse = None
        if self.h_kbd:
            user32.UnhookWindowsHookEx(self.h_kbd)
            self.h_kbd = None
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)  # WM_QUIT
        self._thread.join(timeout=3)

    def _run(self):
        user32 = _user32
        kernel32 = _kernel32
        self.thread_id = kernel32.GetCurrentThreadId()
        # 回调对象必须挂 self 持引用——临时 _HOOKPROC 被 GC 后钩子一触发
        # 即访问违例、整个进程死（E2E 实锤：仪表盘中途消失的元凶）
        self._mouse_proc = _HOOKPROC(self._mouse_cb)
        self._kbd_proc = _HOOKPROC(self._kbd_cb)
        self.h_mouse = user32.SetWindowsHookExW(
            14, self._mouse_proc,
            kernel32.GetModuleHandleW(None), 0)
        self.h_kbd = user32.SetWindowsHookExW(
            13, self._kbd_proc,
            kernel32.GetModuleHandleW(None), 0)
        if not self.h_mouse or not self.h_kbd:
            self.error = kernel32.GetLastError()
        self._ready.set()
        if self.error:
            return
        msg = _wt.MSG()
        while user32.GetMessageW(_ct.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(_ct.byref(msg))
            user32.DispatchMessageW(_ct.byref(msg))

    def _mouse_cb(self, nCode, wParam, lParam):
        try:
            if nCode >= 0 and int(wParam) == 0x201:      # WM_LBUTTONDOWN
                info = _ct.cast(_ct.c_void_p(lParam),
                                _ct.POINTER(_MSLLHOOKSTRUCT)).contents
                self._rec._push({"kind": "click",
                                 "t": int(time.time() * 1000),
                                 "x": int(info.pt.x), "y": int(info.pt.y)})
        except Exception:
            pass
        return _user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _kbd_cb(self, nCode, wParam, lParam):
        try:
            if nCode >= 0:
                wp = int(wParam)
                info = _ct.cast(_ct.c_void_p(lParam),
                                _ct.POINTER(_KBDLLHOOKSTRUCT)).contents
                vk = int(info.vkCode)
                if wp in (0x100, 0x104):                 # KEYDOWN/SYSKEYDOWN
                    self._rec._key_down(vk, int(info.scanCode))
                elif wp in (0x101, 0x105):               # KEYUP/SYSKEYUP
                    self._rec._key_up(vk)
        except Exception:
            pass
        return _user32.CallNextHookEx(None, nCode, wParam, lParam)


# ── 录制器 ──────────────────────────────────────────────────────────
class SkillRecorder(object):
    """线程模型（DeepSeek 审查①③采纳）：
    - 自研 LL 钩子回调只打时间戳入队，微秒级返回，绝不阻塞钩子；
    - 解析 worker 线程 CoInitialize 后消费队列；ControlFromPoint 可能被
      浏览器 provider 卡数百 ms~数秒——单次解析放独立线程加超时，
      超时降级"仅坐标"事件（locator=None），录制节奏不受 UIA 拖累。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._recording = False
        self._name = ""
        self._trigger = ""
        self._events = []
        self._blocked = 0
        self._overflow = False
        self._started = 0.0
        self._q = None
        self._hook = None
        self._down_vks = set()
        self._dropped = 0
        self._hook_lost = False
        self._watchdog = None
        self._worker = None
        self._listeners = []
        self._mods = set()

    # -- 对外状态 --
    def status(self):
        with self._lock:
            return {
                "recording": self._recording,
                "name": self._name,
                "events": len(self._events),
                "blocked_sensitive": self._blocked,
                "dropped": self._dropped,
                "hook_alive": (self._hook is not None
                               and self._hook.h_mouse is not None
                               and self._hook.h_kbd is not None
                               and self._hook._thread.is_alive()),
                "hook_lost": self._hook_lost,
                "seconds": round(time.time() - self._started, 1) if self._recording else 0,
            }

    def start(self, name, trigger=""):
        with self._lock:
            if self._recording:
                return False, "❌ 已在录制「%s」中，请先停止。" % self._name
            name = _safe_name(name)
            if not name:
                return False, "❌ 技能名非法（限 1-40 位中英文/数字/-/_）。"
            _ensure_comtypes_gen_dir()
            self._name = name
            self._trigger = (trigger or "").strip()[:80]
            self._events = []
            self._blocked = 0
            self._overflow = False
            self._started = time.time()
            self._mods = set()
            self._down_vks = set()
            self._q = _queue.SimpleQueue()  # 非阻塞入队（秘书复审①）
            self._hook = _WinHook(self)
            if not self._hook.start():
                err = self._hook.error
                if err:
                    return False, "❌ 全局钩子启动失败（GetLastError=%s）。" % err
                return False, "❌ 全局钩子启动失败。"
            self._listeners = []
            self._worker = threading.Thread(
                target=self._resolve_loop, daemon=True, name="xj3-recorder")
            self._recording = True
            self._worker.start()
            # 秘书复审①：钩子存活看门狗（LL 钩子被系统超时卸载/线程死=
            # 静默丢事件）——每 10s 自检，失效即自动停录并如实入账
            self._watchdog = threading.Thread(
                target=self._hook_watchdog, daemon=True, name="xj3-hookdog")
            self._watchdog.start()
            # UIA 冷启动预热（E2E 实锤：150% DPI 下首例 ControlFromPoint
            # 超 0.8s 超时降级）——后台打一发即弃，首击不再是冷启动
            threading.Thread(target=lambda: self._resolve_with_timeout(1, 1),
                             daemon=True).start()
        _audit("record_start", name, self._trigger)
        return True, "✅ 开始录制「%s」。去操作目标窗口吧，完成后回控制台点停止。" % name

    def stop(self):
        with self._lock:
            if not self._recording:
                return False, {"message": "❌ 当前没有在录制。"}
            self._recording = False
        if self._hook is not None:
            try:
                self._hook.stop()  # 先 Unhook 再 WM_QUIT（秘书铁律②）
            except Exception:
                pass
        self._listeners = []
        if self._watchdog is not None:
            self._watchdog.join(timeout=2)
            self._watchdog = None
        if self._worker is not None:
            self._worker.join(timeout=3)
        with self._lock:
            events = list(self._events)
            blocked = self._blocked
            overflow = self._overflow
            name, trigger = self._name, self._trigger
            self._events = []
        steps, extra_blocked = _postprocess_events(events)
        blocked += extra_blocked
        ok, msg = save_skill(name, trigger, steps, dpi=_dpi_scale())
        summary = {
            "message": msg, "ok": ok, "name": name,
            "steps": len(steps), "blocked_sensitive": blocked,
            "overflow": overflow,
        }
        if overflow:
            summary["message"] += "（事件超上限，已截断保存）"
        _audit("record_stop", name,
               "%d 步 / 敏感拦截 %d" % (len(steps), blocked))
        return ok, summary

    # -- LL 钩子事件处理（只入队语义；解析在 worker；回调层绝不抛）--
    def _key_down(self, vk, scan):
        mod = _VK_MOD_NAME.get(vk)
        if mod:
            self._mods.add(mod)
        self._down_vks.add(vk)
        if mod:
            return
        fg = _foreground_title()          # 前台窗口归属（敏感判定用，不落盘）
        proc = _foreground_proc()         # 敏感进程（合规批实装）
        sens = (is_sensitive_title(fg) or is_sensitive_proc(proc))
        whash = _hash_title(fg)           # 落盘脱敏：只存 进程名+标题哈希
        if self._mods - {"Shift"}:
            # 仅 Shift + 可打印字符 = 文本（大写/符号），不构成组合键；
            # Ctrl/Alt/Win 任一在场才走组合键（E2E 实锤教训）
            main = _vk_to_name(vk)
            if main:
                combo = "+".join(sorted(self._mods) + [main])
                self._push({"kind": "hotkey", "t": int(time.time() * 1000),
                            "combo": combo, "proc": proc, "whash": whash,
                            "sensitive": sens})
            return
        ch = _vk_to_char(vk, scan, self._down_vks)
        if ch:
            self._push({"kind": "char", "t": int(time.time() * 1000),
                        "ch": ch, "proc": proc, "whash": whash,
                        "sensitive": sens})
            return
        name = _VK_SPECIAL_NAME.get(vk)
        if name:
            self._push({"kind": "hotkey", "t": int(time.time() * 1000),
                        "combo": name, "proc": proc, "whash": whash,
                        "sensitive": sens})

    def _key_up(self, vk):
        mod = _VK_MOD_NAME.get(vk)
        if mod:
            self._mods.discard(mod)
        self._down_vks.discard(vk)

    def _hook_watchdog(self):
        """秘书复审①：录制会话内每 10s 自检钩子存活——句柄被卸载/钩子线程
        死亡=静默丢事件，立即自动停录（诚实回执优于无声残缺）。"""
        while True:
            time.sleep(10)
            with self._lock:
                if not self._recording:
                    return
                hook = self._hook
            try:
                alive = (hook is not None
                         and hook.h_mouse is not None
                         and hook.h_kbd is not None
                         and hook._thread.is_alive())
            except Exception:
                alive = False
            if not alive:
                with self._lock:
                    self._hook_lost = True
                _audit("hook_lost", self._name, "看门狗检出钩子失效，自动停录")
                try:
                    self.stop()
                except Exception:
                    pass
                return

    def _push(self, ev):
        # 秘书复审①：入队绝对非阻塞——events 追加持锁极短（微秒级），
        # 队列 put_nowait 永不阻塞钩子回调；异常计数丢弃，绝不拖系统输入
        with self._lock:
            if not self._recording:
                return
            if len(self._events) >= RECORD_MAX_EVENTS:
                self._overflow = True
                return
            self._events.append(ev)
            ev["_idx"] = len(self._events) - 1  # worker 直取槽位（同毫秒连点不串槽）
        if self._q is not None:
            try:
                self._q.put_nowait(ev)
            except Exception:
                with self._lock:
                    self._dropped += 1

    # -- 解析 worker（COM 线程；UIA 单次解析带超时降级）--
    def _resolve_loop(self):
        _com_init()
        while True:
            try:
                ev = self._q.get(timeout=0.3)
            except _queue.Empty:
                with self._lock:
                    if not self._recording:
                        return
                continue
            if ev.get("kind") != "click":
                continue  # 键盘事件无需 UIA（窗口归属用最近点击的窗口）
            result = self._resolve_with_timeout(ev["x"], ev["y"])
            idx = ev.get("_idx")
            with self._lock:
                if not self._events or idx is None or not (0 <= idx < len(self._events)):
                    continue
                slot = self._events[idx]
                if result is None:
                    slot["locator"] = None
                    slot["proc"] = ""
                    slot["whash"] = ""
                    slot["rel"] = None
                    slot["sensitive"] = False
                else:
                    slot.update(result)

    def _resolve_with_timeout(self, x, y):
        """UIA 解析放独立线程 + 超时（浏览器 provider 卡死防线）。"""
        box = {}

        def _job():
            try:
                _com_init()  # COM 纪律：新线程必须自初始化（E2E 实锤：job
                             # 线程漏 init → UIA 创建必败 → 每击必超时降级）
                box["r"] = self._resolve_click_uia(x, y)
            except Exception:
                box["r"] = None

        th = threading.Thread(target=_job, daemon=True)
        th.start()
        th.join(UIA_TIMEOUT_S)
        return box.get("r")

    def _resolve_click_uia(self, x, y):
        auto = _get_auto()
        ctrl = auto.ControlFromPoint(int(x), int(y))
        if ctrl is None:
            return None
        try:
            top = ctrl.GetTopLevelControl()
        except Exception:
            top = None
        title = _norm_title(top.Name) if top is not None else ""
        rel = None
        if top is not None:
            try:
                rect = top.BoundingRectangle
                w = max(1, int(rect.right) - int(rect.left))
                h = max(1, int(rect.bottom) - int(rect.top))
                rel = [round((int(x) - int(rect.left)) / w, 4),
                       round((int(y) - int(rect.top)) / h, 4)]
            except Exception:
                rel = None
        pwd = is_password_control(ctrl)
        proc = ""
        try:
            hwnd = top.NativeWindowHandle if top is not None else None
            proc = _pid_proc_name(hwnd) if hwnd else ""
        except Exception:
            proc = ""
        sens = (pwd or is_sensitive_title(title) or is_sensitive_proc(proc))
        # 脱敏（秘书复审②）：落盘只存 进程名+标题哈希，绝不存明文标题
        return {
            "locator": build_locator_chain(ctrl),
            "proc": proc,
            "whash": _hash_title(title),
            "rel": rel,
            "sensitive": bool(sens),
        }


# 模块级单例（dashboard/工具族共用；技能录制一次只允许一路）
_recorder = SkillRecorder()


# ── 回放 ────────────────────────────────────────────────────────────
def _find_window(auto, proc, whash, locator0=None):
    """两段式定位（秘书复审②：不落明文标题）——①按进程名列候选
    ②按标题哈希校验锁定（同进程多窗口可精确定位）。whash 为空=legacy
    v1 技能（仅按进程匹配，审计标注）；定位链 cls 兜底殿后。
    UIA 枚举偶发瞬时失配——3×0.25s 重试。"""
    proc = (proc or "").lower()
    for attempt in range(3):
        try:
            root = auto.GetRootControl()
            children = root.GetChildren()
            for w in children:
                try:
                    if not proc:
                        continue
                    wproc = _pid_proc_name(w.NativeWindowHandle)
                    if wproc != proc:
                        continue
                    if whash and _hash_title(_norm_title(w.Name)) != whash:
                        continue
                    return w
                except Exception:
                    continue
            if locator0 and locator0.get("cls"):
                for w in children:
                    try:
                        if w.ClassName == locator0["cls"]:
                            return w
                    except Exception:
                        continue
        except Exception:
            pass
        time.sleep(0.25)
    return None


def _descend(auto, window, locator):
    """按定位链下钻（locator[0]=顶窗本体，跳过）；失配返回 None。"""
    node = window
    for i, spec in enumerate(locator):
        if i == 0:
            continue
        try:
            children = node.GetChildren()
        except Exception:
            return None
        hit = None
        for ch in children:
            try:
                if (ch.ControlTypeName or "") != (spec.get("type") or ""):
                    continue
                for field, attr in (("name", "Name"), ("cls", "ClassName"),
                                    ("auto", "AutomationId")):
                    want = spec.get(field) or ""
                    if want and (getattr(ch, attr) or "") != want:
                        break
                else:
                    hit = ch
                    break
            except Exception:
                continue
        if hit is None:
            return None
        node = hit
    return node


_EDITABLE_BASES = ("Edit", "Document", "TextArea")


def _is_editable(control_type_name):
    """ControlTypeName 后缀归一（探针实锤：Win11 记事本编辑区=
    DocumentControl，裸比对 "Document" 永远失配）。"""
    tn = control_type_name or ""
    if tn.endswith("Control"):
        tn = tn[:-7]
    return tn in _EDITABLE_BASES


def _bring_foreground(window):
    """把目标窗口提到前台（UIA SetFocus 只设窗口内焦点不抢前台，
    SendInput 永远发给前台窗口——探针 1/2 实锤：不前台化打字全落空）。"""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = window.NativeWindowHandle
        if hwnd:
            user32.ShowWindow(hwnd, 9)            # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def _focus_editable(window):
    """聚焦窗口内第一个可编辑后代（深度 ≤3），退而顶层窗。
    E2E 实锤：UWP 记事本对顶层 SetFocus 后焦点落在标签栏，type_text
    全部打空——必须落到 Edit/Document 本体。"""
    try:
        frontier = [window]
        depth = 0
        while frontier and depth <= 3:
            nxt = []
            for node in frontier:
                try:
                    children = node.GetChildren()
                except Exception:
                    continue
                for ch in children:
                    try:
                        if _is_editable(ch.ControlTypeName):
                            ch.SetFocus()
                            return True
                    except Exception:
                        continue
                    nxt.append(ch)
            frontier = nxt
            depth += 1
    except Exception:
        pass
    try:
        window.SetFocus()
    except Exception:
        pass
    return False


def _window_rect(window):
    try:
        rect = window.BoundingRectangle
        return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
    except Exception:
        return None


def play_skill(name, source="tool"):
    """回放技能（失败即停，诚实汇报已执行步数）。
    DeepSeek 审查采纳：①type_text 不依赖录制控件，聚焦目标窗口后 SendKeys
    到焦点（控件级挂接是会挂错的启发式——风险已在审计标注）；②DPI 缩放与
    录制时不一致则禁用坐标回退（宁失败不盲点）。"""
    skill = load_skill(name)
    if skill is None:
        return False, "❌ 技能「%s」不存在或已损坏。" % name
    steps = skill.get("steps", [])
    if not steps:
        return False, "❌ 技能「%s」没有步骤。" % name
    try:
        auto = _get_auto()
    except RuntimeError as e:
        return False, str(e)
    _com_init()
    allow_fallback = abs(_dpi_scale() - float(skill.get("dpi", 1.0))) < 0.02
    _audit("play_start", name, "%d 步 / 坐标回退=%s / 来源=%s"
           % (len(steps), allow_fallback, source))
    executed = 0
    try:
        import pyautogui  # 坐标回退用
    except ImportError:
        return False, "❌ pyautogui 不可用——冻结包请核对 spec hiddenimports。"
    pyautogui.FAILSAFE = False
    try:
        for idx, step in enumerate(steps, 1):
            proc = (step.get("proc") or "").lower()
            whash = step.get("whash", "")
            if is_sensitive_proc(proc):
                _audit("play_abort_sensitive", name, "第 %d 步进程「%s」" % (idx, proc))
                return False, ("❌ 第 %d 步目标进程命中敏感黑名单（%s），已中止。"
                               "已执行 %d/%d 步。" % (idx, proc, executed, len(steps)))
            stype = step.get("type")
            delay = max(MIN_STEP_DELAY_MS, min(MAX_STEP_DELAY_MS,
                                               int(step.get("delay_ms", 0) or 0)))
            if delay:
                time.sleep(delay / 1000.0)
            locator0 = (step.get("locator") or [None])[0] if step.get("locator") else None
            window = _find_window(auto, proc, whash, locator0)
            if (proc or whash) and window is None and locator0 is None:
                _audit("play_fail_window", name,
                       "第 %d 步找不到目标（proc=%s）" % (idx, proc))
                return False, ("❌ 第 %d 步找不到目标窗口（进程 %s，可能已关闭）。"
                               "已执行 %d/%d 步。" % (idx, proc, executed, len(steps)))
            if window is not None:
                _bring_foreground(window)  # SendInput 只发给前台窗口
            if stype == "click":
                ctrl = None
                loc = step.get("locator")
                if window is not None and loc:
                    ctrl = _descend(auto, window, loc)
                if ctrl is not None:
                    if is_password_control(ctrl):
                        _audit("play_abort_password", name, "第 %d 步" % idx)
                        return False, ("❌ 第 %d 步目标是密码框（UIA IsPassword），"
                                       "已中止。已执行 %d/%d 步。"
                                       % (idx, executed, len(steps)))
                    ctrl.Click(simulateMove=False)
                else:
                    rel = step.get("rel")
                    xy = step.get("xy") or [None, None]
                    if window is not None and rel and allow_fallback:
                        rect = _window_rect(window)
                        if rect:
                            px = int(rect[0] + rel[0] * (rect[2] - rect[0]))
                            py = int(rect[1] + rel[1] * (rect[3] - rect[1]))
                            pyautogui.click(px, py)
                        else:
                            return False, _fail_progress(idx, executed, len(steps),
                                                         "窗口矩形不可得")
                    elif xy[0] is not None and allow_fallback and window is None:
                        pyautogui.click(int(xy[0]), int(xy[1]))
                    else:
                        _audit("play_fail_locate", name, "第 %d 步定位链失配" % idx)
                        return False, _fail_progress(
                            idx, executed, len(steps),
                            "定位链失配" + ("" if allow_fallback else
                                           "（DPI 缩放与录制时不一致，坐标回退已禁用）"))
            elif stype == "type_text":
                if window is not None:
                    _focus_editable(window)
                text = str(step.get("text", ""))[:MAX_TEXT_RUN]
                if text:
                    auto.SendKeys(text, interval=0.02, waitTime=0)
                    _audit("play_type", name,
                           "第 %d 步 %d 字（焦点投递，进错框风险已知）" % (idx, len(text)))
            elif stype == "hotkey":
                if window is not None:
                    _focus_editable(window)
                auto.SendKeys(combo_to_uia(step.get("combo", "")), waitTime=0)
            else:
                return False, _fail_progress(idx, executed, len(steps),
                                             "未知步骤类型 %s" % stype)
            executed = idx
            _audit("play_step", name, "%d/%d %s" % (idx, len(steps), stype))
    except Exception as e:
        return False, _fail_progress(executed + 1, executed, len(steps),
                                     "执行异常 %s: %s" % (type(e).__name__, e))
    _audit("play_done", name, "%d 步全部完成" % len(steps))
    return True, "✅ 技能「%s」回放完成，共 %d 步。" % (name, len(steps))


def _fail_progress(idx, executed, total, why):
    return ("❌ 第 %d 步失败（%s）。已执行 %d/%d 步，已停下未继续——"
            "可修正环境后重试。" % (idx, why, executed, total))


# ── 模型工具处理器（tool_registry handler 契约：返回中文文本）────────
def tool_list_skills():
    skills = list_skills()
    if not skills:
        return "✅ 技能库还是空的。主人可以在控制台 🧰 小工具面板点「技能录制」教我第一个操作。"
    rows = ["✅ 已有 %d 个桌面技能：" % len(skills)]
    for s in skills:
        rows.append("- %s（%d 步%s）" % (s["name"], s["steps"],
                    "，触发语：%s" % s["trigger"] if s["trigger"] else ""))
    return "\n".join(rows)


def tool_run_skill(name=None, **_):
    if not name:
        return "❌ 缺少技能名。可先调用 desktop_list_skills 查看技能库。"
    ok, msg = play_skill(str(name), source="tool")
    return msg


def tool_list_windows():
    try:
        auto = _get_auto()
        _com_init()
        rows = []
        root = auto.GetRootControl()
        for w in root.GetChildren():
            try:
                title = (w.Name or "").strip()
                if not title:
                    continue
                rect = _window_rect(w)
                size = ("%dx%d" % (rect[2] - rect[0], rect[3] - rect[1])) if rect else "?"
                rows.append("- %s（%s）" % (title, size))
                if len(rows) >= 15:
                    rows.append("- …（仅显示前 15 个）")
                    break
            except Exception:
                continue
        if not rows:
            return "✅ 当前没有可见标题的顶层窗口。"
        return "✅ 当前桌面窗口：\n" + "\n".join(rows)
    except Exception as e:
        return "❌ 窗口枚举失败：%s" % e


# ── dashboard API 薄封装（面板用；返回 (ok, payload)）────────────────
def api_record_start(name, trigger=""):
    ok, msg = _recorder.start(name, trigger)
    return ok, {"message": msg}


def api_record_stop():
    ok, payload = _recorder.stop()
    return ok, payload


def api_record_status():
    return _recorder.status()


def api_skills_list():
    return True, list_skills()


def api_skill_run(name):
    ok, msg = play_skill(str(name or ""), source="panel")
    return ok, {"message": msg, "name": name}
