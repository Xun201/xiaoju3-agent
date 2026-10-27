# -*- coding: utf-8 -*-
"""qq_lifemate · QQ 赛博生命体（#354，切片 a 文字唤醒最小闭环）。

定位（队长拍板口径）：不复刻"大肥鱼"，借鉴其理念（主动唤醒/记忆沉淀/
拟人多模态）结合小橘插件总线长出的小橘专属 QQ 生命体。
★第一指导原则（#354 note）：成败不在模型，在记忆的持久化与鲜活度——
模型不是完整的她，加上长期记忆才是独一无二的她。

切片 a 范围：独立记忆库四表 + 主动唤醒线程（waker.py：静默 4h + quiet
23:00-08:00 + 一天 5 次硬帽）+ scene 场景接续（禁止冷启动尬聊）+
record_fact/scene_report/recall_fact 三个记忆工具。
语音/表情/群聊/对话镜像留切片 b/c。拍板记录见 waker.py 常量注释。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import waker  # noqa: E402  （同目录 waker.py：数据层+唤醒线程，共享状态单一归属）


# ────────────────────────── 模型工具（ext_ 前缀强制） ──────────────────────────

def record_fact(key="", value="", **_):
    """固化长期记忆（第一指导原则）：值得记住的核心事实（喜欢吃什么、
    讨厌什么、重要日子）写进 facts 表——模型在 QQ 对话中自己调用。"""
    key, value = str(key or "").strip(), str(value or "").strip()
    if not key or not value:
        return "❌ 要记的话请同时告诉我：记什么（key）和内容（value）。"
    db = waker._db()
    try:
        db.execute("INSERT INTO facts(key, value, ts) VALUES(?,?,?) "
                   "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                   "ts=excluded.ts", (key[:60], value[:300], waker.now_str()))
        db.commit()
        return f"🦊 记住啦：{key} = {value}"
    finally:
        db.close()


def scene_report(action="", **_):
    """场景状态上报（场景注入的燃料）：模型自述"我现在在干嘛"——主动
    唤醒时据此自然接续，防状态脱节（"在门口蹲着等你"反例实锤）。"""
    action = str(action or "").strip()
    if not action:
        return "❌ 告诉我现在在做什么（一句话）。"
    db = waker._db()
    try:
        db.execute("INSERT INTO scene(action, ts) VALUES(?,?)",
                   (action[:120], waker.now_str()))
        if db.execute("SELECT COUNT(*) FROM rel").fetchone()[0] == 0:
            db.execute("INSERT INTO rel(interactions, mood) "
                       "VALUES(1, 'neutral')")
        else:
            db.execute("UPDATE rel SET interactions = interactions + 1 "
                       "WHERE id = 1")
        db.commit()
        return f"🦊 状态已记录：{action}"
    finally:
        db.close()


def recall_fact(key="", **_):
    """查一条长期记忆（模型自己回忆用）。"""
    key = str(key or "").strip()
    db = waker._db()
    try:
        row = db.execute("SELECT value, ts FROM facts WHERE key=?",
                         (key[:60],)).fetchone()
        if not row:
            return f"🦊 我还没记过「{key}」这件事。"
        return f"🦊 记得：「{key}」= {row[0]}（{row[1]} 记下的）"
    finally:
        db.close()


# ────────────────────────── 生命周期 ──────────────────────────

def setup(ctx):
    """建表 + 启动唤醒线程（daemon；钩子超时由 loader 兜底）。"""
    waker.set_data_dir(ctx.get("data_dir") or ".")
    db = waker._db()
    db.close()
    waker.start()
    ctx.get("log")(f"qq_lifemate setup：data={waker.data_dir()}，"
                   f"唤醒线程已启动")


def teardown():
    """停唤醒线程（卸载即冬眠，零残留）。"""
    waker.stop()


def PLUGIN():
    return {
        "name": "qq_lifemate",
        "version": "0.1.0",
        "desc": "QQ 赛博生命体（#354 切片 a）：独立记忆四表+静默唤醒"
                "（4h/quiet 23-8/日限 5）+场景接续+记忆固化工具",
        "author": "xun",
        "level": 3,
        "tools": [
            {"name": "ext_record_fact",
             "desc": "把主人告诉你的重要事实（喜好/习惯/日子）固化进你的"
                     "长期记忆，以后随时能想起来",
             "params": "key (记什么，如'喜欢的饮料'), value (具体内容)",
             "note": "当主人说「记住我喜欢…/以后记得…」时使用",
             "handler": "agent_state_plugins_qq_lifemate:record_fact"},
            {"name": "ext_scene_report",
             "desc": "上报你当前的动作/状态场景——主动找主人聊天时会自然"
                     "接续，防止说话与真实状态脱节",
             "params": "action (一句话描述现在在干嘛)",
             "note": "每次对话结束或状态变化时主动调用一次",
             "handler": "agent_state_plugins_qq_lifemate:scene_report"},
            {"name": "ext_recall_fact",
             "desc": "回忆一条记过的长期记忆",
             "params": "key (要回忆什么)",
             "note": "当主人问「你还记得…吗」时使用",
             "handler": "agent_state_plugins_qq_lifemate:recall_fact"},
        ],
        "intents": [],
        "setup": setup,
        "teardown": teardown,
    }
