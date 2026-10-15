# -*- coding: utf-8 -*-
"""小橘3号 · 演化放权统一件（autonomy.py，#297 二期/design_297_phase2_unified §一，2026-10-15）。

三态放权阶梯的通用状态机：report（提之前先问）→ checkpoint（有把握
才做，不确定仍问）→ autonomous（自主+用户可随时纠正）。域实例化：
- memory_disclosure（情绪记忆提及，disclosure.py 消费）；
- persona_trigger（D2=A 预留，未实施）。
**域上限=2（2026-10-15 用户拍板）：再加域必须重新评估是否需要统一件**
——防通用件膨胀成万能框架（演化放权框架批注）。

状态机语义（拍板 E3，phase3 口径）：
- promote：连续 N=5 次**未被纠正**的使用升一档（autonomous 封顶；
  checkpoint→autonomous 需累计 10）；
- 负面段使用不计 streak（负面段不参与自主毕业，phase3 §二收紧）；
- demote：纠正 1 次退一档且 streak 清零重攒；连续 2 次纠正直退 report；
- manual 钉档（set_phase via="manual"）压过自动升降，转换落流水审计；
- gate：report→ask；checkpoint→正面 direct/负面 ask；autonomous→direct
  （负面只报结果=内容约束，在域实例文案侧）。

状态文件：AGENT_STATE_DIR/autonomy_state.json（域键隔离，E2 合并口径；
env XIAOJU3_AUTONOMY_STATE_PATH 可覆盖供测试）。损坏/缺失 → 全域回退
report（宁慢勿快）。读写原子（tmp+os.replace）。
"""
import copy
import json
import os
from datetime import datetime

STATES = ("report", "checkpoint", "autonomous")
DEFAULT_STATE = "report"
PROMOTE_N = 5                                # 连续未纠正 N 次升一档
CONSECUTIVE_CORRECTIONS_TO_RESET = 2         # 连续纠正 N 次直退 report


def _state_path():
    """状态文件路径：env 覆盖 > AGENT_STATE_DIR/autonomy_state.json
    （frozen 归位铁律：import xiaoju3 取归位常量，__file__ 同防）。"""
    p = os.environ.get("XIAOJU3_AUTONOMY_STATE_PATH")
    if p:
        return p
    try:
        import xiaoju3
        base = xiaoju3.AGENT_STATE_DIR
    except Exception:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "agent_state")
    return os.path.join(base, "autonomy_state.json")


def default_domain(now=None):
    """域缺省态：report 起步（宁慢勿快）。"""
    return {"phase": DEFAULT_STATE,
            "phase_since": str(now or datetime.now()),
            "uncorrected_streak": 0,
            "consecutive_corrections": 0,
            "corrections": [],      # 纠正/转换流水（审计）
            "data": {}              # 域私有数据（overrides/频次账等）
            }


def load_domains():
    """读全部域（文件缺失/损坏 → {}，域读取侧逐域兜缺省）。"""
    try:
        with open(_state_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and isinstance(
            data.get("domains"), dict) else {}
    except Exception:
        return {}


def save_domains(domains):
    """原子写全部域（tmp+os.replace；失败静默——状态件绝不炸调用方）。"""
    try:
        path = _state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"domains": domains}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def load_domain(name):
    """读单域（缺域/坏域 → 缺省 report 态；域名未登记=域上限护栏拦截点）。"""
    d = load_domains().get(name)
    if not isinstance(d, dict) or d.get("phase") not in STATES:
        return default_domain()
    base = default_domain(now=d.get("phase_since"))
    for k, v in base.items():
        d.setdefault(k, v)
    return d


def save_domain(name, d):
    """写单域（读合并写；并发口径=单机单进程，文件级 last-write-wins）。"""
    domains = load_domains()
    domains[name] = d
    return save_domains(domains)


def _set_phase(d, phase, via, now=None):
    """内部：换档+流水（copy 后的 d 上原地改）。"""
    d["phase"] = phase
    d["phase_since"] = str(now or datetime.now())
    d["corrections"].append({"ts": d["phase_since"], "kind": "phase",
                             "via": via, "to": phase})


def record_use(d, polarity="positive", now=None):
    """未纠正使用一次（纯函数：deepcopy 后改，返回新 dict）。

    - streak +1 且连续纠正计数清零；负面段使用不加 streak（不参与毕业）；
    - streak 达阈值 → 自动升档（report→checkpoint @5；
      checkpoint→autonomous @累计 10）。
    """
    d = copy.deepcopy(d)
    now = now or datetime.now()
    d["consecutive_corrections"] = 0
    if polarity == "positive":
        d["uncorrected_streak"] += 1
        if (d["phase"] == "report"
                and d["uncorrected_streak"] >= PROMOTE_N):
            _set_phase(d, "checkpoint", "auto", now)
        elif (d["phase"] == "checkpoint"
                and d["uncorrected_streak"] >= PROMOTE_N * 2):
            _set_phase(d, "autonomous", "auto", now)
    return d


def record_correction(d, now=None):
    """用户纠正一次（"这个别提"类；纯函数）。连续纠正计数 +1、streak
    清零、退一档（report 为底）；连续 2 次纠正直退 report。"""
    d = copy.deepcopy(d)
    now = now or datetime.now()
    d["consecutive_corrections"] += 1
    d["uncorrected_streak"] = 0
    if d["consecutive_corrections"] >= CONSECUTIVE_CORRECTIONS_TO_RESET:
        _set_phase(d, "report", "correction", now)
    elif d["phase"] != "report":
        idx = STATES.index(d["phase"])
        _set_phase(d, STATES[max(0, idx - 1)], "correction", now)
    return d


def set_phase(d, phase, now=None, via="manual"):
    """手动钉档（用户拍板直改；压过自动升降——自动阈值仍以 streak 计，
    钉档后从新档位继续攒）。非法档位原样返回。"""
    if phase not in STATES:
        return copy.deepcopy(d)
    d = copy.deepcopy(d)
    _set_phase(d, phase, via, now)
    return d


def gate(phase, polarity):
    """放权闸（纯函数）：返回 "direct"（直接提及）或 "ask"（先问）。

    report→一律 ask；checkpoint→正面 direct/负面 ask；
    autonomous→direct（负面只报结果的文案约束在域实例侧）。"""
    if phase == "report":
        return "ask"
    if phase == "checkpoint":
        return "direct" if polarity == "positive" else "ask"
    return "direct"
