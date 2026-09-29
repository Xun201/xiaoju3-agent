#!/bin/bash
# 一键启动小橘3号 Web 控制台（后台运行）
cd /home/orangepi/xiaoju3-agent
# 先杀掉旧的 dashboard 进程（如果还在跑）
pkill -f xiaoju3_dashboard.py 2>/dev/null
sleep 1
# 后台启动，日志写到 dashboard.log
nohup python3 xiaoju3_dashboard.py > dashboard.log 2>&1 &
echo "✅ 小橘3号控制台已启动"
echo "   访问地址：http://192.168.31.82:5003/console"
echo "   查看日志：tail -f /home/orangepi/xiaoju3-agent/dashboard.log"
echo "   停止服务：pkill -f xiaoju3_dashboard.py"