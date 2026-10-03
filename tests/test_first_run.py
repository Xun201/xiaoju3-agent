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

    def test_file_three_states(self):
        """三态：双无=first_run；.env 存在=非；无 .env 有跳过标记=非。"""
        tmp = tempfile.mkdtemp(prefix="xj3_firstrun_")
        try:
            env = os.path.join(tmp, "exists.env")
            with open(env, "w", encoding="utf-8") as f:
                f.write("K=x\n")
            skip = os.path.join(tmp, ".first_run_skipped")
            with open(skip, "w", encoding="utf-8") as f:
                f.write("")
            missing_env = os.path.join(tmp, "missing.env")
            no_skip = os.path.join(tmp, "no_skip.flag")
            with mock.patch.object(first_run, "ENV_FILE", missing_env),                  mock.patch.object(first_run, "SKIP_FLAG_FILE", no_skip):
                self.assertTrue(first_run.is_first_run())
            with mock.patch.object(first_run, "ENV_FILE", env),                  mock.patch.object(first_run, "SKIP_FLAG_FILE", no_skip):
                self.assertFalse(first_run.is_first_run())
            with mock.patch.object(first_run, "ENV_FILE", missing_env),                  mock.patch.object(first_run, "SKIP_FLAG_FILE", skip):
                self.assertFalse(first_run.is_first_run())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class FirstRunOverlayStaticTests(unittest.TestCase):
    """A4b 静态锚：覆盖层 DOM/函数/CSS 存在性 + 跳过语义源码锁定。
    UI 运行行为不可离线单测，此处锁定「壳存在 + 默认不弹 + 既有零触碰」。"""

    @classmethod
    def setUpClass(cls):
        cls.html = open(os.path.join(PROJECT_ROOT, "index.html"),
                        encoding="utf-8").read()
        cls.js = open(os.path.join(PROJECT_ROOT, "console.js"),
                      encoding="utf-8").read()

    def test_overlay_present_and_default_hidden(self):
        """覆盖层存在且默认 hidden（非引导场景零视觉变化锚）。"""
        self.assertIn('<div id="first-run-overlay" hidden>', self.html)

    def test_overlay_css_present(self):
        """CSS 锚：置顶遮罩 + 卡片样式就位。"""
        self.assertIn("#first-run-overlay {", self.html)
        self.assertIn("z-index: 3000", self.html)
        self.assertIn(".first-run-card {", self.html)

    def test_five_form_inputs_and_probe_list(self):
        """5 键表单 + 自启勾选 + 探针灯行元素齐全。"""
        for input_id in ("first-run-deepseek-key", "first-run-ha-url",
                         "first-run-ha-token", "first-run-local-url",
                         "first-run-user-city"):
            self.assertIn(f'id="{input_id}"', self.html)
        self.assertIn('id="first-run-autostart"', self.html)
        self.assertIn('id="first-run-probes"', self.html)
        self.assertIn('id="first-run-error"', self.html)
        self.assertIn('id="first-run-restart-hint"', self.html)
        self.assertIn('id="first-run-restart-btn"', self.html)

    def test_three_functions_and_single_call_site(self):
        """三函数定义存在 + IIFE 尾部单点调用。"""
        for frag in ("function initFirstRun()", "function showFirstRun(",
                     "function submitFirstRun("):
            self.assertIn(frag, self.js)
        self.assertIn("    initFirstRun();", self.js)

    def test_polling_and_minimize_untouched(self):
        """零触碰锚：2s 轮询行原样存在；overlay 逻辑零桌宠缩球依赖
        （不直接操作 xiaoju3-pet-minimized 类的新增写入）。"""
        self.assertIn("setInterval(fetchStatus, 2000)", self.js)
        fr_block = self.js[self.js.index("首装引导覆盖层"):self.js.index("initFirstRun();")]
        self.assertNotIn("classList.add('xiaoju3-pet-minimized'", fr_block)
        self.assertNotIn("classList.remove('xiaoju3-pet-minimized'", fr_block)

    def test_skip_semantics_uses_backend_flag(self):
        """跳过语义（方案 C）源码锁定：skip 走后端端点写标记文件，
        first-run 块整体零 localStorage——浏览器/WebView2 容器差异免疫；
        弹出判定只依赖后端 status（.env 与跳过标记两个文件）。"""
        block = self.js[self.js.index("first-run-overlay"):]
        self.assertIn("/api/first_run/skip", block)
        self.assertIn("method: 'POST'", block)
        self.assertIn("closeFirstRunOverlay()", block)
        self.assertNotIn("localStorage", block)
        self.assertNotIn("FIRST_RUN_DONE_KEY", self.js)
        init_idx = self.js.index("function initFirstRun()")
        init_seg = self.js[init_idx:self.js.index("function showFirstRun(")]
        self.assertNotIn("localStorage", init_seg)

class SkipFlagTests(unittest.TestCase):
    """A4b/C 跳过标记：mark/clear 幂等 + skip 端点写盘翻转 + complete 清除。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xj3_skip_")
        self.skip_flag = os.path.join(self.tmp, ".first_run_skipped")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_mark_and_clear_idempotent(self):
        with mock.patch.object(first_run, "SKIP_FLAG_FILE", self.skip_flag):
            first_run.mark_skipped()
            self.assertTrue(os.path.exists(self.skip_flag))
            first_run.clear_skipped()
            self.assertFalse(os.path.exists(self.skip_flag))
            first_run.clear_skipped()   # 幂等：已不存在不抛

    def test_skip_endpoint_writes_flag_and_flips_status(self):
        import xiaoju3_dashboard as dashboard
        client = dashboard.app.test_client()
        with mock.patch.object(first_run, "SKIP_FLAG_FILE", self.skip_flag),              mock.patch.object(first_run, "ENV_FILE",
                               os.path.join(self.tmp, "missing.env")):
            resp = client.post("/api/first_run/skip")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertFalse(data["first_run"])   # 写标记即自然翻转
        self.assertTrue(os.path.exists(self.skip_flag))

    def test_complete_clears_skip_flag(self):
        import xiaoju3_dashboard as dashboard
        client = dashboard.app.test_client()
        env_path = os.path.join(self.tmp, ".env")
        with open(self.skip_flag, "w", encoding="utf-8") as f:
            f.write("")
        with mock.patch.object(first_run, "SKIP_FLAG_FILE", self.skip_flag),              mock.patch.object(xiaoju3, "ENV_FILE", env_path),              mock.patch.object(first_run, "ENV_FILE", env_path):
            resp = client.post("/api/first_run/complete",
                               json={"env": {"USER_CITY": "示例市"},
                                     "autostart": False})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(os.path.exists(self.skip_flag))   # 完成即清除
        self.assertTrue(os.path.exists(env_path))          # 配置照常落盘


class ParseInstallerReportTests(unittest.TestCase):
    """B3 消费端：parse_installer_report 纯函数（行规则逐条）。"""

    def test_full_five_line_report(self):
        """全量 5 行报告（安装器真实格式，CRLF）：五项各归其位。"""
        text = ("2026/10/03 23:15:42\r\n"
                "硬件自检建议: 推荐完整版（本地优先：可安装 Ollama + 本地模型）\r\n"
                "ollama=1\r\nnapcat=0\r\nha=1\r\n")
        r = first_run.parse_installer_report(text)
        self.assertEqual(r["installed_at"], "2026/10/03 23:15:42")
        self.assertEqual(r["tier_hint"],
                         "推荐完整版（本地优先：可安装 Ollama + 本地模型）")
        self.assertEqual(r["intents"],
                         {"ollama": True, "napcat": False, "ha": True})

    def test_missing_lines_degrade_to_none(self):
        """缺行：缺时间戳行时不误吞意图行（installed_at 保持 None）。"""
        r = first_run.parse_installer_report("ollama=1\nnapcat=0\n")
        self.assertIsNone(r["installed_at"])
        self.assertIsNone(r["tier_hint"])
        self.assertEqual(r["intents"],
                         {"ollama": True, "napcat": False, "ha": None})

    def test_garbage_lines_ignored(self):
        """垃圾行混入：时间戳不误吞，垃圾行忽略，合法行照常解析。"""
        text = ("2026/10/03 23:15:42\n"
                "=== 任意垃圾行 ===\n"
                "硬件自检建议: 推荐轻量版\n"
                "hello=world\n"
                "ha=0\n")
        r = first_run.parse_installer_report(text)
        self.assertEqual(r["installed_at"], "2026/10/03 23:15:42")
        self.assertEqual(r["tier_hint"], "推荐轻量版")
        self.assertEqual(r["intents"],
                         {"ollama": None, "napcat": None, "ha": False})

    def test_empty_string_all_none(self):
        """空串：结构完整、全 None、不抛。"""
        self.assertEqual(
            first_run.parse_installer_report(""),
            {"installed_at": None, "tier_hint": None,
             "intents": {"ollama": None, "napcat": None, "ha": None}})

    def test_bad_intent_value_unknown(self):
        """值非 1/0：该意向降级 None（未知，UI 不展示），其余照常。"""
        r = first_run.parse_installer_report("ollama=yes\nnapcat=1 extra\nha=0\n")
        self.assertEqual(r["intents"],
                         {"ollama": None, "napcat": None, "ha": False})

    def test_none_input_safe(self):
        """None 入参防御：按空串处理不抛。"""
        r = first_run.parse_installer_report(None)
        self.assertIsNone(r["installed_at"])
        self.assertEqual(r["intents"],
                         {"ollama": None, "napcat": None, "ha": None})


class ReadInstallerReportTests(unittest.TestCase):
    """B3 消费端：read_installer_report 编码回退 + 永不外抛。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xj3_report_")
        self.report = os.path.join(self.tmp, "installer_report.txt")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_bytes(self, data):
        with open(self.report, "wb") as f:
            f.write(data)

    def test_missing_file_available_false(self):
        """文件缺失（便携/直跑形态）：available False，绝不外抛。"""
        with mock.patch.object(first_run, "INSTALLER_REPORT_FILE", self.report):
            self.assertEqual(first_run.read_installer_report(),
                             {"available": False})

    def test_gbk_bytes_with_chinese_hint(self):
        """GBK 字节（Inno SaveStringToFile=AnsiString 实锤形态）解析成功。"""
        content = ("2026/10/03 23:15:42\r\n"
                   "硬件自检建议: 推荐轻量版（云端优先）\r\n"
                   "ollama=0\r\nnapcat=1\r\nha=0\r\n")
        self._write_bytes(content.encode("gbk"))
        with mock.patch.object(first_run, "INSTALLER_REPORT_FILE", self.report):
            r = first_run.read_installer_report()
        self.assertTrue(r["available"])
        self.assertEqual(r["tier_hint"], "推荐轻量版（云端优先）")
        self.assertEqual(r["installed_at"], "2026/10/03 23:15:42")
        self.assertEqual(r["intents"],
                         {"ollama": False, "napcat": True, "ha": False})

    def test_utf8_bytes_also_ok(self):
        """utf-8 字节同样通过（回退链第一级直中）。"""
        content = ("2026/10/03 23:15:42\n硬件自检建议: 推荐完整版\n"
                   "ollama=1\nnapcat=0\nha=0\n")
        self._write_bytes(content.encode("utf-8"))
        with mock.patch.object(first_run, "INSTALLER_REPORT_FILE", self.report):
            r = first_run.read_installer_report()
        self.assertTrue(r["available"])
        self.assertEqual(r["tier_hint"], "推荐完整版")
        self.assertTrue(r["intents"]["ollama"])

    def test_binary_garbage_falls_back_without_raise(self):
        """补强：既非 utf-8 也非合法 GBK 的字节 → errors="replace" 兜底，
        不抛异常、返回结构完整合法。"""
        self._write_bytes(b"\xff\xfe\xfd\xfc")   # utf-8/gbk 解码均必炸的字节
        with mock.patch.object(first_run, "INSTALLER_REPORT_FILE", self.report):
            r = first_run.read_installer_report()
        self.assertTrue(r["available"])
        for key in ("installed_at", "tier_hint", "intents"):
            self.assertIn(key, r)
        self.assertEqual(set(r["intents"]), {"ollama", "napcat", "ha"})

    def test_empty_file_available_but_all_none(self):
        """空文件：available True 但全 None（前端三项全无守卫保持隐藏）。"""
        self._write_bytes(b"")
        with mock.patch.object(first_run, "INSTALLER_REPORT_FILE", self.report):
            r = first_run.read_installer_report()
        self.assertTrue(r["available"])
        self.assertIsNone(r["installed_at"])
        self.assertEqual(r["intents"],
                         {"ollama": None, "napcat": None, "ha": None})


class InstallerReportEndpointTests(unittest.TestCase):
    """B3 消费端：/api/first_run/installer_report 独立路由。"""

    def setUp(self):
        import xiaoju3_dashboard as dashboard
        self.client = dashboard.app.test_client()
        self.tmp = tempfile.mkdtemp(prefix="xj3_report_api_")
        self.report = os.path.join(self.tmp, "installer_report.txt")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_report_available_false(self):
        """报告缺失：200 + {"available": False}（路由自身零异常面）。"""
        with mock.patch.object(first_run, "INSTALLER_REPORT_FILE", self.report):
            resp = self.client.get("/api/first_run/installer_report")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(),
                         {"code": 200, "data": {"available": False}})

    def test_report_parsed_and_served(self):
        """GBK 报告在盘：路由吐出完整解析结构（available/时间戳/文案/三意向）。"""
        content = ("2026/10/03 23:15:42\n硬件自检建议: 推荐完整版\n"
                   "ollama=1\nnapcat=1\nha=0\n")
        with open(self.report, "wb") as f:
            f.write(content.encode("gbk"))
        with mock.patch.object(first_run, "INSTALLER_REPORT_FILE", self.report):
            resp = self.client.get("/api/first_run/installer_report")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertTrue(data["available"])
        self.assertEqual(data["tier_hint"], "推荐完整版")
        self.assertEqual(data["intents"],
                         {"ollama": True, "napcat": True, "ha": False})


class InstallerReportFrontendTests(unittest.TestCase):
    """B3 消费端静态锚：报告端点恰一次并行拉取 + hints 块默认隐藏 +
    渲染函数存在 + 禁 Promise.all + 既有零触碰不动（UI 运行行为不可离线
    单测，此处锁定「壳存在 + 默认不显示 + 源码语义」）。"""

    @classmethod
    def setUpClass(cls):
        cls.html = open(os.path.join(PROJECT_ROOT, "index.html"),
                        encoding="utf-8").read()
        cls.js = open(os.path.join(PROJECT_ROOT, "console.js"),
                      encoding="utf-8").read()

    def test_hints_div_present_and_default_hidden(self):
        """hints 块存在且默认 hidden（非安装形态零视觉变化锚），
        且位于浮层卡片内。"""
        self.assertIn('<div id="first-run-install-hints" hidden>', self.html)
        self.assertGreater(self.html.index('id="first-run-install-hints"'),
                           self.html.index('id="first-run-overlay"'))

    def test_report_fetch_exactly_once_inside_initfirstrun(self):
        """报告端点全文件恰一次，且在 initFirstRun 的 first_run=true 分支内。"""
        self.assertEqual(
            self.js.count("fetch('/api/first_run/installer_report')"), 1)
        init_idx = self.js.index("function initFirstRun()")
        seg = self.js[init_idx:self.js.index("function showFirstRun(")]
        self.assertIn("fetch('/api/first_run/installer_report')", seg)

    def test_render_function_and_no_promise_all(self):
        """renderInstallerReport 独立渲染函数存在；首装块禁 Promise.all
        （报告慢不得拖探针——并行独立拉取口径源码锁定）。"""
        self.assertIn("function renderInstallerReport(", self.js)
        seg = self.js[self.js.index("function initFirstRun()"):
                      self.js.index("function submitFirstRun(")]
        self.assertNotIn("Promise.all", seg)

    def test_zero_touch_anchors_intact(self):
        """零触碰锚复述（范围=initFirstRun 定义到 IIFE 尾调用，覆盖全部新增
        代码）：轮询原样、该段零 localStorage、不直操桌宠缩球类——
        （节头注释含"弃用 localStorage"历史字样，故不从节头起切，同 house 锚口径）。"""
        self.assertIn("setInterval(fetchStatus, 2000)", self.js)
        seg = self.js[self.js.index("function initFirstRun()"):
                      self.js.index("initFirstRun();")]
        self.assertNotIn("localStorage", seg)
        self.assertNotIn("classList.add('xiaoju3-pet-minimized'", seg)
        self.assertNotIn("classList.remove('xiaoju3-pet-minimized'", seg)


if __name__ == "__main__":
    unittest.main()
