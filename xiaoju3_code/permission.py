# permission.py
import os
import json
import time

class PermissionManager:
    def __init__(self):
        # 默认状态：未认证，Lv.1（访客）
        self.is_xun_verified = False
        self.current_level = "Lv.1"
        self.last_auth_time = 0
        self.load_identity()

    def get_machine_id(self):
        # 获取设备指纹
        try:
            with open('/sys/class/net/eth0/address', 'r') as f:
                return f.read().strip()
        except:
            return "unknown_machine"

    def load_identity(self):
        # 读取已有身份状态
        if os.path.exists("identity.json"):
            try:
                with open("identity.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.is_xun_verified = data.get("is_xun_verified", False)
                    self.current_level = data.get("current_level", "Lv.1")
            except:
                pass

    def verify_xun(self, user_input):
        """【暂时封死】最高权限识别机制，等待升级哈希+动态密码"""
        # 不论输入什么，直接返回 False，绝对不给 Lv.3
        return False

    def local_auth(self, auth_code):
        """【暂时封死】本地安全认证，等待升级高级防护"""
        # 暂时废弃本地认证，等待未来升级（哈希+动态密码）
        return False, "🛡️ 最高权限系统正在升级（哈希+动态密码），目前暂未开放。"

    def save_identity(self):
        # 保存状态到文件
        with open("identity.json", "w", encoding="utf-8") as f:
            json.dump({
                "is_xun_verified": self.is_xun_verified,
                "current_level": self.current_level,
                "updated_at": time.time()
            }, f, ensure_ascii=False, indent=2)

    def has_permission(self, action):
        """判断当前等级是否允许执行某个操作"""
        permissions = {
            "Lv.1": ["chat", "web_search"],
            "Lv.2": ["chat", "web_search", "read_file", "write_file"],
            "Lv.3": ["*"]
        }
        allowed = permissions.get(self.current_level, [])
        return "*" in allowed or action in allowed

# 全局单例，给其他代码调用
permission_manager = PermissionManager()
