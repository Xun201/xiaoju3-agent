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

import migration
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


class VerifyAndApplyTests(unittest.TestCase):
    """2-b：verify_soul_bundle_payload + apply_soul_bundle_to_core（共用函数，
    dashboard 端点与批 3 receiver 同源）。全 tmp 沙盒零碰生产。"""

    def setUp(self):
        import tempfile
        self.src = tempfile.mkdtemp(prefix="xj3_b2src_")   # 分身侧
        self.core = tempfile.mkdtemp(prefix="xj3_b2core_")  # 核心侧
        for name in ("identity.json", "ui_pref.json"):
            with open(os.path.join(self.src, name), "wb") as f:
                f.write(b'{"v":1}')
        con = sqlite3.connect(os.path.join(self.src, "relationship.db"))
        con.execute("CREATE TABLE IF NOT EXISTS sample(id INTEGER PRIMARY KEY)")
        con.commit()
        con.close()
        r = soul_sync.make_writeback_bundle(
            path=os.path.join(self.src, "wb.zip"), base_dir=self.src)
        self.bundle = open(r["path"], "rb").read()

    @staticmethod
    def _tampered(bundle):
        """结构完好的篡改包：替换条目内容、保留原 soul_meta → sha 不相符。"""
        import io as _io
        import zipfile as _zf
        src = _zf.ZipFile(_io.BytesIO(bundle))
        buf = _io.BytesIO()
        with _zf.ZipFile(buf, "w", _zf.ZIP_DEFLATED) as out:
            for info in src.infolist():
                data = src.read(info.filename)
                if info.filename == "identity.json":
                    data = b'{"v":999,"tampered":true}'
                out.writestr(info, data)
        return buf.getvalue()

    def test_verify_ok_and_tamper_rejected(self):
        ok, reason, meta, files_sha = migration.verify_soul_bundle_payload(self.bundle)
        self.assertTrue(ok, reason)
        self.assertIn("identity.json", meta["files"])
        ok, reason, _, _ = migration.verify_soul_bundle_payload(self._tampered(self.bundle))
        self.assertFalse(ok)
        self.assertIn("sha256", reason)

    def test_apply_accepted_then_idempotent(self):
        r1 = migration.apply_soul_bundle_to_core(
            self.bundle, base_dir=self.core, device_id="dev-a",
            db_path=os.path.join(self.core, "soul.db"))
        self.assertEqual(r1["status"], "accepted")
        self.assertIn("identity.json", r1["applied"])
        self.assertTrue(os.path.isfile(os.path.join(self.core, "identity.json")))
        r2 = migration.apply_soul_bundle_to_core(
            self.bundle, base_dir=self.core, device_id="dev-a",
            db_path=os.path.join(self.core, "soul.db"))
        self.assertEqual(r2["status"], "idempotent")
        self.assertNotIn("identity.json", r2["applied"])
        self.assertIn("identity.json", r2["skipped"])

    def test_apply_db_backup_path(self):
        """.db 走 sqlite3 backup 整库覆盖（Windows 文件锁安全路径）：
        覆盖后目标库可开且内容来自包。核档 .db（relationship.db）才在包内。"""
        target_db = os.path.join(self.core, "relationship.db")
        con = sqlite3.connect(target_db)
        con.execute("CREATE TABLE IF NOT EXISTS marker(x)")
        con.execute("INSERT INTO marker VALUES ('old')")
        con.commit()
        con.close()
        r = migration.apply_soul_bundle_to_core(
            self.bundle, base_dir=self.core, device_id="dev-a",
            db_path=os.path.join(self.core, "soul.db"))
        self.assertIn("relationship.db", r["applied"])
        con = sqlite3.connect(target_db)
        tables = {x[0] for x in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        con.close()
        self.assertNotIn("marker", tables)   # 整库覆盖=包内库形态
        self.assertFalse(os.path.exists(
            os.path.join(self.core, "staging_soul", "relationship.db.staging")))

    def test_apply_dual_change_conflict_pending(self):
        """双变场景：核心侧文件被改后再收新包 → 采纳+conflicts pending
        （replica_trace 带时间戳=§十.8 剪辑素材预留）。"""
        migration.apply_soul_bundle_to_core(
            self.bundle, base_dir=self.core, device_id="dev-a",
            db_path=os.path.join(self.core, "soul.db"))
        with open(os.path.join(self.core, "identity.json"), "w") as f:
            f.write('{"v":2,"changed":"core-side"}')   # 核心侧变更
        r = migration.apply_soul_bundle_to_core(
            self.bundle, base_dir=self.core, device_id="dev-a",
            db_path=os.path.join(self.core, "soul.db"))
        self.assertTrue(any(c["path"] == "identity.json" for c in r["conflicts"]))
        con = sqlite3.connect(os.path.join(self.core, "soul.db"))
        row = con.execute(
            "SELECT path, status, replica_trace FROM soul_conflicts"
            " WHERE path='identity.json'").fetchone()
        con.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], "pending")
        self.assertIn("sha", row[2])

    def test_apply_rejects_tampered(self):
        with self.assertRaises(ValueError):
            migration.apply_soul_bundle_to_core(
                self._tampered(self.bundle), base_dir=self.core, device_id="dev-a",
                db_path=os.path.join(self.core, "soul.db"))


class WritebackEndpointTests(unittest.TestCase):
    """2-b：/api/soul/writeback HTTP 栈（Flask test_client，沙盒 base 注入）。"""

    def setUp(self):
        import tempfile
        from unittest import mock
        import xiaoju3_dashboard as dash
        self.dash = dash
        self.core = tempfile.mkdtemp(prefix="xj3_b2http_")
        self.token = "test-token-123"
        self._env = mock.patch.dict(os.environ, {
            "XIAOJU3_SOUL_TOKEN": self.token,
            "XIAOJU3_SOUL_CORE_BASE": self.core,
        })
        self._env.start()
        self.addCleanup(self._env.stop)
        self.client = dash.app.test_client()
        # 沙盒分身出包（HTTP 全链用）
        src = tempfile.mkdtemp(prefix="xj3_b2src2_")
        for name in ("identity.json", "ui_pref.json"):
            with open(os.path.join(src, name), "w") as f:
                f.write('{"v":1}')
        r = soul_sync.make_writeback_bundle(
            path=os.path.join(src, "wb.zip"), base_dir=src)
        with open(r["path"], "rb") as f:
            self.bundle = f.read()

    def _post(self, data=None, headers=None):
        return self.client.post("/api/soul/writeback", json=data or {},
                                headers=headers or {})

    def test_401_without_or_wrong_token(self):
        self.assertEqual(self._post({}).status_code, 401)
        self.assertEqual(
            self._post({"bundle": "x"}, headers={"X-Soul-Token": "wrong"}).status_code,
            401)

    def test_409_bad_base64_and_missing_meta(self):
        h = {"X-Soul-Token": self.token}
        r = self._post({"bundle": "!!!not-b64!!!"}, headers=h)
        self.assertEqual(r.status_code, 409)
        import base64
        junk = base64.b64encode(b"not a zip at all").decode()
        r = self._post({"bundle": junk}, headers=h)
        self.assertEqual(r.status_code, 409)

    def test_202_full_chain_via_http(self):
        import base64
        h = {"X-Soul-Token": self.token}
        b64 = base64.b64encode(self.bundle).decode()
        r = self._post({"device_id": "dev-http", "protocol_version": 1,
                        "bundle": b64}, headers=h)
        self.assertEqual(r.status_code, 202)
        data = r.get_json()
        self.assertTrue(data["ack"])
        self.assertEqual(data["protocol_version"], 1)
        # 审计行落沙盒 soul.db
        import sqlite3
        con = sqlite3.connect(os.path.join(self.core, "soul.db"))
        rows = con.execute("SELECT device_id, direction, result FROM"
                           " soul_writeback_log").fetchall()
        con.close()
        self.assertTrue(any(x == ("dev-http", "recv", "accepted") for x in rows))


class HeartbeatTickTests(unittest.TestCase):
    """2-c：heartbeat_soul_tick（心跳兜底）+PeerWatch 恢复重排+挂点形态。
    全 env 沙盒（mock.patch.dict），零碰生产。"""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="xj3_b2c_")
        self.box = soul_sync.SoulOutbox(
            path=os.path.join(self.tmp, "soul_outbox.json"))

    def test_tick_noop_without_core_config(self):
        """未配置 XIAOJU3_SOUL_CORE → tick 返回 None（纯现状零行为）。"""
        from unittest import mock
        with mock.patch.dict(os.environ, {"XIAOJU3_SOUL_CORE": ""},
                             clear=False):
            self.assertIsNone(soul_sync.heartbeat_soul_tick(now=1000.0))

    def test_tick_daily_watermark_and_outbox(self):
        """每日全量：跨天入队+watermark 更新；同天不重复。"""
        from unittest import mock
        wm = os.path.join(self.tmp, ".soul_daily_watermark")
        now = time.mktime(time.strptime("2026-10-16", "%Y-%m-%d"))
        with mock.patch.dict(os.environ, {
                "XIAOJU3_SOUL_CORE": "http://127.0.0.1:59999"}, clear=False), \
                mock.patch.object(soul_sync, "AGENT_STATE_DIR", self.tmp), \
                mock.patch.object(soul_sync, "make_writeback_bundle") as mw, \
                mock.patch.object(soul_sync, "process_outbox", return_value=0):
            mw.return_value = {"ok": True, "path": os.path.join(
                self.tmp, "soul_daily.zip"), "size": 10}
            n1 = soul_sync.heartbeat_soul_tick(now=now)
            self.assertIsNotNone(n1)
            self.assertIn("每日全量入队", n1)
            n2 = soul_sync.heartbeat_soul_tick(now=now + 60)
            self.assertNotIn("每日全量入队", n2 or "")   # 同天 watermark 拦重复
        self.assertEqual(open(wm, encoding="utf-8").read().strip(), "2026-10-16")

    def test_peer_watch_recover_callback(self):
        """PeerWatch 恢复回调：失联达阈值→on_peer_down；恢复→on_peer_recover
        恰一次；未传 recover（默认 None）不炸。"""
        from migration import PeerWatch
        from unittest import mock
        events = []
        pw = PeerWatch(peers=["http://127.0.0.1:59998"], fail_threshold=2,
                       on_peer_down=lambda p: events.append("down"),
                       on_peer_recover=lambda p: events.append("recover"),
                       timeout=0.2)
        def fake_get(url, timeout=None):
            raise OSError("down")
        with mock.patch.object(PeerWatch, "watch_loop", lambda self, **k: None):
            with mock.patch("migration.requests.get", side_effect=fake_get):
                pw.check_peers(); pw.check_peers()
                self.assertIn("down", events)
            with mock.patch("migration.requests.get") as ok_get:
                ok_get.return_value.status_code = 200
                pw.check_peers()
        self.assertIn("recover", events)
        # 默认 None：不炸即可
        PeerWatch(peers=["http://127.0.0.1:59998"], fail_threshold=1,
                  timeout=0.2).check_peers()

    def test_heartbeat_hook_wired(self):
        """挂点形态锚：heartbeat.py 快照节拍区含 soul_sync 旁路接线
        （语句形态：import 行+ImportError 旁路）。"""
        import io
        src = io.open("heartbeat.py", encoding="utf-8").read()
        self.assertIn("import soul_sync as _soul_mod", src)
        self.assertIn("heartbeat_soul_tick()", src)
        self.assertIn("soul_sync.py 缺席时静默旁路", src)
