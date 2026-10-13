# -*- coding: utf-8 -*-
"""#297 记忆 V2 批 1 测试：schema 迁移 / 写入打标 / 三乘子召回 /
mood_factor / 开关分流 / 真实场景召回验收。

锚清单对应 design_297_memory_merge_v2.md §9（批 1 部分）+ 2026-10-13
批 1 拍板②（真实场景召回验收锚）③（weight 上限 3.0 夹钳）。
全部离线可跑：库写 tempfile 临时目录，mood 一律 patch 隔离（不触碰
真实 mood.db 与 mood_rules.json 行为）。
"""
import contextlib
import io
import shutil
import sqlite3
import tempfile
import time as _time
import unittest
from unittest import mock

import mood as mood_mod
from agent_state import state_manager as sm_mod
from agent_state.state_manager import (WEIGHT_MAX, StateManager,
                                       _seed_candidates)
from brain import (_inject_memory_context, _memory_emotion_meta,
                   _memory_v2_enabled)


@contextlib.contextmanager
def _quiet_stdout():
    """吞掉模块内 print（含 emoji），保持测试输出干净且编码安全。"""
    with contextlib.redirect_stdout(io.StringIO()):
        yield


_NEUTRAL_MOOD = {"p": 0.0, "a": 0.4, "d": 0.0,
                 "baseline": (0.0, 0.4, 0.0), "updated_at": None}


def _fixed_timestamps(sm, count, start_epoch=1731392400, step=60):
    """固定 memories.timestamp 逐条错开（秒级 CURRENT_TIMESTAMP 同秒
    插入会让 ORDER BY timestamp DESC 排序不稳定——测试确定性需要）。"""
    conn = sqlite3.connect(sm.memory_db)
    try:
        for i in range(count):
            conn.execute(
                "UPDATE memories SET timestamp=? WHERE id=?",
                (_time.strftime("%Y-%m-%d %H:%M:%S",
                                _time.gmtime(start_epoch + i * step)), i + 1))
        conn.commit()
    finally:
        conn.close()


class MemoryV2TestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_memv2_")
        with _quiet_stdout():
            self.sm = StateManager(base_dir=self.tmp)
        # mood 全隔离：中性 PAD（p=0 → calm 档），召回/打标行为可预测
        self._mood_patches = [
            mock.patch.object(mood_mod, "load_mood",
                              return_value=dict(_NEUTRAL_MOOD)),
        ]
        for p in self._mood_patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _rows(self, sql, params=()):
        conn = sqlite3.connect(self.sm.memory_db)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def _seed_memories(self, entries):
        with _quiet_stdout():
            for cat, content in entries:
                self.sm.save_memory(cat, content)
        _fixed_timestamps(self.sm, len(entries))


class SchemaMigrationTests(MemoryV2TestBase):
    """§9 schema/迁移（3 锚）"""

    def test_migration_idempotent(self):
        with _quiet_stdout():
            sm2 = StateManager(base_dir=self.tmp)  # 二次 init
        cols = [r[1] for r in self._rows("PRAGMA table_info(memories)")]
        self.assertEqual(len(cols), 11)  # 4 旧 + 7 新，不重复
        with _quiet_stdout():
            sm2 = StateManager(base_dir=self.tmp)  # 三次 init 仍稳定
        cols2 = [r[1] for r in self._rows("PRAGMA table_info(memories)")]
        self.assertEqual(cols, cols2)

    def test_old_rows_get_defaults(self):
        # 旧格式手插（4 列）→ 读回新列全默认值
        conn = sqlite3.connect(self.sm.memory_db)
        conn.execute("INSERT INTO memories (category, content) VALUES"
                     " ('event', '旧格式记忆')")
        conn.commit()
        conn.close()
        row = self._rows(
            "SELECT weight, access_count, activation, emotion_tag,"
            " sink_status, emotional_impact FROM memories")[0]
        self.assertEqual(row, (1.0, 0, 0.0, 'neutral', 'active', 0.0))

    def test_new_tables_exist_and_legacy_todos_untouched(self):
        tables = {r[0] for r in self._rows(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("memory_edge", "activation_log", "sleep_log",
                  "memory_meta", "memories"):
            self.assertIn(t, tables)
        # 旧 todos 残留表（拍板③保留不动）：手造一行 → init 后原样
        conn = sqlite3.connect(self.sm.memory_db)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS todos (id INTEGER PRIMARY KEY,"
            " content TEXT)")
        conn.execute("INSERT INTO todos (content) VALUES ('残留行')")
        conn.commit()
        conn.close()
        with _quiet_stdout():
            StateManager(base_dir=self.tmp)
        self.assertEqual(self._rows("SELECT content FROM todos"),
                         [("残留行",)])


class SaveMemoryTaggingTests(MemoryV2TestBase):
    """§9 写入打标（3 锚 + helper 2 锚）"""

    def test_save_memory_with_tag_and_impact(self):
        with _quiet_stdout():
            self.sm.save_memory("preference", "我喜欢蓝色",
                                emotion_tag="praised",
                                emotional_impact=0.5)
        row = self._rows("SELECT emotion_tag, emotional_impact FROM"
                         " memories")[0]
        self.assertEqual(row, ("praised", 0.5))

    def test_save_memory_legacy_signature_defaults(self):
        with _quiet_stdout():
            self.sm.save_memory("event", "旧签名调用")  # 旧调用零改动
        row = self._rows("SELECT emotion_tag, emotional_impact FROM"
                         " memories")[0]
        self.assertEqual(row, ("neutral", 0.0))

    def test_emotion_meta_match_event_hit(self):
        with mock.patch.object(mood_mod, "match_event",
                               return_value=({"type": "praised"}, "被夸")):
            tag, impact = _memory_emotion_meta("你真厉害")
        self.assertEqual(tag, "praised")
        self.assertIsInstance(impact, float)

    def test_emotion_meta_no_hit_and_mood_error(self):
        with mock.patch.object(mood_mod, "match_event",
                               return_value=(None, None)):
            tag, impact = _memory_emotion_meta("今天天气不错")
        self.assertIsNone(tag)
        self.assertIsInstance(impact, float)
        # load_mood 异常 → impact 兜底 None（tag 不受牵连，双 try 独立）
        with mock.patch.object(mood_mod, "match_event",
                               return_value=({"type": "praised"}, "被夸")), \
             mock.patch.object(mood_mod, "load_mood",
                               side_effect=RuntimeError("boom")):
            tag, impact = _memory_emotion_meta("你真厉害")
        self.assertEqual(tag, "praised")
        self.assertIsNone(impact)


class RecallTests(MemoryV2TestBase):
    """§9 召回（7 锚：种子增益/夹钳/无边退化/权重排序/mood 翻转/沉睡+
    复活/共激活/回退）"""

    def test_recall_seed_gain(self):
        self._seed_memories([("event", "毕业答辩定在 11 月 11 日"),
                             ("event", "涂鸦插座还没到货")])
        rows = self.sm.recall_memories(query="毕业答辩什么时候", limit=5)
        self.assertEqual(rows[0][1], "毕业答辩定在 11 月 11 日")
        w, ac = self._rows(
            "SELECT weight, access_count FROM memories WHERE content LIKE"
            " '%毕业答辩%'")[0]
        self.assertAlmostEqual(w, 1.0 + 0.30)  # exp01 使用增益
        self.assertEqual(ac, 1)

    def test_recall_weight_clamp(self):
        # 拍板③：weight 上限 3.0（2.9 + 0.30 → 夹钳 3.0）
        self._seed_memories([("event", "毕业答辩定在 11 月 11 日")])
        conn = sqlite3.connect(self.sm.memory_db)
        conn.execute("UPDATE memories SET weight=2.9")
        conn.commit()
        conn.close()
        self.sm.recall_memories(query="毕业答辩", limit=5)
        w = self._rows("SELECT weight FROM memories")[0][0]
        self.assertEqual(w, WEIGHT_MAX)

    def test_recall_no_edges_no_crash(self):
        # 无边：扩散退化为「种子+权重」两乘子，不报错（永缺席只退化）
        self._seed_memories([("event", "小米灯已接入 Home Assistant")])
        rows = self.sm.recall_memories(query="小米灯", limit=5)
        self.assertEqual(rows[0][1], "小米灯已接入 Home Assistant")

    def test_recall_weight_ordering(self):
        # 同 tag 同激活：weight 高者 TOP1
        self._seed_memories([("event", "论文被评审打回重写了"),
                             ("event", "导师表扬了我的论文")])
        conn = sqlite3.connect(self.sm.memory_db)
        conn.execute("UPDATE memories SET weight=1.8 WHERE content LIKE"
                     " '%表扬%'")
        conn.commit()
        conn.close()
        rows = self.sm.recall_memories(query="论文的事怎么样了", limit=5)
        self.assertEqual(rows[0][1], "导师表扬了我的论文")

    def test_recall_mood_factor_flips(self):
        # mood_factor 解耦锚：因子定制 → 排序翻转（接口在，#271① 已接）
        self._seed_memories([("event", "论文被评审打回重写了"),
                             ("event", "导师表扬了我的论文")])
        rows = self.sm.recall_memories(query="论文的事怎么样了", limit=5)
        self.assertEqual(rows[0][1], "论文被评审打回重写了")  # 同分 id 序
        with mock.patch.object(mood_mod, "mood_factor_for",
                               side_effect=lambda tag, state=None:
                                   2.0 if tag == "praised" else 1.0):
            # 打标在写入时已定（neutral）——改打重放：直接 UPDATE tag
            conn = sqlite3.connect(self.sm.memory_db)
            conn.execute("UPDATE memories SET emotion_tag='praised'"
                         " WHERE content LIKE '%表扬%'")
            conn.commit()
            conn.close()
            rows2 = self.sm.recall_memories(query="论文的事怎么样了",
                                            limit=5)
        # 注意：上轮召回已给被打回的记忆 +0.30 增益——因子 2.0 需越过
        # 1.30/1.0 差距：2.0 > 1.3 翻转成立
        self.assertEqual(rows2[0][1], "导师表扬了我的论文")

    def test_recall_sink_excluded_and_revive(self):
        self._seed_memories([("event", "涂鸦插座还没到货"),
                             ("event", "小米灯已接入 Home Assistant")])
        conn = sqlite3.connect(self.sm.memory_db)
        conn.execute("UPDATE memories SET sink_status='pending_sink'"
                     " WHERE content LIKE '%小米灯%'")
        conn.commit()
        conn.close()
        # 非种子沉睡：不出现在召回（下沉=不进意识）
        rows = self.sm.recall_memories(query="涂鸦插座", limit=5)
        self.assertNotIn("小米灯已接入 Home Assistant", [r[1] for r in rows])
        # 种子沉睡：被想起即复活回 active 且参与本轮结果（exp04 语义）
        rows2 = self.sm.recall_memories(query="小米灯", limit=5)
        self.assertIn("小米灯已接入 Home Assistant", [r[1] for r in rows2])
        st = self._rows("SELECT sink_status FROM memories WHERE content"
                        " LIKE '%小米灯%'")[0][0]
        self.assertEqual(st, "active")

    def test_recall_coactivation_growth(self):
        # 拍板①：边权唯一生长来源=召回共激活（同轮 gained 节点对 co+1）
        self._seed_memories([("event", "毕业答辩定在 11 月 11 日"),
                             ("event", "答辩 PPT 还没做完")])
        conn = sqlite3.connect(self.sm.memory_db)
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM memories ORDER BY id").fetchall()]
        lo, hi = min(ids[0], ids[1]), max(ids[0], ids[1])
        conn.execute("INSERT INTO memory_edge (from_id, to_id) VALUES (?,?)",
                     (lo, hi))
        conn.commit()
        conn.close()
        self.sm.recall_memories(query="毕业答辩什么时候", limit=5)
        co = self._rows("SELECT coactivation_count FROM memory_edge")[0][0]
        self.assertEqual(co, 1)

    def test_recall_fallback_time_order(self):
        # 无种子命中 → 回退时间序（旧行为零副作用）
        self._seed_memories([("event", "涂鸦插座还没到货"),
                             ("event", "小米灯已接入 Home Assistant")])
        rows = self.sm.recall_memories(query="今天天气真好啊", limit=5)
        self.assertEqual(rows[0][1], "小米灯已接入 Home Assistant")  # 最新
        w = self._rows("SELECT weight FROM memories WHERE content LIKE"
                       " '%小米灯%'")[0][0]
        self.assertEqual(w, 1.0)  # 回退路径零增益副作用


class MoodFactorTests(MemoryV2TestBase):
    """§9 mood_factor（2 锚）：P 维档位映射 + 三重旁路（拍板④）"""

    def test_mood_factor_tier_mapping(self):
        base = {"a": 0.4, "d": 0.0, "baseline": (0.0, 0.4, 0.0),
                "updated_at": None}
        happy = dict(base, p=0.8)
        anxious = dict(base, p=-0.8)
        calm = dict(base, p=0.0)
        self.assertEqual(mood_mod.mood_factor_for("praised", happy), 1.5)
        self.assertEqual(mood_mod.mood_factor_for("scolded", happy), 0.6)
        self.assertEqual(mood_mod.mood_factor_for("scolded", anxious), 1.5)
        self.assertEqual(mood_mod.mood_factor_for("praised", anxious), 0.5)
        self.assertEqual(mood_mod.mood_factor_for("praised", calm), 1.1)
        self.assertEqual(mood_mod.mood_factor_for("未知tag", calm), 1.0)

    def test_mood_factor_fallback(self):
        with mock.patch.object(mood_mod, "enabled", return_value=False):
            self.assertEqual(mood_mod.mood_factor_for("praised"), 1.0)
        with mock.patch.object(mood_mod, "load_mood",
                               side_effect=RuntimeError("boom")):
            self.assertEqual(mood_mod.mood_factor_for("praised"), 1.0)


class SwitchAndConsumerTests(MemoryV2TestBase):
    """§9 开关与消费方（2 锚）：关=旧通道逐字节 / 开=block 格式不变"""

    def _patch_singleton(self):
        return mock.patch.object(sm_mod, "state_manager", self.sm)

    def test_v2_off_uses_legacy_channel(self):
        os_off = mock.patch.dict("os.environ", {}, clear=False)
        os_off.start()
        self.addCleanup(os_off.stop)
        import os as _os
        _os.environ.pop("XIAOJU3_MEMORY_V2", None)
        self.assertFalse(_memory_v2_enabled())
        self._seed_memories([("preference", "我喜欢蓝色")])
        with self._patch_singleton(), \
             mock.patch.object(self.sm, "recall_memories") as mrecall:
            msgs = _inject_memory_context([
                {"role": "system", "content": "你是小橘3号。"},
                {"role": "user", "content": "我喜欢什么颜色？"}])
        mrecall.assert_not_called()  # 开关关：不进召回通道
        self.assertEqual(len(msgs), 3)
        self.assertTrue(msgs[1]["content"].startswith(
            "以下是关于用户的长期记忆"))
        self.assertIn("[preference] 我喜欢蓝色", msgs[1]["content"])

    def test_v2_on_same_block_format(self):
        import os as _os
        _os.environ["XIAOJU3_MEMORY_V2"] = "1"
        self.addCleanup(_os.environ.pop, "XIAOJU3_MEMORY_V2", None)
        self.assertTrue(_memory_v2_enabled())
        self._seed_memories([("preference", "我喜欢蓝色")])
        fixed = [("preference", "我喜欢蓝色")]
        with self._patch_singleton(), \
             mock.patch.object(self.sm, "recall_memories",
                               return_value=list(fixed)) as mrecall, \
             mock.patch.object(self.sm, "get_recent_memories",
                               return_value=list(fixed)):
            msgs_v2 = _inject_memory_context([
                {"role": "system", "content": "你是小橘3号。"},
                {"role": "user", "content": "我喜欢什么颜色？"}])
            _os.environ.pop("XIAOJU3_MEMORY_V2", None)
            msgs_old = _inject_memory_context([
                {"role": "system", "content": "你是小橘3号。"},
                {"role": "user", "content": "我喜欢什么颜色？"}])
        mrecall.assert_called_once()  # 开关开：走召回通道
        # block 格式逐字节一致（输出形态契约：消费方只换数据源不换格式）
        self.assertEqual(msgs_v2[1]["content"], msgs_old[1]["content"])


class RealisticRecallTests(MemoryV2TestBase):
    """拍板②：真实场景召回验收锚——12 条日常记忆 × 8 条日常查询，
    预演人工核对后固化（2026-10-13，独立库逐查询防增益交叉污染）"""

    MEMS = [
        ("preference", "我喜欢在深夜写代码，安静"),
        ("event", "毕业答辩定在 11 月 11 日"),
        ("event", "论文被评审打回重写了"),
        ("preference", "我偏好方案要省钱不折腾"),
        ("event", "小米灯已接入 Home Assistant"),
        ("event", "涂鸦插座还没到货"),
        ("preference", "我不喜欢香菜"),
        ("event", "主人的生日是 3 月 5 日"),
        ("event", "软著流水号 2026R11L3453611"),
        ("event", "每周三下午有组会"),
        ("preference", "我对芒果过敏"),
        ("event", "导师表扬了我的论文"),
    ]

    def _fresh_manager(self):
        tmp = tempfile.mkdtemp(prefix="xiaoju3_memv2_real_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        with _quiet_stdout():
            sm = StateManager(base_dir=tmp)
            for cat, content in self.MEMS:
                sm.save_memory(cat, content)
        _fixed_timestamps(sm, len(self.MEMS))
        return sm

    def test_realistic_recall_scenarios(self):
        scenarios = [
            ("我毕业答辩准备得怎么样了？", "毕业答辩"),
            ("你还记得我喜欢什么吗", "我喜欢"),
            ("论文的事现在怎么样了", "论文"),
            ("我的流水号是多少", "流水号"),
            ("组会是什么时候", "组会"),
            ("我对什么过敏来着", "过敏"),
            ("生日是什么时候", "生日"),
        ]
        for query, expect in scenarios:
            sm = self._fresh_manager()
            with _quiet_stdout():
                rows = sm.recall_memories(query=query, limit=5)
            tops = [r[1] for r in rows[:3]]
            self.assertTrue(
                any(expect in c for c in tops),
                f"查询 {query!r} TOP3 未命中预期 {expect!r}：{tops}")
            self.assertIn(expect, rows[0][1],
                          f"查询 {query!r} TOP1 应为 {expect!r}：{rows[0]}")
        # 无关查询：无种子命中 → 回退时间序（TOP1=最新一条，零增益）
        sm = self._fresh_manager()
        with _quiet_stdout():
            rows = sm.recall_memories(query="今天天气真好啊", limit=5)
        self.assertEqual(rows[0][1], "导师表扬了我的论文")
        w = sm_mod.sqlite3.connect(sm.memory_db).execute(
            "SELECT weight FROM memories WHERE content LIKE '%论文%'"
        ).fetchall()
        self.assertTrue(all(row[0] == 1.0 for row in w),
                        "回退路径不应产生使用增益")


class SeedCandidatesTests(MemoryV2TestBase):
    """种子切分（朴素口径+段级滑窗）：批 1 实现行为锚"""

    def test_seed_candidates_basic(self):
        cands = _seed_candidates("我毕业答辩准备得怎么样了？")
        self.assertIn("毕业", cands)
        self.assertIn("答辩", cands)  # 段级滑窗出复合词词元
        self.assertLessEqual(len(cands), 12)  # SEED_MAX 截断

    def test_seed_candidates_ascii_and_empty(self):
        self.assertIn("2026R11L3453611",
                      _seed_candidates("软著流水号 2026R11L3453611"))
        self.assertEqual(_seed_candidates(""), [])
        self.assertEqual(_seed_candidates("嗯"), [])  # 单字无候选


if __name__ == "__main__":
    unittest.main()
