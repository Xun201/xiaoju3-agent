# -*- coding: utf-8 -*-
"""主动性引擎（#271③ Phase 0 内账）——张力/抑制/判据/审计，只记账不发声。

设计稿：_dev/design_271c_proactive.md（拍板七项）+ 方案
_dev/plan_271c_phase0.md（拍板：存储=A 独立 proactive.db；tick=60s 随心跳）。

机制（拮抗，design §七）：
- 张力累积：事件驱动（Phase 0 三事件源=待办到期/久未做/久未理/完成汇报），
  时间衰减 ×0.85/h（对齐 mood β 小时级口径），夹钳 [0, 1]；
- 抑制五条件（全即时计算不落库）：深夜/刚被拒/冷却 30min/用户忙/显式别烦；
- 出手判据：张力 ≥ FIRE_THRESHOLD 且 无抑制 → **Phase 0 的"出手"=写
  fire 日志（不发消息）** + 张力清零防连发；静默路径同样写日志（#316
  静默可解释——出手/静默两态都记，坑库 #16）。

安全边界（全部静默，绝不影响对话——mood.py 同款纪律）：
- PROACTIVE_ENABLED 开关（XIAOJU3_PROACTIVE_ENABLED，**缺省关**——
  Phase 0 生命线：开关关时不建库不写日志，现有 2056 测试零影响）；
- proactive.db 懒创建（首次真实写入才建）；
- relationship.db 只读不写、库不存在优雅降级"未拒绝"（三文件可删纪律：
  本模块三文件 proactive.py/plan 文档/test_proactive.py 可整体删除，
  heartbeat 挂钩处 ImportError 即旁路）；
- 虚实红线：全程「主动行为参数/张力参数」措辞，不构造欲望体验叙事
  （对外口径=提醒与问候的调度器）。
"""
import os
import sqlite3
from datetime import datetime, timedelta

# ---- 参数（全部集中此处，无散落魔法数）----
DECAY_PER_HOUR = 0.85   # 张力时间衰减系数/小时（design §七；自检可调）
CLAMP_MAX = 1.0         # 张力上限
FIRE_THRESHOLD = 0.6    # 出手阈值（自检看分布再调）
COOLDOWN_SECONDS = 1800  # 刚找过冷却（design §五③ 默认 30 分钟）
QUIET_HOURS = (23, 7)   # 深夜起止（23:00–7:00 跨零点；design §五①）
LOG_KEEP = 2000         # 审计日志滚动保留（relationship_event_log 同款）

# 张力事件源（Phase 0 最小集，delta 按 design §三语义定）
EVENT_DELTAS = {
    "todo_stale": 0.3,      # ② 久未做某事（created_at 老化 >STALE_DAYS）
    "user_idle": 0.2,       # ⑥ 久未理
    "task_done": 0.2,       # ⑪ 完成汇报（Phase 0 占位）
}
STALE_DAYS = 7   # 久未做阈值（天）——todos 表无 due_date 列，用 created_at 老化

ENABLE_ENV = "XIAOJU3_PROACTIVE_ENABLED"
DB_ENV = "XIAOJU3_PROACTIVE_DB_PATH"


def proactive_enabled():
    """开关（缺省关——Phase 0 生命线：现有测试与生产行为零影响）。"""
    return str(os.environ.get(ENABLE_ENV, "0")).strip().lower() in ("1", "true", "on")


def _db_path():
    """proactive.db 路径：注入键（测试）> xiaoju3.AGENT_STATE_DIR（frozen
    路径陷阱铁律：一律 import xiaoju3，禁 __file__ fallback）。"""
    p = os.environ.get(DB_ENV)
    if p:
        return p
    try:
        from xiaoju3 import AGENT_STATE_DIR as state_dir
        if state_dir:
            return os.path.join(state_dir, "proactive.db")
    except Exception:
        pass
    return os.path.join("agent_state", "proactive.db")


def _connect():
    """懒创建连接：只在真实写入路径调用（开关关时整链不触达=不建库）。"""
    os.makedirs(os.path.dirname(os.path.abspath(_db_path())), exist_ok=True)
    con = sqlite3.connect(_db_path(), timeout=3.0)
    con.execute("""CREATE TABLE IF NOT EXISTS tension_state (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        tension REAL NOT NULL DEFAULT 0.0,
        last_fire_at TEXT,
        updated_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS proactive_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT,
        action TEXT,
        decision TEXT,
        reason TEXT)""")
    return con


def _load_state(now):
    """读单行状态（无行则初始化零张力；读取异常回退零态——静默纪律）。"""
    try:
        con = _connect()
        row = con.execute(
            "SELECT tension, last_fire_at FROM tension_state WHERE id = 1"
        ).fetchone()
        con.close()
        if row:
            return {"tension": float(row[0] or 0.0), "last_fire_at": row[1]}
    except Exception:
        pass
    return {"tension": 0.0, "last_fire_at": None}


def _save_state(tension, last_fire_at, now):
    """写单行状态（UPSERT；失败静默——审计绝不影响主链）。"""
    try:
        con = _connect()
        con.execute(
            "INSERT INTO tension_state (id, tension, last_fire_at, updated_at) "
            "VALUES (1, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "tension = excluded.tension, last_fire_at = excluded.last_fire_at, "
            "updated_at = excluded.updated_at",
            (round(tension, 4), last_fire_at, now.isoformat(timespec="seconds")))
        con.commit()
        con.close()
    except Exception:
        pass


def _append_log(action, decision, reason, now):
    """审计追加（#316：出手/静默两态都记）+ 滚动保留 LOG_KEEP。"""
    try:
        con = _connect()
        con.execute(
            "INSERT INTO proactive_log (ts, action, decision, reason) "
            "VALUES (?, ?, ?, ?)",
            (now.isoformat(timespec="seconds"), action, decision, reason))
        con.execute(
            "DELETE FROM proactive_log WHERE id NOT IN "
            "(SELECT id FROM proactive_log ORDER BY id DESC LIMIT ?)",
            (LOG_KEEP,))
        con.commit()
        con.close()
    except Exception:
        pass


def _decay(tension, last_ts, now):
    """时间衰减 ×DECAY_PER_HOUR/h（小时级，与 mood β 同口径）；无时标不衰减。"""
    if not last_ts:
        return tension
    try:
        dt = now - datetime.fromisoformat(last_ts)
        hours = max(0.0, dt.total_seconds() / 3600.0)
        return tension * (DECAY_PER_HOUR ** hours)
    except Exception:
        return tension


def in_quiet_hours(now):
    """深夜时段（design §五① 默认 23:00–7:00 跨零点）。"""
    h = now.hour
    return h >= QUIET_HOURS[0] or h < QUIET_HOURS[1]


def recently_rejected(now=None, lookback_hours=6):
    """抑制②：刚被拒/无视——读 relationship.db rel_event_log 近期负向事件
    （scolded）；**只读不写**，库不存在/查询异常优雅降级 False（三文件可删
    纪律——relationship 整体删除时本探针静默失效）。"""
    now = now or datetime.now()
    try:
        p = _rel_db_path()
        if not p or not os.path.isfile(p):
            return False
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=2.0)
        cutoff = (now - timedelta(hours=lookback_hours)).isoformat(timespec="seconds")
        row = con.execute(
            "SELECT COUNT(*) FROM rel_event_log "
            "WHERE event = 'scolded' AND ts >= ?", (cutoff,)).fetchone()
        con.close()
        return bool(row and row[0])
    except Exception:
        return False


def _rel_db_path():
    """relationship.db 路径探针（与 relationship.py 同源逻辑，只读）。"""
    try:
        from xiaoju3 import AGENT_STATE_DIR as state_dir
        if state_dir:
            return os.path.join(state_dir, "relationship.db")
    except Exception:
        pass
    return os.path.join("agent_state", "relationship.db")


def in_cooldown(last_fire_at, now, seconds=COOLDOWN_SECONDS):
    """抑制③：刚找过（默认 30 分钟冷却）。"""
    if not last_fire_at:
        return False
    try:
        dt = now - datetime.fromisoformat(last_fire_at)
        return 0 <= dt.total_seconds() < seconds
    except Exception:
        return False


def user_busy(now=None):
    """抑制④：用户忙（Phase 0 最小实现=占位 False；大任务/全屏启发
    Phase 1 接——先立骨架让抑制表完整，行为与未实现等价）。"""
    return False


def told_not_to_bother(now=None):
    """抑制⑤：用户明说别烦我（Phase 0 最小实现=当日显式指令标记；
    Phase 0 无指令通路 → 占位 False，Phase 1 接指令拦截写标记）。"""
    return False


def _collect_events(now):
    """Phase 0 事件源（2026-10-12 修复哑火——原 SQL 查 todos 表不存在的
    due_date 列，OperationalError 被裸 except 吞掉 880 分钟，坑库 #21）：
    - todo_stale：pending 中存在 created_at 老化 >STALE_DAYS（真实列）；
    - user_idle：history_console 最近修改时间距今 > 4h；
    - task_done：Phase 0 暂无独立信号源，占位不计。
    事件源探测失败**不再静默**：写 proactive_log 一条 event_source_error
    （#316 静默可解释自我适用——审计自身失败再兜底忽略）。全部只读。"""
    events = []
    errors = []
    try:
        todos_db = None
        try:
            from xiaoju3 import AGENT_STATE_DIR as state_dir
            if state_dir:
                todos_db = os.path.join(state_dir, "todos.db")
        except Exception:
            todos_db = os.path.join("agent_state", "todos.db")
        if todos_db and os.path.isfile(todos_db):
            con = sqlite3.connect(f"file:{todos_db}?mode=ro", uri=True, timeout=2.0)
            cutoff = (now - timedelta(days=STALE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
            stale = con.execute(
                "SELECT COUNT(*) FROM todos WHERE status = 'pending' "
                "AND created_at < ?", (cutoff,)).fetchone()
            con.close()
            if stale and stale[0]:
                events.append(("todo_stale", EVENT_DELTAS["todo_stale"]))
    except Exception as e:
        errors.append(f"todos:{type(e).__name__}:{e}")
    try:
        # 路径锚（#319 前置侦察修正）：history_console 在 DATA_ROOT/xiaoju3_data/
        # （非 agent_state）——DATA_ROOT 锚与 cwd 解耦（c6dc178 同族，
        # 防多终端/换目录哑火）
        from paths import DATA_ROOT as _data_root
        hist = os.path.join(_data_root, "xiaoju3_data", "history_console.json")
        if os.path.isfile(hist):
            age_h = (now.timestamp() - os.path.getmtime(hist)) / 3600.0
            if age_h >= 4.0:
                events.append(("user_idle", EVENT_DELTAS["user_idle"]))
    except Exception as e:
        errors.append(f"history:{type(e).__name__}:{e}")
    for e in errors:   # #316 自我适用：事件源断链第一天可见（审计自身失败再兜底）
        try:
            _append_log("event_source", "error", e[:180], now)
        except Exception:
            pass
    return events


def proactive_tick(now=None):
    """心跳挂载入口（每轮 60s 调一次；出手慢靠冷却/抑制内建，tick 快无妨）。
    Phase 0 的 fire=只写审计不发消息（design §八 Phase 0 定义）。"""
    now = now or datetime.now()
    if not proactive_enabled():
        return None   # 开关关：早退，不建库不写日志（§6 生命线）
    st = _load_state(now)
    tension = _decay(st["tension"], st["last_fire_at"], now)
    for name, delta in _collect_events(now):
        tension = min(CLAMP_MAX, tension + delta)
    sup = []
    if in_quiet_hours(now):
        sup.append("quiet_hours")
    if recently_rejected(now):
        sup.append("rejected")
    if in_cooldown(st["last_fire_at"], now):
        sup.append("cooldown")
    if user_busy(now):
        sup.append("user_busy")
    if told_not_to_bother(now):
        sup.append("explicit_stop")
    last_fire = st["last_fire_at"]
    fired = False
    if tension >= FIRE_THRESHOLD and not sup:
        fired = True
        _append_log("tension_release", "fire",
                    f"tension={tension:.2f}", now)
        tension = 0.0
        last_fire = now.isoformat(timespec="seconds")
    else:
        reason = ",".join(sup) if sup else f"tension={tension:.2f}<{FIRE_THRESHOLD}"
        _append_log("tension_build", "suppress", reason, now)
    _save_state(tension, last_fire, now)
    return {"tension": round(tension, 4), "suppressed": bool(sup),
            "fired": fired}
