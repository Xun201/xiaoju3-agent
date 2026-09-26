# permission.py
import os
import json
import time
import hashlib
import pyotp
import datetime

class PermissionManager:
    def __init__(self):
        self.is_xun_verified = False
        self.current_level = "Lv.1"
        
        # === 🛡️ 读取本机硬件指纹 ===
        try:
            with open('/sys/class/net/eth0/address', 'r') as f:
                self.machine_mac = f.read().strip()
        except:
            self.machine_mac = "unknown_machine"
        # ========================
        
        self.load_identity()
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

    def verify_xun(self, user_input, source="未知通道"):
        """最高权限验证（TOTP动态密码【支持6位】 + 硬件指纹 + 日志留痕）"""

        # ⚠️ 填入你手机里生成的根密钥
        TOTP_SECRET = "FP25UNBX3TWFXL3KO2UJ4RGUAF2MMYSX" 
        
        # 清理输入：去掉所有空格，只留数字（兼容 6058 0500 这种输入）
        clean_input = user_input.strip().replace(" ", "")
        
        # === 🛡️ 审计日志留痕 ===
        log_dir = "/home/orangepi/xiaoju3_data/logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "permission_audit.log")
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{now}] 来源: {source} | 尝试动态密码: {clean_input} | 机器MAC: {self.machine_mac} | "

        # 验证动态密码（指定 digits=8，以适配微软账号）
        if pyotp.TOTP(TOTP_SECRET, digits=6).verify(clean_input):
            if self.machine_mac == "unknown_machine" or not self.machine_mac:
                log_entry += "结果: 拒绝（未知设备）\n"
                with open(log_file, "a", encoding="utf-8") as f: f.write(log_entry)
                return False, "❌ 未知设备，无权激活最高权限。"
            
            self.is_xun_verified = True
            self.current_level = "Lv.4"
            self.save_identity()
            
            log_entry += "结果: ✅ 成功激活 Lv.4\n"
            with open(log_file, "a", encoding="utf-8") as f: f.write(log_entry)
            return True, "✅ XUN 最高权限（Lv.4）已激活！"
        
        log_entry += "结果: ❌ 认证失败（动态密码错误或过期）\n"
        with open(log_file, "a", encoding="utf-8") as f: f.write(log_entry)
        return False, "❌ 认证失败，动态密码错误或已过期。"
        
    def local_auth(self, auth_code):
        """【本地安全认证】仅限在香橙派本地终端调用"""
        return self.verify_xun(auth_code, source="本地终端")

    def save_identity(self):
        # 保存状态到文件
        with open("identity.json", "w", encoding="utf-8") as f:
            json.dump({
                "is_xun_verified": self.is_xun_verified,
                "current_level": self.current_level,
                "updated_at": time.time()
            }, f, ensure_ascii=False, indent=2)

    def has_permission(self, action):
        """判断当前等级是否允许执行某个操作（四层权限）"""
        permissions = {
            # Lv.1 游客：只能聊天和搜网页
            "Lv.1": ["chat", "web_search"],
            # Lv.2 普通用户：可以读沙箱内的文件
            "Lv.2": ["chat", "web_search", "read_file", "list_files"],
            # Lv.3 代码编写者：可以读写代码、管理插件
            "Lv.3": ["chat", "web_search", "read_file", "list_files", "write_file", "modify_code", "manage_plugins"],
            # Lv.4 最高权限（XUN）：全部放行
            "Lv.4": ["*"]
        }
        allowed = permissions.get(self.current_level, [])
        return "*" in allowed or action in allowed

# 全局单例，给其他代码调用
permission_manager = PermissionManager()
