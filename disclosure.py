# -*- coding: utf-8 -*-
"""小橘3号 · 情绪记忆披露域（disclosure.py，#297 二期/design_297_phase2_unified
§二小批 2.2，2026-10-15）。

autonomy 统一件的 memory_disclosure 域实例：情绪段记忆"提不提、怎么提、
何时提"（design_297_emotional_memory.md §七可感知性四维 +
design_297b_phase3_disclosure.md 消费侧过滤层）。

- B3 频次：同一段 7 天内不重复提（boost 豁免）；
- C2+C4 内容：正面自然提；负面只在你问时提、只提结果不提细节（文案在
  2.3 注入分支侧，本模块只产出 gate 决定）；
- manual_overrides：mute（"这个别提"→该段任何 phase 不提+纠正降档）/
  boost（"这个该多提"→豁免频次）；
- recall 本体零改动（phase3 锚）：过滤只发生在消费侧本模块。

纯函数优先：filter_memories/note_mention/note_correction 全部 deepcopy
后改、可直调锚定；IO 只在 load/save。
"""
import copy
import json
import sqlite3
from datetime import datetime

import autonomy
import mood

DOMAIN = "memory_disclosure"
MUTE = "mute"
BOOST = "boost"
B3_DAYS = 7                    # 同一段 7 天内不重复提（频次 B3）


def load():
    """读披露域（autonomy 文件域键；缺省 report 态）。"""
    return autonomy.load_domain(DOMAIN)


def save(d):
    """写披露域。"""
    return autonomy.save_domain(DOMAIN, d)


def episode_associations():
    """memory_id → {"start_ts","tag"} 段关联反查（mood 侧公共读，纯读；
    异常静默空表——无关联=全走普通直注=零行为变化）。"""
    return mood.episode_associations()


def filter_memories(rows, associations=None, d=None, now=None):
    """消费侧过滤层（批 2.2 核心，纯函数）。

    rows：recall 行 [(id, category, content, weight, emotion_tag,
    sink_status)]（state_manager 同形态）。返回 (direct_rows, ask_rows)：
    - 无段关联的普通行 → 直接注入（现状行为，逐字节透传）；
    - 段关联行走门：manual mute → 丢弃；7 天内已提（B3）→ 丢弃（boost
      豁免）；autonomy.gate(phase, polarity) → direct 入 direct / ask 入
      ask_rows（2.3 渲染问句）。
    """
    d = d if d is not None else load()
    assoc = associations if associations is not None else episode_associations()
    now = now or datetime.now()
    data = d.get("data") or {}
    phase = d.get("phase", "report")
    direct, asks = [], []
    for row in rows:
        a = assoc.get(row[0])
        if a is None:
            direct.append(row)           # 普通记忆：现状行为
            continue
        verdict = _gate_episode(phase, a.get("start_ts"),
                                ("positive" if a.get("tag") == "positive"
                                 else "negative"), data, now)
        if verdict == "drop":
            continue
        (direct if verdict == "direct" else asks).append(row)
    return direct, asks


def _gate_episode(phase, start_ts, polarity, data, now):
    """单段门决策（filter/split 共用语义，纯函数）：
    "direct" / "ask" / "drop"。"""
    overrides = data.get("manual_overrides") or {}
    if overrides.get(start_ts) == MUTE:
        return "drop"                    # 用户说了"这个别提"
    mentioned = (data.get("last_mentioned") or {}).get(start_ts)
    if mentioned and overrides.get(start_ts) != BOOST:
        try:
            age = (now - datetime.strptime(
                mentioned, "%Y-%m-%d %H:%M:%S")).days
        except ValueError:
            age = B3_DAYS                # 账目坏 = 按已提处理（保守）
        if age < B3_DAYS:
            return "drop"                # 频次 B3：7 天内提过不再提
    return autonomy.gate(phase, polarity)


def note_mention(d, episode_start, polarity="positive", now=None):
    """一段被提及（2.3 注入分支调用）：频次账落 last_mentioned；
    正面段计 streak（毕业判定 B；负面段不参与自主毕业）。纯函数。"""
    d = copy.deepcopy(d)
    now = now or datetime.now()
    data = d.setdefault("data", {})
    data.setdefault("last_mentioned", {})[episode_start] = str(now)
    return autonomy.record_use(d, polarity=polarity, now=now)


def note_correction(d, episode_start, kind, text="", now=None):
    """用户纠正（2.3 关键词分支调用："这个别提"=mute / "该多提"=boost）。

    mute：manual_overrides 落账（该段任何 phase 不提）+ 纠正降档
    （autonomy.record_correction）+ 流水；boost：只落偏好不降档。纯函数。"""
    d = copy.deepcopy(d)
    now = now or datetime.now()
    data = d.setdefault("data", {})
    data.setdefault("manual_overrides", {})[episode_start] = kind
    corrections = d.setdefault("corrections", [])
    corrections.append({"ts": str(now), "episode_start": episode_start,
                        "kind": kind, "text": text})
    if kind == MUTE:
        d = autonomy.record_correction(d, now=now)
    return d


# ==================== 注入链分流 + 想听闭环（批 2.3，2026-10-15） ====================

PENDING_ASK_TTL_SECONDS = 86400     # 问句应答窗口 24h（隔天旧账不作数）


def _memory_contents_by_ids(ids):
    """id → content（跨库只读 memories；异常静默空表）。"""
    try:
        conn = sqlite3.connect(mood._memories_db_path())
        try:
            q = ",".join("?" * len(ids))
            return {r[0]: r[1] for r in conn.execute(
                f"SELECT id, content FROM memories WHERE id IN ({q})",
                list(ids))}
        finally:
            conn.close()
    except Exception:
        return {}


def split_recall_rows(rows, now=None):
    """注入链分流（2.3 核心）：recall 二元组行 [(category, content)] →
    (direct_rows, ask_rows, pending, meta_by_content)。

    - 候选=episode_associations ⨝ memories.content（recall 无 id 的适配，
      F1 内容键；同文重复坍缩为同一 gate 决定——同文=同段=同决定）；
    - direct 行保持原相对顺序（普通+过闸情绪段混排），brain 现状渲染
      循环原样复用；无候选/异常 → (list(rows), [], None, {})（现状
      行为零变化硬门兜底）；
    - asks=[(category, content, meta)]；pending={"episodes":[{start_ts,
      polarity,memory_ids}],"ts"} 供"想听"应答闭环。
    """
    try:
        assoc = episode_associations()
        if not assoc:
            return list(rows), [], None, {}
        all_ids = sorted({mid for a in assoc.values()
                          for mid in (a.get("memory_ids") or [])})
        contents = _memory_contents_by_ids(all_ids)
        cand = {}
        for mid, a in assoc.items():
            content = contents.get(mid)
            if content is None:
                continue
            cand[content] = {"start_ts": a.get("start_ts"),
                             "polarity": ("positive" if a.get("tag") == "positive"
                                          else "negative"),
                             "memory_ids": [mid]}
        if not cand:
            return list(rows), [], None, {}
        now = now or datetime.now()
        d = load()
        data = d.get("data") or {}
        phase = d.get("phase", "report")
        direct, asks = [], []
        pend_eps, meta_by_content = {}, {}
        for row in rows:
            category, content = row[0], row[1]
            info = cand.get(content)
            if info is None:
                direct.append((category, content))
                continue
            verdict = _gate_episode(phase, info["start_ts"],
                                    info["polarity"], data, now)
            if verdict == "drop":
                continue
            meta_by_content[content] = info
            if verdict == "direct":
                direct.append((category, content))
            else:
                asks.append((category, content, info))
            pend_eps[info["start_ts"]] = info
        pending = ({"episodes": list(pend_eps.values()), "ts": str(now)}
                   if pend_eps else None)
        return direct, asks, pending, meta_by_content
    except Exception:
        return list(rows), [], None, {}


def note_pending_ask(d, pending):
    """记待应答问句（纯函数）：data.pending_ask（想听闭环用）。"""
    d = copy.deepcopy(d)
    if pending:
        (d.setdefault("data", {}))["pending_ask"] = pending
    return d


def get_pending_ask(d, now=None):
    """取新鲜（≤24h）待应答问句；过期/缺失 → None。"""
    pending = (d.get("data") or {}).get("pending_ask") or {}
    if not pending.get("episodes"):
        return None
    try:
        ts = datetime.strptime(pending["ts"], "%Y-%m-%d %H:%M:%S")
    except (KeyError, ValueError):
        return None
    now = now or datetime.now()
    if (now - ts).total_seconds() > PENDING_ASK_TTL_SECONDS:
        return None
    return pending


def pending_contents(pending):
    """pending → [(content, polarity)]（应答展开素材；异常静默空表）。"""
    out = []
    try:
        ids, polars = [], []
        for ep in pending.get("episodes", []):
            polars.append((ep.get("start_ts"),
                           ep.get("polarity", "positive")))
            ids.extend(ep.get("memory_ids") or [])
        contents = _memory_contents_by_ids(ids)
        for ep in pending.get("episodes", []):
            for mid in ep.get("memory_ids") or []:
                content = contents.get(mid)
                if content:
                    out.append((content, ep.get("polarity", "positive")))
    except Exception:
        return []
    return out
