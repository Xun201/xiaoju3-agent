# -*- coding: utf-8 -*-
"""devlog_export.py 离线单测（_dev 素材导出脚本，私有流水账管线）。

全程临时库 + mock，绝不触碰真实 ~/.zcode 会话库；不读 message 正文。
"""
import importlib.util
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC = importlib.util.spec_from_file_location(
    "devlog_export", os.path.join(PROJECT_ROOT, "_dev", "devlog_export.py"))
devlog_export = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(devlog_export)

PROJECT_DIR = "F:\\Orangepi_number3"


def _mini_db(path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE session (id TEXT PRIMARY KEY, slug TEXT, title TEXT, "
                "parent_id TEXT, directory TEXT, time_created INTEGER, "
                "time_updated INTEGER)")
    con.execute("CREATE TABLE tool_usage (id INTEGER PRIMARY KEY, session_id TEXT, "
                "tool_name TEXT, started_at INTEGER)")
    con.commit()
    con.close()
    return path


class DayBoundsTests(unittest.TestCase):
    """day_bounds_ms：本地日期 → [起, 止) 毫秒，跨度恰一天。"""

    def test_bounds_span_one_day(self):
        start, end = devlog_export.day_bounds_ms("2026-10-03")
        self.assertEqual(end - start, devlog_export.MS_DAY)

    def test_bounds_start_is_midnight_local(self):
        from datetime import datetime
        start, _ = devlog_export.day_bounds_ms("2026-10-03")
        self.assertEqual(datetime.fromtimestamp(start / 1000).strftime("%H:%M:%S"),
                         "00:00:00")


class SessionsForDayTests(unittest.TestCase):
    """sessions_for_day：directory 过滤 + 当日活动时间窗 + 子代理不漏。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xj3_devlog_")
        self.db = _mini_db(os.path.join(self.tmp, "copy.sqlite"))
        self.con = sqlite3.connect(self.db)
        rows = [
            ("s1", "proj 1", "主对话·白天的活", None, PROJECT_DIR, 100, 200),
            ("s2", "proj 2", "子代理·跑腿", "s1", PROJECT_DIR, 150, 250),
            ("s3", "别的项目", "不该出现", None, "C:\\other", 120, 220),
            ("s4", "proj 窗外", "时间窗外", None, PROJECT_DIR, 90_000_000, 90_100_000),
        ]
        self.con.executemany(
            "INSERT INTO session (id, slug, title, parent_id, directory, "
            "time_created, time_updated) VALUES (?,?,?,?,?,?,?)", rows)
        self.con.commit()

    def tearDown(self):
        self.con.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_filters_directory_and_window_keeps_subagent(self):
        rows = devlog_export.sessions_for_day(sqlite3.connect(self.db),
                                              PROJECT_DIR, 0, 50_000_000)
        ids = [r[0] for r in rows]
        self.assertIn("s1", ids)
        self.assertIn("s2", ids)          # 子代理不漏
        self.assertNotIn("s3", ids)       # 别的项目
        self.assertNotIn("s4", ids)       # 时间窗外


class ToolStatsTests(unittest.TestCase):
    """tool_stats：按工具聚合、次数降序、空会话/空窗安全。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xj3_devlog_")
        self.db = _mini_db(os.path.join(self.tmp, "copy.sqlite"))
        self.con = sqlite3.connect(self.db)
        self.con.execute("INSERT INTO session (id, slug, title, parent_id, "
                         "directory, time_created, time_updated) "
                         "VALUES ('s1', '', '', NULL, 'X', 1, 2)")
        rows = [("read_file", 10), ("read_file", 11), ("bash", 12)]
        self.con.executemany(
            "INSERT INTO tool_usage (id, session_id, tool_name, started_at) "
            "VALUES (?,?,?,?)",
            [(i, "s1", name, ts) for i, (name, ts) in enumerate(rows)])
        self.con.commit()

    def tearDown(self):
        self.con.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sorted_and_counted(self):
        stats = devlog_export.tool_stats(sqlite3.connect(self.db), ["s1"], 0, 10**12)
        self.assertEqual(stats, [("read_file", 2), ("bash", 1)])

    def test_empty_sessions_safe(self):
        self.assertEqual(devlog_export.tool_stats(sqlite3.connect(self.db),
                                                  [], 0, 10**12), [])


class RenderTests(unittest.TestCase):
    """render：素材块含会话/工具/commit 三节；空输入输出骨架头。"""

    def test_render_contains_sections(self):
        sessions = [("sess_x", "slug x", "标题 x", "p1", 1, 2)]
        stats = [("bash", 3)]
        md = devlog_export.render("2026-10-03", sessions, stats,
                                  ["abc123 2026-10-03 10:00 +0800 修复某事"])
        self.assertIn("〔素材〕2026-10-03", md)
        self.assertIn("**会话**", md)
        self.assertIn("**工具调用 TOP**", md)
        self.assertIn("**commit 时间线**", md)
        self.assertIn("abc123", md)

    def test_render_empty_day(self):
        md = devlog_export.render("2026-10-03", [], [], [])
        self.assertIn("〔素材〕2026-10-03", md)
        self.assertNotIn("None", md)


class GitCommitsTests(unittest.TestCase):
    """git_commits：mock subprocess，解析非空行。"""

    def test_parses_nonempty_lines(self):
        fake = mock.MagicMock(returncode=0,
                              stdout="abc123 2026-10-03 10:00 +0800 fix one\n\nx9999 2026-10-03 11:00 +0800 fix two\n",
                              stderr="")
        with mock.patch.object(devlog_export.subprocess, "run", return_value=fake):
            lines = devlog_export.git_commits("2026-10-03", r"F:\Orangepi_number3")
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("abc123"))


if __name__ == "__main__":
    unittest.main()
