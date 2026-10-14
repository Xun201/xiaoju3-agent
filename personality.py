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

分批落地（v2 稿 §七）：批 1 只立存储与开关（无调用方消费前全仓行为与
现状逐字节一致）；批 2 判定算法 judge_mode/maybe_rejudge；批 3 brain
后缀链挂点 mode_suffix。

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
from datetime import datetime

import relationship

# ---- 模式枚举与开关定义（ASCII 稳定键，#297 mood_factor 同款规范）----
MODES = ("banter", "dependent", "polite", "caring")
DEFAULT_MODE = "polite"          # 新用户/证据不足/任何异常一律客气档
MANUAL_CONFIDENCE = 1.0

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


def _write_mode(user_id, mode, confidence, source, evidence=None):
    """落一行 rel_mode（INSERT OR REPLACE；judged_at=此刻）。"""
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO rel_mode (user_id, mode,"
                " confidence, source, judged_at, evidence)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (str(user_id), mode, float(confidence), source,
                 datetime.now().isoformat(sep=" ", timespec="seconds"),
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
