# -*- coding: utf-8 -*-
"""终端 CLI 聊天记录写入 agent_state/history_terminal.json 测试（全部离线）。

跨组契约：终端 REPL 每轮对话（用户消息 + 助手回复）写入
agent_state/history_terminal.json，格式与 main.py 通道 history_web.json
完全一致（brain.save_memory 口径：纯 [{role, content}] JSON 列表，
ensure_ascii=False + indent=2，MAX_MESSAGES=50 滚动截断），网页控制台
GET /api/history?source=terminal 直接读取该文件展示终端记录。

覆盖点：路径契约、与 brain.save_memory 产出结构逐字段一致、50 条滚动
截断、原子写（无 .tmp 残留）、写失败容错（警告 + 对话继续）、加载
roundtrip 与 REPL 每轮落盘集成。所有 mock 经上下文管理器自动还原。
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import xiaoju3  # noqa: E402


def _quiet():
    return contextlib.redirect_stdout(io.StringIO())


def _term_file_of(tmp):
    return os.path.join(tmp, "history_terminal.json")


class TerminalHistoryPathContractTest(unittest.TestCase):
    """路径契约：文件必须是 agent_state/history_terminal.json（R1 读取端约定）。"""

    def test_memory_file_is_history_terminal_in_agent_state(self):
        self.assertEqual(
            os.path.normpath(xiaoju3.CLI_MEMORY_FILE),
            os.path.normpath(os.path.join(xiaoju3.AGENT_STATE_DIR,
                                          "history_terminal.json")))


class TerminalHistoryFormatAlignmentTest(unittest.TestCase):
    """格式对齐：与 main.py 保存函数（brain.save_memory，history_web.json
    通道）的产出结构逐字段一致。"""

    def test_saved_bytes_identical_to_brain_save_memory(self):
        """同一份数据分别经 brain.save_memory（网页通道保存函数）与终端
        save_memory 落盘，文件字节必须完全一致（纯列表 + 序列化参数同口径）。"""
        import brain
        data = [{"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好呀！😊 今天有什么打算？"}]
        with tempfile.TemporaryDirectory() as tmp:
            web_file = os.path.join(tmp, "history_web.json")
            term_file = _term_file_of(tmp)
            brain.save_memory(list(data), web_file)
            with mock.patch.object(xiaoju3, "CLI_MEMORY_FILE", term_file), _quiet():
                xiaoju3.save_memory([{"role": "system", "content": "S"}] + list(data))
            with open(web_file, "rb") as f:
                web_bytes = f.read()
            with open(term_file, "rb") as f:
                term_bytes = f.read()
        self.assertEqual(term_bytes, web_bytes)

    def test_saved_structure_is_plain_role_content_list(self):
        """真实结构比对：纯 [{role, content}] 列表，无包裹结构，无多余字段。"""
        with tempfile.TemporaryDirectory() as tmp:
            term_file = _term_file_of(tmp)
            with mock.patch.object(xiaoju3, "CLI_MEMORY_FILE", term_file), _quiet():
                xiaoju3.save_memory([{"role": "system", "content": "S"},
                                     {"role": "user", "content": "hi"},
                                     {"role": "assistant", "content": "hello"}])
            with open(term_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
        self.assertIsInstance(saved, list)          # 无包裹结构
        self.assertEqual([m["role"] for m in saved], ["user", "assistant"])
        for m in saved:                             # 每条恰为 role/content 两字段
            self.assertEqual(set(m.keys()), {"role", "content"})

    def test_system_prompt_not_persisted(self):
        """与 history_web.json 落盘口径一致：置顶 system 提示词不落盘。"""
        with tempfile.TemporaryDirectory() as tmp:
            term_file = _term_file_of(tmp)
            with mock.patch.object(xiaoju3, "CLI_MEMORY_FILE", term_file), _quiet():
                xiaoju3.save_memory([{"role": "system", "content": "S"},
                                     {"role": "user", "content": "hi"}])
            with open(term_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
        self.assertEqual([m["role"] for m in saved], ["user"])


class TerminalHistoryTruncationTest(unittest.TestCase):
    """滚动截断：与 brain.save_memory 同口径（最近 MAX_MESSAGES 条）。"""

    def test_truncates_to_max_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            term_file = _term_file_of(tmp)
            with mock.patch.object(xiaoju3, "CLI_MEMORY_FILE", term_file), _quiet():
                messages = [{"role": "system", "content": "S"}]
                messages += [{"role": "user", "content": f"m{i}"}
                             for i in range(xiaoju3.MAX_MESSAGES + 10)]
                xiaoju3.save_memory(messages)
                with open(term_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
        self.assertEqual(len(saved), xiaoju3.MAX_MESSAGES)
        self.assertEqual(saved[-1]["content"], f"m{xiaoju3.MAX_MESSAGES + 9}")
        self.assertEqual(saved[0]["content"], "m10")   # 最旧的 10 条被滚出

    def test_truncation_follows_configured_max(self):
        """截断上限跟随配置值（MAX_MESSAGES 经 mock 调小后同样生效）。"""
        with tempfile.TemporaryDirectory() as tmp:
            term_file = _term_file_of(tmp)
            with mock.patch.object(xiaoju3, "CLI_MEMORY_FILE", term_file), \
                    mock.patch.object(xiaoju3, "MAX_MESSAGES", 3), _quiet():
                messages = [{"role": "user", "content": f"m{i}"} for i in range(10)]
                xiaoju3.save_memory(messages)
                with open(term_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
        self.assertEqual([m["content"] for m in saved], ["m7", "m8", "m9"])


class TerminalHistoryAtomicWriteTest(unittest.TestCase):
    """原子写：临时文件 + os.replace，成功后无 .tmp 残留。"""

    def test_no_tmp_file_left_behind_after_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            term_file = _term_file_of(tmp)
            with mock.patch.object(xiaoju3, "CLI_MEMORY_FILE", term_file), _quiet():
                for round_no in range(3):   # 多轮写入后同样无残留
                    xiaoju3.save_memory([{"role": "user",
                                          "content": f"r{round_no}"}])
                self.assertEqual(os.listdir(tmp), ["history_terminal.json"])
            with open(term_file, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f)[-1]["content"], "r2")


class TerminalHistoryFailureToleranceTest(unittest.TestCase):
    """写失败容错：mock os.replace 抛异常 → 打警告、不抛出、旧文件完好、
    无 .tmp 残留，对话继续。"""

    def test_replace_failure_warns_without_raising_and_keeps_old_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            term_file = _term_file_of(tmp)
            old = [{"role": "user", "content": "old"}]
            with open(term_file, "w", encoding="utf-8") as f:
                json.dump(old, f, ensure_ascii=False)
            out = io.StringIO()
            with mock.patch.object(xiaoju3, "CLI_MEMORY_FILE", term_file), \
                    mock.patch("os.replace", side_effect=OSError("磁盘故障")), \
                    contextlib.redirect_stdout(out):
                try:   # 绝不向调用方抛异常
                    xiaoju3.save_memory([{"role": "system", "content": "S"},
                                         {"role": "user", "content": "new"}])
                except Exception as e:
                    self.fail(f"save_memory 写失败时应只警告不抛错，实际抛出: {e}")
            self.assertIn("⚠️ 记忆保存失败", out.getvalue())
            with open(term_file, "r", encoding="utf-8") as f:   # 旧文件完好
                self.assertEqual(json.load(f), old)
            self.assertEqual(os.listdir(tmp), ["history_terminal.json"])  # 无 .tmp
        # mock 自动还原：离开 with 后 os.replace 恢复原状（上下文管理器保证）

    def test_repl_continues_after_save_failure(self):
        """保存失败不影响 REPL 对话继续：连续两轮正常应答 + 退出不崩。"""
        with tempfile.TemporaryDirectory() as tmp:
            term_file = _term_file_of(tmp)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(xiaoju3, "CLI_MEMORY_FILE",
                                                      term_file))
                stack.enter_context(mock.patch("os.replace",
                                               side_effect=OSError("磁盘故障")))
                stack.enter_context(mock.patch.object(
                    xiaoju3, "load_memory",
                    return_value=[{"role": "system", "content": "S"}]))
                stack.enter_context(mock.patch.object(
                    xiaoju3, "smart_ask",
                    side_effect=[("第一答", "🏠 本地"), ("第二答", "☁️ 云端")]))
                stack.enter_context(mock.patch(
                    "builtins.input", side_effect=["第一问", "第二问", "/exit"]))
                xiaoju3.main()
        self.assertIn("🤖 小橘3号 [🏠 本地]: 第一答", out.getvalue())
        self.assertIn("🤖 小橘3号 [☁️ 云端]: 第二答", out.getvalue())
        self.assertIn("💾 记忆已保存。", out.getvalue())   # /exit 正常走完不崩


class TerminalHistoryLoadRoundtripTest(unittest.TestCase):
    """启动加载：保存 → 读取 roundtrip；缺失/损坏文件回退纯 system 提示词。"""

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            term_file = _term_file_of(tmp)
            with mock.patch.object(xiaoju3, "CLI_MEMORY_FILE", term_file), _quiet():
                xiaoju3.save_memory([{"role": "system", "content": "S"},
                                     {"role": "user", "content": "你好"},
                                     {"role": "assistant", "content": "你好呀！"}])
                loaded = xiaoju3.load_memory()
        self.assertEqual(loaded[0]["role"], "system")          # system 提示词置顶
        self.assertEqual([m["content"] for m in loaded[1:]], ["你好", "你好呀！"])

    def test_load_missing_file_returns_system_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(xiaoju3, "CLI_MEMORY_FILE",
                                   _term_file_of(tmp)), _quiet():
                loaded = xiaoju3.load_memory()
        self.assertEqual([m["role"] for m in loaded], ["system"])

    def test_load_corrupt_file_returns_system_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            term_file = _term_file_of(tmp)
            with open(term_file, "w", encoding="utf-8") as f:
                f.write("{broken json")
            with mock.patch.object(xiaoju3, "CLI_MEMORY_FILE", term_file), _quiet():
                loaded = xiaoju3.load_memory()
        self.assertEqual([m["role"] for m in loaded], ["system"])

    def test_repl_loads_existing_history_and_appends(self):
        """启动加载对齐 main.py 口径（启动即读 history 文件）：旧历史 + 本轮
        新对话一起追加写入 history_terminal.json。"""
        with tempfile.TemporaryDirectory() as tmp:
            term_file = _term_file_of(tmp)
            with open(term_file, "w", encoding="utf-8") as f:
                json.dump([{"role": "user", "content": "旧话"},
                           {"role": "assistant", "content": "旧答"}],
                          f, ensure_ascii=False)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(xiaoju3, "CLI_MEMORY_FILE",
                                                      term_file))
                stack.enter_context(mock.patch.object(
                    xiaoju3, "smart_ask", return_value=("新答", "🏠 本地")))
                stack.enter_context(mock.patch(
                    "builtins.input", side_effect=["新话", "/exit"]))
                xiaoju3.main()
            with open(term_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
        self.assertIn("📖 已加载 2 条历史记忆。", out.getvalue())   # 启动即加载
        self.assertEqual(saved, [{"role": "user", "content": "旧话"},
                                 {"role": "assistant", "content": "旧答"},
                                 {"role": "user", "content": "新话"},
                                 {"role": "assistant", "content": "新答"}])


if __name__ == "__main__":
    unittest.main()
