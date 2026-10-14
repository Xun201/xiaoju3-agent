# -*- coding: utf-8 -*-
"""关系化人格演化（#271，design_271_personality_evolution v2）——关系模式层。

一句话：底色天生（prompts.py 赤狐五特质，永不变），脾气是处的（本模块
按互动历史在 4 种相处模式中自动判定：斗嘴 banter / 依赖 dependent /
客气 polite / 照顾 caring）。

三层结构对应（v2 稿 §二）：
- 底色层 = prompts.py XIAOJU3_PERSONALITY（本模块绝不触碰——磨合改变的
  是"模式"，不是"它是谁"）；
- 关系模式层 = relationship.db rel_mode 表（本模块读写，relationship.py
  持有 SCHEMA 单一所有）；
- 表现层 = persona_pref.json 6 开关 tri-state（auto/on/off——用户开关
  覆盖模式默认表现，auto=交还自动判定）+ persona_expressions.json（批 3）。

分批落地（v2.1 稿 §七）：批 1 存储（309bc95）、批 2 判定（f52690b）、
批 3 表现层本批落地——mode_suffix 挂 brain 后缀链（关系段→模式段→情绪段），
但总开关 XIAOJU3_PERSONA_ENABLED 缺省关+单用户事件 ≥50 表现闸：拨开关且
证据够才可见（第一批有可感知变化的批，真机冒烟等用户）。

安全边界（mood/relationship 同款纪律）：
- XIAOJU3_PERSONA_ENABLED 表现层总开关缺省关（M2 先例：首个用户可感知
  变化默认关）；存储/判定不受此开关限制（数据积累期，relationship R2
  先例）；
- 任何读写异常静默回默认值；本模块可整体删除（brain 挂钩处 ImportError
  即空串旁路）；
- 虚实红线：全程「关系模式参数」措辞零体验词；模式枚举无负档、退化封顶
  polite（疏远但不敌对）——结构上不存在"记仇/恶意"可落状态。
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta

import relationship

# ---- 模式枚举与开关定义（ASCII 稳定键，#297 mood_factor 同款规范）----
MODES = ("banter", "dependent", "polite", "caring", "familiar")
DEFAULT_MODE = "polite"          # 新用户/证据不足/任何异常一律客气档
MANUAL_CONFIDENCE = 1.0

# ---- 批 2：六规则判定阈值（design v2.1 §3.2；初值拍板 2026-10-14，真机调参）----
WINDOW_DAYS = 90            # 判定窗口（证据只看 90 天内）
EVIDENCE_MIN_EVENTS = 10    # 证据下限：n_int 不足不判定（不拿两条消息定性）
FALLBACK_CONFIDENCE = 0.3   # 客气兜底档置信度（规则未命中仍落 polite）

DEGRADE_SCOLD = 10          # 退化：骂声主旋律+关系冷→强制 polite（可逆）
DEGRADE_POS_RATIO = 0.05
DEGRADE_AFF = -2.0
BANTER_SCOLD = 5            # 斗嘴：骂谢混杂+关系仍暖="骂着玩不伤感情"
BANTER_POS = 5
BANTER_SCOLD_RATIO = 0.25
BANTER_AFF = 3.0
CARING_POS = 8              # 照顾：致谢密集+偶发口角不计（v2.1 放宽 ≤2）
CARING_SCOLD_MAX = 2
CARING_AFF = 5.0
DEPENDENT_INT = 40          # 依赖：高频事务型（generic=中性消息为主体）
DEPENDENT_GENERIC_RATIO = 0.6
DEPENDENT_SCOLD_RATIO = 0.05
FAMILIAR_INT = 15           # 熟络（v2.1 新增）：高频中性，客气<熟络<其余
FAMILIAR_GENERIC_LO = 0.4
FAMILIAR_GENERIC_HI = 0.6
FAMILIAR_SCOLD_RATIO = 0.1

# ---- 批 2：节流与表现层闸（design v2.1 §3.3/§4.2 拍板）----
REJUDGE_EVENT_DELTA = 20        # 事件触发：新事件 ≥20 才重判（galgame 式）
REJUDGE_MIN_INTERVAL_H = 6.0    # 最低间隔防抖动（judged_at 查表=重启安全）
EXPRESSION_MIN_EVENTS = 50      # 表现层单用户闸：累计事件 ≥50 才注入

SWITCH_DEFS = {                  # 6 行为开关（v1 §二.3；ASCII 键→中文标签）
    "banter": "斗嘴",
    "clingy": "撒娇",
    "tsundere": "傲娇",
    "quiet_companion": "安静陪伴",
    "proactive_care": "主动关心",
    "proactive_banter": "主动斗嘴",
}
SWITCH_VALUES = ("auto", "on", "off")   # tri-state：auto=跟随模式默认


def enabled():
    """表现层总开关（XIAOJU3_PERSONA_ENABLED）：缺省关。存储/判定不受限。"""
    return str(os.environ.get("XIAOJU3_PERSONA_ENABLED", "0")) \
        .strip().lower() in ("1", "true", "on")


def _connect():
    """借 relationship._connect（SCHEMA 单一所有方，rel_mode 建表随
    executescript 幂等完成）。同包私有复用；异常由调用方静默兜底。"""
    return relationship._connect()


# ==================== 关系模式存取（批 1） ====================

def get_mode(user_id):
    """读关系模式参数；无行/异常 → 默认档（polite/default/置信 0）。

    返回 dict：mode/confidence/source/judged_at/evidence（JSON 字符串
    原样透传，解释权在判定侧）。
    """
    default = {"mode": DEFAULT_MODE, "confidence": 0.0,
               "source": "default", "judged_at": None, "evidence": None}
    try:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT mode, confidence, source, judged_at, evidence"
                " FROM rel_mode WHERE user_id=?",
                (str(user_id),)).fetchone()
        finally:
            conn.close()
        if row is None:
            return dict(default)
        return {"mode": row[0], "confidence": row[1], "source": row[2],
                "judged_at": row[3], "evidence": row[4]}
    except Exception:
        return dict(default)


def _write_mode(user_id, mode, confidence, source, evidence=None, ts=None):
    """落一行 rel_mode（INSERT OR REPLACE；judged_at=ts 或此刻——ts 形参
    供 maybe_rejudge 透传判定时刻，测试可确定性构造）。"""
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO rel_mode (user_id, mode,"
                " confidence, source, judged_at, evidence)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (str(user_id), mode, float(confidence), source,
                 (ts or datetime.now()).isoformat(sep=" ", timespec="seconds"),
                 evidence))
    finally:
        conn.close()


def set_mode_manual(user_id, mode):
    """手动指定关系模式（source=manual 锁定，自动判定永不覆盖——判定
    可以错，用户说一声就改，改完用户说了算）。mode 非法 → False。"""
    if mode not in MODES:
        return False
    try:
        _write_mode(user_id, mode, MANUAL_CONFIDENCE, "manual")
        return True
    except Exception:
        return False


def clear_mode_manual(user_id):
    """解锁手动指定（删行，回落自动判定/默认档）。异常静默 False。"""
    try:
        conn = _connect()
        try:
            with conn:
                conn.execute("DELETE FROM rel_mode WHERE user_id=?",
                             (str(user_id),))
        finally:
            conn.close()
        return True
    except Exception:
        return False


# ==================== 批 2：六规则判定（design v2.1 §3.2） ====================

def _sat(evidence, threshold):
    """置信度饱和公式：min(1.0, 主证据量/(2×门槛))——可解释、封顶 1。"""
    return min(1.0, evidence / (2.0 * threshold)) if threshold else 1.0


def judge_mode(stats, affinity_now):
    """六规则判定（纯函数，锚可直调）：窗口统计+关系现值 → 判决 dict。

    返回 {"mode", "confidence", "rule"}；证据不足（n_int < 10）返回 None
    （调用方决定保持 default 还是落证据流失档）。优先级递减首条命中即出：
    退化 > 斗嘴 > 照顾 > 依赖 > 熟络 > 客气兜底。
    """
    n_int = int(stats.get("n_int", 0))
    if n_int < EVIDENCE_MIN_EVENTS:
        return None
    n_pos = int(stats.get("thanks", 0)) + int(stats.get("politeness", 0))
    n_scold = int(stats.get("scolded", 0))
    scold_ratio = n_scold / n_int
    pos_ratio = n_pos / n_int
    generic_ratio = max(0.0, n_int - n_pos - n_scold) / n_int
    # 0 退化（包容坏：长期负面→客气，疏远但不敌对；枚举无更坏档=无恶意）
    if (n_scold >= DEGRADE_SCOLD and pos_ratio <= DEGRADE_POS_RATIO
            and affinity_now <= DEGRADE_AFF):
        return {"mode": "polite", "confidence": _sat(n_scold, DEGRADE_SCOLD),
                "rule": "degrade"}
    # 1 斗嘴（骂着玩不伤感情：骂谢混杂且关系仍暖）
    if (n_scold >= BANTER_SCOLD and n_pos >= BANTER_POS
            and scold_ratio <= BANTER_SCOLD_RATIO
            and affinity_now >= BANTER_AFF):
        return {"mode": "banter",
                "confidence": _sat(min(n_scold, n_pos), BANTER_SCOLD),
                "rule": "banter"}
    # 2 照顾（致谢密集+偶发口角不计——v2.1 放宽 n_scold≤2）
    if (n_pos >= CARING_POS and n_scold <= CARING_SCOLD_MAX
            and affinity_now >= CARING_AFF):
        return {"mode": "caring", "confidence": _sat(n_pos, CARING_POS),
                "rule": "caring"}
    # 3 依赖（高频事务型：中性消息为主体）
    if (n_int >= DEPENDENT_INT
            and generic_ratio >= DEPENDENT_GENERIC_RATIO
            and scold_ratio <= DEPENDENT_SCOLD_RATIO):
        return {"mode": "dependent", "confidence": _sat(n_int, DEPENDENT_INT),
                "rule": "dependent"}
    # 4 熟络（v2.1 新增：高频中性，客气<熟络<其余）
    if (n_int >= FAMILIAR_INT
            and FAMILIAR_GENERIC_LO <= generic_ratio <= FAMILIAR_GENERIC_HI
            and scold_ratio <= FAMILIAR_SCOLD_RATIO):
        return {"mode": "familiar", "confidence": _sat(n_int, FAMILIAR_INT),
                "rule": "familiar"}
    # 5 客气兜底
    return {"mode": DEFAULT_MODE, "confidence": FALLBACK_CONFIDENCE,
            "rule": "fallback"}


def _evidence_field(cur, key, default=0):
    """从 evidence JSON 取字段（损坏/缺键回默认——判读不抛异常）。"""
    try:
        return int(json.loads(cur.get("evidence") or "{}").get(key, default))
    except Exception:
        return default


def maybe_rejudge(user_id, now=None):
    """事件触发重判定（v2.1 拍板 §3.3），brain 双入口挂钩，全程静默。

    双闸：新事件数 ≥ REJUDGE_EVENT_DELTA（基线=evidence.baseline_id，
    2000 条滚动裁剪只删旧 id 不影响）+ 距上次判定 ≥ REJUDGE_MIN_INTERVAL_H
    （judged_at 查表=重启安全）；source=manual 手动锁优先永不覆盖。
    判定后更新 judged_at + 事件基线（evidence JSON 整体重写）。
    返回新 mode dict 或 None（未触发/手动锁/证据流失保持/异常）。
    """
    try:
        now = now or datetime.now()
        uid = str(user_id or "")
        if not uid:
            return None
        cur = get_mode(uid)
        if cur["source"] == "manual":
            return None
        # 6h 防抖（无行/未判过不拦首判）
        if cur["source"] == "auto" and cur.get("judged_at"):
            try:
                last = datetime.strptime(cur["judged_at"],
                                         "%Y-%m-%d %H:%M:%S")
                if (now - last).total_seconds() < \
                        REJUDGE_MIN_INTERVAL_H * 3600.0:
                    return None
            except Exception:
                pass
        baseline_id = _evidence_field(cur, "baseline_id", 0)
        conn = _connect()
        try:
            max_id = int(conn.execute(
                "SELECT COALESCE(MAX(id),0) FROM rel_event_log"
            ).fetchone()[0])
            new_events = int(conn.execute(
                "SELECT COUNT(*) FROM rel_event_log"
                " WHERE user_id=? AND id>?", (uid, baseline_id)
            ).fetchone()[0])
        finally:
            conn.close()
        if new_events < REJUDGE_EVENT_DELTA:
            return None
        since = (now - timedelta(days=WINDOW_DAYS)).strftime(
            "%Y-%m-%d %H:%M:%S")
        stats = relationship.event_stats(uid, since=since)
        try:
            affinity_now = float(relationship.get_context(uid)["affinity"])
        except Exception:
            affinity_now = 0.0
        verdict = judge_mode(stats, affinity_now)
        if verdict is None:
            # 证据流失（窗口滚出）：auto 行落回低置信 polite，无行保持 default
            if cur["source"] != "auto":
                return None
            verdict = {"mode": DEFAULT_MODE, "confidence": 0.0,
                       "rule": "evidence_lost"}
        evidence = json.dumps({
            "baseline_id": max_id, "rule": verdict["rule"],
            "stats": stats, "affinity_now": round(affinity_now, 2),
        }, ensure_ascii=False)
        _write_mode(uid, verdict["mode"], verdict["confidence"], "auto",
                    evidence, ts=now)
        return get_mode(uid)
    except Exception:
        return None


def _is_expression_ready(user_id):
    """表现层单用户闸（v2.1 拍板 §4.2）：累计事件 ≥50 才注入模式表现。

    判定层照常记账，本闸只挡消费——防冷启动过度表现（才聊 10 句就
    熟络撒娇=吓人）。任何异常 False（空串路径，绝不影响对话链）。
    """
    try:
        return relationship.event_stats(user_id)["n_int"] \
            >= EXPRESSION_MIN_EVENTS
    except Exception:
        return False


# ==================== 表现层 6 开关（批 1） ====================

def _persona_pref_path(path=None):
    """persona_pref.json 路径：xiaoju3.AGENT_STATE_DIR 优先（frozen 路径
    陷阱铁律，禁 __file__ fallback），缺席回退 paths.DATA_ROOT/agent_state。
    独立文件不并 ui_pref.json：写入方分立避免跨模块竞态（v2 稿决策 D2）。"""
    if path:
        return path
    try:
        from xiaoju3 import AGENT_STATE_DIR as state_dir
        if state_dir:
            return os.path.join(state_dir, "persona_pref.json")
    except Exception:
        pass
    try:
        import paths
        return os.path.join(paths.DATA_ROOT, "agent_state",
                            "persona_pref.json")
    except Exception:
        return "persona_pref.json"


def _default_switches():
    return {name: "auto" for name in SWITCH_DEFS}


def get_switches(path=None):
    """读 6 开关全量（缺省 auto）；文件缺失/损坏/值非法 → 该键回默认。"""
    p = _persona_pref_path(path)
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception:
        data = {}
    out = _default_switches()
    switches = data.get("switches")
    if isinstance(switches, dict):
        for name in SWITCH_DEFS:
            if switches.get(name) in SWITCH_VALUES:
                out[name] = switches[name]
    return out


def set_switch(name, value, path=None):
    """写单个开关（tri-state 校验；读改写合并不丢未知键——多特性共文件
    互不覆盖，ui_pref 同款；tmp+replace 原子写）。非法 → False。"""
    if name not in SWITCH_DEFS or value not in SWITCH_VALUES:
        return False
    try:
        p = _persona_pref_path(path)
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}
        switches = data.get("switches")
        data["switches"] = switches if isinstance(switches, dict) else {}
        data["switches"][name] = value
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


# ==================== 批 3：模式表现段合成（design v2.1 §四） ====================

# 表文件=静态资产随模块走（mood_tone.json 同款 __file__ 路径；spec datas
# 已注册——运行时数据才走 AGENT_STATE_DIR，表文件不是）
_EXPRESS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "persona_expressions.json")

MODE_LABELS = {"banter": "斗嘴型", "dependent": "依赖型",
               "polite": "客气型", "caring": "照顾型",
               "familiar": "熟络型"}
# 模式↔关联开关一对一映射（v1 仅斗嘴；其余模式的 on 档结构保留待扩）
MODE_SWITCH_KEY = {"banter": "banter"}


def _load_mode_table():
    """表现表读取；缺失/损坏/形态不对 → None（静默，空串路径之一）。"""
    try:
        with open(_EXPRESS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and data.get("modes") else None
    except Exception:
        return None


def mode_suffix(user_id):
    """#271 批 3：关系模式参数→表现段后缀（拼在 SYSTEM_PROMPT 尾部）。

    空串路径六重（任一命中=与现状逐字节一致）：总开关关 / 单用户事件
    <50（表现闸 _is_expression_ready）/ 无行且未手动 / 表文件缺失损坏 /
    合成空（模式行被关联开关 off 压制且无加码）/ 任何异常。
    合成规则：模式选行（关联开关 off=压制 / on=on 档 / auto=auto 档）
    + 逐开关 on 加码行追加；verdict 恒定尾注（红线：模式只改亲近度与
    主动度，不改善意与职责）。措辞=关系模式参数口径零体验词。
    """
    try:
        if not enabled():
            return ""
        uid = str(user_id or "")
        if not uid or not _is_expression_ready(uid):
            return ""
        cur = get_mode(uid)
        if cur["source"] == "default":
            return ""
        table = _load_mode_table()
        if not table:
            return ""
        mode = cur["mode"]
        row = (table.get("modes") or {}).get(mode)
        if not isinstance(row, dict):
            return ""
        switches = get_switches()
        parts = []
        related = MODE_SWITCH_KEY.get(mode)
        if related and switches.get(related) == "off":
            pass                       # 用户终裁：该模式表现整段压制
        elif related and switches.get(related) == "on" and row.get("on"):
            parts.append(row["on"])
        elif row.get("auto"):
            parts.append(row["auto"])
        for name in SWITCH_DEFS:
            if switches.get(name) == "on":
                line = ((table.get("switches") or {})
                        .get(name, {}) or {}).get("on")
                if line:
                    parts.append(line)
        if not parts:
            return ""                  # 合成空
        verdict = table.get("verdict", "")
        return (f"\n\n【关系模式参数】：当前对话对象相处模式为"
                f"「{MODE_LABELS.get(mode, mode)}」。本轮表达偏移："
                + "；".join(parts)
                + (f"。{verdict}" if verdict else ""))
    except Exception:
        return ""
