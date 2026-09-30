#!/usr/bin/env bash
# 小橘3号 · 一键重启主程序与仪表盘（参考实现口径：清进程 → 清标记 → 重启）
cd "$(dirname "$0")" || exit 1  # 关键：强制进入项目目录
echo "🔄 正在重启小橘3号（主程序 + 控制台）..."
# 精准清理：只杀带本项目脚本名的进程，避免误杀系统 Python
pkill -9 -f "python.*main\.py" 2>/dev/null
pkill -9 -f "python.*xiaoju3_dashboard\.py" 2>/dev/null
pkill -9 -f "start\.sh" 2>/dev/null
rm -f stop.flag
sleep 1
echo "✅ 清理完成，正在重新启动控制台与守护..."
./start_dashboard.sh
./start.sh
