#!/usr/bin/env bash
# 小橘3号 · 守护启动脚本（架构设计文档 §8）
# 职责：主进程异常退出 2 秒后自动拉起；stop.flag 文件为安全退出标记；
#       可选加载隔离区私有 ADB 无线连接脚本（存在才执行，不存在就跳过，绝不报错）。
trap '' SIGINT

# 进入脚本所在目录（不硬编码机器路径，任意终端可部署）
cd "$(dirname "$0")" || exit 1

while true; do
    # 检查是否存在安全退出标志文件
    if [ -f "stop.flag" ]; then
        echo "🛑 检测到安全退出标志，守护脚本停止运行。"
        rm -f stop.flag
        break
    fi

    # 尝试加载隔离区的私有无线 ADB 连接配置
    # 路径可用环境变量 XIAOJU3_PRIVATE_ADB 覆盖；不存在（他人 clone 下来）就跳过，绝不报错
    PRIVATE_ADB="${XIAOJU3_PRIVATE_ADB:-$HOME/xiaoju3_data/connect_adb.sh}"
    if [ -f "$PRIVATE_ADB" ]; then
        echo "📡 检测到私有 ADB 无线配置，正在尝试连接手机..."
        bash "$PRIVATE_ADB"
    fi

    python3 main.py

    # 如果刚才异常退出，再次检查标志（防止退出瞬间错过检查）
    if [ -f "stop.flag" ]; then
        echo "🛑 检测到安全退出标志，守护脚本停止运行。"
        rm -f stop.flag
        break
    fi

    echo "🔄 小橘3号意外退出，2秒后自动重启..."
    sleep 2
done
