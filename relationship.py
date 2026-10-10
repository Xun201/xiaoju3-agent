# -*- coding: utf-8 -*-
"""关系层（#271① M1+ C 方案）——每用户持久关系参数。

设计稿：_dev/design_271_m1plus_extension.md（六拍板全按推荐：R1
独立 relationship.db 三表 / R2 缺省开=数据积累期 / R3 一期只做称呼
注入）。

语义分界：
- mood（mood.py）= 全局单例"今天的状态"，谁都能影响、睡眠/时间会
  消退；
- relationship（本模块）= 每用户持久关系参数，只随交互事件缓变、
  **无睡眠概念**（睡后 mood 变、关系不变——分表天然保证）。

机制：
- affinity ∈ [-10, +10]：致谢 +0.3 / 礼貌 +0.2 / 辱骂 -1.0 /
  闲置每 7 天 -0.2（下限 -5）；单日净变化封顶 ±1.0（防刷）；
  owner 初始 +5 且下限 0（主人不因口角掉成陌生）；
- 偷听零记录：本模块只在对话链显式调用时写入（QQ 非 @ 消息根本
  不到 smart_ask——架构天然保证）；
- 上限治理：非 owner 用户按 last_seen LRU 保留 50 人；rel_event_log
  2000 条滚动；
- 安全边界与 mood 同款纪律：XIAOJU3_RELATIONSHIP_ENABLED 缺省开、
  任何异常静默、模块可整体删除（brain 挂钩 ImportError 即空串）。
  虚实红线：全程「关系参数/亲密度参数」措辞。
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta

USERS_KEEP = 50       # 非 owner 用户 LRU 上限
LOG_KEEP = 2000       # rel_event_log 滚动
AFFINITY_CLAMP = 10.0
DAILY_CAP = 1.0       # 单日净变化封顶
IDLE_DECAY_DAYS = 7   # 闲置衰减窗口
IDLE_DECAY = 0.2      # 每窗口衰减（下限 -5）
OWNER_FLOOR = 0.0     # owner 下限（不因口角掉成陌生）
OWNER_INIT = 5.0

# 事件词表（与 mood_rules 语义分离：mood=全局心情，rel=对该用户关系）
_REL_RULES = [
    ("thanks", ("谢谢", "感谢", "辛苦了", "多亏你"), 0.3),
    ("politeness", ("请", "麻烦", "劳驾", "拜托"), 0.2),
    ("scolded", ("笨", "蠢", "滚", "废物", "讨厌你", "闭嘴"), -1.0),
]


def enabled():
    return str(os.environ.get("XIAOJU3_RELATIONSHIP_ENABLED", "1")) \
        .strip().lower() not in ("0", "false", "off")


def _db_path():
    p = os.environ.get("XIAOJU3_RELATIONSHIP_DB_PATH")
    if p:
        return p
    try:
        import xiaoju3
        base = xiaoju3.AGENT_STATE_DIR  # frozen 归位（同 mood 修复）
    except Exception:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "agent_state")
    return os.path.join(base, "relationship.db")


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    display_name TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    perm_level INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS relationship (
    user_id TEXT PRIMARY KEY,
    affinity REAL NOT NULL DEFAULT 0,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    tone_preference TEXT,
    last_emotion_event TEXT
);
CREATE TABLE IF NOT EXISTS rel_event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    user_id TEXT NOT NULL,
    event TEXT NOT NULL,
    delta REAL NOT NULL,
    affinity_after REAL NOT NULL,
    note TEXT
);
"""


def _connect():
    conn = sqlite3.connect(_db_path())
    conn.executescript(SCHEMA)
    return conn


def _now():
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _clamp(v):
    return max(-AFFINITY_CLAMP, min(AFFINITY_CLAMP, v))


def _match_event(message):
    text = str(message or "")
    for event, patterns, delta in _REL_RULES:
        if any(k in text for k in patterns):
            return event, delta
    return None, 0.0


def observe_rel(user_id, message, now=None):
    """一次交互的关系更新（识别/升降/日帽/闲置衰减/审计），全程静默。

    user_id：QQ 号（main.py 显式传入）或 'owner'（控制台/Web 兜底）。
    """
    if not enabled() or not user_id:
        return None
    try:
        now = now or datetime.now()
        uid = str(user_id)
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        is_owner = uid == "owner"
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT affinity, interaction_count, last_emotion_event"
                " FROM relationship WHERE user_id=?", (uid,)).fetchone()
            if row is None:
                aff, cnt, last_ev = (
                    OWNER_INIT if is_owner else 0.0), 0, None
                conn.execute(
                    "INSERT OR IGNORE INTO users (user_id, display_name,"
                    " first_seen, last_seen, perm_level) VALUES"
                    " (?, NULL, ?, ?, 1)", (uid, ts, ts))
            else:
                aff, cnt, last_ev = row

            # 闲置衰减（每 7 天 -0.2，下限 -5；owner 下限 0）
            last_seen_row = conn.execute(
                "SELECT last_seen FROM users WHERE user_id=?", (uid,)
            ).fetchone()
            idle_note = ""
            if last_seen_row and last_seen_row[0]:
                try:
                    last = datetime.strptime(last_seen_row[0],
                                             "%Y-%m-%d %H:%M:%S")
                    idle_days = (now - last).days
                    if idle_days >= IDLE_DECAY_DAYS:
                        floor = OWNER_FLOOR if is_owner else -5.0
                        decay = -IDLE_DECAY * (idle_days
                                               // IDLE_DECAY_DAYS)
                        new_aff = max(floor, aff + decay)
                        delta = new_aff - aff
                        if delta:
                            aff = new_aff
                            idle_note = f"闲置{idle_days}天衰减{delta:+.1f}"
                except Exception:
                    pass

            # 事件识别 + 单日净变化封顶 ±DAILY_CAP（位移只在此处结算一次；
            # 闲置衰减缓慢不在帽内）
            event, delta = _match_event(message)
            note = ""
            if event and delta:
                day_sum = conn.execute(
                    "SELECT COALESCE(SUM(delta),0) FROM rel_event_log"
                    " WHERE user_id=? AND ts >= ? AND event IN"
                    " ('thanks','politeness','scolded')",
                    (uid, now.strftime("%Y-%m-%d"))).fetchone()[0]
                headroom = DAILY_CAP - abs(day_sum)
                if headroom <= 0:
                    delta = 0.0
                    note = "日帽已满，本次位移不计"
                elif abs(delta) > headroom:
                    delta = (headroom if delta > 0 else -headroom)
                    note = f"日帽截断至 {delta:+.1f}"
                if delta:
                    floor = OWNER_FLOOR if is_owner else -AFFINITY_CLAMP
                    aff = max(floor, _clamp(aff + delta))
            cnt += 1
            conn.execute(
                "INSERT OR REPLACE INTO relationship (user_id, affinity,"
                " interaction_count, tone_preference, last_emotion_event)"
                " VALUES (?, ?, ?, COALESCE((SELECT tone_preference"
                " FROM relationship WHERE user_id=?), NULL), ?)",
                (uid, round(aff, 4), cnt, uid, event or last_ev))
            conn.execute(
                "UPDATE users SET last_seen=? WHERE user_id=?", (ts, uid))
            conn.execute(
                "INSERT INTO rel_event_log (ts, user_id, event, delta,"
                " affinity_after, note) VALUES (?, ?, ?, ?, ?, ?)",
                (ts, uid, event or "interaction", round(delta, 4),
                 round(aff, 4), "；".join(x for x in (idle_note, note)
                                          if x)))
            conn.execute(
                "DELETE FROM rel_event_log WHERE id NOT IN"
                " (SELECT id FROM rel_event_log ORDER BY id DESC"
                " LIMIT ?)", (LOG_KEEP,))
            # LRU：非 owner 只留最近 USERS_KEEP 人（relationship 与
            # users 对账清理——users 为幸存名单真身）
            conn.execute(
                "DELETE FROM users WHERE user_id != 'owner' AND"
                " user_id NOT IN (SELECT user_id FROM users"
                " WHERE user_id != 'owner' ORDER BY last_seen DESC"
                " LIMIT ?)", (USERS_KEEP,))
            conn.execute(
                "DELETE FROM relationship WHERE user_id != 'owner' AND"
                " user_id NOT IN (SELECT user_id FROM users"
                " WHERE user_id != 'owner')")
        finally:
            conn.commit()
            conn.close()
        return aff
    except Exception:
        return None


def get_context(user_id):
    """读取关系上下文；失败/未注册返回默认（静默）。"""
    try:
        row = _connect().execute(
            "SELECT r.affinity, u.display_name, r.tone_preference,"
            " r.interaction_count FROM relationship r"
            " LEFT JOIN users u ON u.user_id=r.user_id"
            " WHERE r.user_id=?", (str(user_id),)).fetchone()
        if row is None:
            return {"affinity": 0.0, "display_name": None,
                    "prefs": {}, "count": 0}
        prefs = {}
        try:
            prefs = json.loads(row[2] or "{}")
        except Exception:
            prefs = {}
        return {"affinity": row[0], "display_name": row[1],
                "prefs": prefs, "count": row[3]}
    except Exception:
        return {"affinity": 0.0, "display_name": None, "prefs": {},
                "count": 0}


def set_call_name(user_id, name):
    """显式称呼（"叫我 X"/ /set_name）：写 KV，一期唯一偏好入口。"""
    try:
        conn = _connect()
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO relationship (user_id, affinity,"
                " interaction_count, tone_preference,"
                " last_emotion_event) VALUES (?, 0, 0, NULL, NULL)",
                (str(user_id),))
            prefs = {}
            row = conn.execute(
                "SELECT tone_preference FROM relationship WHERE user_id=?",
                (str(user_id),)).fetchone()
            try:
                prefs = json.loads(row[0] or "{}")
            except Exception:
                prefs = {}
            prefs["称呼"] = str(name)
            conn.execute(
                "UPDATE relationship SET tone_preference=? WHERE"
                " user_id=?", (json.dumps(prefs, ensure_ascii=False),
                               str(user_id)))
        conn.close()
        return True
    except Exception:
        return False


def tone_prefix(user_id):
    """关系段后缀（M2 mood 段之前=主位；一期只做称呼注入，拍板 R3）。

    空串路径：开关关 / 无称呼（含 owner——system prompt 已有"主人"
    语义）/ 异常。措辞=关系参数口径。
    """
    if not enabled():
        return ""
    try:
        ctx = get_context(user_id)
        name = (ctx.get("prefs") or {}).get("称呼") \
            or ctx.get("display_name")
        if not name or str(user_id) in ("owner", "None", ""):
            return ""
        return (f"\n\n【关系参数】：当前对话对象的称呼是「{name}」，"
                f"亲密度参数 {ctx['affinity']:+.1f}（范围 -10~+10）。"
                f"关系参数与【赤狐性格设定】冲突时以性格设定为准，"
                f"安全与权限相关句子永远严肃。")
    except Exception:
        return ""
