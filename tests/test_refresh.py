# -*- coding: utf-8 -*-
"""xiaoju3_refresh.py 离线单测：

- 6 位动态确认码校验（正确 / 错误 / 非 6 位）；
- sha256 重算逻辑（对临时目录真实文件执行）；
- systemctl 调用通过注入 runner 被 mock，绝不真实执行。
"""
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import xiaoju3_refresh as refresh  # noqa: E402


class TestVerifyCode(unittest.TestCase):
    """6 位动态码校验。"""

    def test_correct_code(self):
        self.assertTrue(refresh.verify_code("123456", "123456"))
        self.assertTrue(refresh.verify_code("000000", "000000"))

    def test_wrong_code(self):
        self.assertFalse(refresh.verify_code("123456", "654321"))
        self.assertFalse(refresh.verify_code("123456", "123457"))

    def test_non_six_digit_inputs_rejected(self):
        bad_inputs = [
            "12345",        # 少于 6 位
            "1234567",      # 多于 6 位
            "",             # 空串
            "abcdef",       # 非数字
            "12345a",       # 混入字母
            "12 456",       # 含空格
            "１２３４５６",  # 全角数字（与 ASCII 期望值不同）
            None,           # 非字符串
            123456,         # 整数（必须为字符串输入）
        ]
        for bad in bad_inputs:
            with self.subTest(bad=bad):
                self.assertFalse(refresh.verify_code("123456", bad))

    def test_invalid_expected_value_never_matches(self):
        # 期望值本身不是合法 6 位码时，任何输入都不应通过
        self.assertFalse(refresh.verify_code("12345", "12345"))

    def test_generate_code_shape(self):
        for _ in range(100):
            code = refresh.generate_code()
            self.assertIsInstance(code, str)
            self.assertRegex(code, r"^\d{6}$")
            self.assertTrue(100000 <= int(code) <= 999999)


class TestRecomputeChecksums(unittest.TestCase):
    """sha256 重算逻辑（对临时文件）。"""

    def test_recompute_on_tmp_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "a.py").write_text("print('a')\n", encoding="utf-8", newline="\n")
            sub = tmp_path / "agent_state"
            sub.mkdir()
            (sub / "b.py").write_text("print('b')\n", encoding="utf-8", newline="\n")
            (tmp_path / "manifest.txt").write_text(
                "a.py\nagent_state/b.py\n", encoding="utf-8", newline="\n"
            )

            results = refresh.recompute_checksums(str(tmp_path))

            self.assertEqual(len(results), 2)
            expect_a = hashlib.sha256(b"print('a')\n").hexdigest()
            expect_b = hashlib.sha256(b"print('b')\n").hexdigest()
            self.assertEqual(results[0], ("a.py", expect_a))
            self.assertEqual(results[1], ("agent_state/b.py", expect_b))

            out = (tmp_path / "checksums.sha256").read_text(encoding="utf-8")
            # sha256sum 兼容格式："哈希  相对路径"
            self.assertIn(f"{expect_a}  a.py", out)
            self.assertIn(f"{expect_b}  agent_state/b.py", out)
            self.assertTrue(out.endswith("\n"))

    def test_output_passes_sha256sum_c(self):
        """产物必须能被 sha256sum -c 校验通过（secure_start.sh 验收口径）。"""
        sha = shutil.which("sha256sum")
        if not sha:
            self.skipTest("环境中没有 sha256sum，跳过兼容性校验")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "m.py").write_text("# m\n", encoding="utf-8", newline="\n")
            (tmp_path / "manifest.txt").write_text("m.py\n", encoding="utf-8", newline="\n")
            refresh.recompute_checksums(str(tmp_path))
            verify = subprocess.run(
                [sha, "-c", "checksums.sha256", "--quiet"],
                cwd=str(tmp_path),
                capture_output=True,
            )
            self.assertEqual(verify.returncode, 0, verify.stdout.decode("utf-8", "replace"))

    def test_recompute_updates_on_change(self):
        """文件内容变化后重算，哈希必须更新（一键重算语义）。"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target = tmp_path / "m.py"
            target.write_text("v1\n", encoding="utf-8", newline="\n")
            (tmp_path / "manifest.txt").write_text("m.py\n", encoding="utf-8", newline="\n")
            first = refresh.recompute_checksums(str(tmp_path))[0][1]
            target.write_text("v2\n", encoding="utf-8", newline="\n")
            second = refresh.recompute_checksums(str(tmp_path))[0][1]
            self.assertNotEqual(first, second)
            self.assertEqual(second, hashlib.sha256(b"v2\n").hexdigest())

    def test_missing_manifest_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                refresh.recompute_checksums(tmp)

    def test_empty_manifest_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "manifest.txt").write_text("\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                refresh.recompute_checksums(tmp)


class TestRestartService(unittest.TestCase):
    """systemctl 调用被 mock，绝不真实执行。"""

    def test_default_service_command(self):
        fake = mock.Mock()
        refresh.restart_service(runner=fake)
        fake.assert_called_once()
        cmd = fake.call_args[0][0]
        self.assertEqual(cmd, ["sudo", "systemctl", "restart", "xiaoju3"])
        self.assertEqual(fake.call_args[1], {"check": True})

    def test_custom_service_name(self):
        fake = mock.Mock()
        refresh.restart_service(service="my-svc", runner=fake)
        self.assertEqual(
            fake.call_args[0][0], ["sudo", "systemctl", "restart", "my-svc"]
        )

    def test_build_restart_command_pure(self):
        self.assertEqual(
            refresh.build_restart_command("svc"),
            ["sudo", "systemctl", "restart", "svc"],
        )

    def test_subprocess_patched_not_invoked_for_real(self):
        """直接 patch 模块内的 subprocess.run，验证默认路径也被 mock 拦截。"""
        with mock.patch.object(refresh.subprocess, "run") as fake_run:
            fake_run.return_value = 0
            refresh.restart_service()
            fake_run.assert_called_once_with(
                ["sudo", "systemctl", "restart", "xiaoju3"], check=True
            )


class TestSecurityLog(unittest.TestCase):
    """安全日志写入。"""

    def test_write_security_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            refresh.write_security_log(tmp, "测试：通过动态验证。")
            log = Path(tmp) / "logs" / "security.log"
            self.assertTrue(log.is_file())
            text = log.read_text(encoding="utf-8")
            self.assertIn("测试：通过动态验证。", text)
            self.assertTrue(text.startswith("["))  # 带时间戳前缀


class TestMainFlow(unittest.TestCase):
    """main 流程：验证码错误直接终止；正确则重算 + 记日志 + 重启（全部 mock）。"""

    def test_main_rejects_wrong_code(self):
        with mock.patch.object(refresh, "generate_code", return_value="111111"), \
             mock.patch("builtins.input", return_value="999999"), \
             mock.patch.object(refresh, "recompute_checksums") as fake_recompute, \
             mock.patch.object(refresh, "write_security_log") as fake_log, \
             mock.patch.object(refresh, "restart_service") as fake_restart:
            with self.assertRaises(SystemExit) as ctx:
                refresh.main()
            self.assertEqual(ctx.exception.code, 1)
            fake_recompute.assert_not_called()
            fake_log.assert_not_called()
            fake_restart.assert_not_called()

    def test_main_rejects_non_six_digit(self):
        with mock.patch.object(refresh, "generate_code", return_value="111111"), \
             mock.patch("builtins.input", return_value="11111"), \
             mock.patch.object(refresh, "recompute_checksums") as fake_recompute:
            with self.assertRaises(SystemExit):
                refresh.main()
            fake_recompute.assert_not_called()

    def test_main_happy_path(self):
        with mock.patch.object(refresh, "generate_code", return_value="123456"), \
             mock.patch("builtins.input", return_value="123456"), \
             mock.patch.object(refresh, "recompute_checksums") as fake_recompute, \
             mock.patch.object(refresh, "write_security_log") as fake_log, \
             mock.patch.object(refresh, "restart_service") as fake_restart:
            refresh.main()  # 不应抛 SystemExit
            fake_recompute.assert_called_once_with(refresh.PROJECT_DIR)
            fake_log.assert_called_once()
            fake_restart.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
