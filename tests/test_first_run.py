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

import first_run  # noqa: E402  # A3 探针模块（复用 brain/_napcat_running/_headers）
import xiaoju3  # noqa: E402

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


class ProbeOllamaTests(unittest.TestCase):
    """A3 探针①：本地大脑（复用 brain.probe_local，两态）。"""

    def test_two_states(self):
        with mock.patch.object(first_run.brain, "probe_local", return_value=True):
            r = first_run._probe_ollama()
        self.assertTrue(r["ok"])
        self.assertIn("本地大脑在线", r["detail"])
        with mock.patch.object(first_run.brain, "probe_local", return_value=False):
            r = first_run._probe_ollama()
        self.assertFalse(r["ok"])
        self.assertIn("可稍后安装", r["detail"])


class ProbeNapCatTests(unittest.TestCase):
    """A3 探针②：NapCat（复用 _napcat_running，只检测不拉起）。"""

    def test_two_states(self):
        with mock.patch.object(first_run._xl, "_napcat_running", return_value=True):
            r = first_run._probe_napcat()
        self.assertTrue(r["ok"])
        self.assertIn("已就绪", r["detail"])
        with mock.patch.object(first_run._xl, "_napcat_running", return_value=False):
            r = first_run._probe_napcat()
        self.assertFalse(r["ok"])
        self.assertIn("可稍后安装", r["detail"])


class ProbeHaTests(unittest.TestCase):
    """A3 探针③：Home Assistant（未配置=灰显可选项，在线/不可达两态）。"""

    def test_unconfigured_is_optional_grey(self):
        with mock.patch.object(first_run.home_tools, "HA_URL", ""):
            r = first_run._probe_ha()
        self.assertFalse(r["ok"])
        self.assertIn("可选项", r["detail"])

    def test_online_and_unreachable(self):
        with mock.patch.object(first_run.home_tools, "HA_URL",
                               "http://ha-test:8123"), \
             mock.patch.object(first_run.home_tools, "_headers",
                               return_value={"Authorization": "Bearer x"}), \
             mock.patch.object(first_run.requests, "get") as get:
            get.return_value = mock.MagicMock(status_code=200)
            r = first_run._probe_ha()
            self.assertTrue(r["ok"])
            self.assertIn("心跳可用", r["detail"])
            called_url = get.call_args[0][0]
            self.assertEqual(called_url, "http://ha-test:8123/api/")
            get.side_effect = OSError("net down")
            self.assertFalse(first_run._probe_ha()["ok"])


class ValidateDeepSeekKeyTests(unittest.TestCase):
    """A3 探针④前置：DeepSeek key 本地格式校验（sk- 前缀 + 长度）。"""

    def test_formats(self):
        self.assertTrue(first_run.validate_deepseek_key("sk-" + "a" * 27))
        self.assertFalse(first_run.validate_deepseek_key("wp-" + "a" * 27))   # 前缀
        self.assertFalse(first_run.validate_deepseek_key("sk-short"))          # 太短
        self.assertFalse(first_run.validate_deepseek_key(""))                  # 空
        self.assertFalse(first_run.validate_deepseek_key(None))                # None


class RunProbesTests(unittest.TestCase):
    """A3 聚合：四探针并发执行、顺序固定、结果聚合带 name。"""

    def test_aggregate_order_and_ok(self):
        fake = {"ok": True, "detail": "d"}
        patches = [mock.patch.object(first_run, attr, return_value=dict(fake))
                   for attr in ("_probe_ollama", "_probe_napcat",
                                "_probe_ha", "_probe_deepseek")]
        with patches[0], patches[1], patches[2], patches[3]:
            rs = first_run.run_probes()
        self.assertEqual([r["name"] for r in rs],
                         ["ollama", "napcat", "home_assistant", "deepseek"])
        self.assertTrue(all(r["ok"] for r in rs))
        self.assertTrue(all("detail" in r for r in rs))


class FirstRunEndpointsTests(unittest.TestCase):
    """A3 端点：/api/first_run/status 两态 + /api/first_run/probes 聚合。"""

    def setUp(self):
        import xiaoju3_dashboard as dashboard  # noqa: F401 延迟导入风格同路由
        self.client = dashboard.app.test_client()

    def test_status_and_probes(self):
        with mock.patch.object(first_run, "is_first_run", return_value=True):
            resp = self.client.get("/api/first_run/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertTrue(data["first_run"])
        self.assertEqual(data["version"], "1.0.0")

        with mock.patch.object(first_run, "is_first_run", return_value=False), \
             mock.patch.object(first_run, "run_probes",
                               return_value=[{"name": "ollama", "ok": True,
                                              "detail": "d"}]):
            resp = self.client.get("/api/first_run/probes")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertFalse(data["first_run"])
        self.assertEqual(len(data["probes"]), 1)
        self.assertEqual(data["probes"][0]["name"], "ollama")


class IsFirstRunTests(unittest.TestCase):
    """A3 判定：ENV_FILE 存在/不存在两态（单一事实源在文件）。"""

    def test_file_two_states(self):
        tmp = tempfile.mkdtemp(prefix="xj3_firstrun_")
        try:
            existing = os.path.join(tmp, "exists.env")
            with open(existing, "w", encoding="utf-8") as f:
                f.write("DEEPSEEK_API_KEY=x\n")
            with mock.patch.object(first_run, "ENV_FILE", existing):
                self.assertFalse(first_run.is_first_run())
            missing = os.path.join(tmp, "missing.env")
            with mock.patch.object(first_run, "ENV_FILE", missing):
                self.assertTrue(first_run.is_first_run())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


import sys  # noqa: E402  # A4a frozen 形态用例

import autostart  # noqa: E402


class AutostartTargetCommandTests(unittest.TestCase):
    """A4a target_command 两形态（测死）：frozen=exe 自身；非 frozen=pythonw+脚本。"""

    def test_frozen_uses_exe_itself(self):
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable",
                               r"C:\Apps\xiaoju3\xiaoju3.exe"):
            cmd = autostart.target_command()
        self.assertEqual(cmd, r'"C:\Apps\xiaoju3\xiaoju3.exe"')

    def test_non_frozen_uses_windowless_python_and_script(self):
        fake_py = r"C:\Python\pythonw.exe"
        with mock.patch("desktop_launcher._windowless_python",
                        return_value=fake_py):
            cmd = autostart.target_command()
        self.assertIn(fake_py, cmd)
        self.assertIn("desktop_launcher.py", cmd)
        self.assertTrue(cmd.startswith('"') and cmd.endswith('"'))


class AutostartPlatformGuardTests(unittest.TestCase):
    """A4a 平台守卫：非 Windows 四函数全部零操作（winreg 不被触碰）。"""

    def test_non_windows_all_ops_noop(self):
        fake_wr = mock.MagicMock()
        with mock.patch.dict(sys.modules, {"winreg": fake_wr}), \
             mock.patch.object(autostart.os, "name", "posix"):
            self.assertIsNone(autostart.read())
            self.assertFalse(autostart.write())
            self.assertFalse(autostart.remove())
            self.assertFalse(autostart.is_enabled())
        fake_wr.assert_not_called()


class AutostartRegistryTests(unittest.TestCase):
    """A4a 注册表三操作：fake winreg 注入 sys.modules（winreg 延迟 import）。"""

    def setUp(self):
        self.fake_wr = mock.MagicMock()
        self.key = mock.MagicMock()
        self.fake_wr.CreateKey.return_value = self.key
        self.fake_wr.OpenKey.return_value = self.key
        self.fake_wr.REG_SZ = 1
        self._patchers = [mock.patch.dict(sys.modules, {"winreg": self.fake_wr}),
                          mock.patch.object(autostart.os, "name", "nt")]
        for p in self._patchers:
            p.start()
            self.addCleanup(p.stop)

    def test_write_calls_setvalueex(self):
        with mock.patch.object(autostart, "target_command",
                               return_value=r'"C:\x\xiaoju3.exe"'):
            self.assertTrue(autostart.write())
        args = self.fake_wr.SetValueEx.call_args[0]
        self.assertEqual(args[1], autostart.VALUE_NAME)   # 值名 Xiaoju3
        self.assertEqual(args[2], 0)
        self.assertEqual(args[3], 1)                      # REG_SZ
        self.assertEqual(args[4], r'"C:\x\xiaoju3.exe"')

    def test_read_hit_and_miss(self):
        self.fake_wr.QueryValueEx.return_value = (r'"C:\x\xiaoju3.exe"', 1)
        self.assertEqual(autostart.read(), r'"C:\x\xiaoju3.exe"')
        self.fake_wr.QueryValueEx.side_effect = FileNotFoundError
        self.assertIsNone(autostart.read())

    def test_remove_idempotent(self):
        self.assertTrue(autostart.remove())               # 值存在：删除成功
        self.fake_wr.DeleteValue.side_effect = FileNotFoundError
        self.assertFalse(autostart.remove())              # 值已不在：幂等 False 不抛


class FirstRunCompleteTests(unittest.TestCase):
    """A4a complete 端点：落盘/skipped/自启/OSError 500。"""

    def setUp(self):
        import xiaoju3_dashboard as dashboard
        self.client = dashboard.app.test_client()
        self.tmp = tempfile.mkdtemp(prefix="xj3_complete_")
        self.env_path = os.path.join(self.tmp, ".env")
        # save_env_file 缺省读 xiaoju3.ENV_FILE；first_run.ENV_FILE 独立绑定，
        # 两处同 patch 使落盘与翻转判定都指向 tmp
        self._patchers = [mock.patch.object(xiaoju3, "ENV_FILE", self.env_path),
                          mock.patch.object(first_run, "ENV_FILE", self.env_path)]
        for p in self._patchers:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_success_with_skipped_and_autostart(self):
        legal_key = "sk-" + "a" * 27
        with mock.patch.object(autostart, "write", return_value=True) as wr:
            resp = self.client.post("/api/first_run/complete",
                                    json={"env": {"DEEPSEEK_API_KEY": legal_key,
                                                  "EVIL_KEY": "pwn"},
                                          "autostart": True})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(data["written"], ["DEEPSEEK_API_KEY"])
        self.assertEqual(data["skipped"], ["EVIL_KEY"])
        self.assertFalse(data["first_run"])                # 落盘即自然翻转
        self.assertIsNone(data["warning"])
        wr.assert_called_once()                            # 自启勾选 → 写注册表
        text = open(self.env_path, encoding="utf-8").read()
        self.assertIn(f"DEEPSEEK_API_KEY={legal_key}", text)
        self.assertNotIn("EVIL_KEY", text)

    def test_oserror_maps_to_500_with_chinese_error(self):
        with mock.patch.object(xiaoju3, "save_env_file",
                               side_effect=OSError("disk full")):
            resp = self.client.post("/api/first_run/complete",
                                    json={"env": {"DEEPSEEK_API_KEY": "sk-x"},
                                          "autostart": False})
        self.assertEqual(resp.status_code, 500)
        self.assertIn("配置保存失败", resp.get_json()["error"])
        self.assertIn("disk full", resp.get_json()["error"])

    def test_autostart_false_never_touches_registry(self):
        with mock.patch.object(autostart, "write") as wr:
            resp = self.client.post("/api/first_run/complete",
                                    json={"env": {"USER_CITY": "示例市"},
                                          "autostart": False})
        self.assertEqual(resp.status_code, 200)
        wr.assert_not_called()
        self.assertIsNone(resp.get_json()["data"]["warning"])

    def test_autostart_failure_degrades_to_warning_not_500(self):
        with mock.patch.object(autostart, "write", return_value=False):
            resp = self.client.post("/api/first_run/complete",
                                    json={"env": {"USER_CITY": "示例市"},
                                          "autostart": True})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("自启", resp.get_json()["data"]["warning"])


if __name__ == "__main__":
    unittest.main()
