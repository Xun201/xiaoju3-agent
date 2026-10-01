# -*- coding: utf-8 -*-
"""M2 启动脚本静态校验：start.sh / restart_all.sh / 启动小橘3号.bat / 停止小橘3号.bat。

全部为本地静态断言 + 可读性检查，离线可跑：不启动任何服务、不联网、不杀进程。
"""
import os
import re
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START_SH = os.path.join(ROOT, "start.sh")
RESTART_SH = os.path.join(ROOT, "restart_all.sh")
START_BAT = os.path.join(ROOT, "启动小橘3号.bat")
STOP_BAT = os.path.join(ROOT, "停止小橘3号.bat")

# 统一日志口径（shell 与 bat 一致）
LOG_MAIN = "✅ 主程序已启动 (5002)"
LOG_CONSOLE = "✅ 控制台已启动 (5003/console)"
# 停止侧精准匹配正则（原样文本，含转义点）
KILL_REGEX = r"main\.py|xiaoju3_dashboard\.py"


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def read_text(path):
    return read_bytes(path).decode("utf-8")


def find_start_line(bat_lines, keyword):
    """返回以 start 开头且含 keyword 的行号（未找到返回 -1）。"""
    for i, line in enumerate(bat_lines):
        stripped = line.strip().lower()
        if stripped.startswith("start ") and keyword in line:
            return i
    return -1


class BatEncodingTest(unittest.TestCase):
    """编码红线：bat 必须 UTF-8 无 BOM，且使用 CRLF 行尾（Windows 批处理稳健性）。"""

    def _check_bat(self, path):
        data = read_bytes(path)
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"), f"{path} 不应带 BOM")
        data.decode("utf-8")  # 必须是合法 UTF-8
        self.assertIn(b"\r\n", data, f"{path} 应为 CRLF 行尾")
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""), f"{path} 不应有裸 LF")

    def test_start_bat_encoding(self):
        self._check_bat(START_BAT)

    def test_stop_bat_encoding(self):
        self._check_bat(STOP_BAT)


class ShellScriptTest(unittest.TestCase):
    """shell 启动脚本：语法、拉起顺序、日志口径、守护/stop.flag 逻辑保留。"""

    def test_bash_syntax(self):
        if shutil.which("bash") is None:
            self.skipTest("bash 不可用，跳过语法检查")
        for path in (START_SH, RESTART_SH):
            with self.subTest(script=os.path.basename(path)):
                r = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_start_sh_only_two_processes_in_order(self):
        text = read_text(START_SH)
        # 只拉起两个 python 进程：main.py 与 xiaoju3_dashboard.py
        launches = [ln for ln in text.splitlines()
                    if re.search(r"(?:^|\s)(?:nohup\s+)?python3\s+\S+\.py", ln)]
        self.assertEqual(len(launches), 2, f"start.sh 只应拉起两个进程，实际：{launches}")
        main_idx = text.index("python3 main.py &")
        dash_idx = text.index("nohup python3 xiaoju3_dashboard.py")
        self.assertLess(main_idx, dash_idx, "必须先后台拉起 main.py，再拉起控制台")

    def test_start_sh_log_lines(self):
        text = read_text(START_SH)
        self.assertIn(LOG_MAIN, text)
        self.assertIn(LOG_CONSOLE, text)

    def test_start_sh_daemon_and_stop_flag_preserved(self):
        text = read_text(START_SH)
        self.assertIn("while true", text)        # 守护循环保留
        self.assertIn("sleep 2", text)           # 异常退出 2 秒拉起保留
        self.assertIn("2秒后自动重启", text)
        self.assertIn("wait", text)              # 守护等待主程序退出
        self.assertIn("stop.flag", text)         # 安全退出标记保留
        self.assertGreaterEqual(text.count('if [ -f "stop.flag" ]'), 2)  # 双检查保留
        self.assertIn("rm -f stop.flag", text)
        self.assertIn("检测到安全退出标志", text)

    def test_restart_sh_stop_then_start(self):
        text = read_text(RESTART_SH)
        self.assertIn('pkill -9 -f "python.*main\\.py"', text)
        self.assertIn('pkill -9 -f "python.*xiaoju3_dashboard\\.py"', text)
        self.assertIn("rm -f stop.flag", text)
        stop_idx = text.index("pkill")
        start_idx = text.index("./start.sh")
        self.assertLess(stop_idx, start_idx, "restart_all 必须先停后启")
        self.assertTrue(text.rstrip().endswith("./start.sh"),
                        "统一由 start.sh 拉起，保证启动顺序与 ✅ 日志口径一致")


class StartBatTest(unittest.TestCase):
    """启动小橘3号.bat：编码、进程检测、启动顺序、日志、可选桌宠、禁用 taskkill。"""

    def setUp(self):
        self.text = read_text(START_BAT)
        self.lines = self.text.splitlines()

    def test_header_chcp_and_cd(self):
        self.assertEqual(self.lines[0].strip(), "@echo off")
        self.assertEqual(self.lines[1].strip(), "chcp 65001 >nul")
        self.assertIn('cd /d "%~dp0"', self.text)   # 切到 bat 所在目录
        self.assertIn("setlocal", self.text)

    def test_python_env_priority(self):
        self.assertIn('set "PYTHON=python"', self.text)
        self.assertIn('if exist ".venv\\Scripts\\python.exe"', self.text)

    def test_precise_process_detect(self):
        # 按命令行精准检测桌面主入口（排除检测进程自身），避免误判已在运行
        # （桌面软件化后启动 bat 只拉起 desktop_launcher.py，不再直接拉 main/dashboard）
        self.assertIn("CommandLine -match", self.text)
        self.assertIn(r"desktop_launcher\.py", self.text)
        self.assertIn("ProcessId -ne $PID", self.text)

    def test_desktop_window_launch(self):
        # 桌面软件化（S3）：启动 bat 只拉起 desktop_launcher.py（pythonw 纯桌面窗口），
        # 后台三模块由桌面窗口经 xiaoju3_launcher.py 间接拉起，bat 不直接拉起
        desk_i = find_start_line(self.lines, "desktop_launcher.py")
        self.assertGreaterEqual(desk_i, 0, "缺少 desktop_launcher.py 拉起命令")
        self.assertIn('"%PYTHONW%"', self.lines[desk_i])   # 无控制台形态
        for leaked in ("main.py", "xiaoju3_dashboard.py", "xiaoju3_launcher.py"):
            self.assertNotIn(leaked, self.lines[desk_i], f"启动 bat 不应直接拉起 {leaked}")

    def test_no_browser_open(self):
        # 桌面软件化：不再打开浏览器，控制台在 pywebview 独立窗口内打开；
        # 旧 URL 仅存在于注释说明中
        self.assertNotIn('start "" http://', self.text)
        self.assertNotIn("timeout /t 3", self.text)
        self.assertIn("5003/console", self.text)   # 注释口径保留

    def test_two_log_lines(self):
        self.assertIn(LOG_MAIN, self.text)
        self.assertIn(LOG_CONSOLE, self.text)

    def test_desktop_optional(self):
        self.assertIn("/desktop", self.text)
        self.assertIn("desktop_launcher.py", self.text)
        # 文件不存在则提示跳过，不报错
        self.assertIn('if exist "desktop_launcher.py"', self.text)
        self.assertIn("跳过桌面窗口", self.text)

    def test_no_taskkill(self):
        self.assertNotIn("taskkill", self.text.lower())


class StopBatTest(unittest.TestCase):
    """停止小橘3号.bat：精准匹配正则、先列 PID 再杀、自我排除、禁用 taskkill。"""

    def setUp(self):
        self.text = read_text(STOP_BAT)
        self.lines = self.text.splitlines()

    def test_header_chcp_and_cd(self):
        self.assertEqual(self.lines[0].strip(), "@echo off")
        self.assertEqual(self.lines[1].strip(), "chcp 65001 >nul")
        self.assertIn('cd /d "%~dp0"', self.text)
        self.assertIn("setlocal", self.text)

    def test_precise_kill_regex(self):
        self.assertIn(KILL_REGEX, self.text)  # main\.py|xiaoju3_dashboard\.py
        self.assertIn("Get-CimInstance Win32_Process", self.text)
        self.assertIn("CommandLine -match", self.text)
        # 排除匹配进程自身（其命令行含同样关键字），不误杀其他 Python 进程
        self.assertIn("ProcessId -ne $PID", self.text)
        self.assertIn("python*", self.text)

    def test_pid_list_printed_before_kill(self):
        self.assertIn("将关闭 PID", self.text)
        self.assertIn("Stop-Process", self.text)
        self.assertLess(self.text.index("将关闭 PID"), self.text.index("Stop-Process"),
                        "必须先打印将关闭的 PID 列表，再执行停止")
        self.assertIn("已停止", self.text)

    def test_no_taskkill(self):
        self.assertNotIn("taskkill", self.text.lower())


@unittest.skipUnless(os.name == "nt", "仅 Windows 可运行 cmd 可读性检查")
class BatReadableTest(unittest.TestCase):
    """cmd 可读性实测：等价于 bat 语法冒烟（bat 无法 bash -n）。"""

    def test_cmd_can_read_bats(self):
        for path in (START_BAT, STOP_BAT):
            with self.subTest(bat=os.path.basename(path)):
                r = subprocess.run(["cmd", "/c", "type", path], capture_output=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertGreater(len(r.stdout.strip()), 0)


if __name__ == "__main__":
    unittest.main()
