# -*- coding: utf-8 -*-
"""关系化人格演化批 1 测试锚（#271，design_271_personality_evolution_v2）。

范围=存储层（rel_mode 表 + event_stats + 6 开关 tri-state）——判定算法
（批 2）与表现层消费（批 3）不在本批。
隔离：XIAOJU3_RELATIONSHIP_DB_PATH → tmp（relationship 测试同款）；
persona_pref.json 路径 → monkeypatch personality._persona_pref_path。
"""
import json
import sqlite3
from datetime import datetime, timedelta

import pytest

import personality
import relationship

DAY = datetime(2026, 10, 14, 9, 0, 0)


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    db = str(tmp_path / "rel.db")
    monkeypatch.setenv("XIAOJU3_RELATIONSHIP_DB_PATH", db)
    monkeypatch.setattr(personality, "_persona_pref_path",
                        lambda path=None: str(tmp_path / "persona_pref.json"))
    monkeypatch.delenv("XIAOJU3_PERSONA_ENABLED", raising=False)
    yield db


# 1 rel_mode 表由 relationship._connect 幂等建出（生产旧库下一版打开即建）
def test_rel_mode_table_idempotent():
    for _ in range(2):   # 两次连接均不抛=幂等
        conn = relationship._connect()
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert "rel_mode" in names


# 2 无行 → 默认档（polite/default/置信 0）——与现状逐字节一致的空路径
def test_get_mode_default_when_no_row():
    m = personality.get_mode("12345")
    assert m["mode"] == "polite"
    assert m["source"] == "default"
    assert m["confidence"] == 0.0


# 3 手动指定：source=manual + 置信 1.0（用户说了算）
def test_set_mode_manual_roundtrip():
    assert personality.set_mode_manual("12345", "banter") is True
    m = personality.get_mode("12345")
    assert m["mode"] == "banter"
    assert m["source"] == "manual"
    assert m["confidence"] == 1.0
    assert m["judged_at"]


# 4 非法模式名拒绝（枚举无负档=结构上无恶意可落，v2 稿 §六）
def test_set_mode_manual_invalid_rejected():
    assert personality.set_mode_manual("12345", "hostile") is False
    assert personality.get_mode("12345")["mode"] == "polite"


# 5 解锁：clear 后回落默认档（自动判定可重新接管）
def test_clear_mode_manual():
    personality.set_mode_manual("12345", "caring")
    assert personality.clear_mode_manual("12345") is True
    assert personality.get_mode("12345")["source"] == "default"


# 6 event_stats 四类事件计数（observe_rel 真链路落的事件流）
def test_event_stats_counts():
    relationship.observe_rel("u1", "真的谢谢你", now=DAY)
    relationship.observe_rel("u1", "麻烦你了", now=DAY)
    relationship.observe_rel("u1", "你真笨", now=DAY)
    relationship.observe_rel("u1", "今天天气如何", now=DAY)
    s = relationship.event_stats("u1")
    assert (s["thanks"], s["politeness"], s["scolded"],
            s["interaction"]) == (1, 1, 1, 1)
    assert s["n_int"] == 4


# 7 event_stats since 窗口过滤（90 天窗口判定的输入语义）
def test_event_stats_since_window():
    relationship.observe_rel("u1", "谢谢你", now=DAY - timedelta(days=100))
    relationship.observe_rel("u1", "谢谢你", now=DAY)
    s = relationship.event_stats("u1", since=(DAY - timedelta(days=90))
                                 .strftime("%Y-%m-%d %H:%M:%S"))
    assert s["thanks"] == 1
    assert relationship.event_stats("u1")["thanks"] == 2


# 8 陌生用户全零（静默纪律：零证据=判定侧落默认档）
def test_event_stats_unknown_user_zero():
    s = relationship.event_stats("nobody")
    assert s == {"interaction": 0, "thanks": 0, "politeness": 0,
                 "scolded": 0, "n_int": 0}


# 9 开关缺省全 auto（交还模式默认表现）
def test_get_switches_defaults():
    sw = personality.get_switches()
    assert set(sw.keys()) == set(personality.SWITCH_DEFS.keys())
    assert all(v == "auto" for v in sw.values())


# 10 tri-state 往返：on/off/auto 均可写读（用户开关覆盖模式默认）
def test_set_switch_roundtrip():
    for value in ("on", "off", "auto"):
        assert personality.set_switch("banter", value) is True
        assert personality.get_switches()["banter"] == value


# 11 非法键/非法值拒绝
def test_set_switch_invalid_rejected():
    assert personality.set_switch("nope", "on") is False
    assert personality.set_switch("banter", "maybe") is False
    assert all(v == "auto" for v in personality.get_switches().values())


# 12 文件损坏静默回默认（且 set_switch 可自愈重写）
def test_switch_file_corruption_falls_back():
    with open(personality._persona_pref_path(), "w", encoding="utf-8") as f:
        f.write("{corrupted!!")
    assert all(v == "auto" for v in personality.get_switches().values())
    assert personality.set_switch("clingy", "on") is True
    assert personality.get_switches()["clingy"] == "on"


# 13 未知键共存：set_switch 不丢文件里其他特性字段（泛化 KV 纪律）
def test_switch_preserves_unknown_keys(tmp_path):
    p = personality._persona_pref_path()
    with open(p, "w", encoding="utf-8") as f:
        f.write('{"future_feature": {"a": 1}}')
    assert personality.set_switch("tsundere", "off") is True
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    assert data["future_feature"] == {"a": 1}
    assert data["switches"]["tsundere"] == "off"


# 14 表现层总开关缺省关（M2 先例）；env 开=真
def test_persona_enabled_default_off(monkeypatch):
    assert personality.enabled() is False
    monkeypatch.setenv("XIAOJU3_PERSONA_ENABLED", "1")
    assert personality.enabled() is True


# ==================== 批 2：六规则判定 + 事件触发节流（design v2.1） ====================

def _stats(i, t, p, s):
    """窗口统计构造器（judge_mode 纯函数输入）。"""
    return {"interaction": i, "thanks": t, "politeness": p,
            "scolded": s, "n_int": i + t + p + s}


def _seed(uid, kinds, db, start=None, step_h=24.0):
    """直插 rel_event_log（判定的证据源；绕开 observe_rel 词表/日帽——
    规则矩阵要精确计数）。"""
    relationship._connect().close()   # 幂等建表（直插前 schema 未必存在）
    start = start or DAY
    conn = sqlite3.connect(db)
    try:
        for idx, kind in enumerate(kinds):
            ts = (start + timedelta(hours=step_h * idx)).strftime(
                "%Y-%m-%d %H:%M:%S")
            conn.execute(
                "INSERT INTO rel_event_log (ts, user_id, event, delta,"
                " affinity_after, note) VALUES (?, ?, ?, 0, 0, NULL)",
                (ts, uid, kind))
        conn.commit()
    finally:
        conn.close()


def _set_aff(uid, value, db):
    """直写 relationship.affinity（判定输入 affinity_now）。"""
    relationship._connect().close()   # 幂等建表（同 _seed）
    conn = sqlite3.connect(db)
    try:
        conn.execute("INSERT OR IGNORE INTO relationship (user_id,"
                     " affinity, interaction_count) VALUES (?, 0, 0)",
                     (uid,))
        conn.execute("UPDATE relationship SET affinity=? WHERE user_id=?",
                     (value, uid))
        conn.commit()
    finally:
        conn.close()


# 15 v2.1 熟络型进枚举（手动可指定）
def test_set_mode_manual_familiar():
    assert personality.set_mode_manual("u1", "familiar") is True
    assert personality.get_mode("u1")["mode"] == "familiar"


# 16 证据下限：n_int<10 不判定（不拿两条消息定性）
def test_judge_insufficient_evidence():
    assert personality.judge_mode(_stats(9, 0, 0, 0), 0.0) is None


# 17 退化规则：骂声主旋律+关系冷 → 强制 polite（rule=degrade）
def test_judge_degrade_rule():
    v = personality.judge_mode(_stats(86, 1, 1, 12), -3.0)
    assert (v["mode"], v["rule"]) == ("polite", "degrade")
    assert v["confidence"] == 0.6   # 12/(2×10) 饱和公式


# 18 斗嘴规则：骂谢混杂+关系仍暖
def test_judge_banter_rule():
    v = personality.judge_mode(_stats(9, 5, 5, 6), 4.0)
    assert (v["mode"], v["rule"]) == ("banter", "banter")


# 19 照顾规则（v2.1 放宽）：2 次口角不挡照顾
def test_judge_caring_relaxed_scold2():
    v = personality.judge_mode(_stats(9, 6, 4, 2), 6.0)
    assert (v["mode"], v["rule"]) == ("caring", "caring")


# 20 照顾封顶：3 次口角挡照顾（同批证据滑落熟络档）
def test_judge_caring_blocked_scold3():
    v = personality.judge_mode(_stats(17, 6, 4, 3), 6.0)
    assert v["mode"] == "familiar"   # 证明未落 caring


# 21 依赖规则：高频事务型
def test_judge_dependent_rule():
    v = personality.judge_mode(_stats(45, 3, 2, 0), 1.0)
    assert (v["mode"], v["rule"]) == ("dependent", "dependent")


# 22 熟络规则（v2.1 新增）：高频中性；affinity 差一口气挡住照顾
def test_judge_familiar_rule():
    v = personality.judge_mode(_stats(10, 5, 5, 0), 4.0)
    assert (v["mode"], v["rule"]) == ("familiar", "familiar")


# 23 客气兜底：证据不够任何上档规则
def test_judge_polite_fallback():
    v = personality.judge_mode(_stats(8, 1, 1, 0), 1.0)
    assert (v["mode"], v["rule"], v["confidence"]) == \
        ("polite", "fallback", personality.FALLBACK_CONFIDENCE)


# 24 优先级：同批证据照顾与熟络均可命中 → 照顾胜（序 2 < 序 4）
def test_judge_priority_caring_over_familiar():
    v = personality.judge_mode(_stats(10, 5, 5, 0), 6.0)
    assert v["mode"] == "caring"


# 25 置信度饱和封顶 1.0
def test_judge_confidence_cap():
    v = personality.judge_mode(_stats(30, 20, 10, 12), 4.0)
    assert v["mode"] == "banter"
    assert v["confidence"] == 1.0


# 26 首判：20 事件触发落库（source=auto+judged_at+baseline_id 基线）
def test_rejudge_first_judgment_on_20_events(_iso):
    _seed("u1", ["interaction"] * 10 + ["thanks"] * 5 + ["politeness"] * 5,
          _iso)
    _set_aff("u1", 4.0, _iso)
    out = personality.maybe_rejudge("u1", now=DAY)
    assert out["mode"] == "familiar"       # aff 4<5 挡照顾 → 熟络
    assert out["source"] == "auto"
    m = personality.get_mode("u1")
    assert m["judged_at"] == "2026-10-14 09:00:00"
    ev = json.loads(m["evidence"])
    assert ev["baseline_id"] == 20 and ev["rule"] == "familiar"


# 27 事件触发双闸：新事件 <20 不判；攒够 20 且过 6h 防抖才重判
def test_rejudge_event_throttle(_iso):
    _seed("u1", ["interaction"] * 15 + ["thanks"] * 5, _iso)
    _set_aff("u1", 1.0, _iso)
    assert personality.maybe_rejudge("u1", now=DAY)["mode"] == "polite"
    before = personality.get_mode("u1")["judged_at"]
    _seed("u1", ["interaction"] * 5, _iso, start=DAY + timedelta(days=30))
    assert personality.maybe_rejudge(
        "u1", now=DAY + timedelta(hours=1)) is None   # 5<20 且未过 6h
    assert personality.get_mode("u1")["judged_at"] == before
    _seed("u1", ["interaction"] * 15, _iso, start=DAY + timedelta(days=31))
    out = personality.maybe_rejudge("u1", now=DAY + timedelta(hours=7))
    assert out["mode"] == "dependent"   # 40 事件 generic 0.75 → 依赖
    assert personality.get_mode("u1")["judged_at"] == \
        (DAY + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")


# 28 手动锁优先：source=manual 永不被自动判定覆盖
def test_rejudge_manual_lock(_iso):
    _seed("u9", ["interaction"] * 30, _iso)
    assert personality.set_mode_manual("u9", "caring") is True
    assert personality.maybe_rejudge("u9", now=DAY) is None
    m = personality.get_mode("u9")
    assert m["mode"] == "caring" and m["source"] == "manual"


# 29 退化可逆：degrade 是判定结果非终身罚——证据改善后离开 degrade 规则
def test_rejudge_degrade_reversible(_iso):
    _seed("u2", ["interaction"] * 7 + ["thanks"] + ["scolded"] * 12, _iso)
    _set_aff("u2", -3.0, _iso)
    first = personality.maybe_rejudge("u2", now=DAY)
    assert (first["mode"], json.loads(first["evidence"])["rule"]) == \
        ("polite", "degrade")
    _seed("u2", ["thanks"] * 24, _iso, start=DAY + timedelta(days=1),
          step_h=6.0)
    _set_aff("u2", 6.0, _iso)
    second = personality.maybe_rejudge("u2", now=DAY + timedelta(days=8))
    assert json.loads(second["evidence"])["rule"] != "degrade"
    assert second["mode"] == "polite"   # 90 天窗口旧骂声仍在 → 客气兜底


# 30 表现层单用户闸：累计事件 <50 判定照跑表现不开；≥50 开
def test_expression_ready_threshold(_iso):
    _seed("u1", ["interaction"] * 49, _iso)
    assert personality._is_expression_ready("u1") is False
    _seed("u1", ["interaction"], _iso, start=DAY + timedelta(days=60))
    assert personality._is_expression_ready("u1") is True


# 31 brain 双入口挂钩静态锚（smart_ask+stream 两处 maybe_rejudge）
def test_brain_hook_static_anchor():
    with open("brain.py", encoding="utf-8") as f:
        src = f.read()
    assert src.count("personality.maybe_rejudge") >= 2


# ==================== 批 3：模式表现段合成（design v2.1 §四） ====================

def _make_ready(uid, db, mode="banter"):
    """表现闸开通+手动模式（mode_suffix 合成的公共前置）。"""
    _seed(uid, ["interaction"] * 50, db)
    assert personality.set_mode_manual(uid, mode) is True


# 32 空串路径①：总开关缺省关（逐字节现状）
def test_mode_suffix_total_switch_off():
    assert personality.mode_suffix("u1") == ""


# 33 空串路径②：表现闸——事件 <50 判定照跑但返空串
def test_mode_suffix_expression_gate(_iso, monkeypatch):
    monkeypatch.setenv("XIAOJU3_PERSONA_ENABLED", "1")
    _seed("u1", ["interaction"] * 10, _iso)
    personality.set_mode_manual("u1", "banter")
    assert personality._is_expression_ready("u1") is False
    assert personality.mode_suffix("u1") == ""


# 34 空串路径③：50 事件开闸但无模式行（无行且未手动）
def test_mode_suffix_no_row(_iso, monkeypatch):
    monkeypatch.setenv("XIAOJU3_PERSONA_ENABLED", "1")
    _seed("u1", ["interaction"] * 50, _iso)
    assert personality.mode_suffix("u1") == ""


# 35 空串路径④：表文件缺失
def test_mode_suffix_table_missing(_iso, monkeypatch, tmp_path):
    monkeypatch.setenv("XIAOJU3_PERSONA_ENABLED", "1")
    monkeypatch.setattr(personality, "_EXPRESS_PATH",
                        str(tmp_path / "nope.json"))
    _make_ready("u1", _iso)
    assert personality.mode_suffix("u1") == ""


# 36 空串路径⑤：合成空——唯一模式行被关联开关 off 压制且无加码
def test_mode_suffix_synthesis_empty(_iso, monkeypatch):
    monkeypatch.setenv("XIAOJU3_PERSONA_ENABLED", "1")
    _make_ready("u1", _iso, mode="banter")
    assert personality.set_switch("banter", "off") is True
    assert personality.mode_suffix("u1") == ""


# 37 斗嘴合成：auto 档+verdict 红线尾注
def test_mode_suffix_banter_auto(_iso, monkeypatch):
    monkeypatch.setenv("XIAOJU3_PERSONA_ENABLED", "1")
    _make_ready("u1", _iso, mode="banter")
    s = personality.mode_suffix("u1")
    assert "斗嘴型" in s and "接得住玩笑" in s
    assert "安全与权限相关句子永远严肃" in s


# 38 熟络合成（v2.1 第五模式）
def test_mode_suffix_familiar_auto(_iso, monkeypatch):
    monkeypatch.setenv("XIAOJU3_PERSONA_ENABLED", "1")
    _make_ready("u1", _iso, mode="familiar")
    s = personality.mode_suffix("u1")
    assert "熟络型" in s and "老熟人" in s


# 39 客气合成：距离感+礼数红线（绝非冷暴力写进文案）
def test_mode_suffix_polite_auto(_iso, monkeypatch):
    monkeypatch.setenv("XIAOJU3_PERSONA_ENABLED", "1")
    _make_ready("u1", _iso, mode="polite")
    s = personality.mode_suffix("u1")
    assert "客气型" in s and "绝不冷暴力" in s


# 40 照顾合成
def test_mode_suffix_caring_auto(_iso, monkeypatch):
    monkeypatch.setenv("XIAOJU3_PERSONA_ENABLED", "1")
    _make_ready("u1", _iso, mode="caring")
    s = personality.mode_suffix("u1")
    assert "照顾型" in s and "放在心上" in s


# 41 依赖合成
def test_mode_suffix_dependent_auto(_iso, monkeypatch):
    monkeypatch.setenv("XIAOJU3_PERSONA_ENABLED", "1")
    _make_ready("u1", _iso, mode="dependent")
    s = personality.mode_suffix("u1")
    assert "依赖型" in s and "搭档" in s


# 42 开关覆盖：关联开关 on → 用 on 档加码行（用户终裁）
def test_mode_suffix_switch_on_override(_iso, monkeypatch):
    monkeypatch.setenv("XIAOJU3_PERSONA_ENABLED", "1")
    _make_ready("u1", _iso, mode="banter")
    assert personality.set_switch("banter", "on") is True
    s = personality.mode_suffix("u1")
    assert "打趣浓度加码" in s
    assert "接得住玩笑" not in s   # auto 档被 on 档替换


# 43 加码行追加：非关联开关 on → 独立加码行逐维附加
def test_mode_suffix_addon_lines(_iso, monkeypatch):
    monkeypatch.setenv("XIAOJU3_PERSONA_ENABLED", "1")
    _make_ready("u1", _iso, mode="caring")
    assert personality.set_switch("clingy", "on") is True
    s = personality.mode_suffix("u1")
    assert "放在心上" in s and "撒娇维度加码" in s


# 44 表文件红线：零体验词+verdict 三条硬话（善意与职责/安全严肃/绝不冷暴力）
def test_mode_table_redline_words():
    with open("persona_expressions.json", encoding="utf-8") as f:
        table = json.load(f)
    blob = json.dumps({k: v for k, v in table.items() if k != "_comment"},
                      ensure_ascii=False)   # _comment 是文档说明非注入文案
    for bad in ("感到", "开心", "难过", "伤心"):
        assert bad not in blob
    verdict = table["verdict"]
    for must in ("安全与权限相关句子永远严肃", "善意与职责", "绝不冷暴力"):
        assert must in verdict


# 45 brain 后缀链静态锚：_persona_suffix 存在+三段拼接顺序（关系→模式→情绪）
def test_brain_chain_static_anchor():
    with open("brain.py", encoding="utf-8") as f:
        src = f.read()
    assert "def _persona_suffix" in src
    assert "_rel + _persona + _tone" in src   # 顺序即此串本身


# 46 spec datas 注册静态锚（PyInstaller 铁律——缺它 frozen 静默失效）
def test_spec_datas_registered():
    with open("xiaoju3.spec", encoding="utf-8") as f:
        src = f.read()
    assert "persona_expressions.json" in src


# ==================== 批 4 UI 卡：persona_state 聚合（2026-10-15） ====================

def test_persona_state_full_package(_iso):
    """手动锁+开关+相处次数三源打包：manual 判定/标签/值齐全。"""
    personality.set_mode_manual("owner", "banter")
    personality.set_switch("banter", "on")
    relationship.observe_rel("owner", "在吗")
    st = personality.persona_state("owner")
    assert st["mode"] == "banter"
    assert st["manual"] is True
    assert st["mode_label"] == "斗嘴型"
    assert st["switches"]["banter"] == {"label": "斗嘴", "value": "on"}
    assert set(st["switches"]) == set(personality.SWITCH_DEFS)
    assert st["interactions"] >= 1
    assert isinstance(st["expression_ready"], bool)


def test_persona_state_default_empty(_iso):
    """空库缺省档：DEFAULT_MODE/auto 开关/零次数/未就绪/非手动。"""
    st = personality.persona_state()   # 缺省 owner
    assert st["mode"] == personality.DEFAULT_MODE
    assert st["manual"] is False
    assert st["source"] == "default"
    assert all(v["value"] == "auto" for v in st["switches"].values())
    assert st["interactions"] == 0
    assert st["expression_ready"] is False


def test_persona_state_silent_when_ready_probe_raises(_iso, monkeypatch):
    """就绪探针异常 → 静默兜 False（全模块静默纪律）。"""
    monkeypatch.setattr(personality, "_is_expression_ready",
                        lambda uid: 1 / 0)
    st = personality.persona_state("owner")
    assert st["expression_ready"] is False


def test_persona_state_contract_keys(_iso):
    """契约键集合锁定（前端消费面；增删键须过拍板）。"""
    st = personality.persona_state("owner")
    assert set(st) == {"mode", "mode_label", "confidence", "source",
                       "judged_at", "manual", "switches",
                       "expression_ready", "interactions"}
