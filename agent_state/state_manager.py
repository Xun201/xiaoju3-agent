# -*- coding: utf-8 -*-
"""小橘3号 · 状态外置层：SQLite 长期记忆 + 会话落盘。

按《架构设计文档》§4：long_term.db 长期记忆（memories 表）与
save_conversation 会话 JSON 落盘（只保留最近 MAX_MESSAGES 条）。
当前为脚手架，不接入对话主链路，但模块本身完整可用。
路径基于统一配置 xiaoju3.AGENT_STATE_DIR，也支持显式传参以便测试。
"""
import os
import json
import sqlite3

from xiaoju3 import AGENT_STATE_DIR, MAX_MESSAGES


class StateManager:
    """长期记忆与会话历史的持久化管理器。"""

    def __init__(self, base_dir=None):
        # 默认取统一配置；显式传参便于测试隔离
        self.base_dir = base_dir if base_dir is not None else AGENT_STATE_DIR
        self.identity_file = os.path.join(self.base_dir, "identity.json")
        self.memory_db = os.path.join(self.base_dir, "long_term.db")
        self._init_db()

    def _init_db(self):
        """初始化长期记忆数据库（SQLite）"""
        os.makedirs(self.base_dir, exist_ok=True)
        conn = sqlite3.connect(self.memory_db)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                content TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def save_memory(self, category, content):
        """保存一条长期记忆"""
        conn = sqlite3.connect(self.memory_db)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO memories (category, content) VALUES (?, ?)", (category, content))
        conn.commit()
        conn.close()
        print(f"💾 [状态外置层] 已保存记忆: {category}")

    def get_recent_memories(self, limit=5):
        """获取最近几条记忆，用于注入 Prompt"""
        conn = sqlite3.connect(self.memory_db)
        cursor = conn.cursor()
        cursor.execute("SELECT category, content FROM memories ORDER BY timestamp DESC LIMIT ?", (limit,))
        results = cursor.fetchall()
        conn.close()
        return results

    def save_conversation(self, source, messages):
        """把对话历史独立出来，避免污染代码（只保留最近 MAX_MESSAGES 条）"""
        conv_dir = os.path.join(self.base_dir, "conversations")
        os.makedirs(conv_dir, exist_ok=True)
        conv_file = os.path.join(conv_dir, f"{source}_history.json")
        with open(conv_file, "w", encoding="utf-8") as f:
            json.dump(messages[-MAX_MESSAGES:], f, ensure_ascii=False, indent=2)


# 全局单例，供其他模块直接调用
state_manager = StateManager()
