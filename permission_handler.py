# -*- coding: utf-8 -*-
"""权限/身份领域 handler（#227 批 A：register/name/coder_auth/sudo/lv4 族/
reset_fuse，2026-10-14）。

v2 领域拆分版（design_227b_boundary_v2.md §二 handler 1；命名按 D1 拍板
permission_handler）。九块全为薄分派——本体即 permission_manager 方法调用
（register_user/claim_name/activate_lv3/open_operation_window/lv4_mfa_check+
grant_lv4/revoke_lv4），逻辑本体零搬迁；_arg_after 参数解析与
ensure_biometric_sim（生物模拟验证器登记）随迁——二者均属本域分派语义。

接口纪律（D2 拍板）：handle_auth 收 permission_manager 整体（领域服务
对象，9 块共享，逐方法拆 cb=签名爆炸）；本模块零 import main。

分派顺序纪律：main 原块序 register → name → coder_auth → sudo → lv4_auth
→ lv4_revoke（reset_fuse 独立入口由调用方紧随），迁出后调用点保持同序
（行为等价由黄金样本 38 条逐字节 diff 守护）。
"""
import os
import re

from auth_lv4 import root_warning

BIOMETRIC_SIM_ENV = "XIAOJU3_BIOMETRIC_SIM"


def _arg_after(raw_message, command):
    """提取指令后的参数原文（剔 CQ 码+去首尾空白）——main 同名助手全函
    数随迁（初批漏抄 re.sub 尾段被黄金门当场拦下，正是它的价值）。

    取清洗前原文：标点清洗会剥掉 URL 的 : . 、路径盘符与扩展名点，导致
    密码参数失效。（main 仍留一份供 /gen_log 批 B 前使用；批 B 迁走后
    main 副本可退役。）
    """
    if command not in raw_message:
        return ""
    tail = raw_message.split(command, 1)[-1]
    return re.sub(r'\[CQ:[^\]]*\]', '', tail).strip()


def ensure_biometric_sim(pm):
    """env XIAOJU3_BIOMETRIC_SIM=1 时注册恒真生物认证模拟验证器（随迁）。

    ⚠️ 仅供测试/演示：恒真回调模拟"生物认证通过"，不代表真实生物识别硬件；
    生产环境请接入真实验证器（pm.register_biometric_verifier）或保持该
    环境变量关闭。幂等：重复调用只覆盖同一回调。#243 诚实化：label 如实
    标注"模拟/无硬件/实际单因子"。
    （main._ensure_biometric_sim 保留同名委托壳——dashboard 控制台仍调
    main 名。）
    """
    if os.environ.get(BIOMETRIC_SIM_ENV, "").strip() == "1":
        pm.register_biometric_verifier(
            lambda credential: True,
            label="生物认证(模拟：XIAOJU3_BIOMETRIC_SIM=1，本机无硬件，"
                  "实际安全强度=TOTP 单因子)")


def handle_auth(command_text, raw_message, user_key, pm):
    """权限/身份六命令路由（/register /name /coder_auth /sudo /lv4_auth
    /lv4_revoke）。非本域指令返回 None（调用方继续消息管线）。

    回复文案与分支语义与 main 原块逐字节一致（黄金样本守护）。
    """
    # === 🛡️ Lv.2 注册（§7：env 注册密码校验，等级落盘） ===
    if command_text.startswith("/register"):
        arg = _arg_after(raw_message, "/register").strip()
        parts = arg.split(None, 1)
        password = parts[0] if parts else ""
        name = parts[1].strip() if len(parts) > 1 else None
        return pm.register_user(user_key, password, name=name)

    if command_text.startswith("/name"):
        return pm.claim_name(user_key, _arg_after(raw_message, "/name"))

    # === 🛡️ Lv.3 TOTP 动态密码激活（等级持久化接线，修复"重启回落"） ===
    if command_text.startswith("/coder_auth"):
        return pm.activate_lv3(user_key, _arg_after(raw_message, "/coder_auth"))

    # === 🛡️ /sudo：开启 120 秒写操作窗口（与工具链门禁同为缺省用户口径） ===
    if command_text.startswith("/sudo"):
        code = _arg_after(raw_message, "/sudo")
        if not code:
            return ("用法：/sudo <6位动态密码>——开启 120 秒写操作窗口（Lv.3 已可直接写文件，本指令为兼容保留），"
                    "窗口内写文件/写代码无需逐次输入动态密码。")
        return pm.open_operation_window(None, totp_code=code)

    # === 🛡️ /lv4_auth 两步流：类 Root 警告 → 双因子 confirm 授权 ===
    if command_text.startswith("/lv4_auth"):
        ensure_biometric_sim(pm)
        rest = _arg_after(raw_message, "/lv4_auth")
        if not rest:
            # 第一步：类 Root 警告（敏感操作清单 + 后果 + 撤销途径），等待确认
            return (root_warning(print_warning=False)
                    + "\n\n理解并接受上述风险后，请发送 /lv4_auth confirm <6位动态密码> 完成双因子授权。")
        if rest.startswith("confirm"):
            totp = rest[len("confirm"):].strip()
            # 带明细校验：生物认证器未接入时透传"生物认证器未接入"明细
            ok, detail = pm.lv4_mfa_check(
                user_key, {"totp": totp, "biometric": "biometric"})
            if not ok:
                return f"❌ Lv.4 双因子认证未通过：\n{detail}"
            credentials = {"confirmed": True, "totp": totp, "biometric": "biometric"}
            # （2026-10-02 权限重构）授权级验证保留；授权后操作不再逐次
            # 验证，操作级双因子会话已随 /confirm 令牌流一并删除
            return pm.grant_lv4(user_key, credentials)
        return "用法：/lv4_auth 查看类 Root 警告；/lv4_auth confirm <6位动态密码> 完成授权。"

    # === 🛡️ /lv4_revoke：撤销主人级权限（立即生效） ===
    if command_text.startswith("/lv4_revoke"):
        return pm.revoke_lv4(user_key)

    return None


def handle_reset_fuse(command_text, level_value_cb, reset_fuse_cb):
    """⛔ /reset_fuse：防死循环熔断重置（Lv.2+，管理员口径全通道清零）。

    reset_fuse_cb=main.reset_tool_fuse（brain 跨域，回调注入）；非本域
    指令返回 None。
    """
    if not command_text.startswith("/reset_fuse"):
        return None
    if level_value_cb() < 2:
        return "❌ 权限不足，该指令需要 Lv.2（普通用户）权限。请先 /register <密码> 注册升级。"
    reset_fuse_cb()
    return "✅ 防死循环熔断计数已重置，工具调用权限已恢复。"
