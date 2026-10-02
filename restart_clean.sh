#!/usr/bin/env bash
# 小橘3号 · 一键干净重启（Linux/香橙派侧）。
# 流程：清杀全部 xiaoju3 python 进程 → 等 2 秒 → 确认 5003 释放 → 清理旧日志
#（保留最近 10 个）→ nohup 启动 launcher（日志带启动时间戳）。
# Windows 侧请用 restart_clean.bat；日志路径由 xiaoju3_launcher 生成
#（timestamped_log_path / prune_dashboard_logs，与 bat 共用同一实现）。
# 2026-10-02 稳定性排查方案 d：杜绝并发 pair 抢绑 5003（详见排查记录）。
set -u
cd "$(dirname "$0")"

echo "[1/4] 清杀全部小橘3号 python 进程..."
PIDS="$(pgrep -f 'xiaoju3_dashboard.py|xiaoju3_launcher.py' || true)"
if [ -n "$PIDS" ]; then
  for p in $PIDS; do
    echo "  清杀 PID $p"
    kill "$p" 2>/dev/null || true
  done
else
  echo "  未发现运行中的进程。"
fi

echo "[2/4] 等待 2 秒并确认 5003 释放..."
sleep 2
if (exec 3<>/dev/tcp/127.0.0.1/5003) 2>/dev/null; then
  echo "⚠️ 5003 仍被占用，请手动检查后重试。"
  exit 1
fi
echo "  端口已释放。"

echo "[3/4] 清理旧启动日志（保留最近 10 个）..."
REMOVED="$(python3 -c "import xiaoju3_launcher as l; kept,removed=l.prune_dashboard_logs(); print(removed)")"
echo "  已清理旧日志 ${REMOVED} 个。"

echo "[4/4] 启动小橘3号（单实例，日志带启动时间戳）..."
LOGPATH="$(python3 -c "import xiaoju3_launcher as l; print(l.timestamped_log_path())")"
PYTHONUNBUFFERED=1 nohup python3 xiaoju3_launcher.py \
  >> "$LOGPATH" 2>> "${LOGPATH%.log}.err.log" &
echo "  已启动（PID $!），日志：$LOGPATH"
echo "[OK] 干净重启完成。"
