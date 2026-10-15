# -*- coding: utf-8 -*-
"""mood 状态机测试锚（#271① M1，+13 锚）。

隔离纪律：每例 monkeypatch XIAOJU3_MOOD_DB_PATH 到临时库，零生产
agent_state 接触；时间经 observe_message(now=...) 注入，不 sleep。
"""
import os
import io
import json
import sqlite3
from datetime import datetime, timedelta

import pytest
from unittest import mock

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
    for _ in range(60):
        mood.observe_message("笨死了滚滚滚", now=DAY)
    s = _state()
    assert s["p"] <= -0.95  # 收敛至深负区（ε 随机游走下允许近界）
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


# 8 长期不交互（M1+ 睡眠语义）：负 P 归 0（快消退）+ α 一步向基线，
# A 归 0.1 后 α 回升——终态 P∈[0,基线]、A≥0.1
def test_long_idle_back_to_baseline():
    mood.observe_message("笨死了滚滚滚", now=DAY)
    mood.observe_message("普通聊天一句",
                         now=datetime(2026, 10, 12, 14, 0, 0))  # 3 天后
    s = _state()
    assert 0.0 <= s["p"] <= 0.2, f"负 P 应归零后向基线: {s['p']}"
    assert s["a"] >= 0.1


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


# ==================== M2 语气注入（拍板稿三决策已存档） ====================

# 15 开关缺省关：tone_suffix 恒空串（拍板①：首个可感知变化等手动开）
def test_tone_default_off():
    assert mood.tone_suffix({"p": 0.9, "a": 0.9, "d": 0.5}) == ""


# 16 中性基线档：p_mid_a_mid 空串（防"每句话都在演"）
def test_tone_neutral_empty(monkeypatch):
    monkeypatch.setenv("XIAOJU3_MOOD_TONE", "1")
    assert mood.tone_suffix({"p": 0.2, "a": 0.4, "d": 0.3}) == ""
    assert mood.tone_suffix({"p": 0.0, "a": 0.0, "d": 0.0}) == ""


# 17 正向档：p_high_a_high 查表正确 + 措辞口径
def test_tone_positive_tier(monkeypatch):
    monkeypatch.setenv("XIAOJU3_MOOD_TONE", "1")
    s = mood.tone_suffix({"p": 0.9, "a": 0.9, "d": 0.3})
    assert "活泼" in s and "情绪参数" in s
    assert "以性格设定为准" in s        # 裁决句每档传导
    assert "安全与权限" in s            # 安全句永远严肃


# 18 负向极档：保护措辞在位（绝不冷淡失礼），零攻击性词
def test_tone_negative_tier(monkeypatch):
    monkeypatch.setenv("XIAOJU3_MOOD_TONE", "1")
    s = mood.tone_suffix({"p": -0.9, "a": -0.9, "d": -0.3})
    assert "忧郁狐狐" in s and "绝不冷淡失礼" in s
    for bad in ("冷漠", "敷衍", "怼"):
        assert bad not in s


# 19 9 档表完整性：P×A 组合无缺失
def test_tone_table_complete():
    import json
    table = json.load(open(mood._TONE_PATH, encoding="utf-8"))
    keys = set(table["tones"].keys())
    expect = {f"p_{p}_a_{a}" for p in ("high", "mid", "low")
              for a in ("high", "mid", "low")}
    assert keys == expect, f"9 档缺漏: {expect - keys}"


# 20 体验词黑名单：注入面（tones 值+verdict）零"感到/开心/难过"（虚实
# 红线；_comment 元说明不进注入面不扫）
def test_tone_no_experience_words():
    import json
    table = json.load(open(mood._TONE_PATH, encoding="utf-8"))
    injectable = " ".join(table["tones"].values()) + table.get("verdict", "")
    for w in ("感到", "开心", "难过", "伤心"):
        assert w not in injectable, f"红线词泄漏: {w}"


# 21 db 读取失败 + 开关开：load 回退基线=中性档 → 空串（静默闭环）
def test_tone_db_failure_neutral(monkeypatch, tmp_path):
    bad = tmp_path / "file.txt"
    bad.write_text("x")
    monkeypatch.setenv("XIAOJU3_MOOD_DB_PATH", str(bad / "mood.db"))
    monkeypatch.setenv("XIAOJU3_MOOD_TONE", "1")
    assert mood.tone_suffix() == ""


# 22 brain 源码锚：单点动态后缀（_build_messages 唯一组装点，拼 content）
def test_tone_brain_anchor():
    import inspect
    import brain
    src = inspect.getsource(brain)
    assert "_mood_tone_suffix()" in src, "单点后缀调用缺失"
    assert "SYSTEM_PROMPT.get(\"content\", \"\")" in src \
        and "+ _rel + _persona + _tone" in src, "三段注入拼接缺失（M1+ 批3 扩）"
    assert "def _mood_tone_suffix" in src


# 23 后缀拼进 messages 后与空串路径逐字节一致（开关关）
def test_build_messages_byte_identical_when_off(monkeypatch):
    import brain
    monkeypatch.delenv("XIAOJU3_MOOD_TONE", raising=False)
    msgs = brain._build_messages("在吗", [])
    assert msgs[0] == brain.SYSTEM_PROMPT  # 空串路径：逐字节现状


# 24 开关开+真实情绪数据：_build_messages 的 system content 含后缀
def test_build_messages_with_tone(monkeypatch):
    import brain
    monkeypatch.setenv("XIAOJU3_MOOD_TONE", "1")
    # 制造正向情绪（写进 fixture 隔离库）：连续两次被夸 → P 升至 high 档
    mood.observe_message("你好厉害呀", now=DAY)
    mood.observe_message("你好厉害呀",
                         now=datetime(2026, 10, 9, 14, 0, 5))
    msgs = brain._build_messages("在吗", [])
    assert isinstance(msgs[0], dict)
    assert "当前情绪参数" in msgs[0]["content"]
    assert "以性格设定为准" in msgs[0]["content"]
    # prompts 共享常量不被污染
    assert "当前情绪参数" not in brain.SYSTEM_PROMPT["content"]


# 25 frozen 路径优先级：xiaoju3.AGENT_STATE_DIR 优先于 __file__ fallback
# （真机教训：onedir 下 __file__ 误落项目根，生产三 db 曾误建 dev 仓）
def test_db_path_prefers_xiaoju3_anchor(monkeypatch, tmp_path):
    import xiaoju3
    monkeypatch.delenv("XIAOJU3_MOOD_DB_PATH", raising=False)
    monkeypatch.setattr(xiaoju3, "AGENT_STATE_DIR", str(tmp_path))
    assert mood._db_path() == os.path.join(str(tmp_path), "mood.db")


# ==================== #297b 批 1：情绪快照补点（eval_297b_emotional_phase2.md） ====================

class TestHeartbeatSnapshot:
    """快照写入/查表式节流/零位移/心跳挂载（隔离同款：tmp mood.db）。"""

    def test_snapshot_writes_full_fields(self, tmp_path, monkeypatch):
        db = str(tmp_path / "mood.db")
        monkeypatch.setenv("XIAOJU3_MOOD_DB_PATH", db)
        now = datetime(2026, 10, 13, 15, 0, 0)
        snap = mood.heartbeat_snapshot(now=now)
        assert snap is not None
        assert snap["source"] == "heartbeat"
        assert snap["ts"].startswith("2026-10-13 15:00:00")
        for k in ("p", "a", "d"):
            assert isinstance(snap[k], float)
        con = sqlite3.connect(db)
        try:
            row = con.execute(
                "SELECT ts, p, a, d, source FROM mood_snapshot"
            ).fetchall()
        finally:
            con.close()
        assert len(row) == 1
        assert row[0][4] == "heartbeat"

    def test_snapshot_throttled_within_interval(self, tmp_path, monkeypatch):
        db = str(tmp_path / "mood.db")
        monkeypatch.setenv("XIAOJU3_MOOD_DB_PATH", db)
        t0 = datetime(2026, 10, 13, 15, 0, 0)
        assert mood.heartbeat_snapshot(now=t0) is not None
        # 15 分钟内重入 → None（查表式节流，重启安全）
        assert mood.heartbeat_snapshot(now=t0 + timedelta(minutes=5)) is None
        # 超过间隔 → 再写
        assert mood.heartbeat_snapshot(
            now=t0 + timedelta(minutes=16)) is not None

    def test_snapshot_zero_displacement_no_accounting(self, tmp_path, monkeypatch):
        # 零位移：快照不触发记账——mood_state 不变、mood_log 零新增
        db = str(tmp_path / "mood.db")
        monkeypatch.setenv("XIAOJU3_MOOD_DB_PATH", db)
        mood.observe_message("你好呀")          # 先造一条正常记账
        state_before = mood.load_mood()
        log_before = sqlite3.connect(db).execute(
            "SELECT COUNT(*) FROM mood_log").fetchone()[0]
        mood.heartbeat_snapshot(now=datetime(2026, 10, 13, 15, 0, 0))
        state_after = mood.load_mood()
        log_after = sqlite3.connect(db).execute(
            "SELECT COUNT(*) FROM mood_log").fetchone()[0]
        assert state_after["p"] == state_before["p"]
        assert state_after["updated_at"] == state_before["updated_at"]
        assert log_after == log_before

    def test_heartbeat_mounts_snapshot_slot(self):
        # 心跳第四槽源码锚（todo_aging/proactive/memory_sleep 之后）
        import heartbeat
        src = io.open(heartbeat.__file__, encoding="utf-8").read()
        assert "mood.heartbeat_snapshot()" in src or \
            "_mood_mod.heartbeat_snapshot()" in src
        mount = src[src.index("情绪快照补点"):]
        assert "except ImportError" in mount
        # 槽序：快照槽在 memory_sleep 槽之后
        assert src.index("memory_sleep") < src.index("情绪快照补点")


# ==================== #297b 批 2：情绪段判定（emotional_episode） ====================

class TestEmotionalEpisode:
    """段起点/终点判定 / 关键帧缓冲 70-30 / 落表完整 / 空段不落。"""

    BASE = (0.0, 0.4, 0.0)

    def _series(self, points):
        return [(f"2026-10-13 {h:02d}:{m:02d}:00", p, a, d)
                for h, m, p, a, d in points]

    def test_blend_frames_70_30(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XIAOJU3_MOOD_DB_PATH", str(tmp_path / "m.db"))
        # 结尾 (0.5, 0.2, 0.0) × 0.7 + 峰值 (0.9, 0.6, 0.1) × 0.3
        out = mood.blend_frames((0.5, 0.2, 0.0), (0.9, 0.6, 0.1))
        assert out == (0.62, 0.32, 0.03)

    def test_detect_episode_start_and_calm_end(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XIAOJU3_MOOD_DB_PATH", str(tmp_path / "m.db"))
        # 基线内 → 负偏离(-0.5) → 持续 → 回落(<0.10)×2 → 闭合
        series = self._series([
            (10, 0, 0.05, 0.4, 0.0),   # 平静
            (10, 10, -0.45, 0.4, 0.0),  # 起点：p 偏离 0.45>0.25
            (10, 20, -0.40, 0.4, 0.0),  # 持续（峰值 -0.45）
            (10, 30, -0.05, 0.4, 0.0),  # 回落点 1
            (10, 40, -0.03, 0.4, 0.0),  # 回落点 2 → 闭合
        ])
        eps = mood.detect_episodes(series, self.BASE)
        assert len(eps) == 1
        ep = eps[0]
        assert ep["start_ts"] == "2026-10-13 10:10:00"
        assert ep["end_ts"] == "2026-10-13 10:40:00"
        assert ep["peak"][0] == -0.45
        assert ep["tag"] == "negative"

    def test_detect_episode_gap_timeout_closes(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XIAOJU3_MOOD_DB_PATH", str(tmp_path / "m.db"))
        # 两点间隔 40 分钟 > 30 → 间隔超时闭合（且第二点开启新段候选不构成段）
        series = self._series([
            (10, 0, -0.5, 0.4, 0.0),
            (10, 40, -0.45, 0.4, 0.0),
        ])
        eps = mood.detect_episodes(series, self.BASE)
        # 间隔 40min 超时 → 前段在 10:00 闭合；后点仍偏离 → 自开新段
        # （ongoing 截断）= 两次独立波动
        assert len(eps) == 2
        assert eps[0]["end_ts"] == "2026-10-13 10:00:00"
        assert eps[0]["duration"] == 0.0
        assert eps[1]["start_ts"] == "2026-10-13 10:40:00"

    def test_detect_no_episode_when_all_calm(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XIAOJU3_MOOD_DB_PATH", str(tmp_path / "m.db"))
        series = self._series([
            (10, 0, 0.05, 0.4, 0.0),
            (10, 30, 0.08, 0.42, 0.0),
            (11, 0, 0.02, 0.39, 0.0),
        ])
        assert mood.detect_episodes(series, self.BASE) == []   # 空段不产生

    def test_flush_writes_full_row_and_idempotent(self, tmp_path, monkeypatch):
        db = str(tmp_path / "m.db")
        monkeypatch.setenv("XIAOJU3_MOOD_DB_PATH", db)
        # 造双源时序：交互行（mood_log）+ 快照行（mood_snapshot）
        con = sqlite3.connect(db)
        con.executescript(mood.SCHEMA)
        con.execute("INSERT INTO mood_log (ts, event_type, dp, da, dd,"
                    " p_after, a_after, d_after) VALUES"
                    " ('2026-10-13 10:10:00', 'scolded', -0.35, 0, 0,"
                    " -0.45, 0.4, 0.0)")
        con.execute("INSERT INTO mood_snapshot (ts, p, a, d, source)"
                    " VALUES ('2026-10-13 10:20:00', -0.40, 0.4, 0.0,"
                    " 'heartbeat')")
        con.execute("INSERT INTO mood_snapshot (ts, p, a, d, source)"
                    " VALUES ('2026-10-13 10:40:00', -0.05, 0.4, 0.0,"
                    " 'heartbeat')")
        con.commit()
        con.close()
        n = mood.flush_episodes()
        assert n == 1
        con = sqlite3.connect(db)
        row = con.execute(
            "SELECT start_ts, end_ts, peak_p, end_p, duration, tag"
            " FROM emotional_episode").fetchall()
        # 幂等：重跑不重复落
        assert mood.flush_episodes() == 0
        con.close()
        assert len(row) == 1
        assert row[0][0] == "2026-10-13 10:10:00"
        assert row[0][1] == "2026-10-13 10:40:00"
        assert row[0][2] == -0.45
        assert row[0][3] == -0.05
        assert row[0][4] == 30.0
        assert row[0][5] == "negative"


# ==================== 批 2.1：段-记忆关联（2026-10-15） ====================

def test_flush_backfills_memory_ids_from_window(tmp_path, monkeypatch):
    """落表时按 [start_ts, end_ts] 窗回填 memory_ids：窗内记忆 id 命中、
    窗外不混入；旧库（无列）幂等补列。"""
    db = str(tmp_path / "m.db")
    monkeypatch.setenv("XIAOJU3_MOOD_DB_PATH", db)
    con = sqlite3.connect(db)
    con.executescript(mood.SCHEMA)
    con.execute("INSERT INTO mood_log (ts, event_type, dp, da, dd,"
                " p_after, a_after, d_after) VALUES"
                " ('2026-10-13 10:10:00', 'scolded', -0.35, 0, 0,"
                " -0.45, 0.4, 0.0)")
    con.execute("INSERT INTO mood_snapshot (ts, p, a, d, source)"
                " VALUES ('2026-10-13 10:20:00', -0.40, 0.4, 0.0,"
                " 'heartbeat')")
    con.execute("INSERT INTO mood_snapshot (ts, p, a, d, source)"
                " VALUES ('2026-10-13 10:40:00', -0.05, 0.4, 0.0,"
                " 'heartbeat')")
    con.commit()
    con.close()
    # memories 库（tmp 独立）：窗内两条 + 窗外一条。生产语义
    # memories.timestamp=UTC（CURRENT_TIMESTAMP）、episode ts=本地——
    # 测试按本机偏移把语料换算成 UTC 写入（跨时区确定性）
    offset = datetime.now() - datetime.utcnow()

    def _utc(local_s):
        dt = datetime.strptime(local_s, "%Y-%m-%d %H:%M:%S") - offset
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    mem_db = str(tmp_path / "long_term.db")
    con = sqlite3.connect(mem_db)
    con.execute("CREATE TABLE memories (id INTEGER PRIMARY KEY"
                " AUTOINCREMENT, category TEXT, content TEXT,"
                " timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
    con.execute("INSERT INTO memories (category, content, timestamp)"
                " VALUES ('fact', '窗内一', '" + _utc('2026-10-13 10:12:00') + "')")
    con.execute("INSERT INTO memories (category, content, timestamp)"
                " VALUES ('fact', '窗内二', '" + _utc('2026-10-13 10:35:00') + "')")
    con.execute("INSERT INTO memories (category, content, timestamp)"
                " VALUES ('fact', '窗外', '" + _utc('2026-10-13 09:00:00') + "')")
    con.commit()
    con.close()
    monkeypatch.setattr(mood, "_memories_db_path", lambda: mem_db)

    assert mood.flush_episodes() == 1   # 旧库无列 → _ensure 幂等补列后落表
    con = sqlite3.connect(db)
    row = con.execute("SELECT memory_ids FROM emotional_episode").fetchone()
    con.close()
    ids = json.loads(row[0])
    assert sorted(ids) == [1, 2]   # 窗内两条命中，窗外不混入


def test_flush_empty_window_memory_ids_empty_list(tmp_path, monkeypatch):
    """窗内无记忆 → memory_ids='[]'（消费侧空关联=走普通直注）。"""
    db = str(tmp_path / "m.db")
    monkeypatch.setenv("XIAOJU3_MOOD_DB_PATH", db)
    con = sqlite3.connect(db)
    con.executescript(mood.SCHEMA)
    con.execute("INSERT INTO mood_log (ts, event_type, dp, da, dd,"
                " p_after, a_after, d_after) VALUES"
                " ('2026-10-13 10:10:00', 'scolded', -0.35, 0, 0,"
                " -0.45, 0.4, 0.0)")
    con.execute("INSERT INTO mood_snapshot (ts, p, a, d, source)"
                " VALUES ('2026-10-13 10:40:00', -0.05, 0.4, 0.0,"
                " 'heartbeat')")
    con.commit()
    con.close()
    mem_db = str(tmp_path / "long_term.db")
    con = sqlite3.connect(mem_db)
    con.execute("CREATE TABLE memories (id INTEGER PRIMARY KEY"
                " AUTOINCREMENT, category TEXT, content TEXT,"
                " timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
    con.commit()
    con.close()
    monkeypatch.setattr(mood, "_memories_db_path", lambda: mem_db)

    assert mood.flush_episodes() == 1
    con = sqlite3.connect(db)
    row = con.execute("SELECT memory_ids FROM emotional_episode").fetchone()
    con.close()
    assert json.loads(row[0]) == []


# ==================== 批 2.2：episode_associations 反查（2026-10-15） ====================

def test_episode_associations_map(tmp_path, monkeypatch):
    """memory_ids → 段反查表：批 2.1 回填的 memory_ids 解成
    memory_id → {start_ts, tag} 映射（disclosure 过滤层输入）。"""
    db = str(tmp_path / "m.db")
    monkeypatch.setenv("XIAOJU3_MOOD_DB_PATH", db)
    con = sqlite3.connect(db)
    con.executescript(mood.SCHEMA)
    con.execute("INSERT INTO emotional_episode (start_ts, end_ts, peak_p,"
                " peak_a, peak_d, end_p, end_a, end_d, duration, tag,"
                " memory_ids) VALUES ('2026-10-14 10:00:00',"
                " '2026-10-14 10:40:00', -0.4, 0.4, 0.0, -0.05, 0.4, 0.0,"
                " 40.0, 'negative', '[3, 9]')")
    con.commit()
    con.close()
    assoc = mood.episode_associations()
    assert assoc == {3: {"start_ts": "2026-10-14 10:00:00",
                         "tag": "negative"},
                     9: {"start_ts": "2026-10-14 10:00:00",
                         "tag": "negative"}}


# ==================== 批 2.3 接线：heartbeat 顺带 flush（2026-10-15） ====================

def test_heartbeat_wires_flush_episodes(tmp_path, monkeypatch):
    """接线锚：心跳情绪快照节拍顺带调 flush_episodes（幂等去重——
    不接线段永远不产生，二期披露链无米下锅）。"""
    import heartbeat as heartbeat_mod
    calls = []
    fake_mood = mock.MagicMock()
    fake_mood.heartbeat_snapshot.return_value = {"p": 0.1, "a": 0.1, "d": 0.1}
    fake_mood.flush_episodes.side_effect = lambda: calls.append(1) or 0
    monkeypatch.setattr(heartbeat_mod, "_mood_mod", fake_mood, raising=False)
    # heartbeat.py 内是函数内局部 import mood——直接 patch sys.modules 语义
    import mood as real_mood
    monkeypatch.setattr(real_mood, "flush_episodes",
                        lambda: calls.append(1) or 0)
    # 触发：快照补点段（语义=情绪快照+flush 同节拍）
    db = str(tmp_path / "m.db")
    monkeypatch.setenv("XIAOJU3_MOOD_DB_PATH", db)
    con = sqlite3.connect(db)
    con.executescript(real_mood.SCHEMA)
    con.commit()
    con.close()
    # 生产路径=heartbeat_loop（每轮 flush 在 heartbeat_once 之前——
    # once 早退轮也不漏拍）；max_rounds=1 限定单轮（测试阀先例）
    heartbeat_mod.heartbeat_loop(interval=0.01, sense_fn=lambda: {},
                                 ask_fn=lambda x: "好的",
                                 execute_fn=lambda *a, **k: None,
                                 max_rounds=1)
    assert len(calls) >= 1   # flush 已随节拍被调
