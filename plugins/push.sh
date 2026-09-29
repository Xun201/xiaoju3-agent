#!/bin/bash
# push.sh - 一键安检并上传

# 颜色定义，方便看
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}🔍 正在扫描即将上传的文件，检查是否包含隐私...${NC}\n"

# === 1. 列出所有即将提交的文件 ===
# 这里用 git status --porcelain 获取所有被修改/新增的文件列表
CHANGES=$(git status --porcelain | awk '{print $2}')

# 如果没有任何修改
if [ -z "$CHANGES" ]; then
    echo -e "${YELLOW}⚠️ 没有检测到任何改动，无需上传。${NC}"
    exit 0
fi

# === 2. 定义隐私关键词（黑名单） ===
# 只要包含这些关键字的文件，都会被拦截
PRIVACY_LIST=("config.py" ".env" "identity.json" ".key" ".token" "permission.json" "stop.flag" "history" "memory")

# 用于记录是否发现隐私
FOUND_PRIVACY=0

for file in $CHANGES; do
    for keyword in "${PRIVACY_LIST[@]}"; do
        if [[ "$file" == *"$keyword"* ]]; then
            echo -e "${RED}❌ 警告：发现疑似隐私文件 -> $file${NC}"
            FOUND_PRIVACY=1
        fi
    done
done

# === 3. 如果有隐私，直接拦截，不给上传机会 ===
if [ $FOUND_PRIVACY -eq 1 ]; then
    echo -e "\n${RED}🛑 安检不通过！请检查 .gitignore 或手动移除上述文件后再试。${NC}"
    exit 1
fi

# === 4. 安检通过，列出所有改动，让用户确认 ===
echo -e "${GREEN}✅ 安检通过！以下是将要上传的文件：${NC}\n"
git status --short

echo ""
read -p "确认要把这些改动上传到 GitHub 吗？(yes/no): " CONFIRM

if [ "$CONFIRM" == "yes" ] || [ "$CONFIRM" == "y" ]; then
    echo -e "\n${YELLOW}🚀 开始提交并上传...${NC}"
    git add .
    git commit -m "feat: 自动上传 - $(date '+%Y-%m-%d %H:%M')"
    git push origin main
    
    if [ $? -eq 0 ]; then
        echo -e "\n${GREEN}🎉 上传成功！${NC}"
    else
        echo -e "\n${RED}❌ 上传失败，可能是网络问题。请稍后手动执行 git push origin main${NC}"
    fi
else
    echo -e "\n${YELLOW}🚫 已取消上传。${NC}"
fi