# -*- coding: utf-8 -*-
"""migration 单元测试：全离线。

覆盖：
- export/import roundtrip（tmp 目录）：灵魂文件全进包、字节一致、
  MANIFEST.txt 生成且含密钥键名清单与 .env 存在性记录；
- 密钥不进包断言（.env 中的假密钥值不得出现在包内任何成员）；
- overwrite 语义（默认跳过冲突，True 才覆盖）；
- zip 路径穿越防护（../ 成员被拒绝）；
- PeerWatch：env 对端解析、存活/失联快照、连续 N 次触发回调、恢复后
  重新计数、backup_on_down 触发 export_bundle、watch_loop 轮次；
- health_bp：Flask test client 校验 /api/health 返回结构。

requests 一律 mock.patch 自动还原，不做 sys.modules 永久注入。
"""
import os
import socket
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import migration

FAKE_SECRET = "sk-test-secret-abc123"  # 仅用于断言"密钥不进包"的假值


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    with open(path, mode, encoding=None if isinstance(content, bytes) else "utf-8") as f:
        f.write(content)
    return path


def _make_soul_state(base_dir):
    """构造一个典型的 agent_state（状态外置层）样例。"""
    _write(os.path.join(base_dir, "identity.json"), '{"current_level": "Lv.3"}')
    _write(os.path.join(base_dir, "history_qq.json"), '[{"role": "user", "content": "hi"}]')
    _write(os.path.join(base_dir, "history_web.json"), '[{"role": "user", "content": "yo"}]')
    _write(os.path.join(base_dir, "conversations", "web_history.json"), '[{"role": "user", "content": "c"}]')
    _write(os.path.join(base_dir, "long_term.db"), b"sqlite-fake-bytes")
    _write(os.path.join(base_dir, "emoji_links.json"), '{"\u7b11\u54ed": "http://example/1.png"}')


class ExportImportRoundtripTests(unittest.TestCase):
    """export → import roundtrip、密钥不进包、MANIFEST 要素。"""

    def test_export_creates_soul_zip_with_all_soul_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "agent_state")
            _make_soul_state(state)
            env_file = _write(os.path.join(tmp, ".env"), f"DEEPSEEK_API_KEY={FAKE_SECRET}\n")

            # 默认落点为项目根 + xiaoju3_soul_<时间戳>.zip 命名（PROJECT_ROOT 指向 tmp 验证）
            with mock.patch.object(migration, "PROJECT_ROOT", tmp):
                path = migration.export_bundle(base_dir=state, env_file=env_file)

            self.assertTrue(os.path.isfile(path))
            name = os.path.basename(path)
            self.assertTrue(name.startswith("xiaoju3_soul_"), name)
            self.assertTrue(name.endswith(".zip"), name)

            with zipfile.ZipFile(path) as zf:
                names = set(zf.namelist())
            # 灵魂文件全进包
            for expected in ("identity.json", "history_qq.json", "history_web.json",
                             "conversations/web_history.json", "long_term.db",
                             "emoji_links.json", "MANIFEST.txt"):
                self.assertIn(expected, names, f"缺少 {expected}")
            # .env 本体绝不进包
            self.assertNotIn(".env", names)

    def test_secret_value_never_enters_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "agent_state")
            _make_soul_state(state)
            env_file = _write(os.path.join(tmp, ".env"),
                              f"DEEPSEEK_API_KEY={FAKE_SECRET}\nHA_TOKEN=ha-secret-xyz\n")

            path = migration.export_bundle(base_dir=state, env_file=env_file,
                                           path=os.path.join(tmp, "soul.zip"))

            with zipfile.ZipFile(path) as zf:
                for info in zf.infolist():
                    content = zf.read(info).decode("utf-8", errors="ignore")
                    self.assertNotIn(FAKE_SECRET, content,
                                     f"密钥值泄漏进包内成员 {info.filename}")
                    self.assertNotIn("ha-secret-xyz", content,
                                     f"密钥值泄漏进包内成员 {info.filename}")

    def test_manifest_lists_secret_key_names_and_env_existence(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "agent_state")
            _make_soul_state(state)
            env_file = _write(os.path.join(tmp, ".env"), f"X={FAKE_SECRET}\n")

            path = migration.export_bundle(base_dir=state, env_file=env_file,
                                           path=os.path.join(tmp, "soul.zip"))

            with zipfile.ZipFile(path) as zf:
                manifest = zf.read("MANIFEST.txt").decode("utf-8")
            for key in migration.SECRET_KEYS:
                self.assertIn(key, manifest, f"MANIFEST 应列键名 {key}")
            self.assertIn(".env 存在性记录：是", manifest)
            self.assertIn("identity.json", manifest)
            self.assertNotIn(FAKE_SECRET, manifest)  # 只列键名，不含值

    def test_manifest_records_missing_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "agent_state")
            _make_soul_state(state)
            path = migration.export_bundle(
                base_dir=state, env_file=os.path.join(tmp, "no_such.env"),
                path=os.path.join(tmp, "soul.zip"))
            with zipfile.ZipFile(path) as zf:
                manifest = zf.read("MANIFEST.txt").decode("utf-8")
            self.assertIn(".env 存在性记录：否", manifest)

    def test_import_roundtrip_restores_files_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "agent_state")
            _make_soul_state(state)
            env_file = _write(os.path.join(tmp, ".env"), f"X={FAKE_SECRET}\n")
            path = migration.export_bundle(base_dir=state, env_file=env_file,
                                           path=os.path.join(tmp, "soul.zip"))

            target = os.path.join(tmp, "restored_state")
            result = migration.import_bundle(path, base_dir=target)

            self.assertIn("identity.json", result["restored"])
            self.assertIn("conversations/web_history.json", result["restored"])
            self.assertEqual(result["skipped"], [])
            # 字节一致（灵魂完整搬家）
            for rel in ("identity.json", "history_qq.json",
                        "conversations/web_history.json", "long_term.db"):
                with open(os.path.join(state, *rel.split("/")), "rb") as f1, \
                        open(os.path.join(target, *rel.split("/")), "rb") as f2:
                    self.assertEqual(f1.read(), f2.read(), rel)
            # MANIFEST 不落盘（属说明文件）
            self.assertFalse(os.path.exists(os.path.join(target, "MANIFEST.txt")))
            # 恢复报告带密钥手工核对提示
            self.assertIn("DEEPSEEK_API_KEY", result["report"])
            self.assertIn("手工核对", result["report"])

    def test_import_skips_conflicts_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "agent_state")
            _make_soul_state(state)
            path = migration.export_bundle(base_dir=state, path=os.path.join(tmp, "soul.zip"))

            target = os.path.join(tmp, "restored_state")
            migration.import_bundle(path, base_dir=target)
            _write(os.path.join(target, "identity.json"), '{"current_level": "Lv.9"}')

            result = migration.import_bundle(path, base_dir=target)
            self.assertIn("identity.json", result["skipped"])
            with open(os.path.join(target, "identity.json"), "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), '{"current_level": "Lv.9"}')  # 未被覆盖

    def test_import_overwrite_true_replaces_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "agent_state")
            _make_soul_state(state)
            path = migration.export_bundle(base_dir=state, path=os.path.join(tmp, "soul.zip"))

            target = os.path.join(tmp, "restored_state")
            migration.import_bundle(path, base_dir=target)
            _write(os.path.join(target, "identity.json"), '{"current_level": "Lv.9"}')

            result = migration.import_bundle(path, base_dir=target, overwrite=True)
            self.assertIn("identity.json", result["restored"])
            with open(os.path.join(target, "identity.json"), "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), '{"current_level": "Lv.3"}')

    def test_import_rejects_path_traversal_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            evil_zip = os.path.join(tmp, "evil.zip")
            with zipfile.ZipFile(evil_zip, "w") as zf:
                zf.writestr("../evil.txt", "pwned")
                zf.writestr("identity.json", '{"ok": true}')

            target = os.path.join(tmp, "restored_state")
            result = migration.import_bundle(evil_zip, base_dir=target)

            self.assertIn("identity.json", result["restored"])
            self.assertTrue(any("不安全路径" in s for s in result["skipped"]))
            self.assertFalse(os.path.exists(os.path.join(tmp, "evil.txt")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "restored_state_evil.txt")))

    def test_export_empty_state_dir_still_makes_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "empty_state")
            os.makedirs(state)
            path = migration.export_bundle(base_dir=state, path=os.path.join(tmp, "soul.zip"))
            with zipfile.ZipFile(path) as zf:
                self.assertIn("MANIFEST.txt", zf.namelist())
                manifest = zf.read("MANIFEST.txt").decode("utf-8")
            self.assertIn("为空", manifest)


class PeerWatchTests(unittest.TestCase):
    """PeerWatch：env 解析、探测快照、连续 N 次触发回调、恢复重计、备份联动。"""

    def test_peers_parsed_from_env(self):
        with mock.patch.dict(os.environ, {"XIAOJU3_PEERS": "http://a:5002, http://b:5003 ,"},
                             clear=False):
            self.assertEqual(migration._peers_from_env(),
                             ["http://a:5002", "http://b:5003"])
            watch = migration.PeerWatch()
            self.assertEqual(watch.peers, ["http://a:5002", "http://b:5003"])

    def test_peers_param_overrides_env(self):
        with mock.patch.dict(os.environ, {"XIAOJU3_PEERS": "http://a:5002"}, clear=False):
            watch = migration.PeerWatch(peers=["http://b:5002"])
            self.assertEqual(watch.peers, ["http://b:5002"])

    def test_check_peers_alive_snapshot(self):
        watch = migration.PeerWatch(peers=["http://p1:5002"])
        resp = mock.MagicMock(status_code=200)
        with mock.patch.object(migration.requests, "get", return_value=resp) as mget:
            snaps = watch.check_peers()
        mget.assert_called_once_with("http://p1:5002/api/health", timeout=3)
        self.assertEqual(len(snaps), 1)
        self.assertTrue(snaps[0]["alive"])
        self.assertEqual(snaps[0]["fail_count"], 0)
        self.assertIn("ts", snaps[0])

    def test_check_peers_failure_increments_count(self):
        watch = migration.PeerWatch(peers=["http://p1:5002"])
        with mock.patch.object(migration.requests, "get",
                               side_effect=ConnectionError("refused")):
            snaps = watch.check_peers()
            self.assertFalse(snaps[0]["alive"])
            self.assertEqual(snaps[0]["fail_count"], 1)
            snaps = watch.check_peers()
            self.assertEqual(snaps[0]["fail_count"], 2)

    def test_non_200_counts_as_down(self):
        watch = migration.PeerWatch(peers=["http://p1:5002"])
        with mock.patch.object(migration.requests, "get",
                               return_value=mock.MagicMock(status_code=503)):
            snaps = watch.check_peers()
        self.assertFalse(snaps[0]["alive"])
        self.assertEqual(snaps[0]["fail_count"], 1)

    def test_callback_triggers_after_consecutive_threshold(self):
        cb = mock.MagicMock()
        watch = migration.PeerWatch(peers=["http://p1:5002"], fail_threshold=3,
                                    on_peer_down=cb)
        with mock.patch.object(migration.requests, "get",
                               side_effect=ConnectionError("down")):
            watch.check_peers()
            cb.assert_not_called()
            watch.check_peers()
            cb.assert_not_called()
            watch.check_peers()
            cb.assert_called_once_with("http://p1:5002")  # 第 3 次连续失联触发
            watch.check_peers()
            cb.assert_called_once()  # 不重复报警

    def test_recovery_resets_counter_then_can_retrigger(self):
        cb = mock.MagicMock()
        watch = migration.PeerWatch(peers=["http://p1:5002"], fail_threshold=2,
                                    on_peer_down=cb)
        with mock.patch.object(migration.requests, "get",
                               side_effect=ConnectionError("down")):
            watch.check_peers()
            watch.check_peers()
            cb.assert_called_once()
        with mock.patch.object(migration.requests, "get",
                               return_value=mock.MagicMock(status_code=200)):
            snaps = watch.check_peers()
            self.assertTrue(snaps[0]["alive"])
            self.assertEqual(snaps[0]["fail_count"], 0)
        with mock.patch.object(migration.requests, "get",
                               side_effect=ConnectionError("down")):
            watch.check_peers()
            cb.assert_called_once()      # 恢复后重新计数
            watch.check_peers()
            self.assertEqual(cb.call_count, 2)  # 再次连续失联可再次触发

    def test_multiple_peers_independent(self):
        cb = mock.MagicMock()
        watch = migration.PeerWatch(peers=["http://p1:5002", "http://p2:5002"],
                                    fail_threshold=2, on_peer_down=cb)
        responses = {"http://p1:5002/api/health": ConnectionError("down")}
        def fake_get(url, timeout=None):
            if url in responses and isinstance(responses[url], Exception):
                raise responses[url]
            return mock.MagicMock(status_code=200)
        with mock.patch.object(migration.requests, "get", side_effect=fake_get):
            watch.check_peers()
            snaps = watch.check_peers()  # 取第二轮快照（计数已累计到 2）
        by_peer = {s["peer"]: s for s in snaps}
        self.assertEqual(by_peer["http://p1:5002"]["fail_count"], 2)
        self.assertEqual(by_peer["http://p2:5002"]["fail_count"], 0)
        cb.assert_called_once_with("http://p1:5002")

    def test_default_callback_keeps_backup_on_down(self):
        with mock.patch.object(migration, "export_bundle",
                               return_value="/tmp/xiaoju3_soul_x.zip") as mexp:
            watch = migration.PeerWatch(peers=["http://p1:5002"], fail_threshold=1,
                                        backup_on_down=True)
            with mock.patch.object(migration.requests, "get",
                                   side_effect=ConnectionError("down")):
                watch.check_peers()
            mexp.assert_called_once()

    def test_default_callback_no_backup_by_default(self):
        with mock.patch.object(migration, "export_bundle") as mexp:
            watch = migration.PeerWatch(peers=["http://p1:5002"], fail_threshold=1)
            with mock.patch.object(migration.requests, "get",
                                   side_effect=ConnectionError("down")):
                watch.check_peers()
            mexp.assert_not_called()

    def test_callback_exception_does_not_break_check(self):
        cb = mock.MagicMock(side_effect=RuntimeError("回调炸了"))
        watch = migration.PeerWatch(peers=["http://p1:5002"], fail_threshold=1,
                                    on_peer_down=cb)
        with mock.patch.object(migration.requests, "get",
                               side_effect=ConnectionError("down")):
            snaps = watch.check_peers()
        self.assertFalse(snaps[0]["alive"])  # 异常被吞，巡检照常返回快照

    def test_watch_loop_rounds_and_sleep(self):
        watch = migration.PeerWatch(peers=["http://p1:5002"])
        with mock.patch.object(watch, "check_peers") as mcheck, \
                mock.patch.object(migration.time, "sleep") as msleep:
            watch.watch_loop(interval=7, max_rounds=2)
        self.assertEqual(mcheck.call_count, 2)
        msleep.assert_called_once_with(7)  # 末轮不再休眠


class HealthBlueprintTests(unittest.TestCase):
    """health_bp：/api/health 返回 {status, device, ts}。"""

    def test_health_endpoint_payload(self):
        from flask import Flask
        app = Flask(__name__)
        app.register_blueprint(migration.health_bp)
        client = app.test_client()
        resp = client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["device"], socket.gethostname())
        self.assertIn("ts", data)


class ImportSafetyTests(unittest.TestCase):
    """import 本模块零副作用 + 接线契约名。"""

    def test_module_importable_and_contract_names(self):
        self.assertTrue(callable(migration.export_bundle))
        self.assertTrue(callable(migration.import_bundle))
        self.assertTrue(callable(migration.PeerWatch))
        self.assertIsNotNone(migration.health_bp)

    def test_constants(self):
        self.assertEqual(migration.PEERS_ENV, "XIAOJU3_PEERS")
        self.assertTrue(migration.SOUL_PREFIX.startswith("xiaoju3_soul"))
        self.assertEqual(migration.PEER_TIMEOUT, 3)


if __name__ == "__main__":
    unittest.main()
