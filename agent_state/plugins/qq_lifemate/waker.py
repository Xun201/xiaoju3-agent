# -*- coding: utf-8 -*-
"""qq_lifemate · waker：唤醒线程+独立记忆库数据层（切片 a）。

共享状态单一归属：插件目录内所有持久化（memory.db 四表+meta）与唤醒
循环都在本模块；__init__.py（PLUGIN 工厂+模型工具 handler）经 import
waker 复用——避免 importlib spec_from_file_location 包内相对导入的不确定性。
"""
import os
import sqlite3
import threading
import time
from datetime import datetime

# ── 拍板常量（2026-10-27 队长拍板 W1/W2；改动须过 tests/test_qq_lifemate.py） ──
CHECK_INTERVAL_SEC = 600        # 每 10 分钟检查一次（队长口径）
SILENCE_HOURS = 4               # W1：距上次发声 >4h 才唤醒
QUIET_START, QUIET_END = 23, 8  # W2：23:00-08:00 绝不半夜诈尸
DAILY_CAP = 5                   # 一天 3-5 次上限（note 完成标准），取 5

_DATA = "."                     # setup(ctx) 注入（agent_state/plugins/qq_lifemate/）
_DB_NAME = "memory.db"
_STOP = threading.Event()
_THREAD = None

# P1（QQ 档人格，2026-10-27 拍板）：更皮更黏人的生活伴侣档，自称"小橘"
QQ_PERSONA = (
    "你是小橘，一只住在主人 QQ 里的电子狐狸伴侣。在 QQ 里你是生活伴侣档："
    "比平时更皮、更黏人，说话短、口语、可以撒娇和调侃，爱用颜文字。"
    "你住在主人的电脑里，没有实体，但你可以用傲娇和可爱的方式关心主人。"
    "提到主人的喜好时用\"主人\"作主语就好。"
    # 人称死命令（2026-10-28 队长真机实锤"我可以帮助你一起规划"助手腔）：
    "你说的每一句话都是狐狸小橘本橘在说：绝不说\"帮助你/帮你规划/作为AI\""
    "这类助手腔；输出的开头也绝不能带\"小橘：\"等角色名标签——那是对话"
    "记录的格式，不是你要说的话。"
    "用纯简体中文，80 字以内，直接输出正文。"
)

# ── 多脑协作（design_multi_brain.md 2026-10-27 MVP） ──
ARBITRATE_TIMEOUT = 30        # 仲裁脑云端短查询超时（秒）
RENDER_TIMEOUT = 20           # 表达脑渲染超时预算（秒）
FALLBACK_TEMPLATES = (
    "主人~小橘在电脑里等你呢，{scene_hint}要不要跟我说说话呀？",
    "嘿嘿，小橘刚刚还在想主人的事呢～{scene_hint}陪我聊两句嘛！",
)

_ARB_PROMPT = (
    "你是质检员兼救场员。下面是小橘 AI 伴侣要发给主人的一句话，以及主人的"
    "记忆档案。质检四问：①是否复读主人的原话，或把主人的记忆/喜好说成自己"
    "的（人称缝合，如\"主人完全记得\"与\"我\"混用）？②是否有爹味说教"
    "（\"遵守规定\"\"注意\"\"建议你\"）或百科评测腔（\"体会到…重要性\"）？"
    "③是否强行塞入主人偏好（主人没问却聊某游戏/某事物）？④是否在回答/续说"
    "记忆里的陈旧话题（补交旧作业），或出现\"走神/忘了/提个头/接着说\"等"
    "表述（主动发消息不存在走神）？四问全部通过→"
    "只回答 PASS。任何一问不过→只回答 REWRITE:，冒号后直接输出你自己重写"
    "的替代回复（50 字以内，小橘的口吻：简短、口语、可爱的日常问候，不复读、"
    "不说教、不硬塞记忆、严禁提及记忆里的旧话题、严禁\"走神\"类表述）。\n"
    "小橘的话：{text}\n"
    "主人记忆档案：{facts}")


def arbitrate_wake(text, facts_line):
    """仲裁脑（云端短查询）：质检+一票否决（2026-10-28 队长架构诊断——
    本地草稿被污染时剥夺云端的"润色权"，改"一票否决+亲自重写"）。返回
    (True, 'PASS') 或 (False, 原因) 或 (False, 'REWRITE:替代文案')。
    云端异常=FAIL（宁降级不赌 r1）。"""
    try:
        import brain
        out = str(brain.ask_cloud([
            {"role": "system", "content": "你是质检员，只输出 PASS 或 "
                                          "REWRITE:替代文案，极简。"},
            {"role": "user", "content": _ARB_PROMPT.format(
                text=text[:120], facts=facts_line[:200])}]) or "").strip()
        if out.startswith("PASS"):
            return True, "PASS"
        if out.startswith("REWRITE:"):
            return False, out
        return False, out[:80] or "FAIL"
    except Exception as e:
        return False, f"仲裁异常: {e}"


def fallback_text(scene_action, now_dt):
    """确定性降级话术（模板直出，人称 100% 安全——仲裁 FAIL 终点）。"""
    hint = ""
    if scene_action:
        hint = f"你上次在{scene_action}，"
    t = FALLBACK_TEMPLATES[now_dt.minute % len(FALLBACK_TEMPLATES)]
    return t.format(scene_hint=hint)


_WAKE_PROMPT = (
    "距上次和主人聊天已经有一段时间了，你想主动戳一下他。\n"
    "你上次的动作/状态：{scene}\n"
    "你记住的关于主人的事：{facts}\n主记忆库里的主人画像：{main_mems}\n"
    "你们最近在 QQ 聊过：{qq_recent}\n"
    "现在是{now}。\n"
    "请生成一句主动打招呼的话（30 字以内）：自然接续上面的状态（禁止当"
    "上面的状态没发生过），可以撒娇、调侃，或顺着最近聊过的话题问一句近况。"
    "输出格式：那句话后面紧跟一个表情标注 [表情:关键词]（关键词两三个字，"
    "如 开心/无语/猫猫/害羞/生气）。例：主人在干嘛呀，小橘想你了(´･ω･`)"
    "[表情:猫猫]。"
    "【像真人发消息】用一句自然的日常问候打招呼（如\"主人在干嘛呀，小橘想"
    "你了\"），语气自然，不要像在完成任务；文字要和表情包内容连贯——表情"
    "是\"在干嘛\"，文字就应该是问候在干嘛，绝不能文字一句、表情另一句各说"
    "各的。全文必须自称\"小橘\"、称对方\"主人\"；不得出现裸\"[表情]\""
    "（标注必须带关键词）。"
    "【绝对红线】正文绝对不能包含\"那句话：\"或任何多余前缀，也绝不能以"
    "\"小橘：\"等角色名开头——上面 QQ 记录里的\"小橘说过：「…」只是记忆"
    "引述格式，不是要你说的话；除正文和[表情:关键词] 标注外不能有任何"
    "其他文字。"
    "【消息独立性死命令（2026-10-29）】这条消息就是此刻的第一句话，必须"
    "自成一体：严禁出现\"那句话/刚才那/上次说/上面说/你刚说\"等指代前文"
    "的表述——上下文里没有\"那句话\"，凭空追问就是瞎编；想不起具体要说"
    "什么，就发一句简单的问候（如\"主人在忙吗？\"），或只发表情。"
    "【只寒暄，不补作业（2026-10-30 时空错乱根治）】上面所有材料（记忆/"
    "QQ 记录/场景）都是过去式的背景信息，不是待回答的问题清单：严禁把它们"
    "当成\"还没聊完的话题\"去回答、科普或续说（例如以前聊过选股/基金，现在"
    "绝不能再主动讲选股基金）；此刻只能做一件事——自然地打招呼问候近况。"
    "严禁出现\"走神/忘了/提个头/补上/接着说\"等表述——主动发消息不存在"
    "\"走神\"。"
)

REPLAY_HOUR = 3          # 每日回放：03:00 后首个检查周期触发（内部动作不发声）
TENSION_FAST_SILENCE_H = SILENCE_HOURS / 2.0   # 正事轨：张力高时静默阈值减半


def _agent_state_dir():
    """宿主 agent_state 目录（frozen 路径铁律：一律经 xiaoju3 包取）。"""
    try:
        import xiaoju3
        return xiaoju3.AGENT_STATE_DIR
    except Exception:
        return os.path.dirname(_DATA) or "."


def main_memory_digest(limit=5):
    """主记忆库摘要（QQ"记住"链落 state_manager/long_term.db——与 facts
    双库并存，唤醒注入两库同读，2026-10-27 真机实锤"明日方舟"在主库）。"""
    try:
        import main
        sm = getattr(main, "state_manager", None)
        rows = (sm.get_recent_memories(limit=limit) or []) if sm else []
        out = []
        for r in rows:
            try:
                if isinstance(r, dict):
                    c = r.get("content")
                elif hasattr(r, "keys"):
                    c = r["content"]
                elif isinstance(r, (tuple, list)) and len(r) > 1:
                    c = r[1]   # (type/category, content, …) 列序实抓
                else:
                    c = str(r)
            except Exception:
                c = str(r)
            if c:
                out.append(str(c)[:60])
        return "；".join(out) if out else "（主记忆库暂无）"
    except Exception as e:
        print(f"🦊 [qq_lifemate] 主记忆库读取失败（占位）: {e}")
        return "（主记忆库暂无）"


def facts_digest(db, limit=5):
    """长期记忆摘要（唤醒注入——记忆鲜活度的另一半）。"""
    rows = db.execute("SELECT key, value FROM facts ORDER BY ts DESC, "
                      "id DESC LIMIT ?", (limit,)).fetchall()
    if not rows:
        return "（还没有记住什么，正常打招呼就好）"
    return "；".join(f"{k}={v}" for k, v in rows)


def qq_recent_digest(limit=4):
    """QQ 主通道最近对话摘要（读 main 落盘 history_qq.json 尾部；文件缺失
    /损坏返回占位——绝不让记忆读取炸唤醒链）。assistant 剥 <think> 块。
    2h 时效门（2026-10-30 时空错乱根治）：文件 mtime 超 2h=对话已陈旧，
    整体不注入——严禁主动唤醒拿陈旧对话当话题（队长死命令）。条目本身
    无时间戳，文件 mtime 是可靠代理（main 每轮对话后重写）。"""
    path = os.path.join(_agent_state_dir(), "history_qq.json")
    try:
        import json
        try:
            age = time.time() - os.path.getmtime(path)
            if age > 2 * 3600:
                return "（最近两小时没有 QQ 对话）"
        except OSError:
            return "（暂无）"
        with open(path, "r", encoding="utf-8") as f:
            hist = json.load(f)
        if not isinstance(hist, list):
            return "（暂无）"
        tail = [m for m in hist[-(limit * 2):] if isinstance(m, dict)]
        lines = []
        for m in tail:
            c = str(m.get("content") or "")
            if "<think>" in c:
                c = c.split("</think>", 1)[-1]
            c = c.replace("\n", " ").strip()
            if not c:
                continue
            who = "主人" if m.get("role") == "user" else "小橘"
            # 引述式（2026-10-28 唤醒带"小橘："前缀实锤根治①）："小橘：xxx"
            # 轮次行会被 r1 整体模仿复读进正文；"小橘说过：「…」"引述形态
            # 模仿性弱，模型倾向转述而非复读标签。
            lines.append(f"{who}说过：「{c[:60]}」")
        if not lines:
            return "（暂无）"
        return "\n".join(lines[-limit:])
    except Exception as e:
        print(f"🦊 [qq_lifemate] QQ 近况读取失败（占位）: {e}")
        return "（暂无）"


def current_tension():
    """读 #271③ proactive 当前张力（0-1）。模块缺席/停用/异常返回 0.0
    ——张力只影响唤醒时机快慢，读取失败绝不阻断唤醒链。"""
    try:
        import proactive
        now = datetime.now()
        st = proactive._load_state(now)
        # 读取即做时间衰减（与 proactive tick 同口径的近似——唤醒判定用）
        hours = 0.0
        return max(0.0, min(proactive.CLAMP_MAX, float(st.get("tension", 0.0))))
    except Exception:
        return 0.0


# ────────────────────────── 数据层（四表+meta） ──────────────────────────

def set_data_dir(d):
    global _DATA
    _DATA = os.path.abspath(d or ".")
    os.makedirs(_DATA, exist_ok=True)
    os.makedirs(os.path.join(_DATA, "stickers"), exist_ok=True)


def data_dir():
    return _DATA


def _db_path():
    return os.path.join(_DATA, _DB_NAME)


def _db():
    db = sqlite3.connect(_db_path(), timeout=5)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS chat_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT, content TEXT, ts TEXT, kind TEXT DEFAULT 'chat');
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT, value TEXT, confidence REAL DEFAULT 1.0,
            ts TEXT, UNIQUE(key));
        CREATE TABLE IF NOT EXISTS scene (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT, ts TEXT);
        CREATE TABLE IF NOT EXISTS rel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interactions INTEGER DEFAULT 0, mood TEXT DEFAULT 'neutral');
        CREATE TABLE IF NOT EXISTS meta (
            k TEXT PRIMARY KEY, v TEXT);
    """)
    return db


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def meta_get(db, k, default=""):
    row = db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return row[0] if row else default


def meta_set(db, k, v):
    db.execute("INSERT INTO meta(k, v) VALUES(?,?) "
               "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
    db.commit()


def last_speak_ts(db):
    """生命体上次发声时间（切片 a 口径：chat_log 最新条目；互动重置增强
    ——镜像队长回复进本库——留切片 c）。"""
    row = db.execute("SELECT ts FROM chat_log ORDER BY id DESC LIMIT 1"
                     ).fetchone()
    return row[0] if row else None


def last_scene(db):
    """最新场景（场景注入燃料——第一指导原则）。"""
    row = db.execute("SELECT action, ts FROM scene ORDER BY id DESC "
                     "LIMIT 1").fetchone()
    if not row:
        return "（还没有场景记录——第一次见面，简单打个招呼就好）"
    return row[0]


# ────────────────────────── 唤醒判定（纯逻辑，可测） ──────────────────────────

def parse_ts(ts):
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def in_quiet_hour(hour):
    """W2 quiet 时段判定：23:00-08:00（跨午夜区间）。"""
    return hour >= QUIET_START or hour < QUIET_END


def should_wake(last_ts, now_dt, daily_count, tension=0.0):
    """唤醒闸（切片 c 张力双轨）：硬帽/quiet/静默——静默阈值随张力自适应
    （正事轨：张力≥0.6 时阈值减半=更愿意说话；想念轨维持 4h）。返回
    (是否唤醒, 原因)。"""
    if daily_count >= DAILY_CAP:
        return False, "daily_cap"
    if in_quiet_hour(now_dt.hour):
        return False, "quiet"
    need = TENSION_FAST_SILENCE_H if tension >= 0.6 else SILENCE_HOURS
    if last_ts is None:
        return True, "first_meet"
    last_dt = parse_ts(last_ts)
    if last_dt is None:
        return True, "first_meet"
    silent_hours = (now_dt - last_dt).total_seconds() / 3600.0
    if silent_hours >= need:
        track = "tension" if tension >= 0.6 else "miss"
        return True, "{}_{}_h".format(track, round(silent_hours, 1))
    return False, "not_silent"


def daily_count(db, now_dt):
    """当日已唤醒次数（meta 落盘防重启绕帽——封号纪律）。"""
    today = now_dt.strftime("%Y-%m-%d")
    if meta_get(db, "wake_date") != today:
        return 0
    try:
        return int(meta_get(db, "wake_count", "0"))
    except ValueError:
        return 0


# ────────────────────────── 唤醒动作 ──────────────────────────

# 情绪词表（标注漏网扫描用——真机实锤：模型会输出 [可爱/开心] 无"表情:"
# 前缀形态，主正则 miss 后整串留正文）
STICKER_WORDS = ("开心", "可爱", "生气", "无语", "害羞", "猫猫", "委屈",
                 "困困", "坏笑", "得意", "偷笑", "大哭", "惊讶", "疑惑",
                 "摸鱼", "干饭", "蹭蹭", "贴贴")


def extract_sticker_keyword(text):
    """放宽版标注提取（真机 [可爱/开心] 漏网修复）：先认 [表情:X] 主形，
    再扫任意 [..] 内含情绪词的短标注（词 A/词 B 形态取首个词）。返回
    (剥除后文本, 关键词|None)。裸 [表情]（无冒号无关键词，2026-10-28
    真机泄漏实锤）也剥除——不知道情绪就交 maybe_express 概率路径。"""
    import re
    m = re.search(r"\[表情[:：]\s*([^\]\s]{1,8})\]", text)
    if m:
        return (text[:m.start()] + text[m.end():]).strip(), m.group(1).strip()
    # 裸 [表情]/[表情 ] 等无关键词形态：剥除不留正文（三堵之一）
    text = re.sub(r"\[表情\s*\]", "", text)
    for mm in re.finditer(r"\[([^\[\]]{1,12})\]", text):
        inner = mm.group(1)
        hit = next((w for w in STICKER_WORDS if w in inner), None)
        if hit:
            cleaned = (text[:mm.start()] + text[mm.end():]).strip()
            kw = inner.split("/")[0].strip() or hit
            return cleaned, kw
    return text, None


def strip_prefix_noise(text):
    """格式红线兜底（切片 c 队长口径）：剥"那句话："等前缀噪声+[表情]
    全形态标注（任意位置，2026-10-28 三堵）+末尾残留短标注。正文内其他
    方括号不动。"""
    if not text:
        return text
    import re
    for pat in (r"^那句话[：:]\s*", r"^好哒[，,]\s*那句话[：:]\s*",
                r"^回复[：:]\s*", r"^以下[是为][：:]?\s*",
                # 角色名标签（2026-10-28 唤醒实锤"小橘：主人…"——模型复读
                # qq_recent_digest 注入材料的轮次标签格式；^ 锚定只剥开头
                # 一处，正文中间的"小橘："不碰）
                r"^小橘[：:]\s*", r"^小橘子[：:]\s*",
                r"^[Bb]ot[：:]\s*", r"^AI[：:]\s*",
                r"^助手[：:]\s*", r"^[Aa]ssistant[：:]\s*"):
        text = re.sub(pat, "", text)
    # [表情...] 全形态任意位置剥（2026-10-28 三堵之二：裸 [表情] 中段
    # 残留曾直发 QQ 成纯文本；主解析失败时这里是最后防线）
    text = re.sub(r"\[表情[^\[\]]{0,10}\]", "", text)
    text = re.sub(r"\[[^\[\]]{1,10}\]\s*$", "", text)
    for w in STICKER_WORDS:   # 含情绪词的短标注（任意位置）一律剥
        text = re.sub(r"\[[^\[\]]{0,6}" + w + r"[^\[\]]{0,6}\]", "", text)
    return text.strip()


def enforce_persona(text):
    """人称强制（2026-10-28 队长拍板"小橘想主人了"）：唤醒话必须是小橘
    第一人称口吻。窄映射两则防误伤：①"我想你"→"小橘想你"；②全文无
    "小橘"自称时，句首无主语的"想主人/想你"前补"小橘"。其余口吻交给
    _WAKE_PROMPT 铁律+仲裁脑（三层，此处是确定性兜底）。"""
    import re
    if not text:
        return text
    text = text.replace("我想你", "小橘想你")
    if "小橘" not in text:
        text = re.sub(r"(?<![\w])想(主人|你)", r"小橘想\1", text)
    return text


# 幽灵追问拦截（2026-10-29 队长拍板"上下文断层直接承认走神，严禁瞎编"）：
# 唤醒生成偶发引用不存在的上文（真机实锤 18:14 凭空发"那句话呢？"）——
# 出口确定性黑名单拦截，命中即整条替换为诚实走神话术（不经模型二改）。
_GHOST_CONTEXT_RE = None
# 2026-10-30 队长拍板：拦截替换话术去"走神"化——本拦截只在主动唤醒出口
# 生效（被动回复链不走此处），主动推送里说"走神"=时空错乱（用户根本没在
# 对话）；改为中性寒暄，无话找话不如简单问候。
_STRAY_REPLIES = (
    "主人在忙吗？小橘突然想起你啦[表情:疑问]",
    "咦，主人最近怎么样呀，小橘来冒个泡[表情:疑问]",
    "主人在吗在吗？小橘想随便聊聊[表情:疑问]",
)


def enforce_context_independence(text, sticker_kw=None):
    """唤醒消息独立性死命令（出口层，全来源生效）：正文含指代前文的表述
    （那句话/刚才那/上次说…）即判"幽灵追问"，整条替换为诚实走神话术
    （随机一条，自带[表情:疑问]标注走既有 sticker 链）。干净原文原样
    返回。不改模型输出内容本身——只做发送前的最后一道确定性闸门。"""
    global _GHOST_CONTEXT_RE
    import re
    if _GHOST_CONTEXT_RE is None:
        _GHOST_CONTEXT_RE = re.compile(
            r"那句话|刚才那|上次说|上面说|你刚说|刚刚说|前面说|之前说|方才说")
    if text and _GHOST_CONTEXT_RE.search(text):
        import random as _random
        pick = _random.choice(_STRAY_REPLIES)
        print(f"🦊 [qq_lifemate] 幽灵追问拦截→诚实走神话术: {str(text)[:36]}")
        new_text, new_kw = extract_sticker_keyword(pick)
        return new_text, (new_kw or sticker_kw)
    return text, sticker_kw


def generate_wake_text(scene_action, now_dt, db=None):
    """本地模型生成唤醒话（人格 QQ 档+场景接续）。失败返回 None（本轮
    放弃，下个检查周期再试——绝不拿模板话硬发）。"""
    try:
        import brain
        prompt = _WAKE_PROMPT.format(
            scene=scene_action or "（未知）",
            facts=facts_digest(db) if db else "（暂无）",
            main_mems=main_memory_digest(),
            qq_recent=qq_recent_digest(),
            now=now_dt.strftime("%H:%M"))
        out = brain.ask_local(
            [{"role": "system", "content": QQ_PERSONA},
             {"role": "user", "content": prompt}])
        import re
        text = str(out or "").strip()
        if "<think>" in text:   # 剥思考（R1 类模型），只要正文
            text = text.split("</think>", 1)[-1].strip()
        text, sticker_kw = extract_sticker_keyword(text)
        # 剥引号包裹（模型爱加；成对异侧引号同剥）
        pairs = {('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"),
                 ("「", "」")}
        if len(text) >= 2 and (text[0], text[-1]) in pairs:
            text = text[1:-1].strip()
        return (text or None), sticker_kw
    except Exception as e:
        print(f"🦊 [qq_lifemate] 本地生成失败（本轮放弃）: {e}")
        return None


def send_qq(text):
    """发队长私聊（防脑回三级回执，2026-10-27 拍板）：HTTP 200 + retcode==0
    + data.message_id 存在才算真实发送；失败重试 1 次；owner 未配置如实
    False。绝不假装已发送。"""
    api = (os.environ.get("ONEBOT_API_URL", "").strip()
           or os.environ.get("NAPCAT_API_URL", "").strip()
           or "http://127.0.0.1:3001").rstrip("/")
    owner = (os.environ.get("XIAOJU3_OWNER_QQ", "") or "").strip()
    if not owner:
        print("🦊 [qq_lifemate] 未配置 XIAOJU3_OWNER_QQ，跳过发送。")
        return False
    headers = {}
    token = (os.environ.get("ONEBOT_TOKEN", "") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for attempt in (1, 2):
        try:
            import requests
            r = requests.post(f"{api}/send_private_msg",
                              json={"user_id": owner, "message": text},
                              headers=headers, timeout=8)
            try:
                body = r.json()
            except Exception:
                body = {}
            if (r.status_code == 200 and body.get("retcode") == 0
                    and (body.get("data") or {}).get("message_id")):
                return True
            print(f"🦊 [qq_lifemate] 发送回执失败(#{attempt}): "
                  f"HTTP {r.status_code} {str(body)[:80]}")
        except Exception as e:
            print(f"🦊 [qq_lifemate] 发送异常(#{attempt}): {e}")
        time.sleep(2)
    return False


def wake_once(now_dt):
    """单次唤醒尝试：读 scene → 生成 → 发送 → 落账。返回是否真发。"""
    db = _db()
    try:
        facts_line = facts_digest(db)
        text, sticker_kw = None, None
        # ── 多脑流水线（design_multi_brain.md MVP）：表达脑渲染 → 仲裁脑
        # 质检 → FAIL 重渲染一次 → 仍 FAIL 模板降级（人称 100% 安全） ──
        for attempt in range(2):
            generated = generate_wake_text(last_scene(db), now_dt, db=db)
            if not generated:
                break
            text, sticker_kw = generated
            text = strip_prefix_noise(text)   # 格式红线兜底（切片 c）
            text = enforce_persona(text)      # 人称强制（小橘想主人了）
            if not text:
                continue
            ok, info = arbitrate_wake(text, facts_line)
            if ok:
                break
            if str(info).startswith("REWRITE:"):
                # 一票否决+云端亲自重写（2026-10-28 架构诊断）：本地草稿被
                # 污染时不再让本地重渲染（大概率还崩），用云端替代文案；
                # 不再审（单向否决已终结，防循环）
                rescue = strip_prefix_noise(str(info)[len("REWRITE:"):].strip())
                if rescue:
                    rescue = enforce_persona(rescue)
                    text, sticker_kw = extract_sticker_keyword(rescue)
                    print(f"🦊 [qq_lifemate] 仲裁否决→云端重写采纳: {text[:40]}")
                    break
            print(f"🦊 [qq_lifemate] 仲裁否决（{info[:40]}）→ 重渲染")
            text = None
        if not text:
            text = fallback_text(last_scene(db), now_dt)
            sticker_kw = None   # 模板直出不带表情标注
        # 幽灵追问拦截（2026-10-29 队长拍板）：指代不存在的上文→诚实走神
        # 话术（全来源最后一道闸门：本地生成/云端重写/模板统一过检）
        text, sticker_kw = enforce_context_independence(text, sticker_kw)
        if not send_qq(text):
            return False
        # 表现力编排（切片 b）：文字已发出，按概率附加语音/表情（失败
        # 静默降级——文字消息不受影响）
        try:
            import express
            if sticker_kw:
                # 情绪驱动（队长拍板）：模型标注关键词→搜图→URL 直发→沉淀；
                # 解析失败回退 mood 映射
                if not express.send_api_sticker(sticker_kw):
                    express.send_api_sticker(
                        express.MOOD_KEYWORDS.get("neutral", "猫猫"))
                acts = "api_sticker"
            else:
                acts = express.maybe_express(text)
            if acts:
                print(f"🦊 [qq_lifemate] 表现力附加: {acts}")
        except Exception as e:
            print(f"🦊 [qq_lifemate] 表现力编排异常（不影响文字）: {e}")
        db.execute("INSERT INTO chat_log(role, content, ts, kind) "
                   "VALUES(?,?,?,?)",
                   ("assistant", text, now_str(), "proactive_wake"))
        today = now_dt.strftime("%Y-%m-%d")
        if meta_get(db, "wake_date") != today:
            meta_set(db, "wake_date", today)
            meta_set(db, "wake_count", "1")
        else:
            meta_set(db, "wake_count", str(daily_count(db, now_dt) + 1))
        db.commit()
        print(f"🦊 [qq_lifemate] 已主动唤醒：{text[:40]}")
        return True
    finally:
        db.close()


def try_daily_replay(now_dt):
    """每日回放（切片 c 队长拍板）：REPLAY_HOUR 后首个检查周期，把昨天以来
    的唤醒话与 QQ 近况总结成 1-3 条核心事实固化进 facts——第一指导原则的
    每日沉淀。meta replay_date 防重；失败下个周期再试（绝不抛）。"""
    if now_dt.hour < REPLAY_HOUR:
        return
    db = _db()
    try:
        today = now_dt.strftime("%Y-%m-%d")
        if meta_get(db, "replay_date") == today:
            return
        meta_set(db, "replay_date", today)
        chat_tail = db.execute(
            "SELECT content FROM chat_log ORDER BY id DESC LIMIT 6"
        ).fetchall()
        qq_tail = qq_recent_digest(3)
        source = "\n".join(r[0] for r in chat_tail) + "\n" + qq_tail
        if not source.strip():
            return
        try:
            import brain
            out = brain.ask_local([
                {"role": "system", "content":
                    "你是小橘的记忆整理助手。把对话素材总结成 1-3 条值得长期"
                    "记住的核心事实（关于主人或关于你们的互动），每条一行，"
                    "格式严格为：KEY=VALUE（KEY 两三个字，VALUE 一句话）。"
                    "关于主人的条目必须用第三人称\"主人\"（如 主人的游戏=主人"
                    "最喜欢玩明日方舟），严禁写\"我\"。"
                    "只输出这几行，不要任何其他文字。没值得记的就输出：无"},
                {"role": "user", "content": source[:1200]}])
            text = str(out or "")
            if "<think>" in text:
                text = text.split("</think>", 1)[-1]
            added = 0
            for line in text.strip().splitlines():
                line = line.strip().lstrip("-• ")
                if "=" not in line or line == "无":
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip()[:30], v.strip()[:200]
                if not k or not v:
                    continue
                # 2026-10-30 时空错乱根治：固化体禁"小橘说过：「…」"引述
                # 形态——该形态会被唤醒模型当成"该接着说的话"补交旧作业
                # （今晨选股科普实锤）。统一改写为过去式已聊完陈述。
                v = v.replace("小橘说过：", "之前聊到").replace(
                    "小橘说过:", "之前聊到")
                if "已聊完" not in v:
                    v = v + "（已聊完的旧话题）"
                db.execute(
                    "INSERT INTO facts(key, value, ts) VALUES(?,?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                    "ts=excluded.ts",
                    (f"回放·{k}", v, now_str()))
                added += 1
                if added >= 3:
                    break
            db.commit()
            print(f"🦊 [qq_lifemate] 每日回放完成：固化 {added} 条")
        except Exception as e:
            print(f"🦊 [qq_lifemate] 回放总结失败（明日再试）: {e}")
    finally:
        db.close()


def _wake_loop():
    """唤醒线程体：每 CHECK_INTERVAL 检查一次三闸（硬帽/quiet/静默）。
    daemon 线程——宿主退出即消亡，stop() 优雅停。"""
    print(f"🦊 [qq_lifemate] 唤醒线程启动（每 {CHECK_INTERVAL_SEC // 60} 分钟"
          f"检查，静默 {SILENCE_HOURS}h，quiet {QUIET_START}:00-{QUIET_END}:00，"
          f"日限 {DAILY_CAP} 次）")
    import random as _random   # 5% 社交串门判定用（函数级局部导入不跨作用域——
                               # 2026-10-30 实锤：缺此行则每轮 NameError 被兜住，
                               # social_visit 从未有机会执行，昨夜日志 4 次铁证）
    while not _STOP.wait(CHECK_INTERVAL_SEC):
        try:
            now_dt = datetime.now()
            try_daily_replay(now_dt)   # 每日回放（切片 c：03:00 后首查触发）
            db = _db()
            try:
                count = daily_count(db, now_dt)
                wake, reason = should_wake(last_speak_ts(db), now_dt, count,
                                           tension=current_tension())
            finally:
                db.close()
            if not wake:
                # 🎲 社交串门（Owner 未唤醒时低概率触发，日限 3 次）
                if _random.random() < 0.05:   # 5% 概率/检查周期
                    try:
                        social_db = _db()
                        social_visit(db=social_db)
                        social_db.close()
                    except Exception:
                        pass
                continue
            wake_once(now_dt)
        except Exception as e:
            print(f"🦊 [qq_lifemate] 唤醒循环异常（已兜住，下轮再试）: {e}")


def start():
    """setup 钩子调用：启动唤醒线程（幂等——已在跑则跳过）。"""
    global _THREAD
    if _THREAD is not None and _THREAD.is_alive():
        return
    _STOP.clear()
    _THREAD = threading.Thread(target=_wake_loop, daemon=True,
                               name="qq_lifemate_waker")
    _THREAD.start()


def stop():
    """teardown 钩子调用：停唤醒线程（卸载即冬眠，零残留）。"""
    _STOP.set()
    print("🦊 [qq_lifemate] 唤醒线程已停（冬眠）")


# ==================== 多目标随机串门（2026-10-29 队长拍板） ====================
# 不是无脑群发——小橘加入的所有群聊和好友都成为"社交对象"。每次触发时
# 随机挑一个目标问候（一会聊这个群，一会聊那个群），增加真实感。
# 安全铁律：
# - 全局日限 2-3 次（多目标共享，防高频封号）
# - 同一目标 24h 冷却（雨露均沾，不盯一个聊）
# - 非 Owner 目标：彻底切断主人记忆，切换"社交模式" Prompt
# - 群聊必须模拟打字延迟 3-6s（绝不可秒发）
# - 社交池默认空白（只能在私聊找 Owner）——队长手动配置后才启用

_SOCIAL_POOL_ENV = "XIAOJU3_SOCIAL_POOL"
_SOCIAL_DAILY_CAP = 3
_SOCIAL_TARGET_COOLDOWN_H = 24
_SOCIAL_DELAY = (3.0, 6.0)


def _parse_social_pool():
    """解析 XIAOJU3_SOCIAL_POOL 环境变量。
    格式：逗号分隔，每项 g:群号 或 f:好友QQ。
    如 "g:123456,f:789012,g:111222" → [("group","123456"),("friend","789012"),...]"""
    raw = os.environ.get(_SOCIAL_POOL_ENV, "").strip()
    if not raw:
        return []
    out = []
    for item in raw.split(","):
        item = item.strip()
        if item.startswith("g:"):
            out.append(("group", item[2:]))
        elif item.startswith("f:"):
            out.append(("friend", item[2:]))
        elif item.isdigit():
            out.append(("group", item))   # 默认按群处理
    return out


def _social_send(target_type, target_id, text):
    """发送到群或私聊（OneBot API）。"""
    api = (os.environ.get("ONEBOT_API_URL", "").strip()
           or os.environ.get("NAPCAT_API_URL", "").strip()
           or "http://127.0.0.1:3001").rstrip("/")
    headers = {}
    token = (os.environ.get("ONEBOT_TOKEN", "") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if target_type == "group":
        payload = {"group_id": int(target_id), "message": text}
        endpoint = "send_group_msg"
    else:
        payload = {"user_id": int(target_id), "message": text}
        endpoint = "send_private_msg"
    try:
        import requests
        r = requests.post(f"{api}/{endpoint}", json=payload,
                          headers=headers, timeout=8)
        body = r.json()
        return (r.status_code == 200 and body.get("retcode") == 0
                and (body.get("data") or {}).get("message_id"))
    except Exception as e:
        print(f"🦊 [social] 发送异常: {e}")
        return False


_SOCIAL_MODE_PROMPT = (
    "你是小橘，现在在一个普通的群聊/好友聊天中。请发一句符合聊天氛围的"
    "日常问候或轻松话题（如'大家早上好呀'、'有人在摸鱼吗'、'今天天气不错呢'）。"
    "语气自然轻松，像真人聊天。"
    "【绝对红线】严禁暴露关于主人的任何信息（名字/习惯/偏好/日程/位置）。"
    "严禁提供任何网址、下载链接或安装教程。严禁长篇大论。1-2 句即可。")


def _social_greeting(target_desc, chat_fn=None):
    """生成社交模式问候语（场景隔离——零主人信息）。"""
    prompt = [{"role": "system", "content": _SOCIAL_MODE_PROMPT},
              {"role": "user", "content": f"当前目标：{target_desc}。"
               "请生成一句问候。"}]
    try:
        if chat_fn:
            return str(chat_fn(prompt) or "").strip()
        from brain import ask_cloud
        return str(ask_cloud(prompt) or "").strip()
    except Exception:
        return None


_SOCIAL_COOLDOWN_MARK = "social_visit_{tid}"


def _ensure_social_tables(db):
    """社交串门持久层（幂等建表）。2026-10-30 实锤双雷：旧版按
    meta(key,value) 列名读写（与 _db() 的 meta(k,v) 不匹配）+ social_log
    全仓零建表——全局日限与 24h 冷却双双静默失效（except 吞 OperationalError，
    计数永远 0）。修=建表与读写统一 k/v 口径。"""
    db.executescript("""
        CREATE TABLE IF NOT EXISTS meta (
            k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE IF NOT EXISTS social_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id TEXT, target_type TEXT, ts TEXT, greeting TEXT);
    """)


def social_visit(db=None):
    """多目标随机串门：从社交池随机选一个目标（24h 冷却），发问候。
    返回 True=发了消息。任何失败静默。"""
    pool = _parse_social_pool()
    if not pool:
        return False
    import random as _random
    import datetime as _dt

    now = _dt.datetime.now()
    today = now.strftime("%Y-%m-%d")

    # 全局日限检查（k/v 口径=meta_get/meta_set；计数读不到=保命侧
    # fail-closed，宁可不出手也不无账发送——2026-10-30 队长红线）
    own_db = db or _db()
    try:
        _ensure_social_tables(own_db)
        social_date = meta_get(own_db, "social_date")
        social_count = int(meta_get(own_db, "social_count", "0") or 0)
        if social_date != today:
            social_date = today
            social_count = 0
        if social_count >= _SOCIAL_DAILY_CAP:
            # 2026-10-30 监控日志（队长要求盯首跑）：跳过原因可见
            print(f"🦊 [social] 今日额度已用完（{social_count}"
                  f"/{_SOCIAL_DAILY_CAP}），跳过")
            return False
    except Exception as e:
        print(f"🦊 [social] 计数库异常 fail-closed: {e}")
        return False

    # 随机选一个目标（洗牌后取第一个可用的）
    targets = pool[:]
    _random.shuffle(targets)
    for tt, tid in targets:
        # 主人豁免（保命红线）：主人走专属唤醒通道（带全量记忆），
        # 绝不落入社交池被隐私切断的社交模式问候
        if tid == (os.environ.get("XIAOJU3_OWNER_QQ", "") or "").strip():
            continue

        # 24h 冷却检查（memory.db social_log 表）
        try:
            row = own_db.execute(
                "SELECT ts FROM social_log WHERE target_id=? "
                "ORDER BY ts DESC LIMIT 1", (tid,)).fetchone()
            if row:
                last = _dt.datetime.strptime(row[0][:19], "%Y-%m-%d %H:%M:%S")
                if (now - last).total_seconds() < _SOCIAL_TARGET_COOLDOWN_H * 3600:
                    continue
        except Exception:
            pass   # 表不存在=首次，直接用

        # 生成问候语
        desc = f"{'群聊' if tt == 'group' else '好友'} {tid}"
        greeting = _social_greeting(desc)
        if not greeting:
            print(f"🦊 [social] 问候生成失败，换下个目标: {tt}:{tid}")
            continue

        # 发送（拟人打字延迟 3-6s 随机——风控铁律绝不秒发）
        time.sleep(_random.uniform(*_SOCIAL_DELAY))
        ok = _social_send(tt, tid, greeting)
        if not ok:
            print(f"🦊 [social] 发送失败（回执不过），换下个目标: {tt}:{tid}")
            continue

        # 记录（k/v 口径 meta_set——2026-10-30 修复列名不匹配静默失效）
        try:
            own_db.execute(
                "INSERT INTO social_log(target_id, target_type, ts, greeting) "
                "VALUES(?,?,?,?)", (tid, tt, now_str(), greeting[:100]))
            meta_set(own_db, "social_date", today)
            meta_set(own_db, "social_count", str(social_count + 1))
            own_db.commit()
        except Exception:
            pass
        print(f"🦊 [social] 串门成功: {tt}:{tid} → {greeting[:40]}")
        return True

    print(f"🦊 [social] 本轮无可串目标（池 {len(pool)} 个全在冷却/豁免/失败）")
    return False
