#!/usr/bin/env bash
# 小橘3号 · 一键彻底停止（架构设计文档 §8）
# 流程：密码确认 → 清理相关 python 进程 → 释放 5001-5003 端口 → 停 napcat/homeassistant 容器。
# 安全红线：停止密码不得硬编码在脚本内。
#   - 优先从环境变量 STOP_PASSWORD 读取期望密码（如 export STOP_PASSWORD=... 或写入隔离区 .env 后 source）；
#   - 未设置时进入运行时输入模式（两次输入一致即确认），留空则取消。
cd "$(dirname "$0")" || exit 1

echo "⚠️ 你正在申请彻底停止小橘3号（包括所有子服务）。"

if [ -n "$STOP_PASSWORD" ]; then
    # 环境变量模式：输入的密码必须与 STOP_PASSWORD 一致
    read -s -r -p "请输入停止密码以确认（直接回车取消）: " INPUT_PWD
    echo ""
    if [ -z "$INPUT_PWD" ]; then
        echo "❌ 未输入密码，停止操作已取消。"
        exit 1
    fi
    if [ "$INPUT_PWD" != "$STOP_PASSWORD" ]; then
        echo "❌ 密码错误，停止操作已取消。"
        exit 1
    fi
else
    # 运行时输入模式：两次输入一致才算确认（不回显、不落盘）
    read -s -r -p "请输入停止确认密码（直接回车取消）: " PWD_ONE
    echo ""
    if [ -z "$PWD_ONE" ]; then
        echo "❌ 未输入密码，停止操作已取消。"
        exit 1
    fi
    read -s -r -p "请再次输入确认: " PWD_TWO
    echo ""
    if [ "$PWD_ONE" != "$PWD_TWO" ]; then
        echo "❌ 两次输入不一致，停止操作已取消。"
        exit 1
    fi
fi

echo "✅ 密码确认通过，正在彻底停止..."

# 1. 停止守护脚本并清理安全退出标记
pkill -9 -f "start\.sh" 2>/dev/null
rm -f stop.flag

# 2. 精准清理小橘3号的 Python 进程（命令行带脚本名才杀，避免误杀系统 Python）
pkill -9 -f "python.*main\.py" 2>/dev/null
pkill -9 -f "python.*xiaoju3_dashboard\.py" 2>/dev/null

# 3. 释放可能被占用的应用端口（5001/5002/5003）
for PORT in 5001 5002 5003; do
    PORT_PID=$(lsof -t -i:"$PORT" 2>/dev/null)
    if [ -n "$PORT_PID" ]; then
        echo "🛑 正在释放端口 $PORT (PID: $PORT_PID)"
        kill -9 $PORT_PID 2>/dev/null
    fi
done

# 4. 停止 Docker 容器（NapCat 和 Home Assistant；docker 存在才执行）
if command -v docker >/dev/null 2>&1; then
    echo "🐳 正在停止 Docker 容器 (napcat & homeassistant)..."
    docker stop napcat homeassistant 2>/dev/null
else
    echo "ℹ️ 未检测到 docker，跳过容器停止。"
fi

echo "🛑 小橘3号及其所有子服务已彻底停止，5001-5003 端口已释放。"
