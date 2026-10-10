# -*- coding: utf-8 -*-
"""mood 状态机（#271① M1）——PAD 三维情绪参数，悄悄记账不改说话。

设计稿：_dev/design_271_mood_statemachine.md（用户三拍板：基线
P+0.2/A+0.4/D+0.3；一期纯规则表不加 LLM 自评；独立 mood.db）。

模型（MATE 式纯函数 state×event→new_state）：
- PAD 三维 float ∈ [-1, +1]（P 愉悦 / A 唤醒 / D 支配）；
- 基线=性格（层 10 设定点）：交互回归 α=0.10 + 闲置回归 β=0.05/小时
  （hedonic adaptation；mood 时标=小时级，与 exp01 记忆的天级正交）；
- 事件位移：mood_rules.json 规则表命中（关键词组），同型连击衰减
  0.6^n 封顶 3 次（防夸夸刷）+ 随机微扰 ±0.02（层 8 防剧本感）；
- 深夜时段（0-5 点交互）A 额外 -0.05（困倦）。

安全边界（全部静默，绝不影响对话——_remember_user_facts 同款纪律）：
- MOOD_ENABLED 开关（XIAOJU3_MOOD_ENABLED，缺省开）；
- 任何读写异常静默回退基线；本模块三文件（mood.py/mood_rules.json/
  test_mood.py）可整体删除，brain 挂钩处 ImportError 即旁路。
- 虚实红线：本模块一切措辞为"情绪参数/状态机"，坐标→人话仅供日志
  与（二期）语气注入，不构造情绪体验叙事。
"""
import json
import os
import random
import sqlite3
from datetime import datetime

# ---- 参数（全部集中此处，无散落魔法数）----
ALPHA = 0.10          # 每次交互向基线回归比例
BETA_PER_HOUR = 0.05  # 闲置回归比例/小时
CLAMP = 1.0           # 三维夹钳边界
STREAK_DECAY = 0.6    # 同型事件连击衰减系数
STREAK_MAX = 3        # 连击封顶次数（第 3 次后不再衰减加深）
EPS = 0.02            # 随机微扰幅度
LOG_KEEP = 500        # mood_log 保留条数
LATE_NIGHT_HOURS = (0, 1, 2, 3, 4, 5)
LATE_NIGHT_DA = -0.05

# ---- M1+ 睡眠刷新（拍板：S1 负面归 0 / S2 缺省开 / S3 阈值 6h）----
SLEEP_THRESHOLD_H = 6.0   # 无交互 ≥6h = 一次睡眠窗口
P_NEG_RATE = 0.5          # 睡眠期负 P 消退速率/h（向 0 收敛）
P_POS_DECAY_H = 0.05      # 睡眠期正 P 衰减/h（保留）
SLEEP_A = 0.1             # 睡眠期唤醒度（物理性归低；醒后 α 回升）


def sleep_enabled():
    """睡眠刷新开关（XIAOJU3_MOOD_SLEEP）：缺省开（M1 闲置回归的
    升级替换；关=完整回退 M1 行为）。"""
    return str(os.environ.get("XIAOJU3_MOOD_SLEEP", "1")).strip().lower() \
        not in ("0", "false", "off")


def sleep_refresh(state, hours):
    """睡眠补算（纯函数，拍板 S1）：负 P 快消退**向 0 收敛**（不越
    零）、正 P 保留、A 压平、D 不变；超长睡眠自然封顶（24h=72h）。"""
    if state["p"] < 0:
        state["p"] *= max(0.0, 1 - P_NEG_RATE * hours)
    elif state["p"] > 0:
        state["p"] *= max(0.01, 1 - P_POS_DECAY_H * hours)
    state["a"] = SLEEP_A
    return state

BASELINE = {"p": 0.2, "a": 0.4, "d": 0.3}   # 决策点①已拍板
_RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "mood_rules.json")
_TONE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "mood_tone.json")
_FALLBACK_RULES = {  # 规则文件缺失/损坏时的内置最小集（保证可运行）
    "rules": [{"type": "praised", "label": "被夸/道谢",
               "patterns": ["厉害", "谢谢"], "dp": 0.30, "da": 0.15,
               "dd": 0.10}],
}


def enabled():
    """开关：XIAOJU3_MOOD_ENABLED 缺省开，0/false/off 旁路。"""
    return str(os.environ.get("XIAOJU3_MOOD_ENABLED", "1")).strip().lower() \
        not in ("0", "false", "off")


def _db_path():
    """mood.db 路径：XIAOJU3_MOOD_DB_PATH > AGENT_STATE_DIR > 本地目录。"""
    p = os.environ.get("XIAOJU3_MOOD_DB_PATH")
    if p:
        return p
    base = os.environ.get("AGENT_STATE_DIR") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "agent_state")
    return os.path.join(base, "mood.db")


def _now():
    return datetime.now()


SCHEMA = """
CREATE TABLE IF NOT EXISTS mood_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    p REAL NOT NULL, a REAL NOT NULL, d REAL NOT NULL,
    baseline_p REAL NOT NULL, baseline_a REAL NOT NULL,
    baseline_d REAL NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_type TEXT,
    last_event_streak INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS mood_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    dp REAL NOT NULL, da REAL NOT NULL, dd REAL NOT NULL,
    p_after REAL NOT NULL, a_after REAL NOT NULL, d_after REAL NOT NULL,
    note TEXT
);
"""


def _connect():
    conn = sqlite3.connect(_db_path())
    conn.executescript(SCHEMA)
    # 单行初始化（幂等）：无行才插，已有行不动
    row = conn.execute("SELECT id FROM mood_state WHERE id=1").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO mood_state (id, p, a, d, baseline_p, baseline_a,"
            " baseline_d, updated_at, last_event_type, last_event_streak)"
            " VALUES (1, ?, ?, ?, ?, ?, ?, ?, 'init', 0)",
            (BASELINE["p"], BASELINE["a"], BASELINE["d"],
             BASELINE["p"], BASELINE["a"], BASELINE["d"],
             _now().isoformat(sep=" ", timespec="seconds")))
        conn.commit()
    return conn


def _clamp(v):
    return max(-CLAMP, min(CLAMP, v))


def load_mood():
    """读当前状态；任何异常回退基线（不影响调用方）。"""
    try:
        row = _connect().execute(
            "SELECT p, a, d, baseline_p, baseline_a, baseline_d,"
            " updated_at, last_event_type, last_event_streak"
            " FROM mood_state WHERE id=1").fetchone()
        return {"p": row[0], "a": row[1], "d": row[2],
                "baseline": (row[3], row[4], row[5]),
                "updated_at": row[6], "last_event": row[7],
                "streak": row[8]}
    except Exception:
        return {"p": BASELINE["p"], "a": BASELINE["a"], "d": BASELINE["d"],
                "baseline": (BASELINE["p"], BASELINE["a"], BASELINE["d"]),
                "updated_at": None, "last_event": None, "streak": 0}


def _load_rules():
    try:
        with open(_RULES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and data.get("rules") \
            else _FALLBACK_RULES
    except Exception:
        return _FALLBACK_RULES


def match_event(message):
    """关键词组匹配 → (rule, label) 或 (None, None)。首条命中即用。"""
    text = str(message or "")
    for rule in _load_rules().get("rules", []):
        if any(k and k in text for k in rule.get("patterns", [])):
            return rule, rule.get("label", rule["type"])
    return None, None


def _regress(state, now):
    """基线回归：rate = min(1, α + ⌊闲置小时⌋×β)——线性可解释；闲置
    ≥18h 即 rate=1.0 完全回基线（30 天不交互恰好停在基线）。"""
    bp, ba, bd = state["baseline"]
    idle_hours = 0.0
    if state["updated_at"]:
        try:
            last = datetime.strptime(state["updated_at"],
                                     "%Y-%m-%d %H:%M:%S")
            idle_hours = max(0.0, (now - last).total_seconds() / 3600.0)
        except Exception:
            idle_hours = 0.0
    rate = min(1.0, ALPHA + int(idle_hours) * BETA_PER_HOUR)
    state["p"] += rate * (bp - state["p"])
    state["a"] += rate * (ba - state["a"])
    state["d"] += rate * (bd - state["d"])
    return state, idle_hours, rate


def observe_message(message, now=None):
    """交互事件 → 读→评→写一次完成；返回日志摘要 str 或 None（旁路）。

    摘要仅在规则命中/深夜/异常回退时返回（纯回归不打扰控制台）；
    任何异常静默吞掉并返回 None（绝不影响对话链）。
    """
    if not enabled():
        return None
    try:
        now = now or _now()
        state = load_mood()
        p, a, d = state["p"], state["a"], state["d"]
        bp, ba, bd = state["baseline"]

        # ① 基线回归：idle≥6h 走睡眠刷新（M1+ 拍板 S2/S3），否则 M1
        # 闲置线性回归（_regress 本体不动=开关可完整回退）
        idle_hours = 0.0
        if state["updated_at"]:
            try:
                last = datetime.strptime(state["updated_at"],
                                         "%Y-%m-%d %H:%M:%S")
                idle_hours = max(0.0, (now - last).total_seconds() / 3600.0)
            except Exception:
                idle_hours = 0.0
        slept = False
        if idle_hours >= SLEEP_THRESHOLD_H and sleep_enabled():
            state = sleep_refresh(state, idle_hours)
            state["p"] += ALPHA * (bp - state["p"])
            state["a"] += ALPHA * (ba - state["a"])
            state["d"] += ALPHA * (bd - state["d"])
            regress_note = f"睡眠刷新{idle_hours:.1f}h（负面归0/A压平）+α"
            slept = True
        else:
            state, idle_hours, rate = _regress(state, now)
            regress_note = f"回归rate={rate:.2f}" + (
                f"（含闲置{idle_hours:.1f}h）" if idle_hours >= 1 else "")

        # ② 事件评价（规则表首条命中；无命中零位移）
        rule, label = match_event(message)
        dp = da = dd = 0.0
        event_type = "small_talk"
        streak_note = ""
        if rule:
            event_type = rule["type"]
            streak = state["streak"] + 1 \
                if state["last_event"] == event_type else 1
            decay = STREAK_DECAY ** min(streak - 1, STREAK_MAX - 1)
            dp = rule.get("dp", 0.0) * decay \
                + random.uniform(-EPS, EPS)
            da = rule.get("da", 0.0) * decay \
                + random.uniform(-EPS, EPS)
            dd = rule.get("dd", 0.0) * decay \
                + random.uniform(-EPS, EPS)
            state["streak"] = streak
            streak_note = f"连击{streak}衰减×{decay:.2f}"
        else:
            state["streak"] = 0

        # ③ 深夜困倦（时间驱动，独立于文本规则）
        if now.hour in LATE_NIGHT_HOURS:
            da += LATE_NIGHT_DA
            if event_type == "small_talk":
                event_type = "late_night"
                label = "深夜交互"
        if slept and event_type in ("small_talk", "late_night"):
            event_type = "sleep"
            label = "睡眠唤醒"

        # ④ 位移叠加（基于回归后的坐标）+ 夹钳
        state["p"] = _clamp(state["p"] + dp)
        state["a"] = _clamp(state["a"] + da)
        state["d"] = _clamp(state["d"] + dd)
        state["updated_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
        state["last_event"] = event_type

        # ⑤ 落库（单行 UPDATE + 审计 INSERT，一个事务）
        conn = _connect()
        with conn:
            conn.execute(
                "UPDATE mood_state SET p=?, a=?, d=?, updated_at=?,"
                " last_event_type=?, last_event_streak=? WHERE id=1",
                (state["p"], state["a"], state["d"], state["updated_at"],
                 event_type, state["streak"]))
            conn.execute(
                "INSERT INTO mood_log (ts, event_type, dp, da, dd,"
                " p_after, a_after, d_after, note) VALUES (?,?,?,?,?,?,?,?,?)",
                (state["updated_at"], event_type, round(dp, 4),
                 round(da, 4), round(dd, 4), round(state["p"], 4),
                 round(state["a"], 4), round(state["d"], 4),
                 f"{regress_note}; {streak_note}".strip("; ")))
            conn.execute(
                "DELETE FROM mood_log WHERE id NOT IN"
                " (SELECT id FROM mood_log ORDER BY id DESC LIMIT ?)",
                (LOG_KEEP,))
        conn.close()

        if rule or event_type == "late_night":
            return (f"{label} ΔP{dp:+.2f} ΔA{da:+.2f} ΔD{dd:+.2f} → "
                    f"P{state['p']:+.2f} A{state['a']:+.2f} "
                    f"D{state['d']:+.2f}")
        return None  # 纯回归：记账不打扰
    except Exception:
        return None


def mood_line(state=None):
    """坐标→人话（仅供日志与二期语气注入；措辞=参数非体验）。"""
    s = state or load_mood()
    p, a, d = s["p"], s["a"], s["d"]

    def tier(v, names):
        return names[0] if v >= 0.34 else (names[1] if v >= -0.34
                                           else names[2])
    return (f"{tier(p, ('明显积极', '轻微积极', '偏消极'))}、"
            f"{tier(a, ('高唤醒', '中等唤醒', '低唤醒平静'))}、"
            f"{tier(d, ('主导', '平稳', '顺从'))}")


def _tier(v):
    """P/A 维度三档划分（阈值 0.50：基线 a=0.4 必须落在 mid=中性豁免
    区——M2 拍板稿"中性档不注入"的隐含前提，0.34 会把基线判成 high）。"""
    if v >= 0.50:
        return "high"
    if v >= -0.50:
        return "mid"
    return "low"


def tone_enabled():
    """M2 语气注入开关（XIAOJU3_MOOD_TONE）：缺省关（拍板①——首个
    用户可感知变化，等 M1 真机验证后手动开）。"""
    return str(os.environ.get("XIAOJU3_MOOD_TONE", "0")).strip().lower() \
        in ("1", "true", "on")


def tone_suffix(state=None):
    """#271① M2：mood 坐标 → 语气后缀（拼在 SYSTEM_PROMPT 尾部）。

    四条空串路径（任一命中即与现状逐字节一致）：开关关 / 读取异常 /
    中性基线档（p_mid_a_mid）/ 表文件缺失损坏。全程 try/except，
    绝不影响对话链。措辞红线：情绪参数口径，零体验词。
    """
    try:
        if not tone_enabled():
            return ""
        s = state or load_mood()
        key = f"p_{_tier(s['p'])}_a_{_tier(s['a'])}"
        with open(_TONE_PATH, encoding="utf-8") as f:
            table = json.load(f)
        tone = table.get("tones", {}).get(key, "")
        if not tone:
            return ""
        return (f"\n\n【当前情绪参数】：{mood_line(s)}。本轮回复语气："
                f"{tone}。{table.get('verdict', '')}")
    except Exception:
        return ""
