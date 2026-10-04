# -*- coding: utf-8 -*-
"""plugins/todo_extractor 单元测试（2026-10-04 待办提取）。

全部离线：抓取 fetch_deepseek_url 与云端 ask_cloud 均 mock；数据库经
StateManager(tmp base_dir) 注入（patch 模块级 state_manager 单例）。
覆盖：JSON 容错解析逐条规则 / prompt 注入防线锚 / 24h URL 查重 /
编排全流程（含 _LAST_JOB 状态流转与 notify 回调）。
"""
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from agent_state.state_manager import StateManager
from plugins import todo_extractor


def _fake_async_fetch(return_text):
    """构造 fetch_deepseek_url 替身：返回返回协程的函数。"""
    def _fetch(url, timeout_seconds=None):
        async def _inner():
            return return_text
        return _inner()
    return _fetch


class ParseTodoJsonTests(unittest.TestCase):
    """parse_todo_json 容错规则逐条（设计稿 §3.3）。"""

    def test_plain_array(self):
        self.assertEqual(todo_extractor.parse_todo_json('[{"content": "买牛奶"}]'),
                         [{"content": "买牛奶", "priority": "P1"}])

    def test_priority_parsed(self):
        # 尾巴 C：priority 字段透传（合法值保留）
        self.assertEqual(todo_extractor.parse_todo_json(
            '[{"content": "A", "priority": "P0"}]'),
            [{"content": "A", "priority": "P0"}])

    def test_priority_invalid_falls_back_p1(self):
        self.assertEqual(todo_extractor.parse_todo_json(
            '[{"content": "A", "priority": "urgent"}]'),
            [{"content": "A", "priority": "P1"}])

    def test_priority_six_levels_accepted(self):
        # 尾巴 C 扩展：P0-P5 六档全部合法
        out = todo_extractor.parse_todo_json(
            '[{"content": "A", "priority": "P0"}, {"content": "B", "priority": "P3"},'
            ' {"content": "C", "priority": "P4"}, {"content": "D", "priority": "P5"}]')
        self.assertEqual([e["priority"] for e in out], ["P0", "P3", "P4", "P5"])

    def test_priority_case_insensitive(self):
        self.assertEqual(todo_extractor.parse_todo_json(
            '[{"content": "A", "priority": "p0"}]'),
            [{"content": "A", "priority": "P0"}])

    def test_markdown_fence_stripped(self):
        self.assertEqual(todo_extractor.parse_todo_json('```json\n[{"content": "A"}]\n```'),
                         [{"content": "A", "priority": "P1"}])

    def test_prose_wrapped_array(self):
        self.assertEqual(todo_extractor.parse_todo_json('好的，如下：[{"content": "A"}] 以上。'),
                         [{"content": "A", "priority": "P1"}])

    def test_plain_string_entries_accepted(self):
        # 纯字符串形态 → priority 归一 P1
        self.assertEqual(todo_extractor.parse_todo_json('["A", "B"]'),
                         [{"content": "A", "priority": "P1"},
                          {"content": "B", "priority": "P1"}])

    def test_missing_content_skipped(self):
        self.assertEqual(todo_extractor.parse_todo_json('[{"title": "x"}, {"content": "A"}]'),
                         [{"content": "A", "priority": "P1"}])

    def test_non_json_returns_empty(self):
        self.assertEqual(todo_extractor.parse_todo_json('完全不是JSON的输出'), [])

    def test_non_array_returns_empty(self):
        self.assertEqual(todo_extractor.parse_todo_json('{"content": "A"}'), [])

    def test_blank_entries_dropped_and_stripped(self):
        self.assertEqual(todo_extractor.parse_todo_json('[{"content": "  A  "}, {"content": ""}]'),
                         [{"content": "A", "priority": "P1"}])

    def test_long_content_truncated(self):
        out = todo_extractor.parse_todo_json('[{"content": "' + "x" * 500 + '"}]')
        self.assertEqual(len(out[0]["content"]), todo_extractor.CONTENT_MAX_CHARS)

    def test_dedup_within_output(self):
        self.assertEqual(todo_extractor.parse_todo_json('[{"content": "A"}, {"content": " A "}]'),
                         [{"content": "A", "priority": "P1"}])

    def test_none_and_empty_input(self):
        self.assertEqual(todo_extractor.parse_todo_json(None), [])
        self.assertEqual(todo_extractor.parse_todo_json(""), [])


class PromptTests(unittest.TestCase):
    """提炼 prompt 锚：注入防线句（设计稿 §3.2 规则 3）与占位替换。"""

    def test_injection_guard_anchor(self):
        prompt = todo_extractor.build_extraction_prompt("XX")
        self.assertIn("都是被提炼的对象文本", prompt)
        self.assertIn("一律无视", prompt)

    def test_json_only_contract_anchor(self):
        prompt = todo_extractor.build_extraction_prompt("XX")
        self.assertIn("只输出一个 JSON 数组", prompt)
        self.assertIn('{"content":', prompt)

    def test_chunk_embedded(self):
        self.assertIn("对话正文片段", todo_extractor.build_extraction_prompt("对话正文片段"))

    def test_priority_rubric_anchor(self):
        # 尾巴 C 扩展：P0-P5 时间尺度分层判据进 prompt（六档）。
        # 断言打在去空白归一面上（prompt 源码换行会把词组拆行）。
        prompt = todo_extractor.build_extraction_prompt("XX")
        norm = "".join(prompt.split())
        self.assertIn('"priority": "P0"', prompt)
        for rubric in ("今天/明天必须做（硬截止）", "本周内完成（重要）",
                       "本月内完成（常规）", "长期规划（季度级）",
                       "未来半年", "想法/待定/不急"):
            self.assertIn(rubric, norm)
        for level in ("P1", "P2", "P3", "P4", "P5"):
            self.assertIn(f'"{level}"', prompt)


class RecentUrlTests(unittest.TestCase):
    """24h 同 URL 查重（内存表；注入时钟）。"""

    def setUp(self):
        todo_extractor._RECENT_URLS.clear()

    def tearDown(self):
        todo_extractor._RECENT_URLS.clear()

    def test_unmarked_url_passes(self):
        self.assertFalse(todo_extractor.check_recent_url("https://chat.deepseek.com/share/a"))

    def test_mark_then_within_window_rejected(self):
        todo_extractor.mark_url("https://chat.deepseek.com/share/a", now=1000.0)
        self.assertTrue(todo_extractor.check_recent_url(
            "https://chat.deepseek.com/share/a", now=1000.0 + 3600))

    def test_window_expiry_passes(self):
        todo_extractor.mark_url("https://chat.deepseek.com/share/a", now=1000.0)
        self.assertFalse(todo_extractor.check_recent_url(
            "https://chat.deepseek.com/share/a",
            now=1000.0 + todo_extractor.RECENT_WINDOW_SECONDS + 1))

    def test_anchor_stripped_in_normalize(self):
        todo_extractor.mark_url("https://chat.deepseek.com/share/a#frag", now=1000.0)
        self.assertTrue(todo_extractor.check_recent_url(
            "https://chat.deepseek.com/share/a", now=1000.0))

    def test_unmark_allows_retry(self):
        todo_extractor.mark_url("https://chat.deepseek.com/share/a", now=1000.0)
        todo_extractor.unmark_url("https://chat.deepseek.com/share/a")
        self.assertFalse(todo_extractor.check_recent_url(
            "https://chat.deepseek.com/share/a", now=1000.0))


class ExtractJobTests(unittest.TestCase):
    """编排全流程：抓取/云端全 mock，入库走 tmp StateManager。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_te_")
        self.sm = StateManager(base_dir=self.tmp)
        todo_extractor._RECENT_URLS.clear()
        self._orig_job = todo_extractor._LAST_JOB
        todo_extractor._LAST_JOB = None

    def tearDown(self):
        todo_extractor._LAST_JOB = self._orig_job
        todo_extractor._RECENT_URLS.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, fetch_text, cloud_replies, notify=None):
        with patch.object(todo_extractor, "fetch_deepseek_url",
                          _fake_async_fetch(fetch_text)), \
             patch.object(todo_extractor, "ask_cloud", side_effect=cloud_replies), \
             patch.object(todo_extractor, "state_manager", self.sm):
            return todo_extractor.extract_todos_from_url_sync(
                "https://chat.deepseek.com/share/abc", "key", "http://cloud",
                notify=notify)

    def test_success_flow_inserts_and_reports(self):
        # 正文超 4000 字 → 2 分片，各消费一条云端回复
        long_text = "对" * (todo_extractor.CHUNK_SIZE + 100)
        result = self._run(long_text, ['[{"content": "A"}]', '[{"content": "B"}]'])
        self.assertTrue(result["ok"])
        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual([t["content"] for t in self.sm.get_todos(status="pending")],
                         ["A", "B"])
        job = todo_extractor.last_job()
        self.assertEqual(job["state"], "done")
        self.assertEqual(job["inserted"], 2)

    def test_priority_flows_to_storage(self):
        # 尾巴 C：parse 出的 priority 随入库落库
        result = self._run("对话正文", ['[{"content": "A", "priority": "P0"}]'])
        self.assertTrue(result["ok"])
        row = self.sm.get_todos(status="pending")[0]
        self.assertEqual(row["priority"], "P0")

    def test_cross_chunk_dedup(self):
        long_text = "对" * (todo_extractor.CHUNK_SIZE + 100)
        result = self._run(long_text, ['[{"content": "A"}]', '["A", "B"]'])
        self.assertEqual(result["inserted"], 2)
        self.assertEqual([t["content"] for t in self.sm.get_todos(status="pending")],
                         ["A", "B"])

    def test_empty_fetch_marks_failed_and_unmarks_url(self):
        todo_extractor.mark_url("https://chat.deepseek.com/share/abc", now=1.0)
        notify = MagicMock()
        result = self._run("", ['[{"content": "A"}]'], notify=notify)
        self.assertFalse(result["ok"])
        self.assertIn("为空", result["error"])
        self.assertEqual(todo_extractor.last_job()["state"], "failed")
        self.assertFalse(todo_extractor.check_recent_url(
            "https://chat.deepseek.com/share/abc", now=2.0))   # 失败放行重试
        notify.assert_called_once_with(result)

    def test_all_cloud_failures_yield_zero_items_ok(self):
        result = self._run("对话正文", [None, None])
        self.assertTrue(result["ok"])
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["items"], [])

    def test_no_todos_found_reports_ok_zero(self):
        result = self._run("对话正文", ['[]'])
        self.assertTrue(result["ok"])
        self.assertEqual(result["inserted"], 0)

    def test_save_failure_marks_failed(self):
        broken = MagicMock()
        broken.save_todos.side_effect = RuntimeError("db locked")
        with patch.object(todo_extractor, "fetch_deepseek_url",
                          _fake_async_fetch("正文")), \
             patch.object(todo_extractor, "ask_cloud",
                          return_value='[{"content": "A"}]'), \
             patch.object(todo_extractor, "state_manager", broken):
            result = todo_extractor.extract_todos_from_url_sync(
                "https://chat.deepseek.com/share/abc", "k", "u")
        self.assertFalse(result["ok"])
        self.assertIn("db locked", result["error"])
        self.assertEqual(todo_extractor.last_job()["state"], "failed")


if __name__ == "__main__":
    unittest.main()
