@echo off
chcp 65001 >nul
setlocal
rem =====================================================
rem 小橘3号 · Windows 停止脚本
rem 用 PowerShell 按命令行精准匹配 main.py / xiaoju3_dashboard.py 的 Python 进程；
rem 排除匹配进程自身（其命令行含同样关键字），绝不误杀其他 Python 进程。
rem =====================================================
cd /d "%~dp0"
echo 🔄 正在停止小橘3号（主程序 + 控制台）...
powershell -NoProfile -Command "$targets = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.ProcessId -ne $PID -and $_.CommandLine -match 'main\.py|xiaoju3_dashboard\.py' }); if ($targets.Count -gt 0) { $targets | ForEach-Object { Write-Host ('将关闭 PID ' + $_.ProcessId + ' ： ' + $_.CommandLine) }; $targets | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Write-Host '✅ 已停止全部小橘3号进程' } else { Write-Host 'ℹ️ 未发现正在运行的小橘3号进程' }"
endlocal
