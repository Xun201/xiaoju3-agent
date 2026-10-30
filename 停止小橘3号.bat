@echo off
chcp 65001 >nul
setlocal
rem =====================================================
rem xiaoju3-agent - Windows stop script (safe scope)
rem
rem FIX 2026-10-30:
rem   Old rule used -match 'main\.py' globally, which also killed
rem   unrelated Python processes on the same machine (real case:
rem   another project's agent_webui/backend/main.py was killed).
rem
rem New rule: only processes INSIDE this project directory are eligible.
rem   1) exe path starts with this project dir (catches .venv-launched
rem      desktop processes started with a relative script path)
rem   2) command line contains this project dir as an absolute path
rem   3) command line contains a xiaoju3-only script name
rem      (xiaoju3_dashboard / xiaoju3_launcher / desktop_launcher)
rem   main.py counts only when 1) or 2) matches. No cross-project match.
rem =====================================================
cd /d "%~dp0"
echo 🔄 正在停止小橘3号（仅限本项目目录）...
powershell -NoProfile -Command "$root=(Get-Location).Path.TrimEnd('\'); $p=$root+'\'; $targets=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.ProcessId -ne $PID -and (($_.ExecutablePath -and $_.ExecutablePath.StartsWith($p,[System.StringComparison]::OrdinalIgnoreCase)) -or ($_.CommandLine -and $_.CommandLine.IndexOf($p,[System.StringComparison]::OrdinalIgnoreCase) -ge 0) -or ($_.CommandLine -match 'xiaoju3_dashboard\.py|xiaoju3_launcher\.py|desktop_launcher\.py')) }); if ($targets.Count -gt 0) { $targets | ForEach-Object { Write-Host ('将关闭 PID ' + $_.ProcessId + ' ： ' + $_.CommandLine) }; $targets | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Write-Host '✅ 已停止全部小橘3号进程' } else { Write-Host 'ℹ️ 未发现正在运行的小橘3号进程' }"
endlocal
