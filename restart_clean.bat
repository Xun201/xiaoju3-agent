@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem 小橘3号 · 一键干净重启（Windows 侧）。
rem 流程：清杀全部 xiaoju3 python 进程 -^> 等 2 秒 -^> 确认 5003 释放 -^>
rem 清理旧日志（保留最近 10 个）-^> 隐藏窗口启动 launcher（日志带启动时间戳）。
rem 日志路径由 xiaoju3_launcher 生成（timestamped_log_path / prune_dashboard_logs，
rem 与 restart_clean.sh 共用同一实现）。2026-10-02 稳定性排查方案 d。

echo [1/4] 清杀全部小橘3号 python 进程...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*xiaoju3*' } | ForEach-Object { Write-Host ('  清杀 PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force }"

echo [2/4] 等待 2 秒并确认 5003 释放...
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5003 -State Listen -ErrorAction SilentlyContinue) { exit 1 }"
if errorlevel 1 (
    echo ⚠️ 5003 仍被占用，请手动检查后重试。
    exit /b 1
)
echo       端口已释放。

echo [3/4] 清理旧启动日志（保留最近 10 个）...
for /f %%i in ('python -c "import xiaoju3_launcher as l; kept,removed=l.prune_dashboard_logs(); print(removed)"') do set REMOVED=%%i
echo       已清理旧日志 %REMOVED% 个。

echo [4/4] 启动小橘3号（单实例，日志带启动时间戳）...
for /f %%i in ('python -c "import xiaoju3_launcher as l; print(l.timestamped_log_path())"') do set LOGPATH=%%i
powershell -NoProfile -Command "$env:PYTHONUNBUFFERED='1'; Start-Process -FilePath 'python' -ArgumentList 'xiaoju3_launcher.py' -WorkingDirectory '%~dp0' -WindowStyle Hidden -RedirectStandardOutput '%LOGPATH%' -RedirectStandardError '%LOGPATH:.log=.err.log%'"
echo       已启动（隐藏窗口），日志：%LOGPATH%
echo [OK] 干净重启完成。
endlocal
