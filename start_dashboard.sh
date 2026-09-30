#!/usr/bin/env bash
# 小橘3号 · 一键启动 Web 控制台（后台运行，端口 5003）
cd "$(dirname "$0")" || exit 1
# 先杀掉旧的 dashboard 进程（如果还在跑）
pkill -f "xiaoju3_dashboard\.py" 2>/dev/null
sleep 1
# 后台启动，日志写到 dashboard.log
nohup python3 xiaoju3_dashboard.py > dashboard.log 2>&1 &
echo "✅ 小橘3号控制台已启动"
echo "   访问地址：http://127.0.0.1:5003/console"
echo "   查看日志：tail -f dashboard.log"
echo "   停止服务：pkill -f xiaoju3_dashboard.py"
