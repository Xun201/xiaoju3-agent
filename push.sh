#!/bin/bash
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}🔍 正在启动终极安全安检...${NC}\n"

CHANGES=$(git status --porcelain | awk '{print $2}')
UNPUSHED=$(git log origin/main..HEAD --oneline 2>/dev/null)

if [ -z "$CHANGES" ] && [ -z "$UNPUSHED" ]; then
    echo -e "${YELLOW}⚠️ 没有检测到任何改动，且本地已是最新，无需上传。${NC}"
    exit 0
fi

if [ -z "$CHANGES" ] && [ ! -z "$UNPUSHED" ]; then
    echo -e "${YELLOW}📤 检测到本地有已提交但未推送的记录，准备直接推送...${NC}"
fi

# 1. 文件名黑名单检查（扩充了 xun_private.py 和 agent_state 隐私目录）
PRIVACY_LIST=("xiaoju3.py" "config.py" ".env" "identity.json" "core_memory.py" "permission.json" "*.key" "*.token" "*.pem" "memory" "history" "logs" "data" "agent_state/conversations" "agent_state/memory" "xun_private.py")
FOUND_PRIVACY=0

for file in $CHANGES; do
    for keyword in "${PRIVACY_LIST[@]}"; do
        if [[ "$file" == *"$keyword"* ]]; then
            echo -e "${RED}❌ 警告：发现疑似敏感文件 -> $file${NC}"
            FOUND_PRIVACY=1
        fi
    done
done

# 2. 文件内容明文 Key 扫描
echo -e "${YELLOW}🔍 正在扫描待上传文件内容，查找明文 Key...${NC}"
for file in $CHANGES; do
    if [ -f "$file" ]; then
        if grep -qE "sk-[a-zA-Z0-9]{20,}" "$file"; then
            echo -e "${RED}❌ 警告：文件 $file 中包含疑似明文 API Key！${NC}"
            FOUND_PRIVACY=1
        fi
    fi
done

# 3. Git 历史记录扫描
echo -e "${YELLOW}🔍 正在扫描 Git 历史，查找遗留 Key...${NC}"
HISTORY_LEAK=$(git log -p | grep -i "sk-" | head -n 1)
if [ ! -z "$HISTORY_LEAK" ]; then
    echo -e "${RED}❌ 警告：Git 历史记录中依然存在旧 Key，请先重建仓库清理历史！${NC}"
    FOUND_PRIVACY=1
fi

if [ $FOUND_PRIVACY -eq 1 ]; then
    echo -e "\n${RED}🛑 安检不通过！禁止上传。${NC}"
    exit 1
fi

echo -e "${GREEN}✅ 全方位安检通过！以下是即将上传的文件：${NC}\n"
git status --short

echo ""
read -p "确认要把这些改动推送到 GitHub 吗？(yes/no): " CONFIRM

if [ "$CONFIRM" == "yes" ] || [ "$CONFIRM" == "y" ]; then
    echo -e "\n${YELLOW}🚀 开始提交并推送...${NC}"
    git add .
    
    # 4. 新增：使用 secret-time-machine 深度扫描暂存区
    echo -e "${YELLOW}🔍 正在使用 secret-time-machine 进行深度扫描...${NC}"
    if command -v secret-time-machine &> /dev/null; then
        # 先提交，再扫描刚刚生成的 commit，确认干净后再 push
        git commit -m "feat: 更新代码 - $(date '+%Y-%m-%d %H:%M')" > /dev/null
        
        SECRET_SCAN=$(secret-time-machine --repo . --json 2>/dev/null)
        if echo "$SECRET_SCAN" | grep -q '"severity": "high"'; then
            echo -e "${RED}❌ 危险：提交中检测到高风险的敏感信息！${NC}"
            echo -e "${RED}${SECRET_SCAN}${NC}"
            echo -e "${RED}正在回滚此次提交...${NC}"
            git reset --soft HEAD~1
            exit 1
        else
            echo -e "${GREEN}✅ secret-time-machine 扫描通过！正在推送...${NC}"
            git push origin main
        fi
    else
        echo -e "${YELLOW}⚠️ 未安装 secret-time-machine，跳过深度扫描。${NC}"
        git commit -m "feat: 更新代码 - $(date '+%Y-%m-%d %H:%M')"
        git push origin main
    fi
    
    if [ $? -eq 0 ]; then
        echo -e "\n${GREEN}🎉 推送成功！${NC}"
    else
        echo -e "\n${RED}❌ 推送失败，请检查网络或远程仓库权限。${NC}"
    fi
else
    echo -e "\n${YELLOW}🚫 已取消推送。${NC}"
fi