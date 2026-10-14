# -*- coding: utf-8 -*-
"""permission_handler 单元锚（#227 批 A）。

黄金样本（38 条 tests/data）管端到端等价，本文件管分支组合与回调
契约（mock pm 直调 handler，不经过 onebot_event 管线）。
"""
import pytest

import permission_handler


class _FakePM:
    def __init__(self):
        self.calls = []

    def register_user(self, user_key, password, name=None):
        self.calls.append(("register", user_key, password, name))
        return "register-ok"

    def claim_name(self, user_key, name):
        self.calls.append(("claim", user_key, name))
        return "claim-ok"

    def activate_lv3(self, user_key, code):
        self.calls.append(("lv3", user_key, code))
        return "lv3-ok"

    def open_operation_window(self, user_id, totp_code=""):
        self.calls.append(("window", user_id, totp_code))
        return "window-ok"

    def lv4_mfa_check(self, user_key, credentials):
        self.calls.append(("mfa", user_key, credentials))
        return False, "[totp] ❌ 动态密码不正确"

    def grant_lv4(self, user_key, credentials):
        self.calls.append(("grant", user_key, credentials))
        return "grant-ok"

    def revoke_lv4(self, user_key):
        self.calls.append(("revoke", user_key))
        return "revoke-ok"


# 1 六命令路由：/register 参数解析（密码+称呼拆分）直达 pm
def test_register_route_parses_args():
    pm = _FakePM()
    reply = permission_handler.handle_auth(
        "/register", "/register abc123 小狐", "u1", pm)
    assert reply == "register-ok"
    assert pm.calls == [("register", "u1", "abc123", "小狐")]


# 2 /sudo 裸参：用法文案且不开窗（不触 pm）
def test_sudo_bare_usage_without_pm_call():
    pm = _FakePM()
    reply = permission_handler.handle_auth("/sudo", "/sudo", "u1", pm)
    assert "用法：/sudo" in reply
    assert pm.calls == []


# 3 /lv4_auth confirm 失败路：mfa 明细透传、不 grant
def test_lv4_confirm_fail_no_grant():
    pm = _FakePM()
    reply = permission_handler.handle_auth(
        "/lv4_auth confirm 000000", "/lv4_auth confirm 000000", "u1", pm)
    assert reply.startswith("❌ Lv.4 双因子认证未通过")
    assert ("grant",) != pm.calls[-1][:1]   # 未走 grant
    assert pm.calls[-1][0] == "mfa"


# 4 非本域指令返回 None（管线继续）
def test_non_domain_returns_none():
    assert permission_handler.handle_auth(
        "/todos", "/todos", "u1", _FakePM()) is None


# 5 reset_fuse 门禁：Lv<2 拒绝不动 cb；Lv≥2 重置
def test_reset_fuse_gate():
    reply = permission_handler.handle_reset_fuse(
        "/reset_fuse", level_value_cb=lambda: 1, reset_fuse_cb=lambda: None)
    assert "权限不足" in reply
    fired = []
    reply = permission_handler.handle_reset_fuse(
        "/reset_fuse", level_value_cb=lambda: 2,
        reset_fuse_cb=lambda: fired.append(1))
    assert reply.startswith("✅") and fired == [1]
    assert permission_handler.handle_reset_fuse(
        "/help", level_value_cb=lambda: 4,
        reset_fuse_cb=lambda: fired.append(1)) is None


# 6 ensure_biometric_sim：env=1 才注册（幂等由 pm 覆盖语义保证）
def test_ensure_biometric_sim_env_gated(monkeypatch):
    registered = []
    pm = type("PM", (), {"register_biometric_verifier":
                         staticmethod(lambda fn, label=None:
                                     registered.append((fn, label)))})()
    monkeypatch.delenv("XIAOJU3_BIOMETRIC_SIM", raising=False)
    permission_handler.ensure_biometric_sim(pm)
    assert registered == []
    monkeypatch.setenv("XIAOJU3_BIOMETRIC_SIM", "1")
    permission_handler.ensure_biometric_sim(pm)
    assert len(registered) == 1 and registered[0][1].startswith("生物认证(模拟")
