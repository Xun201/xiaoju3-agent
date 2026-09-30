#!/usr/bin/env bash
# 小橘3号 · 生成完整性清单（架构设计文档 §8/§9「启动完整性」）
# 产物：manifest.txt（核心文件清单）+ checksums.sha256（sha256sum 清单）
# 用法：./make_manifest.sh [项目目录]    # 默认为脚本所在目录
# 集成阶段一键重算：任何核心文件变更后重新运行本脚本即可；
# secure_start.sh 校验失败 / xiaoju3_refresh.py 重算前，也以本脚本产物为准。
cd "$(dirname "$0")" || exit 1
TARGET="${1:-$(pwd)}"
cd "$TARGET" || exit 1

# 核心文件清单（并行开发期间允许暂缺：缺失的文件会提示并跳过，集成阶段补齐后重跑即可）
CORE_FILES=(
    xiaoju3.py
    main.py
    brain.py
    prompts.py
    tools.py
    permission.py
    home_tools.py
    heartbeat.py
    adb_tools.py
    android_ui_tools.py
    vision_tools.py
    xiaoju3_dashboard.py
    agent_state/state_manager.py
)

# 1. 生成 manifest.txt（只收录实际存在的核心文件）
: > manifest.txt
for f in "${CORE_FILES[@]}"; do
    if [ -f "$f" ]; then
        echo "$f" >> manifest.txt
    else
        echo "⚠️ 核心文件暂缺（并行开发中可忽略，集成阶段重跑即可）: $f"
    fi
done

# 2. 生成 checksums.sha256（供 secure_start.sh 校验 / xiaoju3_refresh.py 重算使用）
if [ -s manifest.txt ]; then
    sha256sum $(cat manifest.txt) > checksums.sha256
    echo "✅ 已生成 manifest.txt 与 checksums.sha256（共 $(wc -l < manifest.txt) 个核心文件）"
else
    echo "❌ 没有任何核心文件存在，清单未生成。"
    exit 1
fi
