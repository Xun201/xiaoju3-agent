#!/bin/bash
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}🔍 正在扫描即将上传的文件，检查是否包含隐私...${NC}\n"

CHANGES=$(git status --porcelain | awk '{print $2}')

if [ -z "$CHANGES" ]; then
    echo -e "${YELLOW}⚠️ 没有检测到任何改动，无需上传。${NC}"
    exit 0
fi

PRIVACY_LIST=("config.py" ".env" "identity.json" ".key" ".token" "permission.json" "stop.flag" "history" "memory")
FOUND_PRIVACY=0

for file in $CHANGES; do
    for keyword in "${PRIVACY_LIST[@]}"; do
        if [[ "$file" == *"$keyword"* ]]; then
            echo -e "${RED}❌ 警告：发现疑似隐私文件 -> $file${NC}"
            FOUND_PRIVACY=1
        fi
    done
done

if [ $FOUND_PRIVACY -eq 1 ]; then
    echo -e "\n${RED}🛑 安检不通过！请检查 .gitignore 或手动移除上述文件后再试。${NC}"
    exit 1
fi

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
        echo -e "\n${RED}❌ 上传失败，可能是网络问题。${NC}"
    fi
else
    echo -e "\n${YELLOW}🚫 已取消上传。${NC}"
fi
