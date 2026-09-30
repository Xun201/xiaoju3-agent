# -*- coding: utf-8 -*-
"""小橘3号 · 权限管理（Lv.1–Lv.4，第二阶段 §7 用户指令新表）。

等级表（用户 2026-09-30 指令，就权限口径覆盖旧文档表）：
- Lv.1 游客：chat / web_search（默认等级，无需认证；网页搜索维持 Lv.1）
- Lv.2 普通用户：+ read_file / list_files / control_normal_devices
  （密码注册 /register，注册密码走 env XIAOJU3_REGISTER_PASSWORD，不得硬编码；
  旧口径"LV1 可读文件"已由用户调整为 Lv.2 起可读）
- Lv.3 代码编写者：+ write_file / modify_code / manage_plugins（TOTP 动态密码
  激活 /coder_auth）；写文件/写代码属敏感操作，执行时还需**逐次动态密码**
  （lv3_operation_ok：/sudo <code> 开短 TTL 操作窗口 或 凭据携带 totp 两通道）
- Lv.4 主人级：+ control_dangerous_devices / system_manage（动态密码 TOTP +
  生物认证模拟双因子激活）；"无边界"= 包含全部低级能力；owner 标记写入
  identity.json，可 revoke 撤销（立即生效）

继承语义：等级数值 >= 能力所需等级即通过（低级功能无需重复验证）。

身份记忆：load_identity() 读取 agent_state/identity.json（current_level + owner），
save_identity() 落盘。register_user / activate_lv3 / grant_lv4 / revoke_lv4 均
经 save_identity 持久化（等级持久化接线口径，覆盖旧文档"不落盘"）；
Lv.3 操作窗口仅内存，不落盘。

Lv.4 双因子直接消费 auth_lv4 因子链（TOTPFactor + BiometricFactor，AND 语义）：
TOTP 密钥读环境变量 XIAOJU3_TOTP_SECRET（Base32，与 Lv.3 动态密码同源）；
生物认证默认未接入（明确中文降级提示），经 register_biometric_verifier 注册
模拟/硬件回调后参与认证。

【对接线方（S5 / main.py）的接口约定（准确签名）】
- register_user(user_id, password) -> str                  # /register <密码>
- activate_lv3(user_id, totp_code) -> str                  # /coder_auth <TOTP> 新语义
- coder_auth(user_id, totp_code) -> str                    # 旧名兼容包装 = activate_lv3
- verify_lv3_operation(user_id, totp_code) -> bool         # 逐次 TOTP 单次校验
- open_operation_window(user_id=None, ttl_seconds=120, totp_code=None) -> str   # /sudo 通道
- lv3_operation_ok(user_id=None, credentials=None) -> bool # 写文件统一门禁入口
- lv4_mfa_ok(user_id=None, credentials=None) -> bool       # TOTP+生物 双因子 bool 入口
- lv4_mfa_check(user_id=None, credentials=None) -> (bool, str)  # 带明细文案
- grant_lv4(user_id=None, credentials=None) -> str         # confirmed + 双因子 → owner 落盘
- revoke_lv4(user_id=None) -> str                          # 撤销，立即生效
- register_biometric_verifier(fn) -> bool                  # 生物认证模拟回调注册
credentials 约定键：{"totp": 动态密码, "biometric": 生物凭据, "confirmed": 二次确认}
"""
import os
import sys
import json
import time
import hmac

import auth_lv4
from xiaoju3 import AGENT_STATE_DIR

# Lv.2 注册密码（env 注入，不硬编码；键名已报主控补 .env.example）
REGISTER_PASSWORD_ENV = "XIAOJU3_REGISTER_PASSWORD"

# Lv.3 操作窗口默认 TTL（秒）
LV3_WINDOW_DEFAULT_TTL = 120

# 等级序数值（继承语义的比较基准）
LEVEL_ORDER = {"Lv.1": 1, "Lv.2": 2, "Lv.3": 3, "Lv.4": 4}

# 能力 → 所需最低等级（§7 用户新表）
ACTION_LEVELS = {
    "chat": 1,
    "web_search": 1,                    # 网页搜索维持 Lv.1
    "read_file": 2,                     # 用户调整点：旧表 LV1 可读 → Lv.2 起可读
    "list_files": 2,
    "control_normal_devices": 2,        # 普通家居（灯/空调/窗帘等非危险设备）
    "write_file": 3,
    "modify_code": 3,
    "manage_plugins": 3,
    "control_dangerous_devices": 4,     # 危险家居（门锁/燃气等）
    "system_manage": 4,                 # 一键装卸系统组件
}


class PermissionManager:
    """公开版本：支持 Lv.1 - Lv.4（含 Lv.3 逐次动态密码与 Lv.4 双因子/owner）。"""

    IDENTITY_PATH = os.path.join(AGENT_STATE_DIR, "identity.json")

    def __init__(self):
        self.current_level = "Lv.1"
        self.last_auth_time = 0
        self.user_id = "local"      # 单用户助手：门禁接口 user_id 的缺省值
        self.owner = None           # Lv.4 主人级标记（identity.json "owner" 字段）
        self._op_windows = {}       # {user_id: 过期时间戳}——Lv.3 操作窗口，仅内存
        self.last_lv4_message = ""  # 最近一次 lv4_mfa_check 明细（含未接入提示）
        # Lv.4 双因子链：TOTP 动态密码 + 生物认证（默认未接入，明确降级提示）
        self._lv4 = auth_lv4.LV4AuthManager(
            factors=[auth_lv4.TOTPFactor(), auth_lv4.BiometricFactor()])
        self.load_identity()

    # ==================== 身份持久化 ====================

    def load_identity(self):
        if os.path.exists(self.IDENTITY_PATH):
            try:
                with open(self.IDENTITY_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.current_level = data.get("current_level", "Lv.1")
                    self.owner = data.get("owner") or None
            except Exception:
                pass

    def save_identity(self):
        try:
            with open(self.IDENTITY_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "current_level": self.current_level,
                    "owner": self.owner,
                    "updated_at": time.time()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 保存身份状态失败: {e}")

    # ==================== 等级判定（继承语义） ====================

    def level_value(self, level=None):
        """等级序数值；未知等级按 0（无任何能力）处理。"""
        return LEVEL_ORDER.get(level or self.current_level, 0)

    def has_permission(self, action):
        """继承语义：当前等级数值 >= 能力所需最低等级即通过（低级功能无需重复验证）。"""
        required = ACTION_LEVELS.get(action)
        if required is None:
            return False
        return self.level_value() >= required

    def is_owner(self):
        return bool(self.owner)

    # ==================== Lv.2 密码注册 ====================

    def register_user(self, user_id, password):
        """Lv.2 普通用户注册（/register）：校验 env 注册密码，通过升 Lv.2 并落盘。

        未配置 XIAOJU3_REGISTER_PASSWORD 时明确降级拒绝（不得硬编码默认密码）。
        """
        expected = os.environ.get(REGISTER_PASSWORD_ENV, "").strip()
        if not expected:
            return (f"❌ 注册功能未开放：未配置环境变量 {REGISTER_PASSWORD_ENV}"
                    "（注册密码），Lv.2 注册已降级关闭。请主人先在 .env 配置注册密码。")
        supplied = str(password or "").strip()
        if not hmac.compare_digest(supplied, expected):
            return "❌ 注册密码错误，Lv.2 注册失败。请联系主人核对注册密码。"
        if self.level_value() < 2:
            self.current_level = "Lv.2"
        self.save_identity()
        return (f"✅ 用户 {user_id} 注册成功，已升级 Lv.2（普通用户）："
                "可读文件、列目录、控制普通家居设备。权限已落盘。")

    # ==================== Lv.3 TOTP 激活与逐次动态密码 ====================

    def _totp_secret(self):
        """动态密码共享密钥（Base32）：与 auth_lv4 同源（XIAOJU3_TOTP_SECRET）。"""
        return os.environ.get(auth_lv4.TOTP_SECRET_ENV, "").strip()

    def activate_lv3(self, user_id, totp_code):
        """TOTP 动态密码激活 Lv.3（/coder_auth 新语义）：校验通过升级并落盘。

        旧口径"固定认证码、仅内存升级不落盘"已由 §7 用户指令覆盖。
        TOTP 密钥未配置时明确降级拒绝，不抛异常。
        """
        secret = self._totp_secret()
        if not secret:
            return (f"❌ Lv.3 激活功能降级：未配置 {auth_lv4.TOTP_SECRET_ENV}"
                    "（Base32 动态密码密钥）。请主人先在 .env 配置密钥再激活。")
        if not auth_lv4.verify_totp(secret, str(totp_code or "")):
            return "❌ 动态密码不正确或已过期，Lv.3 激活失败。"
        if self.level_value() < 3:
            self.current_level = "Lv.3"
        self.save_identity()
        return (f"✅ 用户 {user_id} 已激活代码编写者权限（Lv.3），权限已落盘。"
                "注意：写文件/写代码属敏感操作，执行时还需逐次动态密码"
                f"（/sudo <动态密码> 开启 {LV3_WINDOW_DEFAULT_TTL} 秒操作窗口，"
                "或工具凭据携带 totp）。")

    def coder_auth(self, user_id, totp_code):
        """旧指令名 /coder_auth 的兼容包装：新语义 = activate_lv3（TOTP 激活+落盘）。

        旧语义（固定认证码、仅内存升级）已废弃，见第二阶段 §7 用户指令。
        """
        return self.activate_lv3(user_id, totp_code)

    def verify_lv3_operation(self, user_id, totp_code):
        """Lv.3 逐次动态密码单次校验（不开启窗口、不落盘、无副作用）。"""
        secret = self._totp_secret()
        if not secret:
            return False
        return auth_lv4.verify_totp(secret, str(totp_code or ""))

    def open_operation_window(self, user_id=None, ttl_seconds=LV3_WINDOW_DEFAULT_TTL,
                              totp_code=None):
        """/sudo 通道：开启短 TTL 写操作窗口（默认 120 秒，仅内存不落盘）。

        totp_code 提供时先校验（失败不开窗，返回 ❌ 文案）；返回中文消息，
        ✅ 开头表示窗口已开启。
        """
        if totp_code is not None and not self.verify_lv3_operation(user_id, totp_code):
            return "❌ 动态密码不正确或已过期，写操作窗口未开启。请用 /sudo <动态密码> 重试。"
        try:
            ttl = max(1, int(ttl_seconds))
        except (TypeError, ValueError):
            ttl = LV3_WINDOW_DEFAULT_TTL
        self._op_windows[user_id or self.user_id] = time.time() + ttl
        return f"✅ 写操作窗口已开启，{ttl} 秒内写文件/写代码无需再次输入动态密码。"

    def operation_window_active(self, user_id=None):
        """写操作窗口是否仍有效（仅内存状态）。"""
        expires = self._op_windows.get(user_id or self.user_id, 0)
        return time.time() < expires

    def close_operation_window(self, user_id=None):
        """手动关闭写操作窗口（撤销途径）。"""
        self._op_windows.pop(user_id or self.user_id, None)

    def lv3_operation_ok(self, user_id=None, credentials=None):
        """Lv.3 敏感操作统一门禁入口：凭据携带有效 totp 或操作窗口有效均通过。

        等级门槛（Lv.3）由调用方（tools.py 门禁）另行校验，本方法只判操作凭据。
        """
        credentials = credentials or {}
        code = credentials.get("totp") or credentials.get("code")
        if code and self.verify_lv3_operation(user_id, code):
            return True
        return self.operation_window_active(user_id)

    # ==================== Lv.4 双因子（经 auth_lv4 因子链） ====================

    def lv4_mfa_check(self, user_id=None, credentials=None):
        """Lv.4 双因子认证：TOTP 动态密码 + 生物认证全部通过（因子链 AND 语义）。

        返回 (ok, 明细文案)；生物认证器未注册时明细含"生物认证器未接入"
        明确中文提示。明细同步存入 self.last_lv4_message。
        credentials 键：{"totp": 动态密码, "biometric": 生物凭据}。
        """
        ok, detail = self._lv4.authenticate(user_id or self.user_id, credentials or {})
        self.last_lv4_message = detail
        return ok, detail

    def lv4_mfa_ok(self, user_id=None, credentials=None):
        """Lv.4 双因子门禁 bool 入口（危险家居/系统装卸的工具层门禁用）。"""
        ok, _ = self.lv4_mfa_check(user_id, credentials)
        return ok

    def register_biometric_verifier(self, verifier):
        """注册生物认证模拟/硬件回调 fn(credential) -> bool（扩展挂载点）。

        测试注入 mock verifier 也走这里；注册成功返回 True。
        """
        for factor in self._lv4.factors:
            if isinstance(factor, auth_lv4.BiometricFactor):
                factor.register_verifier(verifier)
                return True
        return False

    def grant_lv4(self, user_id=None, credentials=None):
        """授予 Lv.4 主人级：①类 Root 警告二次确认（credentials["confirmed"]=True）
        ②TOTP+生物双因子通过。成功置 current_level=Lv.4、owner=user_id 并落盘。
        """
        user_id = user_id or self.user_id
        credentials = credentials or {}
        if not credentials.get("confirmed"):
            return ("❌ 授权失败：请先阅读类 Root 警告（auth_lv4.root_warning()）"
                    "并二次确认（凭据 confirmed=True）后再申请 Lv.4 主人级权限。")
        ok, detail = self.lv4_mfa_check(user_id, credentials)
        if not ok:
            return f"❌ 授权失败，Lv.4 双因子认证未通过：\n{detail}"
        self._lv4.acknowledge_risk(user_id)
        msg = self._lv4.grant_lv4(user_id)
        if not msg.startswith("✅"):
            return msg
        self.current_level = "Lv.4"
        self.owner = user_id
        self.save_identity()
        return (f"✅ 用户 {user_id} 已授予 Lv.4（主人级）权限，owner 标记已写入"
                f" identity.json。撤销途径：revoke_lv4('{user_id}') 立即生效。")

    def revoke_lv4(self, user_id=None):
        """撤销 Lv.4（文档承诺的撤销途径），立即生效：等级回落 Lv.3、owner 清除并落盘。"""
        user_id = user_id or self.user_id
        chain_msg = self._lv4.revoke_lv4(user_id)  # 因子链名单同步清除（无持有则无副作用）
        if self.level_value() >= 4 or self.owner == user_id:
            if self.level_value() >= 4:
                self.current_level = "Lv.3"
            self.owner = None
            self.save_identity()
            return f"✅ 用户 {user_id} 的 Lv.4（主人级）权限已撤销，立即生效。"
        return chain_msg


# 将隔离区（本地私有目录）加入系统路径，以便加载私有扩展；
# 路径可经环境变量覆盖，默认指向本项目的 agent_state/ 隔离区。
_PRIVATE_DIR = os.environ.get("XIAOJU3_PRIVATE_DIR", AGENT_STATE_DIR)
if _PRIVATE_DIR and _PRIVATE_DIR not in sys.path:
    sys.path.append(_PRIVATE_DIR)

# 尝试加载私有扩展。加载成功后，permission_manager 会使用私有子类
try:
    from xun_private import XunPermissionManager
    permission_manager = XunPermissionManager()
    print("🔒 私有扩展已加载。")
except ImportError:
    permission_manager = PermissionManager()
