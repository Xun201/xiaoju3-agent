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
import time

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

    # ==================== 用户位置（搜索指代消解，2026-10-02） ====================
    # 隐私口径：位置只存本文件（agent_state/user_location.json，已 gitignore），
    # 不上传 GitHub、不写 .env、不传给云端（仅天气/本地搜索时用于拼 query）。

    @property
    def user_location_file(self):
        """用户位置记录文件路径（base_dir 下 user_location.json）。"""
        return os.path.join(self.base_dir, "user_location.json")

    def save_user_location(self, city, district=None):
        """记录用户默认位置（全量覆盖写；district 可空——主人只说了城市）。

        文件结构：{"city": "长沙", "district": "天心区", "updated_at": 时间戳}。
        """
        data = {"city": str(city or "").strip(),
                "district": str(district or "").strip(),
                "updated_at": time.time()}
        with open(self.user_location_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        shown = data["city"] + (f" {data['district']}" if data["district"] else "")
        print(f"📍 [状态外置层] 已记录用户位置: {shown}（仅本地，不入库）")
        return data

    def get_user_location(self):
        """读取用户位置 {"city", "district"}；未记录 / 文件损坏 / 城市为空
        返回 None（调用方据此走"主动询问"分支）。"""
        try:
            with open(self.user_location_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
        if not isinstance(data, dict) or not str(data.get("city", "")).strip():
            return None
        return {"city": str(data.get("city", "")).strip(),
                "district": str(data.get("district", "")).strip()}

    def clear_user_location(self):
        """清除用户位置记录（删除文件；本就不存在时静默）。"""
        try:
            os.remove(self.user_location_file)
        except OSError:
            pass


# 全局单例，供其他模块直接调用
state_manager = StateManager()


# ==================== 用户位置模块级便捷封装（2026-10-02） ====================
# brain / main 指令族直接调用；测试可用 tmp base_dir 构造独立 StateManager 验证。

def save_user_location(city, district=None):
    """记录用户默认位置（单例便捷封装，见 StateManager.save_user_location）。"""
    return state_manager.save_user_location(city, district)


def get_user_location():
    """读取用户位置（单例便捷封装；无记录返回 None）。"""
    return state_manager.get_user_location()


def clear_user_location():
    """清除用户位置记录（单例便捷封装）。"""
    return state_manager.clear_user_location()
