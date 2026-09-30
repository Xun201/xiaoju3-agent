#!/usr/bin/env bash
# 小橘3号 · 版本备份脚本
# 用法: bash backup.sh [功能简述]   例: bash backup.sh 权限体系调整
# 只备份公开代码（.py/.sh/.md/.html/.js）；隔离区、密钥、记忆、日志、压缩包一律不进包。
# 备份失败只打印原因，不中断调用方主流程（失败时退出码 1，供需要者检测）。
set -u

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="$PROJECT_DIR/backups"
DESC="${1:-自动备份}"
# 清洗描述：去掉路径分隔符与空白等危险字符，空则回退默认
DESC="$(printf '%s' "$DESC" | tr -d '/\\:*?"<>| ')"
[ -z "$DESC" ] && DESC="自动备份"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/backup_${STAMP}_${DESC}.tar.gz"

mkdir -p "$BACKUP_DIR" 2>/dev/null || { echo "❌ 备份失败：无法创建备份目录 $BACKUP_DIR"; exit 1; }

# 生成文件清单：扩展名白名单 + 目录剪枝（隔离区/运行数据/产物/备份目录全部排除）
LIST="$(mktemp)"
trap 'rm -f "$LIST"' EXIT
find "$PROJECT_DIR" \
  \( -name backups -o -name __pycache__ -o -name logs -o -name data \
     -o -name platform-tools -o -name build-tools -o -name .git \
     -o -name xiaoju3_data -o -name node_modules -o -name .venv \
     -o -path "$PROJECT_DIR/agent_state/memory" \
     -o -path "$PROJECT_DIR/agent_state/conversations" \) -prune \
  -o -type f \( -name '*.py' -o -name '*.sh' -o -name '*.md' \
     -o -name '*.html' -o -name '*.js' \) -print \
  | sed "s|^$PROJECT_DIR/||" > "$LIST"

if [ ! -s "$LIST" ]; then
  echo "❌ 备份失败：未找到任何公开代码文件，请检查目录"
  exit 1
fi

if tar -czf "$OUT" -C "$PROJECT_DIR" -T "$LIST" 2>/dev/null; then
  TOTAL=$(ls -1 "$BACKUP_DIR"/backup_*.tar.gz 2>/dev/null | wc -l)
  echo "✅ 已备份至 backups/backup_${STAMP}_${DESC}.tar.gz（当前共 ${TOTAL} 个备份）"
else
  rm -f "$OUT"
  echo "❌ 备份失败：tar 打包出错（文件清单见 $LIST，已清理半成品 $OUT）"
  exit 1
fi

# 保留策略：只保留最近 10 个（文件名含时间戳，字典序即时间序），超出删除最旧
ls -1 "$BACKUP_DIR"/backup_*.tar.gz 2>/dev/null | sort | head -n -10 | while read -r old; do
  rm -f "$old" && echo "🧹 已清理最旧备份：$(basename "$old")"
done
exit 0
