#!/bin/bash
cd /home/orangepi/xiaoju3-agent

# 校验核心文件的哈希
if ! sha256sum -c checksums.sha256 --quiet; then
    echo "⚠️ 警告：检测到核心代码被篡改！启动已拒绝！" | tee -a logs/security.log
    exit 1
fi

# 校验通过，启动小橘3号
exec /usr/bin/python3 /home/orangepi/xiaoju3-agent/main.py
