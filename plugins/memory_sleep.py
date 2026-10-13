# -*- coding: utf-8 -*-
"""plugins/memory_sleep · #297 批 2 记忆睡眠批处理（exp04 sleep_cycle 主项目版）。

心跳每天 1 次离线巩固（todo_aging 同款插件槽：静态 import + try/except
静默 + 幂等闸）。开关 = XIAOJU3_MEMORY_V2（缺省关——关=首行早退零副作用，
与召回链同一总开关，2026-10-13 拍板）。

四步（顺序对应睡眠神经生物学分期，参数同 exp04 口径）：
  1) night_decay   隔夜衰减：全表 weight ×0.95（下限 0.01 永不绝对归零）；
  2) replay        重放强化：access_count ≥2 按频率 ×(1+bonus)，其中
                   bonus = 0.30×min(ac,4)/4 + 情绪项 0.5×min(impact,0.8)/0.8
                   （情绪记忆巩固远高于普通——#297 情绪记忆 P0 子项）；
                   回放后夹钳 WEIGHT_MAX=3.0（拍板③睡眠侧）；
  3) consolidate   关联巩固：coactivation ≥2 的边 ×(1+0.20×min(co,6)/6)；
  4) sink          低权下沉：weight <0.30 且不在重放集且
                   emotional_impact <0.4 → pending_sink（打标不删；
                   情绪记忆近永留 = EMO_SINK_GUARD 豁免）。

审计：sleep_log 每动作一条（exp04 口径）；activation_log 7 天前旧行
清理挂批处理尾部（膨胀控制）。幂等闸：memory_meta.sleep_last_date
（同天重入返回 None；只在成功完成后写入——失败次日自动重试）。
睡眠状态属记忆库，自立 memory_meta 门户（todos_meta 在 todos.db，跨库）。
"""
import os
import sqlite3
from datetime import datetime, timedelta

from xiaoju3 import AGENT_STATE_DIR

# ---- 睡眠批处理参数（exp04 同口径；design_297_memory_merge_v2.md §6）----
NIGHT_DECAY = 0.95
WEIGHT_FLOOR = 0.01        # 永不绝对归零（exp01 口径）
REPLAY_MIN = 2             # 重放资格：access_count 下限
REPLAY_CAP = 4             # 使用频率封顶（ac≥4 一视同仁）
REWARD = 0.30              # 满额重放奖励（ac=CAP 时 ×1.30）
EDGE_MIN_CO = 2            # 巩固资格：共激活次数下限
EDGE_CAP = 6               # 共激活封顶
EDGE_REWARD = 0.20         # 满额边强化
SINK_THRESHOLD = 0.30      # 下沉阈值（且不在重放集）
WEIGHT_MAX = 3.0           # 拍板③：睡眠回放后夹钳（与召回侧同上限）
EMO_REWARD = 0.5           # 情绪巩固权重（远高于普通 REWARD 上限）
EMO_CAP = 0.8              # impact 封顶（偏离基线 0.8 已是很强情绪）
EMO_SINK_GUARD = 0.4       # sink 豁免阈：情绪记忆近永留
LOG_RETENTION_DAYS = 7     # activation_log 膨胀控制
SLEEP_META_KEY = "sleep_last_date"


def enabled():
    """开关：XIAOJU3_MEMORY_V2 缺省关（与 brain._memory_v2_enabled 同口径；
    本地重实现保持插件自包含可删纪律，不反向依赖 brain）。"""
    return str(os.environ.get("XIAOJU3_MEMORY_V2", "0")).strip().lower() \
        in ("1", "true", "on")


def _db_path():
    """long_term.db 路径：StateManager 单例同源（frozen 路径铁律——
    单例 memory_db 已按 xiaoju3.AGENT_STATE_DIR 解析）。"""
    from agent_state.state_manager import state_manager
    return state_manager.memory_db


def run_daily_sleep(db_path=None, now=None):
    """一天一次睡眠四步批处理；返回汇总 dict 或 None。

    - 开关关（XIAOJU3_MEMORY_V2 缺省关）→ None 零副作用；
    - memory_meta.sleep_last_date 幂等闸：同天已跑 → None；
    - 空库 → None 不空转（也不写闸）；
    - 任何 SQLite 异常 → 打印 ⚠️ 返回 None（绝不抛出干扰心跳）；
    - db_path/now 显式传参仅供测试隔离。
    """
    if not enabled():
        return None
    now = now or datetime.now()
    today = now.strftime("%Y-%m-%d")
    db_path = db_path or _db_path()
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        last = conn.execute(
            "SELECT value FROM memory_meta WHERE key=?",
            (SLEEP_META_KEY,)).fetchone()
        if last and last[0] == today:
            return None
        count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        if count == 0:
            return None
        log = []
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        def _log(action, target, before, after):
            conn.execute(
                "INSERT INTO sleep_log (cycle, action, target, before,"
                " after, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (today, action, target, before, after, now_str))
            log.append((action, target, before, after))

        # 四步单事务（无中间 commit）：任一步异常整体回滚=零部分生效，
        # 幂等闸未写=次日自动完整重试（分步 commit 会衰减两次）
        # ① 隔夜时间流逝（下限 WEIGHT_FLOOR 永不绝对归零）
        conn.execute("UPDATE memories SET weight = MAX(weight * ?, ?)",
                     (NIGHT_DECAY, WEIGHT_FLOOR))

        # ② 重放强化（NREM 海马回放：高频按使用频率 + 情绪加权巩固）
        replay_ids = [r[0] for r in conn.execute(
            "SELECT id FROM memories WHERE access_count >= ?"
            " ORDER BY access_count DESC", (REPLAY_MIN,)).fetchall()]
        for rid in replay_ids:
            ac, content, w, impact = conn.execute(
                "SELECT access_count, content, weight, emotional_impact"
                " FROM memories WHERE id=?", (rid,)).fetchone()
            bonus = REWARD * min(ac, REPLAY_CAP) / REPLAY_CAP
            bonus += EMO_REWARD * min(impact or 0.0, EMO_CAP) / EMO_CAP
            after = round(min(w * (1 + bonus), WEIGHT_MAX), 4)
            conn.execute("UPDATE memories SET weight=? WHERE id=?",
                         (after, rid))
            _log("replay", content, w, after)

        # ③ 关联巩固（回放连带强化共激活联想边）
        for fid, tid, ew, co in conn.execute(
                "SELECT from_id, to_id, weight, coactivation_count"
                " FROM memory_edge WHERE coactivation_count >= ?",
                (EDGE_MIN_CO,)).fetchall():
            bonus = EDGE_REWARD * min(co, EDGE_CAP) / EDGE_CAP
            after = round(ew * (1 + bonus), 4)
            conn.execute(
                "UPDATE memory_edge SET weight=? WHERE from_id=? AND to_id=?",
                (after, fid, tid))
            _log("consolidate", f"{fid}<->{tid}", ew, after)

        # ④ 低权下沉（SHY 稳态修剪：打标不删；不在重放集；情绪记忆豁免）
        sinked = 0
        for rid, content, w in conn.execute(
                "SELECT id, content, weight FROM memories"
                " WHERE weight < ? AND sink_status = 'active'"
                " AND emotional_impact < ?",
                (SINK_THRESHOLD, EMO_SINK_GUARD)).fetchall():
            if rid in replay_ids:
                continue
            conn.execute(
                "UPDATE memories SET sink_status='pending_sink' WHERE id=?",
                (rid,))
            _log("sink", content, w, w)
            sinked += 1

        # ⑤ activation_log 膨胀控制（7 天前旧行清理）
        cutoff = (now - timedelta(days=LOG_RETENTION_DAYS)).strftime(
            "%Y-%m-%d %H:%M:%S")
        conn.execute("DELETE FROM activation_log WHERE timestamp < ?",
                     (cutoff,))

        stats = conn.execute(
            "SELECT COUNT(*), AVG(weight) FROM memories"
            " WHERE sink_status='active'").fetchone()
        conn.execute(
            "INSERT OR REPLACE INTO memory_meta (key, value) VALUES (?, ?)",
            (SLEEP_META_KEY, today))
        conn.commit()
        return {
            "date": today,
            "replayed": len(replay_ids),
            "edges_consolidated": sum(1 for a, *_ in log
                                      if a == "consolidate"),
            "sinked": sinked,
            "active_nodes": stats[0],
            "active_avg_weight": round(stats[1], 4) if stats[1] is not None
            else 0.0,
        }
    except sqlite3.Error as e:
        print(f"⚠️ [记忆睡眠] 执行失败（已跳过，次日重试）: {e}")
        return None
    finally:
        conn.close()
