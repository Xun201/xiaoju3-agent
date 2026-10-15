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
    overrides = data.get("manual_overrides") or {}
    mentioned = data.get("last_mentioned") or {}
    direct, asks = [], []
    for row in rows:
        mid = row[0]
        a = assoc.get(mid)
        if a is None:
            direct.append(row)           # 普通记忆：现状行为
            continue
        start = a.get("start_ts")
        polarity = "positive" if a.get("tag") == "positive" else "negative"
        override = overrides.get(start)
        if override == MUTE:
            continue                     # 用户说了"这个别提"
        if override != BOOST and mentioned.get(start):
            try:
                age = (now - datetime.strptime(
                    mentioned[start], "%Y-%m-%d %H:%M:%S")).days
            except ValueError:
                age = B3_DAYS            # 账目坏 = 按已提处理（保守）
            if age < B3_DAYS:
                continue                 # 频次 B3：7 天内提过不再提
        if autonomy.gate(d.get("phase", "report"), polarity) == "direct":
            direct.append(row)
        else:
            asks.append(row)
    return direct, asks


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
