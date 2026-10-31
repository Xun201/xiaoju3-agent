# -*- coding: utf-8 -*-
"""小橘3号 · 桌面技能录制回放（DA1 · 阶段一：技能录制回放）。

路线图：_dev/design_desktop_automation_roadmap.md（2026-10-31 队长拍板立项）。
设计已过 DeepSeek 秘书审查，四条致命点全采纳（见各函数标注）。

能力：
- 录制：pynput 全局钩子捕获鼠标点击/键盘输入；点击落点经 uiautomation
  ControlFromPoint 解析 UIA 控件树生成"祖先定位链"（比裸坐标抗 DPI/布局漂移）；
  连续字符键合并 type_text；Ctrl/Alt/Win 组合按 vk 直取记 hotkey。
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
uiautomation/comtypes/pynput/pyautogui 全部进 hiddenimports（pynput 的
_win32 后端是动态 import，漏了=冻结包 ModuleNotFoundError）。comtypes 的
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
        "version": 1,
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
                "type": "click", "window": ev.get("window", ""),
                "locator": ev.get("locator"), "rel": ev.get("rel"),
                "xy": [ev.get("x"), ev.get("y")], "delay_ms": _delay(t),
            })
            last_t = t
            i += 1
        elif kind == "char":
            # 合并连续字符（≤MAX_TEXT_RUN）；窗口取最近一次 click 的窗口
            run = []
            window = ev.get("window", "")
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
                window = e2.get("window", "") or window
                j += 1
                if len(run) >= MAX_TEXT_RUN:
                    break
            steps.append({
                "type": "type_text", "window": window,
                "text": "".join(run), "delay_ms": _delay(t),
            })
            last_t = events[j - 1].get("t", t) if j > i else t
            i = j
        elif kind == "hotkey":
            steps.append({
                "type": "hotkey", "window": ev.get("window", ""),
                "combo": ev.get("combo", ""), "delay_ms": _delay(t),
            })
            last_t = t
            i += 1
        else:
            i += 1
    return steps, blocked


# ── hotkey：pynput vk → uiautomation SendKeys 语法 ──────────────────
_SPECIAL_NAME = {
    "enter": "Enter", "space": "Space", "tab": "Tab", "backspace": "Backspace",
    "delete": "Delete", "esc": "Esc", "up": "Up", "down": "Down",
    "left": "Left", "right": "Right", "home": "Home", "end": "End",
    "page_up": "PageUp", "page_down": "PageDown", "insert": "Insert",
}
_MOD_NAME = {"ctrl_l": "Ctrl", "ctrl_r": "Ctrl", "alt_l": "Alt",
             "alt_r": "Alt", "alt_gr": "Alt", "cmd_l": "Win", "cmd_r": "Win",
             "cmd": "Win", "shift_l": "Shift", "shift_r": "Shift",
             "shift": "Shift"}
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


# ── 录制器 ──────────────────────────────────────────────────────────
class SkillRecorder(object):
    """线程模型（DeepSeek 审查①③采纳）：
    - pynput 钩子回调只打时间戳入队，微秒级返回，绝不阻塞钩子；
    - 解析 worker 线程 CoInitialize 后消费队列；ControlFromPoint 可能被
      浏览器 provider 卡数百 ms~数秒——单次解析放独立线程加 800ms 超时，
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
                "seconds": round(time.time() - self._started, 1) if self._recording else 0,
            }

    def start(self, name, trigger=""):
        with self._lock:
            if self._recording:
                return False, "❌ 已在录制「%s」中，请先停止。" % self._name
            name = _safe_name(name)
            if not name:
                return False, "❌ 技能名非法（限 1-40 位中英文/数字/-/_）。"
            try:
                from pynput import mouse, keyboard  # noqa: F401  缺席即报
            except ImportError as e:
                return False, ("❌ pynput 不可用（%s）——冻结包请核对 spec "
                               "hiddenimports。" % e)
            _ensure_comtypes_gen_dir()
            self._name = name
            self._trigger = (trigger or "").strip()[:80]
            self._events = []
            self._blocked = 0
            self._overflow = False
            self._started = time.time()
            self._mods = set()
            self._q = _queue.Queue()
            try:
                m_listener = mouse.Listener(on_click=self._on_click)
                k_listener = keyboard.Listener(
                    on_press=self._on_press, on_release=self._on_release)
                m_listener.start()
                k_listener.start()
            except Exception as e:
                return False, "❌ 全局钩子启动失败：%s" % e
            self._listeners = [m_listener, k_listener]
            self._worker = threading.Thread(
                target=self._resolve_loop, daemon=True, name="xj3-recorder")
            self._recording = True
            self._worker.start()
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
        for ln in self._listeners:
            try:
                ln.stop()
            except Exception:
                pass
        self._listeners = []
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

    # -- pynput 钩子（只入队，绝不阻塞）--
    def _on_click(self, x, y, button, pressed):
        if not pressed:
            return
        try:
            from pynput import mouse
            if button != mouse.Button.left:
                return
        except Exception:
            return
        self._push({"kind": "click", "t": int(time.time() * 1000),
                    "x": int(x), "y": int(y)})

    def _on_press(self, key):
        try:
            from pynput import keyboard
            fg = _foreground_title()  # 前台窗口归属（敏感键记录缺口封堵）
            sens = is_sensitive_title(fg)
            if isinstance(key, keyboard.Key):
                base = _MOD_NAME.get(key.name)
                if base:
                    self._mods.add(base)
                    return
                combo = "+".join(sorted(self._mods) + [_SPECIAL_NAME.get(
                    key.name, key.name.capitalize())])
                self._push({"kind": "hotkey", "t": int(time.time() * 1000),
                            "combo": combo, "window": fg, "sensitive": sens})
                return
            if self._mods:
                # 仅 Shift + 可打印字符 = 文本（大写/符号），不构成组合键；
                # Ctrl/Alt/Win 任一在场才走 vk 组合键（E2E 实锤：Shift 漏映射
                # 曾把大写打字拆成 N 个 "Shift" hotkey 步骤）
                ctrl_like = self._mods - {"Shift"}
                if ctrl_like:
                    main = _vk_to_name(getattr(key, "vk", None))
                    if main:
                        combo = "+".join(sorted(self._mods) + [main])
                        self._push({"kind": "hotkey", "t": int(time.time() * 1000),
                                    "combo": combo, "window": fg,
                                    "sensitive": sens})
                    return
            ch = getattr(key, "char", None)
            if ch and ch.isprintable():
                self._push({"kind": "char", "t": int(time.time() * 1000),
                            "ch": ch, "window": fg, "sensitive": sens})
        except Exception:
            pass  # 钩子里绝不抛

    def _on_release(self, key):
        try:
            from pynput import keyboard
            if isinstance(key, keyboard.Key):
                base = _MOD_NAME.get(key.name)
                if base:
                    self._mods.discard(base)
        except Exception:
            pass

    def _push(self, ev):
        with self._lock:
            if not self._recording:
                return
            if len(self._events) >= RECORD_MAX_EVENTS:
                self._overflow = True
                return
            self._events.append(ev)
            ev["_idx"] = len(self._events) - 1  # worker 直取槽位（同毫秒连点不串槽）
        if self._q is not None:
            self._q.put(ev)

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
                    slot["window"] = ""
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
        sens = pwd or is_sensitive_title(title)
        return {
            "locator": build_locator_chain(ctrl),
            "window": title,
            "rel": rel,
            "sensitive": bool(sens),
        }


# 模块级单例（dashboard/工具族共用；技能录制一次只允许一路）
_recorder = SkillRecorder()


# ── 回放 ────────────────────────────────────────────────────────────
def _find_window(auto, title, locator0=None):
    """按标题在根控件子级找顶层窗口；找不到再按定位链[0]的 cls/auto 兜底。
    UIA 枚举偶发瞬时失配（E2E 实锤：同标题 0.15s 内一中一失）——3×0.25s
    重试 + 去空格归一化兜底。"""
    t = _norm_title(title)
    for attempt in range(3):
        try:
            root = auto.GetRootControl()
            children = root.GetChildren()
            for w in children:
                try:
                    if t and _norm_title(w.Name) == t:
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
            title = step.get("window", "")
            if is_sensitive_title(title):
                _audit("play_abort_sensitive", name, "第 %d 步窗口「%s」" % (idx, title))
                return False, ("❌ 第 %d 步目标窗口命中敏感黑名单（%s），已中止。"
                               "已执行 %d/%d 步。" % (idx, title, executed, len(steps)))
            stype = step.get("type")
            delay = max(MIN_STEP_DELAY_MS, min(MAX_STEP_DELAY_MS,
                                               int(step.get("delay_ms", 0) or 0)))
            if delay:
                time.sleep(delay / 1000.0)
            window = _find_window(auto, title,
                                  (step.get("locator") or [None])[0]
                                  if step.get("locator") else None)
            if title and window is None:
                _audit("play_fail_window", name, "第 %d 步找不到窗口「%s」" % (idx, title))
                return False, ("❌ 第 %d 步找不到窗口「%s」（可能已关闭）。已执行 "
                               "%d/%d 步。" % (idx, title, executed, len(steps)))
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
