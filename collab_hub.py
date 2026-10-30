# -*- coding: utf-8 -*-
"""collab_hub · AI 多方协作总线服务（2026-10-30 队长"Multi-Agent UI"核心）。

职责（宿主 :5003 dashboard 进程，start_background_services 拉起 daemon 线程）：
- 监听 SYNC_DEEPSEEK.md（ZCode 战报）与 TASK_BUS.md（秘书回复/老板拍板）
  的增量变化，解析为角色消息 → ui_events.publish("collab_msg", ...) 实时
  推给控制台「协作」Tab（三色气泡），同时留内存历史（/api/collab/history
  回放，刷新不丢）。
- 秘书自动回话（可选，XIAOJU3_BUS_ENABLED=1 才联网）：SYNC 新战报 →
  DeepSeek 审查 → 回复写回 TASK_BUS「## [秘书回复]」节 → 轮询自然捕获
  → 推送前端（闭环：ZCode 写战报 → 面板出 🔧气泡 → 秘书回 → 🧠气泡）。
- 老板介入（HITL）：POST /api/collab/send（前端确认卡片/输入框）→
  write_boss() 写 TASK_BUS「## [老板拍板]」节 + publish 回显。

消息模型：{"role": "zcode|secretary|boss", "text": str, "ts": iso, "hitl": bool}
（text 含「@老板」→ hitl=True，前端渲染确认卡片）。

安全与成本（继承 ai_bus_daemon/ask_deepseek 三闸）：XIAOJU3_BUS_ENABLED=1
才联网；日帽 15 次；黑名单拒发；Key 只读不打印；留痕 ai_consult_log.md。
"""
import hashlib
import os
import re
import sys
import threading
import time
from datetime import datetime

# frozen/console=False 环境 stdout 可能是 GBK——emoji 打印即 UnicodeEncodeError
# （2026-10-30 桌面工作台启动实锤，错误落盘日志捕获）。统一重配 UTF-8+replace。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
# 路径解析（2026-10-30 frozen 路径陷阱修复）：PYZ 内 __file__ 指向
# _MEIPASS（_internal），按 __file__ 拼出的 _dev 路径不存在=监听永远空转
# （部署实锤：协作线程启动正常但 history 恒空）。frozen 下项目根=exe 所
# 在目录（_internal 的父目录）；源码运行=仓库根（_HERE 的上级）。
if getattr(sys, "frozen", False):
    _ROOT = os.path.dirname(sys.executable)
else:
    _ROOT = os.path.dirname(_HERE)
_TASK_BUS = os.path.join(_ROOT, "_dev", "TASK_BUS.md")
_SYNC = os.path.join(_ROOT, "_dev", "SYNC_DEEPSEEK.md")
_PROD_ENV = r"F:\XUNandxiaoju3\xiaoju3_data\.env"
_LOG = os.path.join(_ROOT, "_dev", "ai_consult_log.md")

POLL_SEC = 1.5
MAX_PER_DAY = 15
SYNC_TRUNC = 4000
REPLY_MAX = 1500
HISTORY_MAX = 200
SECRET_TAG = "## [秘书回复]"
BOSS_TAG = "## [老板拍板]"

_SYS_PROMPT = (
    "你是小橘3号项目的秘书（技术架构与审查方）。包工头（ZCode）刚交付新"
    "战报。审查并给下一步技术指令或结论：最多 5 条要点，每条一行以「- 」"
    "开头，简体中文；需要包工头或队长确认时在对应行尾加「@老板 请确认…」。"
    "不确定明确说不确定，禁止编造。今天是 {today}。")

_BLACKLIST = (
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"BEGIN (?:RSA )?PRIVATE KEY"),
    re.compile(r"(?:ONEBOT_TOKEN|XIAOJU3_OWNER_QQ|API_KEY|PASSWORD|SECRET)"
               r"\s*=", re.I),
)


def _now_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_env():
    env = dict(os.environ)
    try:
        with open(_PROD_ENV, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip())
    except Exception:
        pass
    return env


def _blacklisted(text):
    return any(rx.search(text) for rx in _BLACKLIST)


def _log(q, a, tk="?"):
    try:
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n## {datetime.now():%Y-%m-%d %H:%M:%S} [collab]\n"
                    f"**问**：{q[:600]}\n\n**答**：{a[:800]}\n（tokens={tk}）\n")
    except Exception:
        pass


def _recent_boss_lines(task_path, window_h=24, max_n=5, max_chars=300):
    """24h 窗口内的老板拍板（秘书回执②：单条改窗口多条——时间倒序、
    最多 5 条、多条时附冲突提示）。无拍板/读失败返回空串。"""
    try:
        with open(task_path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        blocks = re.split(r"## \[老板拍板\]", text)
        now = datetime.now()
        picked = []
        for blk in reversed(blocks[1:]):
            head, _, body = blk.partition("\n")
            body = body.split("---")[0].strip()
            if not body:
                continue
            m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", head)
            if m:
                try:
                    ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                    if (now - ts).total_seconds() > window_h * 3600:
                        continue   # 超 24h 窗口：旧拍板不注入（时效门）
                except ValueError:
                    pass
            picked.append(body[:max_chars])
            if len(picked) >= max_n:
                break
        if not picked:
            return ""
        if len(picked) == 1:
            return picked[0]
        return ("\n【注意：24h 内有多条拍板，语义冲突以最新为准】\n"
                + "\n".join(f"{i+1}. {b}" for i, b in enumerate(picked)))
    except Exception:
        return ""


def _boss_context(task_path):
    """老板拍板上下文段（有拍板才拼——秘书必须知道老板刚说了什么）。"""
    boss = _recent_boss_lines(task_path)
    if not boss:
        return ""
    return "\n【老板最新拍板（必须知晓并遵守）】\n" + boss


# ==================== 协议行解析（秘书回执①：边界收严版） ====================
# 只认「回复开头 3 行内」或「尾部独立段（末 3 行）」的整行协议；代码围栏内
# 与正文中段一律不解析；列表前缀（- @options:）/加粗（**@options:**）不认。
# 选项单项 ≤30 字符截断；@summary 摘要 ≤200。

_PROTO_EDGE_LINES = 3
_PROTO_OPT_MAX = 30
_OPTIONS_LINE = re.compile(r"^@options[:：]\s*(.+)$")
_SUMMARY_LINE = re.compile(r"^@summary[:：]\s*(.+)$")
_FENCE = re.compile(r"```.*?```", re.S)


def parse_protocol_lines(text):
    """收严版协议行解析（v2，DeepSeek 审查回执采纳 5 项修复）。
    返回 (clean_text, options|None, summary|None, hitl)。

    边界规则（秘书回执①）：
    - 代码围栏（```…```）先置**随机不可预测占位**（uuid——v1 的
      \\x00FENCE{i} 可被正文伪造致内容错乱），解析后还原；
    - 协议行只认「开头 3 行内」或「末尾 3 行内」的**整行锚定**命中
      （v2 改显式 idx 判定——v1 的 lo/hi 区间在 n≤6 短文本下恒空=全漏判）；
    - 首尾空行先裁剪再算窗口（尾部空行把真实协议行挤出窗口的漏判堵死）；
    - 整行锚定=行首 strip 后必须以 @options:/@summary: 开头——列表前缀
      （- @options:）与加粗（**@options:**）天然不认；
    - 命中的协议行从正文剥离（多协议行**取首个**，语义明确）；正文其余
      部分原样保留（v1 的全局连续空行压缩已撤销——违反原样保留）；
    - hitl 判定基于围栏占位后的文本（围栏内 @老板 不触发）。"""
    import uuid
    fences = []
    tokens = []

    def _stash(m):
        fences.append(m.group(0))
        tok = f"\x00{uuid.uuid4().hex}\x00"
        tokens.append(tok)
        return tok

    work = _FENCE.sub(_stash, text)
    hitl = "@老板" in work   # 围栏免疫：占位后判定（v1 在原文判定=围栏内 @老板 误触发）
    lines = work.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    n = len(lines)
    options = None
    summary = None

    def _in_edge(idx):
        return idx < _PROTO_EDGE_LINES or idx >= n - _PROTO_EDGE_LINES

    for idx, line in enumerate(lines):
        if _in_edge(idx):
            stripped = line.strip()
            m = _OPTIONS_LINE.match(stripped)
            if m:
                if options is None:   # 取首个（多协议行语义明确）
                    opts = [x.strip()[:_PROTO_OPT_MAX]
                            for x in m.group(1).split("|") if x.strip()][:6]
                    if opts:
                        options = opts
                        lines[idx] = ""
                continue
            m = _SUMMARY_LINE.match(stripped)
            if m:
                if summary is None:
                    summary = m.group(1).strip()[:200]
                    lines[idx] = ""
    work = "\n".join(lines)
    for tok, f in zip(tokens, fences):
        work = work.replace(tok, f)
    clean = work.strip()
    return clean, options, summary, hitl


class CollabHub:
    """协作总线：文件监听 → 角色消息流（publish+history）。"""

    def __init__(self, sync_path=None, task_path=None, env=None):
        self.env = env or _load_env()
        # 路径 env 覆盖（2026-10-30 部署实锤：生产 _dev 无总线文件——
        # hub 进程与 ZCode 同机时直接监听仓库 _dev 绝对路径，零拷贝实时；
        # 跨机部署再议远端方案）。缺省=项目根 _dev。
        self.sync_path = (sync_path
                          or self.env.get("XIAOJU3_COLLAB_SYNC") or _SYNC)
        self.task_path = (task_path
                          or self.env.get("XIAOJU3_COLLAB_TASK") or _TASK_BUS)
        self.history = []            # [{role,text,ts,hitl}]
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        # 指纹状态：文件 hash + 已解析的节标题集合（防重放）
        self._sync_hash = None
        self._task_seen_secret = set()   # 已推送的秘书节签名
        self._task_seen_boss = set()
        self._day = datetime.now().strftime("%Y-%m-%d")
        self._calls = 0

    # ---------- 消息入流 ----------
    def _emit(self, role, text, thinking=None, round_tag=None):
        if not text or not text.strip():
            return False
        text = text.strip()[:4000]
        options = None
        summary = None
        hitl = False
        text, options, summary, hitl = parse_protocol_lines(text)
        msg = {"role": role, "text": text,
               "ts": _now_iso(), "hitl": hitl}
        if options and msg["hitl"]:
            msg["options"] = options
        if summary and msg["hitl"]:
            msg["summary"] = summary
        if thinking:
            msg["thinking"] = thinking   # 工作思维链上屏（2026-10-30 队长）
        if round_tag:
            msg["round"] = round_tag
        with self._lock:
            self.history.append(msg)
            del self.history[:-HISTORY_MAX]
        try:
            import ui_events
            ui_events.publish("collab_msg", **msg)
        except Exception:
            pass   # 推送失败不致命（history 兜底回放）
        return True

    def emit_boss(self, text):
        """老板发言/拍板（前端 HITL 卡片或输入框）：写 TASK_BUS + 推流。"""
        text = str(text or "").strip()
        if not text:
            return {"code": 400, "error": "空消息"}
        with open(self.task_path, "a", encoding="utf-8") as f:
            f.write(f"\n{BOSS_TAG} {_now_iso()}\n\n{text}\n\n---\n")
        self._emit("boss", text)
        return {"code": 200, "data": {"ok": True}}

    def snapshot(self, limit=100):
        with self._lock:
            return list(self.history[-limit:])

    # ---------- 文件监听 ----------
    @staticmethod
    def _read(path):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            return ""

    def poll_once(self):
        """单轮监听：SYNC 增量→zcode 消息+秘书回话；TASK_BUS 新节→
        secretary/boss 消息。返回本轮产生的新消息数。"""
        n = 0
        sync_text = self._read(self.sync_path)
        h = hashlib.md5(sync_text.encode("utf-8", "replace")).hexdigest()
        if h != self._sync_hash:
            first = self._sync_hash is None
            self._sync_hash = h
            if not first and sync_text.strip():
                # 增量=尾部一段（文件增长型；重写=取尾部窗口）
                tail = sync_text[-SYNC_TRUNC:]
                # 去掉文件头导航行（首次全量只取尾窗，避免整档重播）
                if self._emit("zcode", tail):
                    n += 1
                n += self._auto_secretary(tail)

        task_text = self._read(self.task_path)
        for m in re.finditer(
                re.escape(SECRET_TAG) + r"[^\n]*\n(.*?)(?=\n## |\Z)",
                task_text, re.S):
            sig = hashlib.md5(m.group(0).encode("utf-8")).hexdigest()
            if sig not in self._task_seen_secret:
                self._task_seen_secret.add(sig)
                if self._emit("secretary", m.group(1).strip()):
                    n += 1
        for m in re.finditer(
                re.escape(BOSS_TAG) + r"[^\n]*\n(.*?)(?=\n## |\Z)",
                task_text, re.S):
            sig = hashlib.md5(m.group(0).encode("utf-8")).hexdigest()
            if sig not in self._task_seen_boss:
                self._task_seen_boss.add(sig)
                if self._emit("boss", m.group(1).strip()):
                    n += 1
        return n

    # ---------- 秘书自动回话（联网可关） ----------
    def _auto_secretary(self, report_tail):
        """战报增量 → DeepSeek 审查 → 写 TASK_BUS 秘书节（轮询自然捕获
        推流）。开关关/黑名单/日帽/失败 → 静默跳过。"""
        if self.env.get("XIAOJU3_BUS_ENABLED") != "1":
            return 0
        if not report_tail or len(report_tail) < 40:
            return 0
        if _blacklisted(report_tail):
            print("🚫 [collab] 战报含敏感特征，拒绝发送")
            return 0
        today = datetime.now().strftime("%Y-%m-%d")
        if self._day != today:
            self._day, self._calls = today, 0
        if self._calls >= MAX_PER_DAY:
            return 0
        try:
            import urllib.request
            key = self.env.get("DEEPSEEK_API_KEY") or self.env.get(
                "CLOUD_KEY") or ""
            url = self.env.get("CLOUD_URL") or \
                "https://api.deepseek.com/chat/completions"
            model = self.env.get("CLOUD_MODEL") or "deepseek-chat"
            if not key:
                return 0
            payload = {
                "model": model,
                "messages": [
                    {"role": "system",
                     "content": _SYS_PROMPT.format(today=today)},
                    {"role": "user",
                     "content": "【包工头战报增量】\n"
                                + report_tail[:SYNC_TRUNC]
                                + _boss_context(self.task_path)}],
                "stream": False, "temperature": 0.3, "max_tokens": 600}
            req = urllib.request.Request(
                url, data=json_dumps(payload),
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {key}"})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = json_loads(r.read().decode())
            content = (body.get("choices") or [{}])[0].get(
                "message", {}).get("content", "").strip()
            if not content:
                return 0
            self._calls += 1
            tk = body.get("usage", {}).get("total_tokens", "?")
            _log(report_tail, content, tk)
            with open(self.task_path, "a", encoding="utf-8") as f:
                f.write(f"\n{SECRET_TAG} {_now_iso()}\n\n"
                        f"{content[:REPLY_MAX]}\n\n---\n")
            return 1   # 写文件后下轮 poll 自然捕获推流
        except Exception as e:
            print(f"⚠️ [collab] 秘书回话失败（静默）: {e}")
            return 0

    # ---------- 线程 ----------
    def _loop(self):
        # 启动首次 poll：把两文件当前尾窗入历史（不打扰：静默入流不推？
        # ——推，让打开面板的队长立刻看到最近上下文。首次 SYNC 尾窗视为
        # 最新战报回放。）
        self.poll_once()
        while not self._stop.wait(POLL_SEC):
            try:
                self.poll_once()
            except Exception as e:
                print(f"⚠️ [collab] 轮询异常（已兜住）: {e}")

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="collab-hub")
        self._thread.start()
        print("🚌 [collab] 协作总线已启动（SYNC/TASK_BUS 监听中，"
              f"联网秘书回话={'开' if self.env.get('XIAOJU3_BUS_ENABLED') == '1' else '关'}）")

    def stop(self):
        self._stop.set()


# 兼容无 json 模块顶级 import 的极简封装（测试桩可覆盖）
def json_dumps(obj):
    import json
    return json.dumps(obj).encode("utf-8")


def json_loads(text):
    import json
    return json.loads(text)


_HUB = None


def get_hub():
    """进程级单例（dashboard 与端点共用）。"""
    global _HUB
    if _HUB is None:
        _HUB = CollabHub()
    return _HUB


def start_background():
    get_hub().start()
