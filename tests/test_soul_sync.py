# -*- coding: utf-8 -*-
"""#319 批 2 锚（design_319_batch2_impl.md §五）：outbox 退避曲线/原子写/
积压生活化/soul.db 幂等建表/core-only 包。2-a 先落 6 锚，端点与闭环锚随
2-b/2-c 续增（+9 总账）。"""
import json
import os
import sqlite3
import tempfile
import time
import unittest

import soul_manifest
import soul_sync


class SoulOutboxTests(unittest.TestCase):
    """SoulOutbox：入队/due 过滤/退避曲线/出队/原子写/积压提示。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xj3_soulsync_")
        self.box = soul_sync.SoulOutbox(
            path=os.path.join(self.tmp, "soul_outbox.json"))

    def test_enqueue_and_due_filter(self):
        """入队后立即 due 命中；next_ts 未来的条目不出队。"""
        self.box.enqueue("b1.zip", "http://core", device_id="d1", now=1000.0)
        self.assertEqual(len(self.box.due(now=1000.0)), 1)
        self.assertEqual(len(self.box.due(now=500.0)), 0)   # 未到期不出队

    def test_backoff_schedule(self):
        """退避曲线逐档：1→60s，2→300s，3→1800s，≥4 封顶 7200s。"""
        e = self.box.enqueue("b.zip", "http://core", now=1000.0)
        for attempt, expect in ((1, 60), (2, 300), (3, 1800), (4, 7200),
                                (9, 7200)):
            e["attempts"] = attempt - 1
            e["next_ts"] = 0
            self.box.mark_fail(e, now=1000.0)
            entries = self.box.all_entries()
            delta = entries[0]["next_ts"] - 1000.0
            self.assertEqual(delta, expect, f"attempt={attempt}")
        # 临时包文件防 unlink 报错（测试目录随 rmtree 清理，无需手动删）

    def test_mark_done_removes_entry(self):
        """成功出队：同 bundle_path+created_at 精确匹配移除。"""
        e1 = self.box.enqueue("a.zip", "http://core", now=1.0)
        e2 = self.box.enqueue("b.zip", "http://core", now=2.0)
        self.box.mark_done(e1)
        left = self.box.all_entries()
        self.assertEqual(len(left), 1)
        self.assertEqual(left[0]["bundle_path"], "b.zip")

    def test_backlog_alert_lifecycle_and_wording(self):
        """积压阈值（件数≥5 或最老件>2h）触发生活化提示；
        负向锁：文案禁 ERROR/CRITICAL 词族（§十.11 生活事件非技术故障）。"""
        text = self.box.backlog_alert(now=1000.0)
        self.assertIsNone(text)   # 空队列不告警
        for i in range(soul_sync.BACKLOG_COUNT_THRESHOLD):
            self.box.enqueue(f"b{i}.zip", "http://core", now=999.0)
        text = self.box.backlog_alert(now=1000.0)
        self.assertIsNotNone(text)
        self.assertNotIn("ERROR", text.upper().replace("错误", ""))
        for bad in ("ERROR", "CRITICAL", "FATAL"):
            self.assertNotIn(bad, text)
        # 年龄路径：单件最老件 >2h 同样触发
        box2 = soul_sync.SoulOutbox(
            path=os.path.join(self.tmp, "outbox2.json"))
        box2.enqueue("old.zip", "http://core", now=1.0)
        self.assertIsNotNone(box2.backlog_alert(now=1.0 + 7201))


class SoulDbTests(unittest.TestCase):
    """soul.db（S1 幂等建表）+manifest 三档扩充核对。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xj3_souldb_")
        self.db = os.path.join(self.tmp, "soul.db")

    def test_idempotent_init_and_audit_row(self):
        """幂等建表：重复调用零副作用；审计行落库可查。"""
        p1 = soul_sync.init_soul_db(self.db)
        p2 = soul_sync.init_soul_db(self.db)
        self.assertEqual(p1, p2)
        soul_sync.log_writeback("dev-x", "recv", "accepted", files_n=6,
                                bytes_n=1234, db_path=self.db)
        soul_sync.log_writeback("dev-x", "send", "done", db_path=self.db)
        con = sqlite3.connect(self.db)
        rows = con.execute(
            "SELECT device_id, action, result, files_n FROM soul_writeback_log"
            " ORDER BY id").fetchall()
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        con.close()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], ("dev-x", "recv", "accepted", 6))
        self.assertIn("soul_conflicts", tables)
        cols = {r[1] for r in sqlite3.connect(self.db).execute(
            "PRAGMA table_info(soul_conflicts)").fetchall()}
        self.assertIn("replica_trace", cols)   # §十.8 剪辑素材预留
        self.assertIn("status", cols)

    def test_manifest_tiers_extended(self):
        """soul_manifest 扩两行：soul.db=core；soul_outbox/watermark 不迁
        （NOT_SOUL 与 default deny 同为 None）。"""
        self.assertEqual(soul_manifest.is_soul_path("soul.db"), "core")
        self.assertIsNone(soul_manifest.is_soul_path("soul_outbox.json"))
        self.assertIsNone(soul_manifest.is_soul_path(".soul_daily_watermark"))
        self.assertIn("soul.db", soul_manifest.SOUL_CORE)
        self.assertIn("soul_outbox.json", soul_manifest.NOT_SOUL)


class MakeWritebackBundleTests(unittest.TestCase):
    """make_writeback_bundle：core-only 轻量包（§十.9 派半个人）。"""

    def test_core_only_bundle(self):
        """临时 agent_state 种核+扩档文件：包含核、不含扩；
        soul_meta 带 include_extensions=False 与逐文件 sha256。"""
        import zipfile
        base = tempfile.mkdtemp(prefix="xj3_soulpkg_")
        for name, tier in (("identity.json", "core"), ("todos.db", "ext")):
            with open(os.path.join(base, name), "wb") as f:
                f.write(b"x" * 16)
        out = os.path.join(base, "bundle.zip")
        r = soul_sync.make_writeback_bundle(path=out, base_dir=base)
        self.assertTrue(r["ok"])
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            meta = json.loads(zf.read("soul_meta.json").decode("utf-8"))
        # v2 包内路径=裸相对路径（以 base_dir 为基准，无 agent_state/ 前缀）
        self.assertIn("identity.json", names)
        self.assertNotIn("todos.db", names)   # ext 不入
        self.assertFalse(meta["include_extensions"])
        self.assertIn("identity.json", meta["files"])
        self.assertIn("sha256", meta["files"]["identity.json"])


if __name__ == "__main__":
    unittest.main()
