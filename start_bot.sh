#!/bin/bash
cd /home/orangepi/xiaoju3-agent
echo "🛑 正在清理旧进程..."
pkill -9 -f python3
rm -f stop.flag
echo "🚀 正在后台启动小橘3号..."
nohup ./start.sh > run.log 2>&1 &
echo "✅ 启动成功！日志已写入 run.log"
