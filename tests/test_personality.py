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
