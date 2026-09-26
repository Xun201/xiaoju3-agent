# identity.py
import json
import os
import time

IDENTITY_FILE = "/home/orangepi/xiaoju3_data/identity.json"

class XiaojuIdentity:
    def __init__(self):
        # 默认状态：没有注册主人，机器人叫“小橘”
        self.is_registered = False
        self.owner_name = None
        self.bot_name = "小橘"
        self.load_identity()

    def load_identity(self):
        """读取保存在本地的身份信息"""
        if os.path.exists(IDENTITY_FILE):
            try:
                with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.is_registered = data.get("is_registered", False)
                    self.owner_name = data.get("owner_name")
                    self.bot_name = data.get("bot_name", "小橘")
            except:
                pass

    def register_owner(self, name):
        """核心：初始化仪式，让新主人注册"""
        self.owner_name = name
        self.bot_name = f"小橘·{name}号"  # 比如“小橘·老王号”
        self.is_registered = True
        self.save_identity()
        return f"注册成功！现在我是你的专属助手：{self.bot_name}。"

    def revoke_owner(self):
        """撤销主人（给最高权限用的）"""
        self.is_registered = False
        self.owner_name = None
        self.bot_name = "小橘"
        self.save_identity()
        return "已撤销当前主人身份。现在处于失忆状态。"

    def get_identity_status(self):
        """获取当前身份信息（给最高权限查看用的）"""
        if not self.is_registered:
            return "当前状态：尚未注册主人（访客模式）。"
        return f"当前状态：已注册主人[{self.owner_name}]，机器人名称[{self.bot_name}]。"

    def save_identity(self):
        """保存身份信息到本地文件"""
        with open(IDENTITY_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "is_registered": self.is_registered,
                "owner_name": self.owner_name,
                "bot_name": self.bot_name,
                "updated_at": time.time()
            }, f, ensure_ascii=False, indent=2)

# 全局单例，供其他模块调用
xiaoju_identity = XiaojuIdentity()
