# -*- coding: utf-8 -*-
"""小橘3号 · 灵魂核清单（#319 灵魂架构落地，单一事实源）。

设计稿 _dev/design_319_soul_landing_v2.md §1.1/§2.2：灵魂核=跨设备语义
数据（跟人走）；载体=端点/密钥/日志/缓存（跟设备走）。三档判定判据
一句话：**换一台设备后，缺了它"它就不是它"的=核；缺了只是"冷启动
重来"的=载体；体验连续性可权衡的=扩展。**

三档清单：
- SOUL_CORE（核，必迁）：long_term.db（记忆库）/ relationship.db（关系
  库，含称呼 KV+rel_mode）/ identity.json（身份等级）/ ui_pref.json /
  user_location.json / persona_pref.json（人格开关，按需生成）；
- SOUL_EXTENSION（扩展，可选迁，开关控制）：mood.db / todos.db /
  context_summary.json / account_book.json / emoji_links.json /
  stickers_meta.json + history_*.json + conversations/；
- NOT_SOUL（不迁，载体/派生）：.env、trace.db、proactive.db、
  recent_actions.json、日志、就地备份残迹等——显式列出供审计。

判定语义：**default deny**——不在核/扩展清单里的一切（含 NOT_SOUL 与
未登记新文件）is_soul_path 一律返回 None，migration 不打包。未来新增
数据文件时在这里登记档位，migration/personality/同步器自动跟随，消灭
清单散落。

SQLite 侧车文件（-wal/-shm/-journal）跟随主库档位：X.db 是核 →
X.db-wal 也是核（整组拷贝才能保 SQLite 恢复语义）。

import 本模块零副作用（纯常量+纯函数，不读 env 不碰盘）。
"""
import fnmatch
import os
import socket

# ==================== 三档清单（单一事实源） ====================

# 核（必迁）：没有它=不是"同一个它"
SOUL_CORE = (
    "long_term.db",        # 长期记忆库（V2 11 列+四表）
    "relationship.db",     # 关系库（users/relationship/rel_event_log/rel_mode+称呼 KV）
    "identity.json",       # 身份等级（current_level/owner/display_name）
    "ui_pref.json",        # 控制台偏好（exit/dev_unlocked/dev_mode_on）
    "user_location.json",  # 主人位置事实
    "persona_pref.json",   # 人格开关（#271 批 3，按需生成）
    "soul.db",             # 灵魂审计（#319 批 2：writeback_log+conflicts，跟人走）
)

# 扩展（可选迁，include_extensions 开关控制）：体验连续性，体积/隐私可权衡
SOUL_EXTENSION = (
    "mood.db",               # 情绪状态（PAD 记账）
    "todos.db",              # 待办库
    "context_summary.json",  # 前情提要缓存
    "account_book.json",     # 记账（跟人）
    "emoji_links.json",      # 表情链接
    "stickers_meta.json",    # 贴纸元数据
)

# 扩展档通配/目录模式（fnmatchcase；conversations/* 的 * 可跨 /）
SOUL_EXTENSION_PATTERNS = (
    "history_*.json",    # 双通道会话记忆
    "conversations",     # 会话归档目录
    "conversations/*",   # 归档目录下一切
)

# 不迁（载体/派生）：可重建或设备私有——显式列出供审计；
# is_soul_path 对它们（及一切未登记路径）返回 None（default deny）。
NOT_SOUL = (
    ".env",                  # 端点/密钥（永不进包，MANIFEST 只列键名）
    "trace.db",              # #282 行车记录仪（派生可重建）
    "proactive.db",          # #271③ 主动性观测（派生可重建）
    "recent_actions.json",   # 近期动作缓存（派生可重建）
    ".todo_sync_watermark",  # 已退役同步线残迹
    "soul_outbox.json",      # 回写投递队列（#319 批 2：设备私有投递态）
    ".soul_daily_watermark", # 每日全量回写按天去重戳（设备私有）
)
NOT_SOUL_PATTERNS = (
    "napcat_fire_*.log",  # NapCat 发送审计日志（设备私有）
    "*.bak-*",            # 就地备份残迹（identity.json.bak-* 族）
)

# 档位常量（is_soul_path 返回值）
TIER_CORE = "core"
TIER_EXT = "ext"

# SQLite 侧车后缀（跟随主库档位）
_DB_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


def device_id():
    """设备标识：hostname 派生（health_bp 的 device 字段同源）。"""
    return socket.gethostname()


def is_soul_path(rel_path):
    """相对 agent_state 的路径 → "core"/"ext"/None（None=不迁）。

    - 正反斜杠统一按 posix 判定；"./" 前缀剥除；空/目录路径 → None；
    - SQLite 侧车（X.db-wal/-shm/-journal）跟随主库档位；
    - 未登记路径一律 None（default deny，NOT_SOUL 在列亦然）。
    """
    rel = str(rel_path).replace("\\", "/").strip()
    while rel.startswith("./"):
        rel = rel[2:]
    if not rel or rel.endswith("/"):
        return None
    for suf in _DB_SIDECAR_SUFFIXES:
        if rel.endswith(suf):
            return is_soul_path(rel[: -len(suf)])
    if rel in SOUL_CORE:
        return TIER_CORE
    if rel in SOUL_EXTENSION:
        return TIER_EXT
    for pat in SOUL_EXTENSION_PATTERNS:
        if rel == pat or fnmatch.fnmatchcase(rel, pat):
            return TIER_EXT
    return None


def soul_targets(agent_state_dir, include_extensions=True):
    """扫 agent_state_dir → 灵魂文件相对路径列表（posix 风格、排序）。

    - 分类走 is_soul_path（单一事实源），未登记文件一律不迁；
    - include_extensions=False 只迁核档（轻量包，回写通道用）；
    - 目录不存在/为空返回空列表。
    """
    targets = []
    if not os.path.isdir(agent_state_dir):
        return targets
    for root, _dirs, files in os.walk(agent_state_dir):
        for fn in sorted(files):
            rel = os.path.relpath(os.path.join(root, fn), agent_state_dir)
            rel = rel.replace(os.sep, "/")
            tier = is_soul_path(rel)
            if tier == TIER_CORE or (include_extensions and tier == TIER_EXT):
                targets.append(rel)
    return sorted(targets)
