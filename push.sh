#!/usr/bin/env bash
# 小橘3号 · 上传隐私门禁（架构设计文档 §9：四道扫描，命中即拦截并回滚，人工确认后才推送）
#   [1/4] 文件名黑名单：配置/密钥/身份/记忆/历史/.env 等敏感文件
#   [2/4] 明文 Key 内容扫描：正则匹配常见 API Key 形态
#   [3/4] Git 历史遗留 Key 扫描（存在提交历史才扫）
#   [4/4] secret-time-machine 深度扫描（工具存在才执行，可选）
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

cd "$(dirname "$0")" || exit 1

echo -e "${YELLOW}🔍 正在启动终极安全安检（四道扫描）...${NC}\n"

# 隐私门禁依赖 git 状态，非 git 仓库直接拒绝
if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo -e "${RED}❌ 当前目录不是 git 仓库，安检无法进行。${NC}"
    exit 1
fi

CHANGES=$(git status --porcelain | awk '{print $2}')
UNPUSHED=$(git log origin/main..HEAD --oneline 2>/dev/null)

if [ -z "$CHANGES" ] && [ -z "$UNPUSHED" ]; then
    echo -e "${YELLOW}⚠️ 没有检测到任何改动，且本地已是最新，无需上传。${NC}"
    exit 0
fi

FOUND_PRIVACY=0

# ===== [1/4] 文件名黑名单扫描（配置/密钥/身份/记忆/历史/.env 等） =====
echo -e "${YELLOW}🔎 [1/4] 文件名黑名单扫描...${NC}"
# 关键词按"子串匹配"生效：identity.json/记忆/历史/密钥/日志/工作区/隔离区私有文件
PRIVACY_LIST=("config.py" ".env" "identity.json" ".key" ".token" ".pem" "secret" "password" "memory" "history" "long_term.db" "logs" ".log" "agent_state/conversations" "agent_state/memory" "workspace/" "private")
for file in $CHANGES; do
    # .env.example 是键名模板（不含真实值），允许上传
    [ "$file" = ".env.example" ] && continue
    for keyword in "${PRIVACY_LIST[@]}"; do
        if [[ "$file" == *"$keyword"* ]]; then
            echo -e "${RED}❌ 警告：发现疑似敏感文件 -> $file${NC}"
            FOUND_PRIVACY=1
        fi
    done
done

# ===== [2/4] 明文 Key 内容扫描 =====
echo -e "${YELLOW}🔎 [2/4] 扫描待上传文件内容，查找明文 Key...${NC}"
# 常见 Key 形态：DeepSeek/OpenAI(sk-)、GitHub(ghp_/github_pat_)、AWS(AKIA)、Google(AIza)、Slack(xox)
KEY_PATTERNS=(
    "sk-[a-zA-Z0-9]{20,}"
    "ghp_[a-zA-Z0-9]{30,}"
    "github_pat_[a-zA-Z0-9_]{30,}"
    "AKIA[0-9A-Z]{16}"
    "AIza[0-9A-Za-z_-]{35}"
    "xox[baprs]-[a-zA-Z0-9-]{10,}"
)
for file in $CHANGES; do
    if [ -f "$file" ]; then
        for pattern in "${KEY_PATTERNS[@]}"; do
            if grep -qE "$pattern" "$file" 2>/dev/null; then
                echo -e "${RED}❌ 警告：文件 $file 中包含疑似明文 API Key！${NC}"
                FOUND_PRIVACY=1
            fi
        done
    fi
done

# ===== [3/4] Git 历史遗留 Key 扫描（存在提交历史才扫） =====
echo -e "${YELLOW}🔎 [3/4] 正在扫描 Git 历史，查找遗留 Key...${NC}"
if git log -1 >/dev/null 2>&1; then
    # 排除 push.sh 自身（内含 Key 正则字面量，会造成误报）
    HISTORY_LEAK=$(git log -p -- . ':!push.sh' 2>/dev/null | grep -iE "sk-[a-zA-Z0-9]{20,}" | head -n 1)
    if [ -n "$HISTORY_LEAK" ]; then
        echo -e "${RED}❌ 警告：Git 历史记录中依然存在旧 Key，请先重建仓库清理历史！${NC}"
        FOUND_PRIVACY=1
    fi
else
    echo -e "${YELLOW}ℹ️ 尚无提交历史，跳过历史扫描。${NC}"
fi

# 命中即拦截：回滚暂存区，提示人工确认
if [ "$FOUND_PRIVACY" -eq 1 ]; then
    echo -e "\n${RED}🛑 安检不通过！禁止上传。请人工确认敏感信息处理完毕后重试。${NC}"
    git reset -q 2>/dev/null
    exit 1
fi

echo -e "${GREEN}✅ 前三道安检通过！以下是即将上传的文件：${NC}\n"
git status --short

echo ""
read -p "确认要把这些改动推送到 GitHub 吗？(yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ] && [ "$CONFIRM" != "y" ]; then
    echo -e "\n${YELLOW}🚫 已取消推送。${NC}"
    exit 0
fi

echo -e "\n${YELLOW}🚀 开始提交并推送...${NC}"
git add .

# ===== [4/4] secret-time-machine 深度扫描（工具存在才执行，可选） =====
echo -e "${YELLOW}🔎 [4/4] 正在使用 secret-time-machine 进行深度扫描...${NC}"
if command -v secret-time-machine >/dev/null 2>&1; then
    # 先提交，再扫描刚刚生成的 commit，确认干净后再 push
    git commit -m "feat: 更新代码 - $(date '+%Y-%m-%d %H:%M')" > /dev/null

    SECRET_SCAN=$(secret-time-machine --repo . --json 2>/dev/null)
    if echo "$SECRET_SCAN" | grep -q '"severity": "high"'; then
        echo -e "${RED}❌ 危险：提交中检测到高风险的敏感信息！${NC}"
        echo -e "${RED}${SECRET_SCAN}${NC}"
        echo -e "${RED}正在回滚此次提交与暂存变更，请人工确认后处理...${NC}"
        git reset -q --soft HEAD~1
        git reset -q
        exit 1
    fi
    echo -e "${GREEN}✅ secret-time-machine 扫描通过！正在推送...${NC}"
else
    echo -e "${YELLOW}⚠️ 未安装 secret-time-machine，跳过深度扫描。${NC}"
    git commit -m "feat: 更新代码 - $(date '+%Y-%m-%d %H:%M')"
fi

git push origin main
if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}🎉 推送成功！${NC}"
else
    echo -e "\n${RED}❌ 推送失败，请检查网络或远程仓库权限。${NC}"
fi
