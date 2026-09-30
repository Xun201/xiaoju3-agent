# -*- coding: utf-8 -*-
"""部署脚本静态验收（全部离线）：

1. 对每个 .sh 做 bash -n 语法检查；
2. 关键行为断言：读取脚本内容，断言守护循环、完整性校验、停止密码、
   端口释放、四道隐私扫描、清单生成等标志文案存在；
3. 安全红线断言：不得出现内网 IP、不得硬编码停止密码、行尾必须是 LF。
"""
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCRIPTS = [
    "start.sh",
    "secure_start.sh",
    "stop_all.sh",
    "start_dashboard.sh",
    "restart_all.sh",
    "push.sh",
    "make_manifest.sh",
]


def read_script(name):
    return (ROOT / name).read_text(encoding="utf-8")


class TestScriptBasics(unittest.TestCase):
    """语法、行尾与安全红线。"""

    def test_all_scripts_exist(self):
        for name in SCRIPTS:
            with self.subTest(script=name):
                self.assertTrue((ROOT / name).is_file(), f"缺少脚本 {name}")

    def test_bash_n_syntax(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("环境中没有 bash，跳过 bash -n 语法检查")
        for name in SCRIPTS:
            with self.subTest(script=name):
                result = subprocess.run(
                    [bash, "-n", (ROOT / name).as_posix()],
                    capture_output=True,
                )
                stderr = result.stderr.decode("utf-8", "replace")
                self.assertEqual(
                    result.returncode, 0, f"{name} 语法错误: {stderr}"
                )

    def test_shebang_and_lf_line_endings(self):
        for name in SCRIPTS:
            with self.subTest(script=name):
                raw = (ROOT / name).read_bytes()
                self.assertTrue(
                    raw.startswith(b"#!/usr/bin/env bash"),
                    f"{name} 必须以 #!/usr/bin/env bash 开头",
                )
                self.assertNotIn(b"\r", raw, f"{name} 行尾必须为 LF，不得含 CR")

    def test_no_internal_ip_or_hardcoded_password(self):
        """安全红线：禁止内网 IP 与参考实现中的真实停止密码字面量。"""
        for name in SCRIPTS:
            content = read_script(name)
            with self.subTest(script=name):
                self.assertNotIn("192.168.", content, f"{name} 含内网 IP")
                self.assertNotIn("orangepi", content, f"{name} 含参考实现真实密码/用户名")


class TestStartSh(unittest.TestCase):
    """守护循环：异常退出 2 秒拉起、stop.flag 安全退出、可选私有 ADB 脚本。"""

    def setUp(self):
        self.content = read_script("start.sh")

    def test_daemon_loop(self):
        self.assertIn("while true", self.content)
        self.assertIn("python3 main.py", self.content)
        self.assertIn("sleep 2", self.content)
        self.assertIn("2秒后自动重启", self.content)
        self.assertIn('cd "$(dirname "$0")"', self.content)

    def test_stop_flag_logic(self):
        self.assertIn("stop.flag", self.content)
        self.assertIn('rm -f stop.flag', self.content)
        # 双检查：循环开头 + 进程退出后各一次
        self.assertGreaterEqual(self.content.count('if [ -f "stop.flag" ]'), 2)
        self.assertIn("检测到安全退出标志", self.content)

    def test_optional_private_adb(self):
        self.assertIn("connect_adb.sh", self.content)
        self.assertIn("XIAOJU3_PRIVATE_ADB", self.content)
        # 存在才执行：必须是 [ -f ... ] 守卫
        self.assertIn('[ -f "$PRIVATE_ADB" ]', self.content)


class TestSecureStartSh(unittest.TestCase):
    """启动前 sha256sum -c 校验，失败拒绝启动。"""

    def test_checksum_gate(self):
        content = read_script("secure_start.sh")
        self.assertIn("sha256sum -c checksums.sha256", content)
        self.assertIn("exit 1", content)
        self.assertIn("篡改", content)
        self.assertIn("拒绝", content)

    def test_missing_manifest_refuses(self):
        content = read_script("secure_start.sh")
        self.assertIn('[ ! -f "checksums.sha256" ]', content)
        self.assertIn("make_manifest.sh", content)  # 说明先跑 make_manifest.sh

    def test_launch_after_pass(self):
        content = read_script("secure_start.sh")
        self.assertIn("exec python3 main.py", content)
        self.assertIn("logs/security.log", content)


class TestStopAllSh(unittest.TestCase):
    """密码确认 → 清进程 → 释放 5001-5003 → 停容器（docker 存在才执行）。"""

    def setUp(self):
        self.content = read_script("stop_all.sh")

    def test_password_confirmation_via_env_or_input(self):
        self.assertIn("STOP_PASSWORD", self.content)  # 环境变量，未硬编码真实值
        self.assertIn("read -s", self.content)  # 运行时输入且不回显
        self.assertIn("密码错误", self.content)

    def test_ports_5001_5003(self):
        for port in ("5001", "5002", "5003"):
            self.assertIn(port, self.content)
        self.assertIn('for PORT in 5001 5002 5003', self.content)
        self.assertIn("lsof -t -i", self.content)

    def test_process_cleanup(self):
        self.assertIn("pkill", self.content)
        self.assertIn("main\\.py", self.content)
        self.assertIn("xiaoju3_dashboard\\.py", self.content)
        self.assertIn("rm -f stop.flag", self.content)

    def test_docker_optional(self):
        self.assertIn("command -v docker", self.content)  # docker 存在才执行
        self.assertIn("docker stop napcat homeassistant", self.content)


class TestStartDashboardSh(unittest.TestCase):
    """后台启动 xiaoju3_dashboard.py。"""

    def test_background_start(self):
        content = read_script("start_dashboard.sh")
        self.assertIn("nohup python3 xiaoju3_dashboard.py", content)
        self.assertIn("2>&1 &", content)
        self.assertIn("dashboard.log", content)
        self.assertIn("5003", content)


class TestRestartAllSh(unittest.TestCase):
    """重启主程序与仪表盘（参考实现口径）。"""

    def test_restart_flow(self):
        content = read_script("restart_all.sh")
        self.assertIn("pkill", content)
        self.assertIn("rm -f stop.flag", content)
        self.assertIn("start_dashboard.sh", content)  # 仪表盘
        self.assertIn("./start.sh", content)  # 守护主程序


class TestPushSh(unittest.TestCase):
    """四道隐私扫描：命中即拦截并回滚 staged 变更。"""

    def setUp(self):
        self.content = read_script("push.sh")

    def test_scan_1_filename_blacklist(self):
        self.assertIn("[1/4]", self.content)
        self.assertIn("文件名黑名单", self.content)
        self.assertIn("PRIVACY_LIST", self.content)
        for keyword in ('".env"', '"identity.json"', '"memory"', '"history"', '"config.py"'):
            self.assertIn(keyword, self.content)

    def test_scan_2_plaintext_key(self):
        self.assertIn("[2/4]", self.content)
        self.assertIn("明文 API Key", self.content)
        self.assertIn("sk-[a-zA-Z0-9]{20,}", self.content)  # 常见 Key 形态正则
        self.assertIn("grep -qE", self.content)

    def test_scan_3_git_history(self):
        self.assertIn("[3/4]", self.content)
        self.assertIn("Git 历史", self.content)
        self.assertIn("git log -p", self.content)
        self.assertIn("git log -1", self.content)  # 存在提交历史才扫

    def test_scan_4_secret_time_machine_optional(self):
        self.assertIn("[4/4]", self.content)
        self.assertIn("secret-time-machine", self.content)
        self.assertIn("command -v secret-time-machine", self.content)  # 工具存在才执行
        self.assertIn("跳过深度扫描", self.content)

    def test_intercept_and_rollback(self):
        self.assertIn("安检不通过", self.content)
        self.assertIn("git reset", self.content)  # 回滚 staged 变更
        self.assertIn("exit 1", self.content)
        self.assertIn("人工确认", self.content)

    def test_env_example_whitelisted(self):
        """键名模板 .env.example 不含真实值，应被放行。"""
        self.assertIn('.env.example', self.content)


class TestMakeManifestSh(unittest.TestCase):
    """生成 manifest.txt 与 checksums.sha256，可一键重算。"""

    def test_generates_manifest_and_checksums(self):
        content = read_script("make_manifest.sh")
        self.assertIn("manifest.txt", content)
        self.assertIn("checksums.sha256", content)
        self.assertIn("sha256sum $(cat manifest.txt) > checksums.sha256", content)
        self.assertIn("CORE_FILES", content)

    def test_accepts_target_dir(self):
        """支持传入目标目录（集成阶段可在任意位置重算）。"""
        content = read_script("make_manifest.sh")
        self.assertIn('TARGET="${1:-$(pwd)}"', content)


class TestMakeManifestFunctional(unittest.TestCase):
    """功能测试：在临时目录实际运行 make_manifest.sh（不触碰项目根清单）。"""

    def test_run_in_tmp_dir(self):
        bash = shutil.which("bash")
        sha = shutil.which("sha256sum")
        if not bash or not sha:
            self.skipTest("环境中没有 bash/sha256sum，跳过功能测试")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # 必须创建核心清单内的文件（如 xiaoju3.py），否则清单为空会被正确拒绝
            (tmp_path / "xiaoju3.py").write_text("# core module a\n", encoding="utf-8", newline="\n")
            result = subprocess.run(
                [bash, (ROOT / "make_manifest.sh").as_posix(), tmp_path.as_posix()],
                capture_output=True,
            )
            stderr = result.stderr.decode("utf-8", "replace")
            self.assertEqual(result.returncode, 0, f"make_manifest.sh 执行失败: {stderr}")

            manifest = (tmp_path / "manifest.txt").read_text(encoding="utf-8")
            self.assertIn("xiaoju3.py", manifest)

            sums = (tmp_path / "checksums.sha256").read_text(encoding="utf-8")
            expect = hashlib.sha256(b"# core module a\n").hexdigest()
            self.assertIn(expect, sums)

            # 产物必须能被 sha256sum -c 校验通过（secure_start.sh 的验收口径）
            verify = subprocess.run(
                [sha, "-c", "checksums.sha256", "--quiet"],
                cwd=str(tmp_path),
                capture_output=True,
            )
            self.assertEqual(verify.returncode, 0, verify.stdout.decode("utf-8", "replace"))


class TestInstaller(unittest.TestCase):
    """install.sh 静态验收（S7 一键部署）：语法、关键行为断言、安全红线。"""

    def setUp(self):
        self.content = read_script("install.sh")
        self.raw = (ROOT / "install.sh").read_bytes()

    def test_exists_shebang_and_lf(self):
        self.assertTrue((ROOT / "install.sh").is_file(), "缺少 install.sh")
        self.assertTrue(
            self.raw.startswith(b"#!/usr/bin/env bash"),
            "install.sh 必须以 #!/usr/bin/env bash 开头",
        )
        self.assertNotIn(b"\r", self.raw, "install.sh 行尾必须为 LF，不得含 CR")

    def test_bash_n_syntax(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("环境中没有 bash，跳过 bash -n 语法检查")
        result = subprocess.run(
            [bash, "-n", (ROOT / "install.sh").as_posix()],
            capture_output=True,
        )
        stderr = result.stderr.decode("utf-8", "replace")
        self.assertEqual(result.returncode, 0, f"install.sh 语法错误: {stderr}")

    def test_env_self_check(self):
        """python3 必须（≥3.8 口径）；git/docker 可选，缺失降级提示不中断。"""
        self.assertIn("command -v python3", self.content)
        self.assertIn("3.8", self.content)  # 功能口径：Python ≥ 3.8
        self.assertIn("command -v git", self.content)
        self.assertIn("command -v docker", self.content)
        self.assertIn("降级", self.content)  # 可选依赖缺失时降级提示

    def test_venv_and_dependencies(self):
        self.assertIn("python3 -m venv .venv", self.content)
        self.assertIn(". .venv/bin/activate", self.content)
        self.assertIn("pip install -r requirements.txt", self.content)
        self.assertIn("python -m playwright install chromium", self.content)
        # 网络失败：镜像源建议 + 重试一次但不中断整体流程
        self.assertIn("PLAYWRIGHT_DOWNLOAD_HOST", self.content)
        self.assertIn("npmmirror.com/mirrors/playwright", self.content)
        self.assertIn("重试一次", self.content)
        self.assertIn("优雅降级", self.content)

    def test_env_bootstrap_from_template(self):
        """ .env 从模板生成；密钥交互不回显（read -s）；非交互只复制模板并提示手工填写。"""
        self.assertIn("cp .env.example .env", self.content)
        self.assertIn("read -s", self.content)
        for key in (
            "DEEPSEEK_API_KEY",
            "WEB_API_KEY",
            "XIAOJU3_TOTP_SECRET",
            "XIAOJU3_REGISTER_PASSWORD",
            "HA_URL",
            "HA_TOKEN",
        ):
            with self.subTest(key=key):
                self.assertIn(key, self.content)
        # 随机 Base32 密钥生成选项（标准 base64/secrets 实现）
        self.assertIn("b32encode", self.content)
        self.assertIn("--non-interactive", self.content)
        self.assertIn("请手工填写", self.content)
        # 已有 .env 绝不覆盖
        self.assertIn("绝不覆盖现有配置", self.content)

    def test_checksum_gate(self):
        self.assertIn("sha256sum -c checksums.sha256", self.content)
        self.assertIn("make_manifest.sh", self.content)  # 失败提示先跑 make_manifest.sh 重算
        self.assertIn("拒绝继续", self.content)  # 非交互模式校验失败拒绝继续

    def test_start_and_guide(self):
        """复用 start.sh / start_dashboard.sh；127.0.0.1 占位地址；LV2/LV3 引导文案。"""
        self.assertIn("bash start.sh", self.content)
        self.assertIn("start_dashboard.sh", self.content)
        self.assertIn("http://127.0.0.1:5003/console", self.content)
        self.assertIn("http://127.0.0.1:5002", self.content)
        self.assertIn("/register <注册密码>", self.content)
        self.assertIn("类 Root 安全警告", self.content)
        self.assertIn("TOTP", self.content)
        self.assertIn("stop_all.sh", self.content)
        # 可选 --register：经本机 /onebot 自调发出 LV2 注册请求
        self.assertIn("--register", self.content)
        self.assertIn("127.0.0.1:5002/onebot", self.content)

    def test_idempotent_and_failure_report(self):
        self.assertIn("跳过创建", self.content)  # .venv 已存在跳过（幂等）
        self.assertIn("已完成的步骤", self.content)  # 失败时打印已完成步骤清单
        self.assertIn("exit 1", self.content)
        self.assertIn("stop_all.sh", self.content)  # 已启动服务不回滚，提示手动停止

    def test_no_secrets_or_internal_ip(self):
        """安全红线：无内网 IP、无真实用户名/密码字面量、无明文 Key 形态。"""
        self.assertNotIn("192.168.", self.content, "install.sh 含内网 IP")
        self.assertNotIn("orangepi", self.content, "install.sh 含参考实现真实用户名/密码")
        self.assertNotRegex(self.content, r"sk-[A-Za-z0-9]{20,}", "install.sh 疑似含明文 Key")
        self.assertNotRegex(self.content, r"ghp_[A-Za-z0-9]{30,}", "install.sh 疑似含 GitHub Token")


# ===== 测试桩：模拟 python3（记录调用；venv/pip/playwright 全部不实际安装） =====
STUB_PY = """#!/usr/bin/env bash
# 测试桩 python3：只记录调用并模拟产物，绝不实际装包（离线）
STUB_SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
if [ -n "${FAKE_PY_LOG:-}" ]; then echo "$*" >> "$FAKE_PY_LOG"; fi
case "$1" in
    -c)
        CODE="${2:-}"
        case "$CODE" in
            *version_info*) echo "3.10.0" ;;
            *b32encode*) echo "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP" ;;
            *) : ;;
        esac
        ;;
    -m)
        case "${2:-}" in
            venv)
                VENV_DIR="${3:-.venv}"
                mkdir -p "$VENV_DIR/bin"
                printf 'home = stub\\nversion = 3.10.0\\n' > "$VENV_DIR/pyvenv.cfg"
                printf 'VIRTUAL_ENV="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"\\nPATH="$VIRTUAL_ENV/bin:$PATH"\\nexport VIRTUAL_ENV PATH\\n' > "$VENV_DIR/bin/activate"
                printf '#!/usr/bin/env bash\\nexec bash "%s" "$@"\\n' "$STUB_SELF" > "$VENV_DIR/bin/python"
                chmod +x "$VENV_DIR/bin/python" 2>/dev/null
                ;;
        esac
        ;;
esac
exit 0
"""


def _build_fake_project(root):
    """构造假 PROJECT_ROOT：假 requirements.txt / .env.example / 假启动脚本 + python3 桩。"""
    (root / "requirements.txt").write_text(
        "playwright==0.0.0-test\n", encoding="utf-8", newline="\n"
    )
    (root / ".env.example").write_text(
        "# 测试模板\n"
        "DEEPSEEK_API_KEY=\n"
        "WEB_API_KEY=changeme-xiaoju3\n"
        "XIAOJU3_TOTP_SECRET=\n"
        "XIAOJU3_REGISTER_PASSWORD=\n"
        "HA_URL=\n"
        "HA_TOKEN=\n",
        encoding="utf-8",
        newline="\n",
    )
    # 假启动脚本：只打标记不真启动（验证安装器确实调用了它们）
    (root / "start.sh").write_text(
        "#!/usr/bin/env bash\ntouch started_main.marker\n",
        encoding="utf-8",
        newline="\n",
    )
    (root / "start_dashboard.sh").write_text(
        "#!/usr/bin/env bash\ntouch started_dashboard.marker\n",
        encoding="utf-8",
        newline="\n",
    )
    stub_dir = root / "_stub"
    stub_dir.mkdir()
    stub = stub_dir / "python3"
    stub.write_text(STUB_PY, encoding="utf-8", newline="\n")
    stub.chmod(0o755)
    # 安装器自身也要复制进假项目根（install.sh 以"脚本所在目录"为项目根，避免误装真实仓库）
    shutil.copy2(ROOT / "install.sh", root / "install.sh")
    return stub_dir


def _run_installer(root, stub_dir, *args):
    """在假项目根运行 install.sh（PATH 前插 python3 桩，环境变量自动随子进程结束还原）。"""
    bash = shutil.which("bash")
    env = os.environ.copy()
    env["PATH"] = str(stub_dir) + os.pathsep + env["PATH"]
    env["FAKE_PY_LOG"] = str(root / "pystub.log")
    return subprocess.run(
        [bash, (root / "install.sh").as_posix(), *args],
        cwd=str(root),
        env=env,
        capture_output=True,
        timeout=120,
    )


class TestInstallerFunctional(unittest.TestCase):
    """tmp 目录集成小测：假 PROJECT_ROOT + python3 桩，全部离线（不装包、不联网）。"""

    def test_non_interactive_generates_env_and_degrades(self):
        """非交互路径：.env 从模板生成、提示手工填写、依赖调用被桩记录、启动脚本被调用。"""
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("环境中没有 bash，跳过安装器集成测试")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub_dir = _build_fake_project(root)
            result = _run_installer(root, stub_dir, "--non-interactive")
            out = result.stdout.decode("utf-8", "replace") + result.stderr.decode(
                "utf-8", "replace"
            )
            self.assertEqual(result.returncode, 0, f"install.sh 非交互安装失败:\n{out}")

            # .env 已从模板生成，内容与模板一致
            env_content = (root / ".env").read_text(encoding="utf-8")
            self.assertIn("DEEPSEEK_API_KEY=", env_content)
            self.assertIn("changeme-xiaoju3", env_content)

            # 非交互降级：打印"请手工填写"提示
            self.assertIn("请手工填写", out)

            # 虚拟环境/依赖安装调用被桩记录（不实际装包）
            stub_log = (root / "pystub.log").read_text(encoding="utf-8")
            self.assertIn("-m venv .venv", stub_log)
            self.assertIn("-m pip install -r requirements.txt", stub_log)
            self.assertIn("-m playwright install chromium", stub_log)

            # 启动脚本被真实调用（假脚本打标记）
            self.assertTrue((root / "started_main.marker").is_file())
            self.assertTrue((root / "started_dashboard.marker").is_file())

    def test_non_interactive_refuses_on_checksum_failure(self):
        """清单校验失败：非交互模式拒绝继续，退出码 1，不触达启动步骤。"""
        bash = shutil.which("bash")
        sha = shutil.which("sha256sum")
        if not bash or not sha:
            self.skipTest("环境中没有 bash/sha256sum，跳过安装器集成测试")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub_dir = _build_fake_project(root)
            # 构造一份必然失败的清单
            (root / "xiaoju3.py").write_text("# core\n", encoding="utf-8", newline="\n")
            (root / "checksums.sha256").write_text(
                "deadbeef  xiaoju3.py\n", encoding="utf-8", newline="\n"
            )
            result = _run_installer(root, stub_dir, "--non-interactive")
            out = result.stdout.decode("utf-8", "replace") + result.stderr.decode(
                "utf-8", "replace"
            )
            self.assertEqual(result.returncode, 1, f"校验失败应退出码 1:\n{out}")
            self.assertIn("make_manifest.sh", out)  # 提示先重算清单
            self.assertIn("拒绝继续", out)  # 非交互拒绝继续
            self.assertIn("已完成的步骤", out)  # 打印已完成步骤清单
            # 未触达启动步骤
            self.assertFalse((root / "started_main.marker").exists())

    def test_reinstall_is_idempotent(self):
        """重复安装安全：.venv 跳过创建、.env 不被覆盖。"""
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("环境中没有 bash，跳过安装器集成测试")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub_dir = _build_fake_project(root)
            first = _run_installer(root, stub_dir, "--non-interactive")
            self.assertEqual(
                first.returncode, 0, first.stdout.decode("utf-8", "replace")
            )
            # 用户已填写的 .env 加一个标记
            with open(root / ".env", "a", encoding="utf-8", newline="\n") as f:
                f.write("MARKER_TEST=1\n")
            second = _run_installer(root, stub_dir, "--non-interactive")
            out2 = second.stdout.decode("utf-8", "replace") + second.stderr.decode(
                "utf-8", "replace"
            )
            self.assertEqual(second.returncode, 0, f"二次安装失败:\n{out2}")
            # .env 未被覆盖（标记仍在），venv 跳过创建，配置引导跳过
            env_content = (root / ".env").read_text(encoding="utf-8")
            self.assertIn("MARKER_TEST=1", env_content)
            self.assertIn("跳过创建", out2)
            self.assertIn("跳过配置引导", out2)


class InstallerLegacyDepsTests(unittest.TestCase):
    """install.sh 的 Python 版本自适应依赖逻辑（香橙派 3.8 降级组合）。"""

    def setUp(self):
        with open("install.sh", "r", encoding="utf-8") as f:
            self.content = f.read()

    def test_legacy_branch_detects_python_version(self):
        self.assertIn('PY_MINOR_V', self.content)
        self.assertIn('-lt 10', self.content)

    def test_legacy_pins_in_requirements_py38(self):
        with open("requirements-py38.txt", "r", encoding="utf-8") as f:
            req38 = f.read()
        for pin in ('Flask==3.0.3', 'requests==2.32.3', 'playwright==1.48.0', 'psutil==7.2.2'):
            self.assertIn(pin, req38, f"requirements-py38.txt 缺少 3.8 兼容钉版 {pin}")
        self.assertNotIn("flask-cors==", req38, "3.8 依赖不应包含 flask-cors")

    def test_installer_reads_py38_file_on_old_python(self):
        self.assertIn("requirements-py38.txt", self.content)
        self.assertIn("-lt 10", self.content)
        self.assertIn("linux-arm64", self.content)

    def test_latest_pins_unchanged(self):
        with open("requirements.txt", "r", encoding="utf-8") as f:
            req = f.read()
        for pin in ('Flask==3.1.3', 'requests==2.34.2', 'playwright==1.63.0', 'psutil==7.2.2'):
            self.assertIn(pin, req, f"requirements.txt 缺少最新钉版 {pin}")


if __name__ == "__main__":
    unittest.main()
