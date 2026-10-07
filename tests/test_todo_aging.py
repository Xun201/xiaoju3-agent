# -*- coding: utf-8 -*-
"""plugins/todo_aging 单元测试（2026-10-07 时间老化+梯队递补四拍板）。

全部离线：云端 ask_cloud 注入 MagicMock；库走 StateManager(tmp base_dir)。
覆盖：判据同源（提炼/老化 prompt） / 解析容错 / 兜底四则（满 N 天/只升
一档/只升不降/封顶 P0） / 只增不回退+手动清 effective / COALESCE 显示 /
递补级联+新项不回退 / 同天幂等闸。
"""
import datetime
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock

from agent_state.state_manager import StateManager
from plugins import todo_aging, todo_extractor

TODAY = datetime.date(2026, 10, 7)


class TodoAgingTests(unittest.TestCase):
    """时间老化 + 梯队递补逐拍板锚。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_aging_")
        self.sm = StateManager(base_dir=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _add(self, content, priority="P1", created=None):
        """入库（content 唯一）并按需回拨 created_at（直接 SQL，仅测试库）。

        返回该条 id（tmp 库自增，按 content 反查最稳）。"""
        self.sm.save_todos([{"content": content, "priority": priority}],
                           source_url="aging_test")
        tid = next(t["id"] for t in self.sm.get_todos()
                   if t["content"] == content)
        if created:
            conn = sqlite3.connect(self.sm.todos_db)
            conn.execute("UPDATE todos SET created_at = ? WHERE id = ?",
                         (created, tid))
            conn.commit()
            conn.close()
        return tid

    def test_priority_criteria_single_source(self):
        """判据同源锚：提炼 prompt 与老化 prompt 引用同一 PRIORITY_CRITERIA
        常量——单源防漂移（改判据两处同步生效）。"""
        self.assertIn(todo_extractor.PRIORITY_CRITERIA,
                      todo_extractor.build_extraction_prompt("片段"))
        self.assertIn(todo_extractor.PRIORITY_CRITERIA,
                      todo_extractor.build_aging_prompt(
                          [{"id": 1, "priority": "P2", "content": "x",
                            "created_at": "2026-10-01"}]))

    def test_parse_aging_json_tolerant(self):
        """解析容错锚：剥围栏 / 数字字符串 id 收 / 非法 id·非六档 suggest·
        非 dict 项丢 / 脏输入与 None 永不抛错返回 []。"""
        dirty = ('```json\n[{"id": "3", "suggest": "p1"}, '
                 '{"id": "x", "suggest": "P1"}, {"id": 4}, '
                 '{"id": 5, "suggest": "PX"}, {"id": 6, "suggest": "P2"}, '
                 '"junk"]\n```')
        self.assertEqual(
            todo_extractor.parse_aging_json(dirty),
            [{"id": 3, "suggest": "P1"}, {"id": 6, "suggest": "P2"}])
        self.assertEqual(todo_extractor.parse_aging_json("不是JSON"), [])
        self.assertEqual(todo_extractor.parse_aging_json(None), [])

    def test_aging_backstop_rules(self):
        """兜底四则锚：不满 N 天不升 / 满档只升一档（P3 建议 P1 → 实升 P2）/
        降档建议忽略 / 升一档封顶 P0。AI 只建议、代码真升。"""
        fresh = self._add("新条目还没满三天", "P3",
                          created="2026-10-06 08:00:00")     # 1 天 < N=3
        old = self._add("老条目满三天该升了", "P3",
                        created="2026-09-01 08:00:00")       # 36 天
        dem = self._add("建议降档的条目", "P2",
                        created="2026-09-01 08:00:00")
        cap = self._add("顶档附近条目", "P1",
                        created="2026-09-01 08:00:00")
        reply = (f'[{{"id": {fresh}, "suggest": "P1"}}, '
                 f'{{"id": {old}, "suggest": "P1"}}, '
                 f'{{"id": {dem}, "suggest": "P4"}}, '
                 f'{{"id": {cap}, "suggest": "P0"}}]')
        with mock.patch.object(todo_aging, "ask_cloud", return_value=reply):
            summary = todo_aging.run_daily_aging(sm=self.sm, today=TODAY)
        # 兜底四则看老化层记录 summary["promoted"]（递补级联在其后另跑，
        # 会再整体抬档——那由 cascade 锚单独覆盖）：
        self.assertEqual(
            sorted((p["id"], p["to"]) for p in summary["promoted"]),
            sorted([(old, "P2"), (cap, "P0")]))          # 只升一档 / 封顶 P0
        promoted_ids = [p["id"] for p in summary["promoted"]]
        self.assertNotIn(fresh, promoted_ids)            # 不满 N 天不升
        self.assertNotIn(dem, promoted_ids)              # 降档建议忽略

    def test_effective_only_increase_and_manual_clear(self):
        """只增不回退 + 拍板④手动清：降档/同档/非法档一律 False；升档写
        effective 且原列不动；clear 后显示回归原档。"""
        tid = self._add("手动覆盖实验", "P1")
        self.assertFalse(self.sm.set_effective_priority(tid, "P3"))   # 降档拒绝
        self.assertFalse(self.sm.set_effective_priority(tid, "P1"))   # 同档拒绝
        self.assertFalse(self.sm.set_effective_priority(tid, "PX"))   # 非法档
        self.assertTrue(self.sm.set_effective_priority(tid, "P0"))    # 升档
        row = self.sm.get_todos(status="pending")[0]
        self.assertEqual(row["effective_priority"], "P0")
        self.assertEqual(row["priority"], "P1")                       # 原列不动
        self.sm.clear_effective_priority(tid)
        row = self.sm.get_todos(status="pending")[0]
        self.assertEqual(row["effective_priority"], "P1")             # 回归原档

    def test_get_todos_coalesce_display(self):
        """COALESCE 显示锚：未老化=原档；已老化=生效档；原 priority 照返
        （前端"↑已升"标记据两列对照）。"""
        self._add("未老化显示原档", "P2")
        aged = self._add("已老化显示新档", "P4", created="2026-09-01 08:00:00")
        self.sm.set_effective_priority(aged, "P3")
        rows = {t["content"]: t for t in self.sm.get_todos(status="pending")}
        self.assertEqual(rows["未老化显示原档"]["effective_priority"], "P2")
        self.assertEqual(rows["已老化显示新档"]["effective_priority"], "P3")
        self.assertEqual(rows["已老化显示新档"]["priority"], "P4")

    def test_backfill_cascade_and_no_rollback(self):
        """递补锚：P1-P4 全空 → P5 整体级联升到 P1（P0 有货不空）；新项加入
        自己的档后只触发自己档的递补，已升项不回退（只增不回退）。"""
        self._add("顶档独苗", "P0")
        low1 = self._add("底层一号", "P5")
        low2 = self._add("底层二号", "P5")
        moved = todo_aging.run_backfill(sm=self.sm)
        # 级联：P1-P4 全空 → P5 整体逐档升到 P1（P0 有货不空），每档一步
        self.assertEqual([m["to"] for m in moved], ["P4", "P3", "P2", "P1"])
        self.assertEqual(moved[0]["from"], "P5")
        self.assertEqual(sorted(moved[0]["ids"]), sorted([low1, low2]))
        eff = {t["content"]: t for t in self.sm.get_todos(status="pending")}
        self.assertEqual(eff["底层一号"]["effective_priority"], "P1")
        self.assertEqual(eff["底层二号"]["effective_priority"], "P1")
        self.assertEqual(eff["底层一号"]["priority"], "P5")   # 原档不动
        # 新项加入 P3：只把自己档往上补（P2 空 → P3→P2），P1 已升项不回退
        self._add("新来的常规项", "P3")
        todo_aging.run_backfill(sm=self.sm)
        eff = {t["content"]: t for t in self.sm.get_todos(status="pending")}
        self.assertEqual(eff["底层一号"]["effective_priority"], "P1")   # 不回退
        self.assertEqual(eff["新来的常规项"]["effective_priority"], "P2")
        self.assertEqual(eff["新来的常规项"]["priority"], "P3")

    def test_daily_gate_idempotent(self):
        """幂等闸锚：同天二次 run 返回 None（心跳 60s 重入安全）；
        aging_last_date 落 todos_meta。"""
        self._add("任意条目", "P3", created="2026-09-01 08:00:00")
        with mock.patch.object(todo_aging, "ask_cloud", return_value="[]"):
            first = todo_aging.run_daily_aging(sm=self.sm, today=TODAY)
            second = todo_aging.run_daily_aging(sm=self.sm, today=TODAY)
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(self.sm.get_meta(todo_aging.AGING_META_KEY),
                         str(TODAY))


if __name__ == "__main__":
    unittest.main()
