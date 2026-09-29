# permission.py
import os
import sys
import json
import time

# 将隔离区加入系统路径，以便加载私有扩展
sys.path.append('/home/orangepi/xiaoju3_data')


class PermissionManager:
    """公开版本：仅支持 Lv.1 - Lv.3"""

    IDENTITY_PATH = "/home/orangepi/xiaoju3-agent/agent_state/identity.json"

    def __init__(self):
        self.current_level = "Lv.1"
        self.last_auth_time = 0
        self.load_identity()

    def load_identity(self):
        if os.path.exists(self.IDENTITY_PATH):
            try:
                with open(self.IDENTITY_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.current_level = data.get("current_level", "Lv.1")
            except Exception:
                pass

    def save_identity(self):
        try:
            with open(self.IDENTITY_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "current_level": self.current_level,
                    "updated_at": time.time()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 保存身份状态失败: {e}")

    def has_permission(self, action):
        permissions = {
            "Lv.1": ["chat", "web_search"],
            "Lv.2": ["chat", "web_search", "read_file", "list_files"],
            "Lv.3": ["chat", "web_search", "read_file", "list_files",
                     "write_file", "modify_code", "manage_plugins"],
        }
        allowed = permissions.get(self.current_level, [])
        return action in allowed


# 尝试加载私有扩展。加载成功后，permission_manager 会使用私有子类
try:
    from xun_private import XunPermissionManager
    permission_manager = XunPermissionManager()
    print("🔒 私有扩展已加载。")
except ImportError:
    permission_manager = PermissionManager()