@echo off
chcp 65001 >nul
setlocal
rem =====================================================
rem 小橘3号 · Windows 双击启动器（桌面软件化主入口）
rem 只拉起 desktop_launcher.py（pywebview 独立桌面窗口，1200x800 无地址栏）：
rem   窗口内部自动后台拉起 xiaoju3_launcher.py（5003 一个进程承载一切：
rem   QQ webhook /onebot + 控制台 + 心跳；5002 端口已废弃），
rem   关闭桌面窗口即自动停止全部后台进程；
rem   旧形态（浏览器打开 http://127.0.0.1:5003/console）已废弃，不再开浏览器。
rem =====================================================

rem ① 切换到 bat 所在目录（兼容中文与空格路径）
cd /d "%~dp0"

rem ② 选择 Python：优先项目内置 .venv，其次系统 python
rem    pythonw 为无控制台形态（纯桌面窗口，像 exe 一样）
set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
set "PYTHONW=pythonw"
if exist ".venv\Scripts\pythonw.exe" set "PYTHONW=.venv\Scripts\pythonw.exe"

rem ③ 兼容旧参数 /desktop（桌面窗口现为主入口默认行为，参数仅兼容保留）

rem ④ 精准检测：只看命令行含 desktop_launcher.py 的 python 进程（排除检测进程自身），已跑则跳过拉起
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.ProcessId -ne $PID -and $_.CommandLine -match 'desktop_launcher\.py' }) { exit 0 } else { exit 1 }"
if %errorlevel%==0 (
    echo ℹ️ 桌面控制台已在运行，跳过拉起
    pause >nul
    endlocal
    exit /b 0
)

rem ⑤ 拉起桌面主入口（独立桌面窗口；文件缺失则提示跳过，不报错）
if exist "desktop_launcher.py" (
    start "xiaoju3-desktop" "%PYTHONW%" "desktop_launcher.py"
) else (
    echo ℹ️ 未找到 desktop_launcher.py，跳过桌面窗口
    pause >nul
    endlocal
    exit /b 0
)

rem ⑥ 启动结果（后台服务由桌面窗口拉起，稍候数秒就绪；与 start.sh 日志口径一致）
echo ✅ 主程序已启动 (5003)（由桌面窗口后台拉起，稍候数秒就绪；5002 端口已废弃）
echo ✅ 控制台已启动 (5003/console)（原生桌面窗口内打开，不再开浏览器）
echo ⚠️ QQ webhook 已迁移至 5003：请将 LLOneBot 的 HTTP 上报地址改为 http://127.0.0.1:5003/onebot，否则 QQ 会断连

echo 提示：关闭桌面窗口即自动停止全部小橘3号后台进程；也可运行 停止小橘3号.bat 一键关闭
pause >nul
endlocal
