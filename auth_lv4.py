# -*- coding: utf-8 -*-
"""小橘3号 · LV4 多因素认证。

按《架构设计文档》§6 LV4 行（动态密码 + 生物认证等多因素，解放全部权限，
高危操作仍保留二次确认）、功能文档 §10.2 / §11（LV4 类 Root 警告）、
开发日志第一章"只认 XUN"（只有我能到最高级）。

组成：
1. TOTP 动态密码（RFC 6238，纯 stdlib：hmac + hashlib + base64 + struct）：
   30 秒步长、6 位数字、允许 ±1 窗口（容忍时钟偏差）。密钥从环境变量
   XIAOJU3_TOTP_SECRET（Base32）读取；未配置时功能明确降级——校验不通过
   并给出中文提示，不抛异常、不让 import 崩溃。
   provisioning_uri(account) 生成 otpauth:// URI，便于接入验证器 App
   （Google Authenticator / Microsoft Authenticator 等）。
2. 可插拔因子链：Factor 协议 + TOTPFactor 内置实现 + BiometricFactor
   扩展挂载点。生物识别在本机无硬件，设计为可注册的自定义验证器接口
   （如 Windows Hello / 外设指纹仪的回调），默认未注册时明确提示
   "生物认证器未接入"。认证通过条件 = 全部已注册因子依次通过（多因素
   AND 语义）；未注册任何因子一律拒绝。
3. 类 Root 警告（用户界面设计文档 §8.3 口径：列明敏感操作清单与后果
   说明、二次确认、撤销途径）：root_warning() 返回/打印红字风格警告文案；
   grant_lv4(user_id) 需先 acknowledge_risk(user_id) 二次确认且多因素
   认证通过；revoke_lv4(user_id) 撤销途径，立即生效。

【接口约定（接线方 S5 / main.py 阅读）】
- 本模块状态为内存 + 可选 JSON 快照（save_snapshot / load_snapshot），
  不直接改写 permission.py。等级落盘走 permission.PermissionManager
  .save_identity() 语义（agent_state/identity.json），接线约定：
    grant_lv4 返回成功后，接线方执行：
        permission_manager.current_level = "Lv.4"   # 或按私有扩展等级表
        permission_manager.save_identity()
    revoke_lv4 返回成功后同理回落 "Lv.3" 并 save_identity()。
  注意：公开版 PermissionManager 权限表仅含 Lv.1–Lv.3，LV4 能力表由
  接线方/私有扩展补齐（架构 §6：LV4 解放全部权限）。
- 开锁/燃气等高危家居实体的二次确认令牌交互流，由接线方在 main.py
  实现，分类函数见 home_tools.is_dangerous_entity（架构 §10 #8）。

import 本模块零副作用：默认因子链仅含 TOTPFactor，TOTP 密钥在 verify
时才读取环境变量，import 期不做网络 / 磁盘 / 环境写入。
"""
import base64
import hashlib
import hmac
import json
import os
import struct
import time
import urllib.parse

from xiaoju3 import AGENT_STATE_DIR

# ==================== 配置（本模块自读 env；键名已报主控补 .env.example） ====================

# TOTP 共享密钥（Base32，与验证器 App 一致）
TOTP_SECRET_ENV = "XIAOJU3_TOTP_SECRET"

# RFC 6238 参数（验证器 App 兼容口径）
TOTP_STEP = 30      # 步长（秒）
TOTP_DIGITS = 6     # 位数
TOTP_WINDOW = 1     # 允许 ±1 窗口

# 可选 JSON 快照默认路径（save_snapshot / load_snapshot 不传 path 时使用）
DEFAULT_SNAPSHOT_PATH = os.path.join(AGENT_STATE_DIR, "lv4_snapshot.json")


# ==================== TOTP 动态密码（RFC 6238，纯 stdlib） ====================

def _normalize_secret(secret):
    """Base32 密钥规整：去空格、大写、补齐 padding（验证器导出串常见缺省）。"""
    secret = str(secret).strip().replace(" ", "").upper()
    pad = (8 - len(secret) % 8) % 8
    return secret + "=" * pad


def generate_totp(secret_b32, timestamp=None, step=TOTP_STEP, digits=TOTP_DIGITS):
    """按 RFC 4226/6238 生成动态密码。timestamp 缺省取当前时间（unix 秒）。"""
    if timestamp is None:
        timestamp = time.time()
    key = base64.b32decode(_normalize_secret(secret_b32), casefold=True)
    counter = int(timestamp // step)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def verify_totp(secret_b32, code, timestamp=None, window=TOTP_WINDOW,
                step=TOTP_STEP, digits=TOTP_DIGITS):
    """校验动态密码：允许 ±window 个步长内的时钟偏差（默认 ±1 窗口）。

    密钥非法 / 码不匹配一律返回 False（不抛异常——功能降级口径，
    保证未配置密钥时 LV4 流程拿到明确失败而非崩溃）。
    """
    if code is None:
        return False
    code = str(code).strip()
    if not code:
        return False
    if timestamp is None:
        timestamp = time.time()
    try:
        for offset in range(-window, window + 1):
            candidate = generate_totp(secret_b32, timestamp + offset * step,
                                      step=step, digits=digits)
            if hmac.compare_digest(candidate, code):
                return True
    except Exception:
        return False
    return False


def totp_configured():
    """TOTP 功能是否可用（XIAOJU3_TOTP_SECRET 已配置）。"""
    return bool(os.environ.get(TOTP_SECRET_ENV, "").strip())


def provisioning_uri(account="xiaoju3", issuer="xiaoju3-agent", secret=None):
    """生成 otpauth:// URI，供验证器 App 扫码/手动录入。

    secret 缺省读环境变量 XIAOJU3_TOTP_SECRET；未配置时返回空串
    （功能降级口径，调用方应给出中文提示）。
    """
    secret = secret if secret is not None else os.environ.get(TOTP_SECRET_ENV, "")
    if not str(secret).strip():
        return ""
    label = urllib.parse.quote(f"{issuer}:{account}")
    query = urllib.parse.urlencode({
        "secret": _normalize_secret(secret).rstrip("="),
        "issuer": issuer,
        "algorithm": "SHA1",
        "digits": str(TOTP_DIGITS),
        "period": str(TOTP_STEP),
    })
    return f"otpauth://totp/{label}?{query}"


# ==================== 可插拔因子链（多因素 AND 语义） ====================

class Factor:
    """认证因子协议：子类实现 verify(credential) -> (bool, 中文提示)。

    credential 为该因子对应用户输入（如 6 位动态密码 / 生物特征数据）。
    verify 永不抛异常（内部捕获，失败返回 (False, 提示)）。
    """

    name = "factor"

    def verify(self, credential):
        raise NotImplementedError("认证因子需实现 verify(credential)")


class TOTPFactor(Factor):
    """内置因子：TOTP 动态密码。

    密钥构造时可注入（便于测试/多密钥），缺省 verify 时读环境变量
    XIAOJU3_TOTP_SECRET（Base32）；未配置时明确降级并给中文提示。
    """

    name = "totp"

    def __init__(self, secret=None):
        self.secret = secret

    def _get_secret(self):
        if self.secret is not None:
            return self.secret
        return os.environ.get(TOTP_SECRET_ENV, "")

    def verify(self, credential):
        secret = self._get_secret()
        if not str(secret).strip():
            return False, (f"❌ 未配置 {TOTP_SECRET_ENV}（Base32 动态密码密钥），"
                           "LV4 动态密码功能已降级关闭。请先在 .env 配置密钥，"
                           "或用 provisioning_uri() 生成 otpauth:// 链接接入验证器 App。")
        if verify_totp(secret, credential):
            return True, "✅ 动态密码校验通过"
        return False, "❌ 动态密码不正确或已过期（30 秒步长，±1 窗口）"


class BiometricFactor(Factor):
    """扩展挂载点：生物认证。

    本机无生物识别硬件，默认未接入——通过 register_verifier(fn) 注册
    自定义验证器回调（如 Windows Hello / 外设指纹仪），签名 fn(credential)
    -> bool。未注册时明确提示"生物认证器未接入"。
    """

    name = "biometric"

    NOT_CONNECTED_MSG = ("❌ 生物认证器未接入：本机无生物识别硬件。"
                         "请先 register_verifier(自定义验证回调) 注册后启用。")

    def __init__(self, verifier=None):
        self._verifier = verifier
        self.label = "生物认证"   # #243：可注入诚实标签（如"模拟:SIM=1 无硬件"）

    def register_verifier(self, verifier):
        """注册自定义生物验证回调 fn(credential) -> bool。"""
        self._verifier = verifier

    def verify(self, credential):
        if self._verifier is None:
            return False, self.NOT_CONNECTED_MSG
        try:
            ok = bool(self._verifier(credential))
        except Exception as e:
            return False, f"❌ 生物认证器调用异常：{e}"
        return (True, f"✅ {self.label}通过") if ok else (False, f"❌ {self.label}未通过")


# ==================== 类 Root 警告与授予/撤销（界面文档 §8.3 口径） ====================

ROOT_WARNING = """🚨🚨🚨 类 Root 权限警告（LV4 · 解放全部权限）🚨🚨🚨
你正在申请小橘3号的最高等级权限（LV4），效力类似系统 Root。授予后小橘3号可执行以下敏感操作：
  1. 写文件 / 修改代码 —— 可能改动、覆盖任意项目文件，影响小橘3号自身运行；
  2. 家居控制（含门锁、燃气阀等高危实体）—— 直接关系人身与财产安全；
  3. ADB 接管手机 —— 可在手机上执行任意点击、滑动等触控操作；
  4. 删除数据 —— 不可恢复地删除文件与记忆数据。
后果说明：误操作可能导致数据丢失、设备误控乃至安全事故，请确认你完全理解上述风险。
二次确认：理解并接受后，请先调用 acknowledge_risk(user_id) 完成风险确认，再申请 grant_lv4(user_id)。
撤销途径：随时可调用 revoke_lv4(user_id) 撤销 LV4 权限，立即生效。"""


def root_warning(print_warning=True):
    """返回（并默认打印）类 Root 红字风格警告文案（敏感操作清单 + 后果 +
    二次确认 + 撤销途径，界面文档 §8.3 口径）。"""
    if print_warning:
        print(ROOT_WARNING)
    return ROOT_WARNING


class LV4AuthManager:
    """LV4 多因素认证管理器：因子链 AND 语义 + 风险二次确认 + 撤销途径。

    状态存内存；可选 JSON 快照（save_snapshot / load_snapshot）供重启参考。
    等级正式落盘走 permission.PermissionManager.save_identity() 语义，
    由接线方（S5 / main.py）完成——见模块 docstring 接口约定。
    """

    def __init__(self, factors=None, snapshot_path=None):
        # 默认因子链：TOTP 动态密码。生物认证为扩展挂载点，按需 register。
        self.factors = list(factors) if factors is not None else [TOTPFactor()]
        self.snapshot_path = snapshot_path
        self.acknowledged = set()    # 已完成风险二次确认的用户
        self._authenticated = set()  # 最近一次多因素认证通过的用户
        self.granted = set()         # 当前持有 LV4 的用户

    # ---- 因子链 ----
    def register_factor(self, factor):
        """注册认证因子（追加进链；认证时全部已注册因子依次通过才放行）。"""
        self.factors.append(factor)
        return self.factors

    def authenticate(self, user_id, credentials):
        """多因素认证：全部已注册因子依次通过（AND 语义）才算通过。

        credentials: {factor.name: credential}；缺参按该因子失败处理。
        返回 (ok, 明细文案)；通过者记入已认证名单（grant_lv4 前置）。
        """
        if not self.factors:
            return False, "❌ 未注册任何认证因子，无法认证。"
        creds = credentials or {}
        lines, ok_all = [], True
        for factor in self.factors:
            ok, msg = factor.verify(creds.get(factor.name))
            lines.append(f"[{factor.name}] {msg}")
            ok_all = ok_all and ok
        detail = "\n".join(lines)
        if ok_all:
            self._authenticated.add(user_id)
        else:
            self._authenticated.discard(user_id)
        return ok_all, detail

    # ---- 类 Root 警告流程 ----
    def acknowledge_risk(self, user_id):
        """风险二次确认（grant_lv4 前置）：确认前请先阅读 root_warning()。"""
        self.acknowledged.add(user_id)
        return f"✅ 用户 {user_id} 已确认 LV4 类 Root 风险，可继续 grant_lv4('{user_id}')。"

    def grant_lv4(self, user_id):
        """授予 LV4：需 ①已 acknowledge_risk 二次确认 ②多因素认证已通过。

        成功后由接线方同步 permission_manager 等级并 save_identity() 落盘
        （本模块不直接触碰 permission.py）。
        """
        if user_id not in self.acknowledged:
            return (f"❌ 授权失败：用户 {user_id} 尚未完成风险二次确认。"
                    f"请先展示 root_warning() 并调用 acknowledge_risk('{user_id}')。")
        if user_id not in self._authenticated:
            return (f"❌ 授权失败：用户 {user_id} 的多因素认证未通过"
                    "（动态密码/生物认证等全部因子需依次通过）。")
        self.granted.add(user_id)
        self.save_snapshot()
        return (f"✅ 用户 {user_id} 已授予 LV4（类 Root）权限。"
                "【接线约定】请同步 permission_manager 等级并调用 save_identity() 落盘。")

    def revoke_lv4(self, user_id):
        """撤销 LV4（文档承诺的撤销途径），立即生效；重授需重新多因素认证。"""
        if user_id not in self.granted:
            return f"用户 {user_id} 当前未持有 LV4 权限。"
        self.granted.discard(user_id)
        self._authenticated.discard(user_id)
        self.save_snapshot()
        return f"✅ 用户 {user_id} 的 LV4 权限已撤销，立即生效。"

    def is_lv4(self, user_id):
        return user_id in self.granted

    # ---- 可选 JSON 快照（内存状态落盘参考；正式落盘归 permission.save_identity） ----
    def save_snapshot(self, path=None):
        """把内存名单写入 JSON 快照；未配置路径时为无操作（返回 None）。"""
        path = path or self.snapshot_path
        if not path:
            return None
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"granted": sorted(self.granted),
                           "acknowledged": sorted(self.acknowledged),
                           "updated_at": time.time()}, f, ensure_ascii=False, indent=2)
            return path
        except Exception as e:
            print(f"⚠️ LV4 快照保存失败：{e}")
            return None

    def load_snapshot(self, path=None):
        """从 JSON 快照恢复内存名单；成功返回 True。"""
        path = path or self.snapshot_path
        if not path or not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.granted = set(data.get("granted", []))
            self.acknowledged = set(data.get("acknowledged", []))
            return True
        except Exception as e:
            print(f"⚠️ LV4 快照读取失败：{e}")
            return False


# 模块级单例：接线方（S5 / main.py）可直接 import 使用
lv4_manager = LV4AuthManager()


# ---- 模块级便捷入口（委托单例，签名稳定便于接线） ----

def authenticate(user_id, credentials):
    return lv4_manager.authenticate(user_id, credentials)


def acknowledge_risk(user_id):
    return lv4_manager.acknowledge_risk(user_id)


def grant_lv4(user_id):
    return lv4_manager.grant_lv4(user_id)


def revoke_lv4(user_id):
    return lv4_manager.revoke_lv4(user_id)


def is_lv4(user_id):
    return lv4_manager.is_lv4(user_id)


if __name__ == "__main__":
    root_warning()
    print("TOTP 已配置：" + ("是" if totp_configured() else f"否（请设置 {TOTP_SECRET_ENV}）"))
    uri = provisioning_uri()
    if uri:
        print("验证器 App 接入链接：", uri)
