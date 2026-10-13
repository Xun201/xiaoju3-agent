# -*- coding: utf-8 -*-
"""主动性引擎测试锚（#271③ Phase 0，plan_271c_phase0.md §6 +6 锚）。

隔离：XIAOJU3_PROACTIVE_DB_PATH 全程指 tmp（mood 同款），绝不碰生产
proactive.db；开关缺省关=现有 2056 测试零影响的生命线（锚 1 钉死）。
"""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

import proactive


class ProactiveBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_proactive_")
        self.db = os.path.join(self.tmp, "proactive.db")
        self.env = mock.patch.dict(os.environ, {
            "XIAOJU3_PROACTIVE_ENABLED": "1",
            "XIAOJU3_PROACTIVE_DB_PATH": self.db,
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        for f in ("proactive.db",):
            p = os.path.join(self.tmp, f)
            if os.path.isfile(p):
                os.remove(p)


class SwitchOffTests(ProactiveBase):
    """锚 1：开关关 → tick 早退、不建库不写日志（§6 生命线）。"""

    def test_disabled_returns_none_and_creates_nothing(self):
        with mock.patch.dict(os.environ, {"XIAOJU3_PROACTIVE_ENABLED": "0"}):
            now = datetime.now()
            self.assertIsNone(proactive.proactive_tick(now))
        # 开关关时从未触达 _connect：db 不存在
        self.assertFalse(os.path.isfile(self.db), "开关关时不得建 proactive.db")


class TensionTests(ProactiveBase):
    """锚 2/3：张力累积（clamp）+ 时间衰减数学。"""

    def test_event_accumulation_with_clamp(self):
        # 累积触顶 clamp → 达阈值即 fire（张力清零）；钉正午避开
        # quiet_hours（23-7 点 suppress 会让 fire 断言随运行时刻翻转）
        now = datetime(2026, 10, 12, 12, 0, 0)
        with mock.patch.object(proactive, "_collect_events",
                               return_value=[("todo_due", 0.3)] * 5):   # 5×0.3=1.5 → clamp 1.0
            r = proactive.proactive_tick(now)
        self.assertTrue(r["fired"])   # clamp 后 1.0 ≥ 0.6 且无抑制 → fire
        self.assertEqual(r["tension"], 0.0)   # 出手后清零
        self.assertLessEqual(r["tension"], proactive.CLAMP_MAX)

    def test_decay_math(self):
        now = datetime.now()
        two_hours_ago = (now - timedelta(hours=2)).isoformat(timespec="seconds")
        v = proactive._decay(1.0, two_hours_ago, now)
        self.assertAlmostEqual(v, proactive.DECAY_PER_HOUR ** 2, places=4)
        self.assertEqual(proactive._decay(0.5, None, now), 0.5)   # 无时标不衰减


class SuppressTests(ProactiveBase):
    """锚 4：抑制五条件逐条命中 → suppress + reason 入日志。"""

    def _suppress_reasons(self, patch_kwargs, now=None):
        now = now or datetime.now()
        patch_kwargs = {k: v for k, v in patch_kwargs.items() if v is not None}
        patches = [mock.patch.object(proactive, k, v)
                   for k, v in patch_kwargs.items()]
        with mock.patch.object(proactive, "_collect_events",
                               return_value=[("todo_due", 0.9)]):
            for pt in patches:
                pt.start()
            try:
                proactive.proactive_tick(now)
            finally:
                for pt in patches:
                    pt.stop()
        con = sqlite3.connect(self.db)
        row = con.execute(
            "SELECT reason FROM proactive_log WHERE decision='suppress' "
            "ORDER BY id DESC LIMIT 1").fetchone()
        con.close()
        return row[0] if row else ""

    def test_quiet_hours(self):
        late = datetime(2026, 10, 11, 23, 30)
        reason = self._suppress_reasons(
            {"in_quiet_hours": lambda now: True}, now=late)
        self.assertIn("quiet_hours", reason)

    def test_rejected(self):
        with mock.patch.object(proactive, "recently_rejected", return_value=True):
            reason = self._suppress_reasons({})
        self.assertIn("rejected", reason)

    def test_cooldown(self):
        now = datetime.now()
        st_ts = (now - timedelta(seconds=600)).isoformat(timespec="seconds")
        proactive._save_state(0.9, st_ts, now)
        reason = self._suppress_reasons(
            {"in_cooldown": lambda last, now, seconds=proactive.COOLDOWN_SECONDS: True},
            now=now)
        self.assertIn("cooldown", reason)

    def test_user_busy_and_explicit_stop(self):
        reason = self._suppress_reasons(
            {"user_busy": lambda now: True,
             "told_not_to_bother": lambda now: True})
        self.assertIn("user_busy", reason)
        self.assertIn("explicit_stop", reason)


class FireTests(ProactiveBase):
    """锚 5/6：fire（张力≥阈值+无抑制→张力清零+last_fire_at）+ 冷却。"""

    def test_fire_resets_tension_and_sets_last_fire(self):
        now = datetime(2026, 10, 12, 12, 0, 0)   # 正午：避开 quiet_hours
        with mock.patch.object(proactive, "_collect_events",
                               return_value=[("todo_due", 0.9)]):
            r = proactive.proactive_tick(now)
        self.assertTrue(r["fired"])
        self.assertEqual(r["tension"], 0.0)   # 出手后张力清零
        con = sqlite3.connect(self.db)
        row = con.execute(
            "SELECT decision FROM proactive_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        con.close()
        self.assertEqual(row[0], "fire")

    def test_cooldown_after_fire_suppresses(self):
        now = datetime(2026, 10, 12, 12, 0, 0)   # 正午：避开 quiet_hours
        # 先 fire 一次建立 last_fire_at
        with mock.patch.object(proactive, "_collect_events",
                               return_value=[("todo_due", 0.9)]):
            proactive.proactive_tick(now)
        # 5 分钟后再判：张力再涨但冷却中 → suppress(cooldown)
        later = now + timedelta(seconds=300)
        with mock.patch.object(proactive, "_collect_events",
                               return_value=[("todo_due", 0.9)]):
            r = proactive.proactive_tick(later)
        self.assertTrue(r["suppressed"])
        con = sqlite3.connect(self.db)
        row = con.execute(
            "SELECT reason FROM proactive_log WHERE decision='suppress' "
            "ORDER BY id DESC LIMIT 1").fetchone()
        con.close()
        self.assertIn("cooldown", row[0])


class RealEventSourceIntegrationTests(unittest.TestCase):
    """#271③ 哑火修复——真集成锚（不打 _collect_events 的 mock）。

    背景（坑库 #21）：9 锚全 mock 注入，真链路断链（SQL 查不存在的
    due_date 列）880 分钟零察觉。本组锚建**临时真 todos.db**，让
    _collect_events 本体跑真 SQL——堵“单元全绿但集成哑火”盲区。
    环境隔离=xiaoju3.AGENT_STATE_DIR 指向 tmp（mood 测试同款环境级
    隔离，被测函数本体全真）。"""

    def _make_env(self, todo_rows):
        import sqlite3 as sq
        tmp = tempfile.mkdtemp(prefix="xiaoju3_p0int_")
        con = sq.connect(os.path.join(tmp, "todos.db"))
        con.execute("CREATE TABLE todos (id INTEGER PRIMARY KEY, content TEXT, "
                    "source_url TEXT DEFAULT '', status TEXT DEFAULT 'pending', "
                    "priority TEXT DEFAULT 'P3', created_at DATETIME DEFAULT "
                    "CURRENT_TIMESTAMP, done_at DATETIME, note TEXT DEFAULT '', "
                    "effective_priority TEXT)")
        for created in todo_rows:
            con.execute("INSERT INTO todos (content, status, created_at) "
                        "VALUES ('t', 'pending', ?)", (created,))
        con.commit()
        con.close()
        return tmp

    def test_real_stale_todo_fires_event(self):
        """真库真 SQL：created_at 老化 >7 天的 pending → todo_stale 事件。"""
        import xiaoju3
        old = (datetime.now() - timedelta(days=9)).strftime("%Y-%m-%d %H:%M:%S")
        tmp = self._make_env([old])
        with mock.patch.object(xiaoju3, "AGENT_STATE_DIR", tmp):
            events = proactive._collect_events(datetime.now())
        self.assertIn(("todo_stale", proactive.EVENT_DELTAS["todo_stale"]),
                      events)

    def test_real_fresh_todo_no_stale_event(self):
        """对照：全部新创建 pending → 无 todo_stale（阈值未到）。"""
        import xiaoju3
        fresh = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        tmp = self._make_env([fresh])
        with mock.patch.object(xiaoju3, "AGENT_STATE_DIR", tmp):
            events = proactive._collect_events(datetime.now())
        self.assertNotIn("todo_stale", [e[0] for e in events])

    def test_real_corrupt_todos_db_audited(self):
        """哑火根因复现+审计锚：todos.db 损坏 → SQL 报错**不再静默**，
        proactive_log 记 event_source_error（#316 自我适用）。"""
        import xiaoju3
        tmp = tempfile.mkdtemp(prefix="xiaoju3_p0err_")
        with open(os.path.join(tmp, "todos.db"), "w", encoding="utf-8") as f:
            f.write("this is not a sqlite database {{{")
        db = os.path.join(tmp, "proactive.db")
        with mock.patch.object(xiaoju3, "AGENT_STATE_DIR", tmp),                 mock.patch.dict(os.environ, {"XIAOJU3_PROACTIVE_DB_PATH": db}):
            events = proactive._collect_events(datetime.now())
        self.assertNotIn("todo_stale", [e[0] for e in events])
        con = sqlite3.connect(db)
        row = con.execute(
            "SELECT decision, reason FROM proactive_log "
            "WHERE decision='error' ORDER BY id DESC LIMIT 1").fetchone()
        con.close()
        self.assertIsNotNone(row)
        self.assertIn("todos:", row[1])


class DataRootAnchorTests(unittest.TestCase):
    """#319 前置侦察修正锚：user_idle 探针路径锚 DATA_ROOT（cwd 解耦）。
    真文件流：tmp 建真 history_console.json（旧 mtime）→ 事件命中；
    新 mtime → 不命中。不打 _collect_events mock。"""

    def _probe_with_history(self, age_hours):
        import time as _t
        tmp = tempfile.mkdtemp(prefix="xiaoju3_dr_")
        xd = os.path.join(tmp, "xiaoju3_data")
        os.makedirs(xd)
        h = os.path.join(xd, "history_console.json")
        with open(h, "w", encoding="utf-8") as f:
            f.write("[]")
        old = _t.time() - age_hours * 3600
        os.utime(h, (old, old))
        with mock.patch("paths.DATA_ROOT", tmp):
            return proactive._collect_events(datetime.now())

    def test_old_history_fires_user_idle(self):
        events = self._probe_with_history(age_hours=6)
        self.assertIn(("user_idle", proactive.EVENT_DELTAS["user_idle"]),
                      events)

    def test_fresh_history_no_idle_event(self):
        events = self._probe_with_history(age_hours=0.5)
        self.assertNotIn("user_idle", [e[0] for e in events])


if __name__ == "__main__":
    unittest.main()


class Phase1Batch1Tests(ProactiveBase):
    """#271③ Phase 1 批 1（design_271c_phase1.md §9 锚 1-7）：
    events 明细列 + 每日配额（proactive_meta 存 N）。"""

    def test_events_column_idempotent(self):
        # ALTER 幂等：重复 _connect 不炸不重复
        for _ in range(3):
            con = proactive._connect()
            con.close()
        cols = [r[1] for r in sqlite3.connect(self.db).execute(
            "PRAGMA table_info(proactive_log)")]
        self.assertEqual(cols.count("events"), 1)
        meta_tables = [r[0] for r in sqlite3.connect(self.db).execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        self.assertIn("proactive_meta", meta_tables)

    def test_fire_row_records_event_names(self):
        now = datetime(2026, 10, 13, 12, 0, 0)
        with mock.patch.object(proactive, "_collect_events",
                               return_value=[("todo_stale", 0.9)]):
            proactive.proactive_tick(now)
        row = sqlite3.connect(self.db).execute(
            "SELECT events FROM proactive_log WHERE decision='fire'"
        ).fetchone()
        self.assertEqual(row[0], "todo_stale")

    def test_suppress_row_records_event_names(self):
        # 多事件累积不达阈值 → suppress 行同样落明细（抑制时谁在累积同可对账）
        now = datetime(2026, 10, 13, 12, 0, 0)
        with mock.patch.object(proactive, "_collect_events",
                               return_value=[("todo_stale", 0.3),
                                             ("user_idle", 0.2)]):
            r = proactive.proactive_tick(now)
        self.assertFalse(r["fired"])
        row = sqlite3.connect(self.db).execute(
            "SELECT events FROM proactive_log WHERE decision='suppress'"
        ).fetchone()
        self.assertEqual(row[0], "todo_stale,user_idle")

    def test_old_rows_null_events_compat(self):
        # 旧行（4 列时代 events=NULL）读取兼容（先 _connect 建表）
        con = proactive._connect()
        con.close()
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO proactive_log (ts, action, decision,"
                    " reason) VALUES ('2026-10-01 08:00:00',"
                    " 'tension_release', 'fire', 'tension=0.90')")
        con.commit()
        row = con.execute(
            "SELECT events, COALESCE(events, '') FROM proactive_log"
        ).fetchone()
        con.close()
        self.assertIsNone(row[0])
        self.assertEqual(row[1], "")

    def test_daily_quota_blocks_fire(self):
        # 当日 fire 达 N（meta=2）→ 第 3 次张力达标也 suppress 且
        # reason 含 daily_quota（三次 tick 各隔 >30min 冷却窗，同日内）
        t1 = datetime(2026, 10, 13, 9, 0, 0)
        step = timedelta(seconds=proactive.COOLDOWN_SECONDS + 60)
        proactive.set_daily_limit(2)
        for i, t in enumerate((t1, t1 + step, t1 + 2 * step)):
            with mock.patch.object(proactive, "_collect_events",
                                   return_value=[("todo_stale", 0.9)]):
                r = proactive.proactive_tick(t)
            if i < 2:
                self.assertTrue(r["fired"], f"第 {i+1} 次应在配额内 fire")
        self.assertFalse(r["fired"])   # 第 3 次：daily_quota 拦截
        row = sqlite3.connect(self.db).execute(
            "SELECT reason FROM proactive_log WHERE decision='suppress'"
            " ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIn("daily_quota", row[0])

    def test_quota_within_limit_fires_normal(self):
        # 配额内：reason 无 daily_quota，fire 正常
        now = datetime(2026, 10, 13, 12, 0, 0)
        proactive.set_daily_limit(5)
        with mock.patch.object(proactive, "_collect_events",
                               return_value=[("todo_stale", 0.9)]):
            r = proactive.proactive_tick(now)
        self.assertTrue(r["fired"])
        row = sqlite3.connect(self.db).execute(
            "SELECT reason FROM proactive_log WHERE decision='fire'"
        ).fetchone()
        self.assertNotIn("daily_quota", row[0])

    def test_daily_limit_default_and_meta_roundtrip(self):
        con = sqlite3.connect(self.db)
        self.assertEqual(proactive._daily_limit(con), 5)   # 缺省 5
        con.close()
        self.assertEqual(proactive.set_daily_limit(8), 8)
        con = sqlite3.connect(self.db)
        self.assertEqual(proactive._daily_limit(con), 8)   # meta 生效
        con.close()

    def test_set_daily_limit_clamp(self):
        self.assertIsNone(proactive.set_daily_limit(0))
        self.assertIsNone(proactive.set_daily_limit(51))
        self.assertIsNone(proactive.set_daily_limit("abc"))
        self.assertEqual(proactive.set_daily_limit(1), 1)     # 下边界
        self.assertEqual(proactive.set_daily_limit(50), 50)   # 上边界


class TestTransitionLog:
    """Phase 1 跃迁日志（2026-10-13 UI 修复批）：连续同状态不重复记。"""

    def _count(self, db):
        import sqlite3
        con = sqlite3.connect(db)
        try:
            return con.execute(
                "SELECT COUNT(*), COALESCE(SUM(decision='fire'), 0)"
                " FROM proactive_log").fetchone()
        finally:
            con.close()

    def test_same_state_not_repeated(self, tmp_path, monkeypatch):
        db = str(tmp_path / "p.db")
        monkeypatch.setenv("XIAOJU3_PROACTIVE_ENABLED", "1")
        monkeypatch.setenv("XIAOJU3_PROACTIVE_DB_PATH", db)
        t0 = datetime(2026, 10, 13, 9, 0, 0)
        # 5 连 tick 同为 suppress:calm（无抑制+张力不足）→ 只记第 1 条
        for i in range(5):
            with mock.patch.object(proactive, "_collect_events",
                                   return_value=[]):
                proactive.proactive_tick(t0 + timedelta(seconds=60 * i))
        total, fires = self._count(db)
        assert total == 1, f"同状态应只记 1 条，实际 {total}"
        assert fires == 0

    def test_transition_records_and_fire_always(self, tmp_path, monkeypatch):
        db = str(tmp_path / "p.db")
        monkeypatch.setenv("XIAOJU3_PROACTIVE_ENABLED", "1")
        monkeypatch.setenv("XIAOJU3_PROACTIVE_DB_PATH", db)
        t0 = datetime(2026, 10, 13, 9, 0, 0)
        step = timedelta(seconds=60)
        # tick1: calm suppress（记）→ tick2: 带 quiet_hours 抑制（状态变，记）
        with mock.patch.object(proactive, "_collect_events",
                               return_value=[]):
            proactive.proactive_tick(t0)
        with mock.patch.object(proactive, "_collect_events",
                               return_value=[]), \
                mock.patch.object(proactive, "in_quiet_hours",
                                  return_value=True):
            proactive.proactive_tick(t0 + step)
        total, _ = self._count(db)
        assert total == 2   # calm → quiet_hours 两次跃迁各记一条
