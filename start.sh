#!/bin/bash
trap '' SIGINT
cd ~/xiaoju3-agent
while true; do
    # 检查是否存在安全退出标志文件
    if [ -f "stop.flag" ]; then
        echo "🛑 检测到安全退出标志，守护脚本停止运行。"
        rm stop.flag
        break
    fi

    python3 main.py
    
    # 如果刚才异常退出，再次检查标志（防止退出瞬间错过检查）
    if [ -f "stop.flag" ]; then
        echo "🛑 检测到安全退出标志，守护脚本停止运行。"
        rm stop.flag
        break
    fi
    
    echo "🔄 小橘3号意外退出，2秒后自动重启..."
    sleep 2
done
