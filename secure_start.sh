#!/usr/bin/env bash
# 小橘3号 · 完整性校验启动（架构设计文档 §8 / §9「启动完整性」）
# 职责：启动前 sha256sum -c 校验核心文件，发现篡改拒绝启动。
# 说明：checksums.sha256 由 make_manifest.sh 生成。
#       首次部署或核心文件变更后，请先运行以下命令重算清单，再启动：
#           ./make_manifest.sh
cd "$(dirname "$0")" || exit 1

# 缺少清单时拒绝启动（防止"无校验裸奔"）
if [ ! -f "checksums.sha256" ]; then
    echo "⚠️ 缺少 checksums.sha256 完整性清单，请先运行 ./make_manifest.sh 生成后再启动。"
    exit 1
fi

# 校验核心文件的哈希
if ! sha256sum -c checksums.sha256 --quiet; then
    mkdir -p logs
    echo "⚠️ 警告：检测到核心代码被篡改！启动已拒绝！$(date '+%Y-%m-%d %H:%M:%S')" | tee -a logs/security.log
    exit 1
fi

# 校验通过，启动小橘3号
exec python3 main.py
