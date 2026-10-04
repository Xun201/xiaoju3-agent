@echo off
chcp 65001 >nul
rem 常驻窗口监控（后台静默）：抓 DeepSeek 提取链偶发闪窗，留证 xiaoju3_data\console_window_watch.log
rem 停止方式：taskkill /f /pid <监控进程PID>（精准停止；
rem   勿用 taskkill /f /im pythonw.exe——会误杀机器上所有 pythonw 进程）
cd /d "%~dp0.."
start "" pythonw _dev\watch_console_window.py
echo 监控已在后台启动（pythonw，无窗口）。日志: xiaoju3_data\console_window_watch.log
