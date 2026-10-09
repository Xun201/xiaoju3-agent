# -*- coding: utf-8 -*-
"""mood 状态机测试锚（#271① M1，+13 锚）。

隔离纪律：每例 monkeypatch XIAOJU3_MOOD_DB_PATH 到临时库，零生产
agent_state 接触；时间经 observe_message(now=...) 注入，不 sleep。
"""
import os
import sqlite3
from datetime import datetime

import pytest

import mood


DAY = datetime(2026, 10, 9, 14, 0, 0)      # 白天基准（避开深夜规则）
LATE = datetime(2026, 10, 9, 2, 30, 0)     # 深夜
LATER = datetime(2026, 10, 9, 14, 0, 5)    # 同刻 +5 秒


_DB = {"path": None}


@pytest.fixture(autouse=True)
def _iso_db(tmp_path, monkeypatch):
    db = str(tmp_path / "mood.db")
    monkeypatch.setenv("XIAOJU3_MOOD_DB_PATH", db)
    _DB["path"] = db
    yield db


def _iso():
    """测试体内取当前临时库路径（fixture 不可直接调用）。"""
    return _DB["path"]


def _state():
    return mood.load_mood()


def _last_log(db):
    c = sqlite3.connect(db)
    row = c.execute(
        "SELECT event_type, dp, da, dd, p_after FROM mood_log"
        " ORDER BY id DESC LIMIT 1").fetchone()
    c.close()
    return row


# 1 初值=基线：首连建库即基线坐标（决策点①）
def test_initial_state_is_baseline():
    s = _state()
    assert (s["p"], s["a"], s["d"]) == (0.2, 0.4, 0.3)


# 2 被夸 → P 上升（praised 规则命中）
def test_praised_raises_p():
    mood.observe_message("小橘你真厉害，帮我搞定了", now=DAY)
    assert _last_log(_iso())[0] == "praised"
    assert _last_log(_iso())[1] > 0  # dp>0


# 3 被骂 → P 下降（scolded 规则命中）
def test_scolded_lowers_p():
    mood.observe_message("你怎么这么笨啊", now=DAY)
    row = _last_log(_iso())
    assert row[0] == "scolded"
    assert row[1] < 0


# 4 无命中 → 仅基线回归零位移（small_talk 不位移，防"每句话都在演"）
def test_smalltalk_no_displacement():
    mood.observe_message("今天天气不错呀", now=DAY)
    row = _last_log(_iso())
    assert row[0] == "small_talk"
    assert (row[1], row[2], row[3]) == (0.0, 0.0, 0.0)


# 5 夹钳：连续被骂 P 稳定在 -1，无 NaN 无越界
def test_clamp_extreme():
    for _ in range(30):
        mood.observe_message("笨死了滚滚滚", now=DAY)
    s = _state()
    assert s["p"] == -1.0
    assert -1.0 <= s["a"] <= 1.0 and -1.0 <= s["d"] <= 1.0


# 6 基线回归数学：无命中交互按 α=0.10 向基线收敛
def test_regress_alpha_math():
    mood.observe_message("笨死了滚滚滚", now=DAY)          # P 掉到低位
    p_low = _state()["p"]
    assert p_low < 0.2
    mood.observe_message("普通聊天一句", now=LATER)         # 无命中纯回归
    p_after = _state()["p"]
    expect = p_low + 0.10 * (0.2 - p_low)
    assert abs(p_after - expect) < 1e-6


# 7 闲置回归：距上次 3 小时 → rate=0.10+3×0.05=0.25
def test_idle_regress():
    mood.observe_message("笨死了滚滚滚", now=DAY)
    p_low = _state()["p"]
    mood.observe_message("普通聊天一句",
                         now=datetime(2026, 10, 9, 17, 0, 0))  # +3h
    p_after = _state()["p"]
    expect = p_low + 0.25 * (0.2 - p_low)
    assert abs(p_after - expect) < 1e-6


# 8 长期不交互：rate 封顶 1.0 → 恰好回到基线
def test_long_idle_back_to_baseline():
    mood.observe_message("笨死了滚滚滚", now=DAY)
    mood.observe_message("普通聊天一句",
                         now=datetime(2026, 10, 12, 14, 0, 0))  # 3 天后
    s = _state()
    assert (s["p"], s["a"], s["d"]) == (0.2, 0.4, 0.3)


# 9 同型连击衰减：praised×3 → 第三次位移 ×0.36
def test_streak_decay():
    for i in range(3):
        mood.observe_message("你好厉害呀",
                             now=datetime(2026, 10, 9, 14, 0, i * 5))
    c = sqlite3.connect(_iso())
    rows = c.execute(
        "SELECT dp FROM mood_log WHERE event_type='praised'"
        " ORDER BY id").fetchall()
    c.close()
    assert len(rows) == 3
    # 去掉随机微扰的影响：断言单调递减且第三次约 0.36 倍量级（<0.2）
    assert rows[0][0] > rows[1][0] > rows[2][0] > 0
    assert rows[2][0] < 0.30 * 0.36 + 0.03  # 0.108+ε 容差


# 10 深夜规则：凌晨交互 A 额外 -0.05
def test_late_night():
    mood.observe_message("在吗", now=LATE)
    row = _last_log(_iso())
    assert row[0] == "late_night"
    assert row[2] <= -0.05 + 0.03  # da≈-0.05±ε


# 11 持久化往返：observe 后新连接直读一致
def test_persistence_roundtrip():
    mood.observe_message("小橘你真厉害", now=DAY)
    s1 = _state()
    c = sqlite3.connect(_iso())
    row = c.execute(
        "SELECT p, a, d, last_event_type FROM mood_state"
        " WHERE id=1").fetchone()
    c.close()
    assert abs(row[0] - s1["p"]) < 1e-9
    assert row[3] == "praised"


# 12 开关旁路：MOOD_ENABLED=0 → 零读写（连库文件都不建）
def test_enabled_off_bypass(tmp_path, monkeypatch):
    db = tmp_path / "off.db"
    monkeypatch.setenv("XIAOJU3_MOOD_DB_PATH", str(db))
    monkeypatch.setenv("XIAOJU3_MOOD_ENABLED", "0")
    assert mood.observe_message("你好厉害呀", now=DAY) is None
    assert not os.path.exists(str(db))


# 13 故障兜底：路径不可建 → observe 返回 None 不抛 + load 回退基线
def test_db_failure_fallback(monkeypatch, tmp_path):
    bad = tmp_path / "not_a_dir.txt"
    bad.write_text("x")
    monkeypatch.setenv("XIAOJU3_MOOD_DB_PATH", str(bad / "mood.db"))
    assert mood.observe_message("你好厉害呀", now=DAY) is None
    s = mood.load_mood()
    assert (s["p"], s["a"], s["d"]) == (0.2, 0.4, 0.3)  # 回退基线


# 14 brain 挂钩锚锁（源码级：两入口都有挂钩且静默包裹）
def test_brain_hook_anchor():
    import inspect
    import brain
    src = inspect.getsource(brain)
    assert src.count("mood.observe_message") >= 2, "双入口挂钩缺失"
    # 静默纪律：挂钩必须包在 try/except 内（抓不到 try 就是不合格）
    hook_seg = src[src.index("mood.observe_message") - 200:
                   src.index("mood.observe_message") + 200]
    assert "except" in hook_seg
