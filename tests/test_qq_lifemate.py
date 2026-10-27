# -*- coding: utf-8 -*-
"""qq_lifemate 切片 a 测试（2026-10-27）——契约+三闸纯逻辑+工具行为+落账。

覆盖：
- plugin_loader 目录包装载：rejected=0、tools 3 个 ext_ 前缀、setup 建表；
- 唤醒三闸纯逻辑（静默/quiet 跨午夜/日限帽/首次见面）；
- record_fact / scene_report / recall_fact 真库行为（UNIQUE 更新/场景最新）；
- wake_once 落账（chat_log+meta 计数+跨日重置，mock 生成与发送）。

mock 注意：知识库一律临时目录（patch external_dir/data_dir）；唤醒线程在
装载 setup 时真实启动（daemon，600s 间隔不打扰）——用例结束 teardown 冬眠。
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import plugin_loader  # noqa: E402

PLUGIN_SRC = os.path.join(PROJECT_ROOT, "agent_state", "plugins",
                          "qq_lifemate")


# waker 与插件内部 import 的是同一 sys.modules 实例（sys.path 先插插件
# 目录）——否则两个模块对象并存，set_data_dir 作用不到插件用的那一份
if PLUGIN_SRC not in sys.path:
    sys.path.insert(0, PLUGIN_SRC)
import waker  # noqa: E402


class WakeGateTests(unittest.TestCase):
    """唤醒三闸纯逻辑（W1/W2/硬帽——队长拍板契约）。"""

    def setUp(self):
        self.now = datetime(2026, 10, 27, 14, 0, 0)   # 周二 14:00 非 quiet

    def test_not_silent_blocks(self):
        """距上次发声 <4h：不唤醒。"""
        last = "2026-10-27 12:00:00"   # 2h 前
        wake, reason = waker.should_wake(last, self.now, 0)
        self.assertFalse(wake)
        self.assertEqual(reason, "not_silent")

    def test_silence_passed_wakes(self):
        """≥4h：唤醒（原因带静默时长）。"""
        last = "2026-10-27 09:00:00"   # 5h 前
        wake, reason = waker.should_wake(last, self.now, 0)
        self.assertTrue(wake)
        # 切片 c 双轨：低张力=想念轨 miss_，高张力=正事轨 tension_
        self.assertTrue(reason.startswith("miss_")
                        or reason.startswith("tension_"))

    def test_quiet_hours_block(self):
        """W2：23:00-08:00 绝不唤醒（跨午夜两端+午夜本体）。"""
        for h in (23, 0, 3, 7):
            now = self.now.replace(hour=h)
            wake, reason = waker.should_wake(None, now, 0)
            self.assertFalse(wake, f"hour={h} 应被 quiet 挡住")
            self.assertEqual(reason, "quiet")

    def test_quight_ends_at_8(self):
        """08:00 整起不再 quiet（白天可唤醒）。"""
        wake, _ = waker.should_wake(None, self.now.replace(hour=8), 0)
        self.assertTrue(wake)

    def test_daily_cap_blocks_even_if_silent(self):
        """硬帽：当日已 5 次即使静默足够也不唤醒（封号纪律）。"""
        last = "2026-10-26 08:00:00"   # 30h 前
        wake, reason = waker.should_wake(last, self.now, waker.DAILY_CAP)
        self.assertFalse(wake)
        self.assertEqual(reason, "daily_cap")

    def test_first_meet_wakes(self):
        """从未发声（库空）：first_meet 唤醒。"""
        wake, reason = waker.should_wake(None, self.now, 0)
        self.assertTrue(wake)
        self.assertEqual(reason, "first_meet")

    def test_bad_ts_treated_as_first_meet(self):
        """ts 损坏：保守按首次处理。"""
        wake, reason = waker.should_wake("垃圾数据", self.now, 0)
        self.assertTrue(wake)
        self.assertEqual(reason, "first_meet")


class SliceCTests(unittest.TestCase):
    """切片 c：张力双轨/格式红线/facts 注入/每日回放。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lm_c_")
        waker.set_data_dir(self.tmp)

    def tearDown(self):
        waker.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tension_fast_track_halves_silence(self):
        """张力≥0.6：静默阈值减半（正事轨）。"""
        now = datetime(2026, 10, 27, 14, 0, 0)
        last = "2026-10-27 11:30:00"   # 2.5h 前
        wake, _ = waker.should_wake(last, now, 0, tension=0.0)
        self.assertFalse(wake)
        wake, reason = waker.should_wake(last, now, 0, tension=0.7)
        self.assertTrue(wake)
        self.assertTrue(reason.startswith("tension_"))

    def test_tension_low_keeps_4h(self):
        """张力低：维持 4h（想念轨不变）。"""
        now = datetime(2026, 10, 27, 14, 0, 0)
        last = "2026-10-27 12:00:00"   # 2h 前（<4h）
        wake, _ = waker.should_wake(last, now, 0, tension=0.1)
        self.assertFalse(wake)

    def test_cap_and_quiet_still_win(self):
        """硬帽与 quiet 优先于张力（帽/quiet 不因张力放行）。"""
        now = datetime(2026, 10, 27, 23, 30, 0)
        wake, reason = waker.should_wake(None, now, 0, tension=0.9)
        self.assertFalse(wake)
        self.assertEqual(reason, "quiet")

    def test_strip_prefix_noise(self):
        self.assertEqual(waker.strip_prefix_noise("那句话：主人好"),
                         "主人好")
        self.assertEqual(waker.strip_prefix_noise("回复：在呢"), "在呢")
        self.assertEqual(waker.strip_prefix_noise("正常话"), "正常话")

    def test_facts_digest(self):
        db = waker._db()
        db.execute("INSERT INTO facts(key, value, ts) VALUES(?,?,?)",
                   ("喜欢的饮料", "热可可", "2026-10-27 10:00"))
        db.commit()
        d = waker.facts_digest(db)
        db.close()
        self.assertIn("喜欢的饮料=热可可", d)

    def test_facts_digest_empty(self):
        db = waker._db()
        d = waker.facts_digest(db)
        db.close()
        self.assertIn("还没有记住", d)

    def test_daily_replay_persists_facts(self):
        """回放：LLM 总结行→facts 落库+meta 防重。"""
        db = waker._db()
        db.execute("INSERT INTO chat_log(role, content, ts, kind) "
                   "VALUES('assistant','想你了','2026-10-27 10:00','w')")
        db.commit()
        db.close()
        with patch("brain.ask_local",
                   return_value="饮料=热可可\n心情=想主人\n无"):
            waker.try_daily_replay(datetime(2026, 10, 28, 3, 10, 0))
        db = waker._db()
        n = db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        replays = db.execute("SELECT v FROM meta WHERE k='replay_date'"
                             ).fetchall()
        db.close()
        self.assertEqual(n, 2)   # "无" 行不落
        self.assertEqual(replays[0][0], "2026-10-28")

    def test_daily_replay_once_per_day(self):
        """同日二次检查不重复回放（meta 防重）。"""
        with patch("brain.ask_local", return_value="a=b"):
            waker.try_daily_replay(datetime(2026, 10, 28, 3, 10, 0))
            with patch("brain.ask_local") as second:
                waker.try_daily_replay(datetime(2026, 10, 28, 4, 10, 0))
                second.assert_not_called()

    def test_replay_before_hour_skipped(self):
        """03:00 前不回放。"""
        with patch("brain.ask_local") as a:
            waker.try_daily_replay(datetime(2026, 10, 28, 2, 0, 0))
            a.assert_not_called()


class StickerParseHardeningTests(unittest.TestCase):
    """标注解析加固（真机 [可爱/开心] 漏网修复）+假承诺防线锚。"""

    def test_mid_slash_annotation_extracted(self):
        """中间 [可爱/开心]：提取首个词+剥除（真机漏网复现场景）。"""
        c, kw = waker.extract_sticker_keyword("太开心了[可爱/开心]，希望你也开心！")
        self.assertEqual(c, "太开心了，希望你也开心！")
        self.assertEqual(kw, "可爱")

    def test_plain_text_untouched(self):
        c, kw = waker.extract_sticker_keyword("没有标注的普通话")
        self.assertEqual(c, "没有标注的普通话")
        self.assertIsNone(kw)

    def test_strip_mid_emotion_annotation(self):
        """strip 兜底：含情绪词的中间短标注剥除。"""
        self.assertEqual(waker.strip_prefix_noise("太开心了[可爱/开心]，希望你也开心！"),
                         "太开心了，希望你也开心！")

    def test_record_fact_note_has_dead_order(self):
        """假承诺防线锚：ext_record_fact note 必须含死命令（2026-10-27
        真机实锤：模型口头'已存入'未调工具）。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "lm_note_check",
            os.path.join(PROJECT_ROOT, "agent_state", "plugins",
                         "qq_lifemate", "__init__.py"),
            submodule_search_locations=[
                os.path.join(PROJECT_ROOT, "agent_state", "plugins",
                             "qq_lifemate")])
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        note = next(t["note"] for t in mod.PLUGIN()["tools"]
                    if t["name"] == "ext_record_fact")
        self.assertIn("必须", note)
        self.assertIn("不许", note)


class PersonConversionTests(unittest.TestCase):
    """人称转换（人格认知 Bug 修复）：主人第一人称落库前转第三人称。"""

    def test_to_third_person_basic(self):
        from agent_state.state_manager import to_third_person_memory as t3
        self.assertEqual(t3("我最喜欢玩明日方舟"), "主人最喜欢玩明日方舟")
        self.assertEqual(t3("我喜欢在周末打游戏"), "主人喜欢在周末打游戏")
        self.assertEqual(t3("我的账号是Lv60"), "主人的账号是Lv60")

    def test_to_third_person_sentence_mid(self):
        from agent_state.state_manager import to_third_person_memory as t3
        self.assertEqual(
            t3("周末打半天游戏，我的账号是Lv60"),
            "周末打半天游戏，主人的账号是Lv60")

    def test_to_third_person_non_first_person_untouched(self):
        from agent_state.state_manager import to_third_person_memory as t3
        self.assertEqual(t3("今天天气不错"), "今天天气不错")
        self.assertEqual(t3(""), "")

    def test_record_fact_converts_first_person(self):
        """record_fact 落库前转换：value 的"我"变"主人"。"""
        tmp = tempfile.mkdtemp(prefix="lm_person_")
        waker.set_data_dir(tmp)
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "agent_state_plugins_qq_lifemate",
                os.path.join(PLUGIN_SRC, "__init__.py"),
                submodule_search_locations=[PLUGIN_SRC])
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            mod.record_fact(key="喜欢的游戏", value="我最喜欢玩明日方舟")
            db = waker._db()
            v = db.execute("SELECT value FROM facts WHERE key='喜欢的游戏'"
                           ).fetchone()[0]
            db.close()
            self.assertEqual(v, "主人最喜欢玩明日方舟")
        finally:
            waker.stop()
            shutil.rmtree(tmp, ignore_errors=True)


class MultiBrainTests(unittest.TestCase):
    """多脑协作 MVP（design_multi_brain.md）：仲裁脑/降级模板/防脑回。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lm_mb_")
        waker.set_data_dir(self.tmp)
        self.now = datetime(2026, 10, 27, 14, 0, 0)

    def tearDown(self):
        waker.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_arbitrate_pass(self):
        with patch("brain.ask_cloud", return_value="PASS"):
            ok, why = waker.arbitrate_wake("主人最喜欢玩明日方舟啦", "主人的游戏")
        self.assertTrue(ok)
        self.assertEqual(why, "PASS")

    def test_arbitrate_fail_on_leak(self):
        with patch("brain.ask_cloud",
                   return_value="FAIL:第一人称代入主人的记忆"):
            ok, why = waker.arbitrate_wake("我最喜欢玩明日方舟", "主人的游戏")
        self.assertFalse(ok)
        self.assertIn("FAIL", why)

    def test_arbitrate_cloud_down_is_fail(self):
        """云端挂=FAIL（宁降级模板不赌 r1）。"""
        with patch("brain.ask_cloud", side_effect=RuntimeError("断网")):
            ok, why = waker.arbitrate_wake("嗨", "")
        self.assertFalse(ok)
        self.assertIn("仲裁异常", why)

    def test_wake_once_fail_twice_falls_back_template(self):
        """表达脑两次渲染均被仲裁否决→模板降级（人称 100% 安全）且发送。"""
        with patch.object(waker, "generate_wake_text",
                          return_value=("我最喜欢玩明日方舟", None)),              patch.object(waker, "arbitrate_wake",
                          return_value=(False, "FAIL:抢戏")),              patch.object(waker, "send_qq", return_value=True) as sq:
            self.assertTrue(waker.wake_once(self.now))
        sent = sq.call_args[0][0]
        self.assertIn("主人", sent)          # 模板含主人
        self.assertNotIn("我最喜欢玩", sent)  # 绝不发抢戏文本
        self.assertNotIn("明日方舟", sent)    # 模板不带记忆细节

    def test_wake_once_pass_goes_through(self):
        """仲裁 PASS：原文发送。"""
        with patch.object(waker, "generate_wake_text",
                          return_value=("主人最喜欢玩明日方舟啦，陪你玩", None)),              patch.object(waker, "arbitrate_wake", return_value=(True, "PASS")),              patch.object(waker, "send_qq", return_value=True) as sq:
            self.assertTrue(waker.wake_once(self.now))
        self.assertIn("主人最喜欢玩明日方舟啦", sq.call_args[0][0])

    def test_send_qq_three_level_receipt(self):
        """防脑回三级回执：200+retcode==0+message_id 才算真发。"""
        import types
        def _resp(status, body):
            r = types.SimpleNamespace()
            r.status_code = status
            r.json = lambda: body
            r.headers = {"content-type": "application/json"}
            return r
        with patch.dict(os.environ, {"XIAOJU3_OWNER_QQ": "123",
                                     "ONEBOT_API_URL": "http://x",
                                     "ONEBOT_TOKEN": ""}),              patch("requests.post") as post:
            # 200 但 retcode!=0：假回执拒绝
            post.return_value = _resp(200, {"retcode": 1, "status": "failed"})
            self.assertFalse(waker.send_qq("hi"))
            # 200+retcode 0+message_id：真发
            post.return_value = _resp(200, {"retcode": 0,
                                            "data": {"message_id": 777}})
            self.assertTrue(waker.send_qq("hi"))
            # 重试恰好 1 次+token header 缺省（env token 空）
            self.assertEqual(post.call_count, 3)
            self.assertNotIn("Authorization", post.call_args[1]["headers"])


class PersonaLeakGuardTests(unittest.TestCase):
    """人称泄露质检门（持久战第四保险）：回复含"我"+记忆 4-gram→纠正。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lm_leak_")
        waker.set_data_dir(self.tmp)

    def tearDown(self):
        waker.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_leak_converted(self):
        """回复"我最喜欢玩明日方舟"+记忆含该 4-gram→纠正为主人。"""
        db = waker._db()
        db.execute("INSERT INTO facts(key, value, ts) VALUES(?,?,?)",
                   ("喜欢的游戏", "主人最喜欢玩明日方舟", "2026-10-27"))
        db.commit()
        db.close()
        import main as main_mod
        with patch.object(main_mod.state_manager, "get_recent_memories",
                          return_value=[("user", "主人最喜欢玩明日方舟")]):
            out = main_mod._persona_leak_guard("我最喜欢玩明日方舟好玩！")
        self.assertEqual(out, "主人最喜欢玩明日方舟好玩！")

    def test_no_leak_untouched(self):
        """无记忆命中（"我最喜欢蓝色"vs 记忆"主人喜欢猫"）：零误伤。"""
        import main as main_mod
        with patch.object(main_mod.state_manager, "get_recent_memories",
                          return_value=[("user", "主人喜欢猫")]):
            out = main_mod._persona_leak_guard("我最喜欢蓝色")
        self.assertEqual(out, "我最喜欢蓝色")

    def test_no_wo_untouched(self):
        """回复不含"我"：直接放行。"""
        import main as main_mod
        with patch.object(main_mod.state_manager, "get_recent_memories",
                          return_value=[("user", "主人喜欢猫")]):
            out = main_mod._persona_leak_guard("主人喜欢猫呢")
        self.assertEqual(out, "主人喜欢猫呢")


class PluginLoadContractTests(unittest.TestCase):
    """目录包装载契约（plugin_loader 六步生命周期）。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="xj3_lifemate_")
        self._enter = patch.object(plugin_loader, "external_dir",
                                   lambda: self._tmp)
        self._enter.start()
        plugin_loader._loaded.clear()
        plugin_loader._rejected.clear()
        shutil.copytree(PLUGIN_SRC, os.path.join(self._tmp, "qq_lifemate"))
        plugin_loader.load_all()
        self.plugin = plugin_loader.loaded_plugins().get("qq_lifemate")
        self.mod = self.plugin["module"] if self.plugin else None

    def tearDown(self):
        plugin_loader.unload_all()
        plugin_loader._loaded.clear()
        plugin_loader._rejected.clear()
        self._enter.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_loaded_not_rejected(self):
        """目录包装载成功（rejected=0）——契约 v1.1 兼容目录包首例。"""
        self.assertIsNotNone(self.plugin, "qq_lifemate 应装载成功")
        self.assertEqual(plugin_loader.rejected_plugins(), [])

    def test_tools_three_with_ext_prefix(self):
        names = [t["name"] for t in self.plugin["plugin"]["tools"]]
        self.assertEqual(sorted(names),
                         ["ext_recall_fact", "ext_record_fact",
                          "ext_scene_report"])

    def test_setup_creates_four_tables(self):
        import sqlite3
        dbp = os.path.join(self.plugin["module"].waker.data_dir(),
                           "memory.db")
        self.assertTrue(os.path.isfile(dbp))
        db = sqlite3.connect(dbp)
        tabs = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        db.close()
        self.assertTrue({"chat_log", "facts", "scene", "rel", "meta"
                         } <= tabs)


class ToolBehaviorTests(unittest.TestCase):
    """record_fact / scene_report / recall_fact 真库行为。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="xj3_lifemate_tool_")
        waker.set_data_dir(self._tmp)
        self.spec = importlib.util.spec_from_file_location(
            "agent_state_plugins_qq_lifemate",
            os.path.join(PLUGIN_SRC, "__init__.py"),
            submodule_search_locations=[PLUGIN_SRC])
        self.mod = importlib.util.module_from_spec(self.spec)
        sys.modules[self.spec.name] = self.mod
        self.spec.loader.exec_module(self.mod)

    def tearDown(self):
        waker.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_record_fact_and_recall(self):
        out = self.mod.record_fact(key="喜欢的饮料", value="冰可乐")
        self.assertIn("记住啦", out)
        back = self.mod.record_fact(key="喜欢的饮料", value="热可可")
        self.assertIn("热可可", back)   # UNIQUE(key) 更新语义
        got = self.mod.recall_fact(key="喜欢的饮料")
        self.assertIn("热可可", got)
        self.assertIn("还没记过", self.mod.recall_fact(key="没记过的"))

    def test_record_fact_requires_both(self):
        out = self.mod.record_fact(key="只有key")
        self.assertIn("❌", out)

    def test_scene_report_appends_and_counts(self):
        self.mod.scene_report(action="在整理待办")
        self.mod.scene_report(action="在陪主人聊天")
        db = waker._db()
        try:
            top = db.execute("SELECT action FROM scene ORDER BY id DESC "
                             "LIMIT 1").fetchone()[0]
            n = db.execute("SELECT COUNT(*) FROM scene").fetchone()[0]
            rel = db.execute("SELECT interactions FROM rel").fetchone()[0]
        finally:
            db.close()
        self.assertEqual(top, "在陪主人聊天")   # 最新在前
        self.assertEqual(n, 2)
        self.assertEqual(rel, 2)
        self.assertIn("状态已记录", self.mod.scene_report(action="x"))

    def test_scene_report_requires_action(self):
        self.assertIn("❌", self.mod.scene_report())


class WakeOnceAccountingTests(unittest.TestCase):
    """wake_once 落账：chat_log+meta 计数+跨日重置。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="xj3_lifemate_wake_")
        waker.set_data_dir(self._tmp)

    def tearDown(self):
        waker.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_wake_once_writes_log_and_counts(self):
        with patch.object(waker, "generate_wake_text",
                          return_value=("主人~想你了 (´･ω･`)", "害羞")), \
             patch.object(waker, "send_qq", return_value=True):
            now = datetime(2026, 10, 27, 14, 0, 0)
            self.assertTrue(waker.wake_once(now))
            self.assertTrue(waker.wake_once(now))
        db = waker._db()
        try:
            n = db.execute("SELECT COUNT(*) FROM chat_log WHERE "
                           "kind='proactive_wake'").fetchone()[0]
            cnt = waker.daily_count(db, now)
            ts = waker.last_speak_ts(db)
        finally:
            db.close()
        self.assertEqual(n, 2)
        self.assertEqual(cnt, 2)
        self.assertIsNotNone(ts)

    def test_daily_count_resets_next_day(self):
        with patch.object(waker, "generate_wake_text",
                          return_value=("嗨", None)), \
             patch.object(waker, "send_qq", return_value=True):
            waker.wake_once(datetime(2026, 10, 27, 14, 0, 0))
        db = waker._db()
        try:
            self.assertEqual(waker.daily_count(
                db, datetime(2026, 10, 28, 9, 0, 0)), 0)   # 次日重置
        finally:
            db.close()

    def test_wake_once_send_fail_no_count(self):
        """发送失败不计次不写账（下轮重试）。"""
        with patch.object(waker, "generate_wake_text",
                          return_value=("嗨", None)), \
             patch.object(waker, "send_qq", return_value=False):
            self.assertFalse(waker.wake_once(datetime(2026, 10, 27, 14, 0, 0)))
        db = waker._db()
        try:
            n = db.execute("SELECT COUNT(*) FROM chat_log").fetchone()[0]
            cnt = waker.daily_count(db, datetime(2026, 10, 27, 14, 0, 0))
        finally:
            db.close()
        self.assertEqual(n, 0)
        self.assertEqual(cnt, 0)

    def test_generate_wake_text_strips_think_and_quotes(self):
        """生成清洗：剥 <think>+剥引号包裹；返回 (话, 表情关键词|None)。"""
        with patch("brain.ask_local", return_value="<think>思考</think>“想你了”"):
            self.assertEqual(waker.generate_wake_text("在待命", self._now()),
                             ("想你了", None))

    @staticmethod
    def _now():
        return datetime(2026, 10, 27, 14, 0, 0)


if __name__ == "__main__":
    unittest.main()
