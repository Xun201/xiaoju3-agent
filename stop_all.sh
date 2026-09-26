#!/bin/bash
echo "⚠️ 你正在申请彻底停止小橘3号。"
read -s -p "请输入停止密码以确认（直接回车取消）: " INPUT_PWD
echo ""
if [ "$INPUT_PWD" != "orangepi" ]; then
    echo "❌ 密码错误，停止操作已取消。"
    exit 1
fi
echo "✅ 密码正确，正在彻底停止..."
sudo pkill -9 -f start.sh
sudo pkill -9 -f python3
rm -f /home/orangepi/xiaoju3-agent/stop.flag
PORT_PID=$(sudo lsof -t -i:5002)
if [ ! -z "$PORT_PID" ]; then
    sudo kill -9 $PORT_PID
fi
echo "🛑 小橘3号已彻底停止，端口已释放。"
