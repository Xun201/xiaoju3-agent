# -*- coding: utf-8 -*-
"""soul_manifest 单元测试（#319 批 1）：三档分类 / is_soul_path 各档 /
soul_targets 清单收集 / default deny / 单一事实源契约。全离线。"""
import os
import socket
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import soul_manifest


class TierClassificationTests(unittest.TestCase):
    """三档分类锚：核/扩展各代表 + 不迁档 default deny + 侧车跟随主库。"""

    def test_core_files_classified_core(self):
        for name in soul_manifest.SOUL_CORE:
            self.assertEqual(soul_manifest.is_soul_path(name), "core", name)

    def test_extension_files_classified_ext(self):
        for name in soul_manifest.SOUL_EXTENSION:
            self.assertEqual(soul_manifest.is_soul_path(name), "ext", name)

    def test_pattern_members_classified_ext(self):
        for rel in ("history_qq.json", "history_console.json",
                    "conversations/web_history.json",
                    "conversations/2026-10/deep/x.json"):
            self.assertEqual(soul_manifest.is_soul_path(rel), "ext", rel)

    def test_not_soul_and_unknown_default_deny(self):
        """不迁档（NOT_SOUL 在列）与未登记新文件一律 None（default deny）。"""
        for rel in ("trace.db", "proactive.db", "recent_actions.json",
                    ".env", ".todo_sync_watermark",
                    "napcat_fire_20261011_160245.log",
                    "identity.json.bak-20261009-163631",
                    "todos.db.bak-20261005",
                    "exports/report.csv", "future_new_file.json"):
            self.assertIsNone(soul_manifest.is_soul_path(rel), rel)

    def test_sqlite_sidecars_follow_main_db_tier(self):
        self.assertEqual(soul_manifest.is_soul_path("relationship.db-wal"), "core")
        self.assertEqual(soul_manifest.is_soul_path("long_term.db-shm"), "core")
        self.assertEqual(soul_manifest.is_soul_path("todos.db-wal"), "ext")
        self.assertEqual(soul_manifest.is_soul_path("todos.db-journal"), "ext")
        self.assertIsNone(soul_manifest.is_soul_path("trace.db-wal"))

    def test_path_forms_normalized(self):
        self.assertEqual(soul_manifest.is_soul_path("conversations\\a.json"), "ext")
        self.assertEqual(soul_manifest.is_soul_path("./identity.json"), "core")
        self.assertIsNone(soul_manifest.is_soul_path(""))
        self.assertIsNone(soul_manifest.is_soul_path("conversations/"))


class SoulTargetsTests(unittest.TestCase):
    """soul_targets：清单收集 / include_extensions 开关 / 空态。"""

    def _make(self, base):
        os.makedirs(base, exist_ok=True)
        files = [
            "identity.json", "relationship.db", "long_term.db",      # 核
            "ui_pref.json", "user_location.json",
            "todos.db", "mood.db", "history_qq.json",                # 扩展
            "conversations/web_history.json",                        # 扩展目录
            "trace.db", "recent_actions.json", "napcat_fire_x.log",  # 不迁
            "identity.json.bak-20261009",                            # 备份残迹
        ]
        for rel in files:
            p = os.path.join(base, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write("{}")
        return files

    def test_targets_core_and_ext_only_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make(tmp)
            targets = soul_manifest.soul_targets(tmp)
            for expected in ("identity.json", "relationship.db", "long_term.db",
                             "ui_pref.json", "user_location.json",
                             "todos.db", "mood.db", "history_qq.json",
                             "conversations/web_history.json"):
                self.assertIn(expected, targets, expected)
            for banned in ("trace.db", "recent_actions.json",
                           "napcat_fire_x.log", "identity.json.bak-20261009"):
                self.assertNotIn(banned, targets, banned)
            self.assertEqual(targets, sorted(targets))

    def test_targets_core_only_when_extensions_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make(tmp)
            targets = soul_manifest.soul_targets(tmp, include_extensions=False)
            self.assertIn("relationship.db", targets)
            for banned in ("todos.db", "mood.db", "history_qq.json",
                           "conversations/web_history.json"):
                self.assertNotIn(banned, targets, banned)

    def test_targets_empty_and_missing_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = os.path.join(tmp, "empty")
            os.makedirs(empty)
            self.assertEqual(soul_manifest.soul_targets(empty), [])
            self.assertEqual(soul_manifest.soul_targets(os.path.join(tmp, "nope")), [])


class ContractTests(unittest.TestCase):
    """单一事实源契约：migration 挂本模块；device_id 与 health 同源。"""

    def test_migration_reads_manifest_single_source(self):
        import migration
        self.assertIs(migration.soul_manifest, soul_manifest)

    def test_device_id_is_hostname(self):
        self.assertEqual(soul_manifest.device_id(), socket.gethostname())

    def test_tier_constants(self):
        self.assertEqual(soul_manifest.TIER_CORE, "core")
        self.assertEqual(soul_manifest.TIER_EXT, "ext")

    def test_no_overlap_between_core_and_extension(self):
        self.assertEqual(
            set(soul_manifest.SOUL_CORE) & set(soul_manifest.SOUL_EXTENSION),
            set())


if __name__ == "__main__":
    unittest.main()
