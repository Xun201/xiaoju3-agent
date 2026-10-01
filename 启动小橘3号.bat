@echo off
chcp 65001 >nul
setlocal
rem =====================================================
rem 小橘3号 · Windows 双击启动器
rem 拉起：main.py（主程序 5002） + xiaoju3_dashboard.py（控制台 5003/console）
rem 可选参数 /desktop：同时拉起桌面桌宠窗口（可选组件，缺失自动跳过不报错）
rem =====================================================

rem ① 切换到 bat 所在目录（兼容中文与空格路径）
cd /d "%~dp0"

rem ② 选择 Python：优先项目内置 .venv，其次系统 python
set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"

rem ③ 可选参数 /desktop
set "LAUNCH_DESKTOP=0"
if /i "%~1"=="/desktop" set "LAUNCH_DESKTOP=1"
if /i "%~2"=="/desktop" set "LAUNCH_DESKTOP=1"

rem ④ 精准检测：只看命令行含 main.py 的 python 进程（排除检测进程自身），已跑则跳过拉起
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.ProcessId -ne $PID -and $_.CommandLine -match 'main\.py' }) { exit 0 } else { exit 1 }"
if %errorlevel%==0 (
    echo ℹ️ 主程序已在运行，跳过拉起
) else (
    start "xiaoju3-main" /min cmd /c ""%PYTHON%" main.py"
)

rem ④ 精准检测：只看命令行含 xiaoju3_dashboard.py 的 python 进程，已跑则跳过拉起
powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.ProcessId -ne $PID -and $_.CommandLine -match 'xiaoju3_dashboard\.py' }) { exit 0 } else { exit 1 }"
if %errorlevel%==0 (
    echo ℹ️ 控制台已在运行，跳过拉起
) else (
    start "xiaoju3-dashboard" /min cmd /c ""%PYTHON%" xiaoju3_dashboard.py"
)

rem ⑤ 等服务就绪后打开控制台
timeout /t 3 >nul
start "" http://127.0.0.1:5003/console

rem ⑥ 启动结果（与 start.sh 日志口径一致）
echo ✅ 主程序已启动 (5002)
echo ✅ 控制台已启动 (5003/console)

rem ⑦ 可选：拉起桌面桌宠窗口（desktop_launcher.py 为可选组件，文件不存在则提示跳过，不报错）
if "%LAUNCH_DESKTOP%"=="1" (
    if exist "desktop_launcher.py" (
        start "xiaoju3-desktop" /min cmd /c ""%PYTHON%" desktop_launcher.py"
    ) else (
        echo ℹ️ 未找到 desktop_launcher.py，跳过桌面窗口
    )
)

echo 提示：小橘3号在本窗口后台运行，请保持窗口开启（关闭窗口即停止服务，或运行 停止小橘3号.bat）
pause >nul
endlocal
