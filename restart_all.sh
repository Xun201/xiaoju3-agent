#!/bin/bash
cd /home/orangepi/xiaoju3-agent  # 关键：强制进入项目目录
echo "🔄 正在重启小橘3号..."
sudo pkill -9 -f python3
sudo pkill -9 -f start.sh
rm -f stop.flag
sleep 1
echo "✅ 清理完成，正在重新启动守护..."
./start.sh
