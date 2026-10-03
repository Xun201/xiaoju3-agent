# -*- coding: utf-8 -*-
"""save_env_file 写入函数离线单测（安装器方案步 A2）。

四条防线逐条覆盖（白名单/单槽备份/原子落盘/增量合并）+ 防漂移锚
（ENV_WRITE_ALLOWLIST == .env.example 键集）。全程 tmp 目录隔离，
绝不触碰真实 xiaoju3_data 与 .env；无网络、无子进程。
"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

import xiaoju3

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _parse_keys(path):
    """与 .env.example 同口径解析键集：跳过注释/空行、剥 export 前缀。"""
    keys = set()
    for line in open(path, encoding="utf-8-sig"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("export "):
            s = s[7:]
        if "=" in s:
            keys.add(s.split("=", 1)[0].strip())
    return keys


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class SaveEnvFileTests(unittest.TestCase):
    """save_env_file 四条防线（A2，无调用点纯函数期）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xj3_saveenv_")
        self.env_path = os.path.join(self.tmp, ".env")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_original(self, text):
        with open(self.env_path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_allowlist_filters_illegal_keys(self):
        """防线①：合法键写入，非法键进 skipped 且绝不落盘。"""
        written, skipped, _ = xiaoju3.save_env_file(
            {"DEEPSEEK_API_KEY": "sk-test-123", "EVIL_KEY": "pwn",
             "PATH": "C:\\Windows"}, path=self.env_path, backup=False)
        self.assertEqual(written, ["DEEPSEEK_API_KEY"])
        self.assertIn("EVIL_KEY", skipped)
        self.assertIn("PATH", skipped)
        text = _read(self.env_path)
        self.assertIn("DEEPSEEK_API_KEY=sk-test-123", text)
        self.assertNotIn("EVIL_KEY", text)
        self.assertNotIn("C:\\Windows", text)

    def test_backup_created_and_content_matches(self):
        """防线②：旧文件存在时轮换出 .env.bak，内容等于写前原文。"""
        original = "DEEPSEEK_API_KEY=old-key\nUSER_CITY=示例市\n"
        self._write_original(original)
        written, skipped, backup_path = xiaoju3.save_env_file(
            {"DEEPSEEK_API_KEY": "sk-new-key"}, path=self.env_path)
        self.assertEqual(backup_path, self.env_path + ".bak")
        self.assertEqual(_read(self.env_path + ".bak"), original)
        self.assertIn("DEEPSEEK_API_KEY=sk-new-key", _read(self.env_path))

    def test_no_backup_when_file_absent(self):
        """首次创建（无旧文件）：不产生备份，返回 None。"""
        written, skipped, backup_path = xiaoju3.save_env_file(
            {"DEEPSEEK_API_KEY": "sk-first"}, path=self.env_path)
        self.assertIsNone(backup_path)
        self.assertFalse(os.path.exists(self.env_path + ".bak"))
        self.assertIn("DEEPSEEK_API_KEY=sk-first", _read(self.env_path))

    def test_idempotent_rewrite(self):
        """防线④补面：同值重复写，文件内容逐字节不变（幂等无害）。"""
        xiaoju3.save_env_file({"DEEPSEEK_API_KEY": "sk-same",
                               "USER_CITY": "示例市"},
                              path=self.env_path, backup=False)
        first = _read(self.env_path)
        xiaoju3.save_env_file({"DEEPSEEK_API_KEY": "sk-same",
                               "USER_CITY": "示例市"},
                              path=self.env_path, backup=False)
        self.assertEqual(_read(self.env_path), first)

    def test_incremental_merge_preserves_unmentioned_and_comments(self):
        """防线④：未提及键/注释行原样保留，提及键就地替换，新键追加尾部。"""
        original = ("# 用户手写注释必须活下来\n"
                    "DEEPSEEK_API_KEY=old-key\n"
                    "USER_CITY=示例市\n")
        self._write_original(original)
        xiaoju3.save_env_file({"DEEPSEEK_API_KEY": "sk-new-key",
                               "TTS_VOICE": "zh-CN-XiaoxiaoNeural"},
                              path=self.env_path, backup=False)
        text = _read(self.env_path)
        self.assertIn("# 用户手写注释必须活下来", text)      # 注释保留
        self.assertIn("USER_CITY=示例市", text)              # 未提及键保留
        self.assertIn("DEEPSEEK_API_KEY=sk-new-key", text)   # 提及键替换
        self.assertIn("TTS_VOICE=zh-CN-XiaoxiaoNeural", text)  # 新键追加
        # 行序不变：注释 → DEEPSEEK → USER_CITY → … → TTS_VOICE（尾部）
        lines = text.splitlines()
        self.assertEqual(lines.index("# 用户手写注释必须活下来"), 0)
        self.assertLess(lines.index("DEEPSEEK_API_KEY=sk-new-key"),
                        lines.index("USER_CITY=示例市"))
        self.assertEqual(lines[-1], "TTS_VOICE=zh-CN-XiaoxiaoNeural")

    def test_atomic_failure_leaves_original_intact(self):
        """防线③：os.replace 失败（模拟写盘中断）→ 抛 OSError、原文件
        逐字节无损、tmp 残留被清理。"""
        original = "DEEPSEEK_API_KEY=old-key\n"
        self._write_original(original)
        with mock.patch("os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                xiaoju3.save_env_file({"DEEPSEEK_API_KEY": "sk-new"},
                                      path=self.env_path)
        self.assertEqual(_read(self.env_path), original)
        self.assertFalse(os.path.exists(self.env_path + ".tmp"))

    def test_allowlist_matches_env_example(self):
        """防漂移锚：ENV_WRITE_ALLOWLIST == .env.example 键集——
        两边任何一边增删键此测试必红，强制同步。"""
        example_keys = _parse_keys(os.path.join(PROJECT_ROOT, ".env.example"))
        self.assertEqual(xiaoju3.ENV_WRITE_ALLOWLIST, example_keys)


if __name__ == "__main__":
    unittest.main()
