#!/bin/bash
echo "⚠️ 你正在申请彻底停止小橘3号（包括所有子服务）。"
read -s -p "请输入停止密码以确认（直接回车取消）: " INPUT_PWD
echo ""
if [ "$INPUT_PWD" != "orangepi" ]; then
    echo "❌ 密码错误，停止操作已取消。"
    exit 1
fi

echo "✅ 密码正确，正在彻底停止..."

# 1. 停止守护脚本
sudo pkill -9 -f "start.sh" 2>/dev/null
rm -f /home/orangepi/xiaoju3-agent/stop.flag

# 2. 精准清理小橘3号的 Python 进程（避免误杀系统 Python）
sudo pkill -9 -f "python3.*xiaoju3-agent.*main.py" 2>/dev/null
sudo pkill -9 -f "python3.*xiaoju3-agent.*dashboard.py" 2>/dev/null

# 3. 释放可能被占用的应用端口（5001/5002/5003）
for PORT in 5001 5002 5003; do
    PORT_PID=$(sudo lsof -t -i:$PORT 2>/dev/null)
    if [ ! -z "$PORT_PID" ]; then
        echo "🛑 正在释放端口 $PORT (PID: $PORT_PID)"
        sudo kill -9 $PORT_PID 2>/dev/null
    fi
done

# 4. 停止 Docker 容器（NapCat 和 Home Assistant）
echo "🐳 正在停止 Docker 容器 (NapCat & Home Assistant)..."
sudo docker stop napcat homeassistant 2>/dev/null

echo "🛑 小橘3号及其所有子服务已彻底停止，所有端口已释放。"