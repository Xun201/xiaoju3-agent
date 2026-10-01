#!/usr/bin/env bash
# 小橘3号 · 守护启动脚本（架构设计文档 §8）
# 职责：只拉起两个进程——main.py（主程序 5002）与 xiaoju3_dashboard.py（控制台 5003/console）；
#       主程序异常退出 2 秒后自动拉起；stop.flag 文件为安全退出标记；
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

    # 先后台拉起主程序，再拉起控制台（口径：5002 主程序 → 5003/console 控制台）
    python3 main.py &
    MAIN_PID=$!
    # 控制台仅在未运行时拉起（nohup 脱离终端，日志落 dashboard.log），
    # 守护循环重启主程序时不会重复拉起
    if ! pgrep -f "xiaoju3_dashboard\.py" > /dev/null 2>&1; then
        nohup python3 xiaoju3_dashboard.py > dashboard.log 2>&1 &
    fi
    echo "✅ 主程序已启动 (5002)"
    echo "✅ 控制台已启动 (5003/console)"

    # 守护等待：主程序退出后由循环决定重启或安全退出（控制台进程不受影响）
    wait "$MAIN_PID"

    # 如果刚才异常退出，再次检查标志（防止退出瞬间错过检查）
    if [ -f "stop.flag" ]; then
        echo "🛑 检测到安全退出标志，守护脚本停止运行。"
        rm -f stop.flag
        break
    fi

    echo "🔄 小橘3号意外退出，2秒后自动重启..."
    sleep 2
done
