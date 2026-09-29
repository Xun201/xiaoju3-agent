import os
import json
import sqlite3
from datetime import datetime

class StateManager:
    def __init__(self, base_dir="/home/orangepi/xiaoju3-agent/agent_state"):
        self.base_dir = base_dir
        self.identity_file = os.path.join(base_dir, "identity.json")
        self.memory_db = os.path.join(base_dir, "memory", "long_term.db")
        self._init_db()

    def _init_db(self):
        """初始化长期记忆数据库（SQLite）"""
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
        """把对话历史独立出来，避免污染代码"""
        conv_file = os.path.join(self.base_dir, "conversations", f"{source}_history.json")
        with open(conv_file, "w", encoding="utf-8") as f:
            json.dump(messages[-50:], f, ensure_ascii=False, indent=2)

# 全局单例，供其他模块直接调用
state_manager = StateManager()