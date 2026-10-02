# -*- coding: utf-8 -*-
"""permission 单元测试：Lv.1–Lv.4 权限新表（第二阶段 §7 用户指令）、继承语义、
identity 读写 roundtrip（含 owner 标记）、Lv.2 密码注册、Lv.3 TOTP 激活+落盘、
Lv.3 逐次动态密码/操作窗口、Lv.4 双因子与 grant/revoke、私有扩展挂载点回退。

身份文件一律指向 tempfile（setUp 内改挂类属性 IDENTITY_PATH，tearDown
还原），不触碰真实 agent_state/。TOTP 用 auth_lv4 RFC 参考密钥 + mock 时间，
env 键（XIAOJU3_TOTP_SECRET / XIAOJU3_REGISTER_PASSWORD）全部经
mock.patch.dict 注入，用后自动还原。
"""
import io
import json
import os
import contextlib
import shutil
import tempfile
import unittest
from unittest import mock

import auth_lv4
import permission
from permission import PermissionManager

# RFC 6238 附录 B SHA1 参考密钥（Base32），与 tests/test_auth_lv4.py 同源
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
REGISTER_PASSWORD_ENV = permission.REGISTER_PASSWORD_ENV

# §7 用户指令新表：能力全集（按所需最低等级分组）
# 2026-10-02 权限重构定稿：读/写维持原档；安全家居升 LV3；ADB 全套/
# 发图/restart_service 归 LV4
LV1_ACTIONS = ("chat", "web_search")
LV2_ACTIONS = ("read_file", "list_files")
LV3_ACTIONS = ("write_file", "control_normal_devices", "modify_code",
               "manage_plugins")
LV4_ACTIONS = ("control_dangerous_devices", "system_manage",
               "read_private_memory", "adb_full", "send_image",
               "restart_service")
ALL_ACTIONS = LV1_ACTIONS + LV2_ACTIONS + LV3_ACTIONS + LV4_ACTIONS


def _env_with(pairs):
    """在当前环境副本上注入键值（配合 patch.dict 用后自动还原）。"""
    env = dict(os.environ)
    env.update(pairs)
    return env


class PermissionTestBase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_perm_")
        self._old_path = PermissionManager.IDENTITY_PATH
        PermissionManager.IDENTITY_PATH = os.path.join(self.tmp, "identity.json")

    def tearDown(self):
        PermissionManager.IDENTITY_PATH = self._old_path
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _pm(self, level=None):
        pm = PermissionManager()
        if level is not None:
            pm.current_level = level
        return pm


class PermissionTableTests(PermissionTestBase):
    """§7 权限新表：Lv.1 游客 / Lv.2 普通用户 / Lv.3 代码编写者 / Lv.4 主人级。"""

    def test_default_level_is_lv1(self):
        self.assertEqual(self._pm().current_level, "Lv.1")

    def test_lv1_scope(self):
        # Lv.1 游客：聊天 + 网页搜索（web_search 维持 Lv.1，不设限）
        pm = self._pm("Lv.1")
        self.assertTrue(pm.has_permission("chat"))
        self.assertTrue(pm.has_permission("web_search"))
        # 用户调整点：读文件/列目录从旧表 LV1 调整为 Lv.2 起
        self.assertFalse(pm.has_permission("read_file"))
        self.assertFalse(pm.has_permission("list_files"))
        self.assertFalse(pm.has_permission("control_normal_devices"))
        self.assertFalse(pm.has_permission("write_file"))

    def test_lv2_scope(self):
        # Lv.2 普通用户：+ 读文件、列目录、控制普通家居
        pm = self._pm("Lv.2")
        for action in LV1_ACTIONS + LV2_ACTIONS:
            self.assertTrue(pm.has_permission(action), action)
        self.assertFalse(pm.has_permission("write_file"))
        self.assertFalse(pm.has_permission("control_dangerous_devices"))
        self.assertFalse(pm.has_permission("system_manage"))

    def test_lv3_scope(self):
        # Lv.3 代码编写者：+ 写文件 / modify_code / manage_plugins
        pm = self._pm("Lv.3")
        for action in LV1_ACTIONS + LV2_ACTIONS + LV3_ACTIONS:
            self.assertTrue(pm.has_permission(action), action)
        self.assertFalse(pm.has_permission("control_dangerous_devices"))
        self.assertFalse(pm.has_permission("system_manage"))

    def test_lv4_scope(self):
        # Lv.4 主人级：+ 危险家居 / 系统装卸（"无边界"= 包含全部低级能力）
        pm = self._pm("Lv.4")
        for action in ALL_ACTIONS:
            self.assertTrue(pm.has_permission(action), action)

    def test_web_search_activated_as_lv1_capability(self):
        # 网页搜索属 Lv.1（§7 表），各档均可用
        for level in ("Lv.1", "Lv.2", "Lv.3", "Lv.4"):
            pm = self._pm(level)
            self.assertTrue(pm.has_permission("web_search"), level)

    def test_lv2_adds_read_and_list(self):
        # 相对 Lv.1 的新增面 = read_file / list_files（写文件门槛保持 LV3）
        before = self._pm("Lv.1")
        after = self._pm("Lv.2")
        gained = {a for a in ALL_ACTIONS
                  if after.has_permission(a) and not before.has_permission(a)}
        self.assertEqual(gained, set(LV2_ACTIONS))

    def test_lv3_adds_writer_and_safe_home(self):
        before = self._pm("Lv.2")
        after = self._pm("Lv.3")
        gained = {a for a in ALL_ACTIONS
                  if after.has_permission(a) and not before.has_permission(a)}
        self.assertEqual(gained, set(LV3_ACTIONS))

    def test_lv4_adds_dangerous_and_system_manage(self):
        before = self._pm("Lv.3")
        after = self._pm("Lv.4")
        gained = {a for a in ALL_ACTIONS
                  if after.has_permission(a) and not before.has_permission(a)}
        self.assertEqual(gained, set(LV4_ACTIONS))

    def test_unknown_level_has_no_permission(self):
        pm = self._pm("Lv.9")
        self.assertFalse(pm.has_permission("chat"))

    def test_unknown_action_has_no_permission(self):
        self.assertFalse(self._pm("Lv.4").has_permission("no_such_action"))


class InheritanceTests(PermissionTestBase):
    """继承语义：等级数值 >= 所需等级即通过，低级功能无需重复验证。"""

    def test_higher_level_inherits_all_lower_actions(self):
        # 每一档的通过集合 = 所有所需等级 <= 当前等级的能力（前缀包含）
        order = ["Lv.1", "Lv.2", "Lv.3", "Lv.4"]
        required = dict(permission.ACTION_LEVELS)
        for i, level in enumerate(order):
            pm = self._pm(level)
            expected = {a for a, lv in required.items() if lv <= i + 1}
            got = {a for a in ALL_ACTIONS if pm.has_permission(a)}
            self.assertEqual(got, expected, level)
            # 低档能力集是高档能力集的子集（继承链条）
            if i > 0:
                lower = self._pm(order[i - 1])
                lower_set = {a for a in ALL_ACTIONS if lower.has_permission(a)}
                self.assertTrue(lower_set.issubset(got), level)

    def test_lv4_needs_no_reverification_for_lower_actions(self):
        # Lv.4"无边界"：Lv.1/2/3 的能力在 Lv.4 下无需任何重复验证
        pm = self._pm("Lv.4")
        for action in ALL_ACTIONS:
            self.assertTrue(pm.has_permission(action), action)


class IdentityTests(PermissionTestBase):
    """identity.json 读写 roundtrip（含 owner 主人级标记）与容错。"""

    def test_save_and_load_roundtrip(self):
        pm1 = self._pm("Lv.3")
        pm1.save_identity()
        self.assertTrue(os.path.exists(PermissionManager.IDENTITY_PATH))
        pm2 = PermissionManager()
        self.assertEqual(pm2.current_level, "Lv.3")

    def test_owner_flag_persists_across_instances(self):
        # owner 标记写入 identity.json 并可被新实例读回
        pm = self._pm("Lv.4")
        pm.owner = "xun"
        pm.save_identity()
        self.assertTrue(PermissionManager().owner == "xun")
        self.assertTrue(PermissionManager().is_owner())

    def test_saved_json_shape(self):
        pm = self._pm("Lv.2")
        pm.save_identity()
        with open(PermissionManager.IDENTITY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["current_level"], "Lv.2")
        self.assertIsNone(data["owner"])
        self.assertIn("updated_at", data)

    def test_missing_identity_file_defaults_lv1(self):
        self.assertFalse(os.path.exists(PermissionManager.IDENTITY_PATH))
        pm = self._pm()
        self.assertEqual(pm.current_level, "Lv.1")
        self.assertIsNone(pm.owner)

    def test_corrupt_identity_falls_back_to_lv1(self):
        with open(PermissionManager.IDENTITY_PATH, "w", encoding="utf-8") as f:
            f.write("{bad json")
        pm = self._pm()
        self.assertEqual(pm.current_level, "Lv.1")
        self.assertIsNone(pm.owner)

    def test_save_failure_warns_without_raise(self):
        pm = self._pm()
        pm.IDENTITY_PATH = os.path.join(self.tmp, "missing_dir", "identity.json")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            pm.save_identity()  # 不应抛异常
        self.assertIn("保存身份状态失败", buf.getvalue())


class RegisterTests(PermissionTestBase):
    """Lv.2 密码注册：env 校验、未配置降级、密码对错、落盘。"""

    def test_register_without_env_degrades_with_hint(self):
        env = _env_with({})  # 保证无注册密码键
        env.pop(REGISTER_PASSWORD_ENV, None)
        with mock.patch.dict(os.environ, env, clear=True):
            msg = self._pm().register_user("guest", "whatever")
        self.assertTrue(msg.startswith("❌"), msg)
        self.assertIn(REGISTER_PASSWORD_ENV, msg)   # 明确指出缺失的配置键
        self.assertIn("降级", msg)
        self.assertEqual(self._pm().current_level, "Lv.1")

    def test_register_wrong_password_rejected(self):
        env = _env_with({REGISTER_PASSWORD_ENV: "right-pass"})
        with mock.patch.dict(os.environ, env):
            msg = self._pm().register_user("guest", "wrong-pass")
        self.assertTrue(msg.startswith("❌"), msg)
        self.assertIn("注册密码错误", msg)
        self.assertEqual(self._pm().current_level, "Lv.1")
        self.assertFalse(os.path.exists(PermissionManager.IDENTITY_PATH))

    def test_register_correct_password_upgrades_and_persists(self):
        env = _env_with({REGISTER_PASSWORD_ENV: "right-pass"})
        with mock.patch.dict(os.environ, env):
            msg = self._pm().register_user("guest", "right-pass")
        self.assertTrue(msg.startswith("✅"), msg)
        pm = self._pm()
        self.assertEqual(pm.current_level, "Lv.2")
        # 等级持久化接线（覆盖旧口径"不落盘"）
        self.assertTrue(os.path.exists(PermissionManager.IDENTITY_PATH))
        self.assertEqual(PermissionManager().current_level, "Lv.2")

    def test_register_does_not_downgrade_higher_level(self):
        env = _env_with({REGISTER_PASSWORD_ENV: "right-pass"})
        with mock.patch.dict(os.environ, env):
            msg = self._pm("Lv.3").register_user("dev", "right-pass")
        self.assertTrue(msg.startswith("✅"), msg)
        self.assertEqual(self._pm().current_level, "Lv.3")


class ActivateLv3Tests(PermissionTestBase):
    """/coder_auth 新语义 = activate_lv3：TOTP 激活 + 落盘 roundtrip。"""

    def _env_totp(self):
        return _env_with({auth_lv4.TOTP_SECRET_ENV: RFC_SECRET})

    def test_activate_without_totp_secret_degrades(self):
        env = _env_with({})
        env.pop(auth_lv4.TOTP_SECRET_ENV, None)
        with mock.patch.dict(os.environ, env, clear=True):
            msg = self._pm().activate_lv3("u", "123456")
        self.assertTrue(msg.startswith("❌"), msg)
        self.assertIn(auth_lv4.TOTP_SECRET_ENV, msg)
        self.assertIn("降级", msg)
        self.assertEqual(self._pm().current_level, "Lv.1")

    def test_activate_wrong_code_rejected_and_not_persisted(self):
        with mock.patch.dict(os.environ, self._env_totp()):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                wrong = auth_lv4.generate_totp(RFC_SECRET, 1000 + 9999)  # 远离窗口的码
                msg = self._pm().activate_lv3("u", wrong)
        self.assertTrue(msg.startswith("❌"), msg)
        self.assertIn("动态密码", msg)
        self.assertEqual(self._pm().current_level, "Lv.1")
        self.assertFalse(os.path.exists(PermissionManager.IDENTITY_PATH))

    def test_activate_correct_code_upgrades_and_persists_roundtrip(self):
        # 【用户指定覆盖】Lv.3 经 TOTP 激活并落盘：新实例读回 Lv.3
        with mock.patch.dict(os.environ, self._env_totp()):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                code = auth_lv4.generate_totp(RFC_SECRET, 1000)
                msg = self._pm().activate_lv3("u", code)
        self.assertTrue(msg.startswith("✅"), msg)
        self.assertEqual(self._pm().current_level, "Lv.3")
        self.assertTrue(os.path.exists(PermissionManager.IDENTITY_PATH))
        self.assertEqual(PermissionManager().current_level, "Lv.3")

    def test_activate_success_message_sudo_free_wording(self):
        # 【口径锁定 2026-09-30 用户指令】激活成功消息不得再暗示"写文件还需
        # 逐次动态密码 /sudo 开窗"——旧文案随回复进入对话历史，会被模型复读。
        with mock.patch.dict(os.environ, self._env_totp()):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                code = auth_lv4.generate_totp(RFC_SECRET, 1000)
                msg = self._pm().activate_lv3("u42", code)
        self.assertIn("已激活代码编写者权限（Lv.3）", msg)
        self.assertIn("权限已落盘", msg)
        self.assertIn("无需 /sudo", msg)
        self.assertIn("ADB", msg)
        # 旧口径残留锁定：不再出现逐次动态密码/操作窗口要求字样
        self.assertNotIn("逐次动态密码", msg)
        self.assertNotIn("操作窗口", msg)
        self.assertNotIn("执行时还需", msg)

    def test_activate_does_not_downgrade_lv4(self):
        with mock.patch.dict(os.environ, self._env_totp()):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                code = auth_lv4.generate_totp(RFC_SECRET, 1000)
                self._pm("Lv.4").activate_lv3("u", code)
        self.assertEqual(self._pm().current_level, "Lv.4")

    def test_coder_auth_wrapper_delegates_to_activate_lv3(self):
        # 旧方法名兼容包装：新语义 = TOTP 激活 + 落盘（行为等价于 activate_lv3）
        self.assertTrue(callable(PermissionManager.coder_auth))
        with mock.patch.dict(os.environ, self._env_totp()):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                code = auth_lv4.generate_totp(RFC_SECRET, 1000)
                msg = self._pm().coder_auth("u", code)
        self.assertTrue(msg.startswith("✅"), msg)
        self.assertEqual(self._pm().current_level, "Lv.3")


class Lv3OperationTests(PermissionTestBase):
    """Lv.3 逐次动态密码：单次校验、/sudo 操作窗口（仅内存）、统一入口。"""

    def _env_totp(self):
        return _env_with({auth_lv4.TOTP_SECRET_ENV: RFC_SECRET})

    def _code(self, ts=1000):
        return auth_lv4.generate_totp(RFC_SECRET, ts)

    def test_verify_operation_accepts_only_correct_code(self):
        with mock.patch.dict(os.environ, self._env_totp()):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                pm = self._pm()
                self.assertTrue(pm.verify_lv3_operation("u", self._code(1000)))
                self.assertFalse(pm.verify_lv3_operation("u", "000000"))
                self.assertFalse(pm.verify_lv3_operation("u", None))

    def test_verify_operation_without_secret_fails_closed(self):
        env = _env_with({})
        env.pop(auth_lv4.TOTP_SECRET_ENV, None)
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(self._pm().verify_lv3_operation("u", "123456"))

    def test_window_opens_with_valid_totp_and_expires(self):
        with mock.patch.dict(os.environ, self._env_totp()):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000), \
                 mock.patch.object(permission.time, "time", return_value=1000):
                pm = self._pm()
                msg = pm.open_operation_window("u", ttl_seconds=120,
                                               totp_code=self._code(1000))
                self.assertTrue(msg.startswith("✅"), msg)
                self.assertTrue(pm.operation_window_active("u"))
                self.assertTrue(pm.lv3_operation_ok("u"))
            # 过期（1000 + 120 之后）→ 窗口失效
            with mock.patch.object(permission.time, "time", return_value=1121):
                self.assertFalse(pm.operation_window_active("u"))
                self.assertFalse(pm.lv3_operation_ok("u"))

    def test_window_refused_with_wrong_totp(self):
        with mock.patch.dict(os.environ, self._env_totp()):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                pm = self._pm()
                msg = pm.open_operation_window("u", totp_code="000000")
        self.assertTrue(msg.startswith("❌"), msg)
        self.assertFalse(pm.operation_window_active("u"))

    def test_lv3_operation_ok_via_credentials_or_window(self):
        # 统一入口：凭据带有效 totp 或窗口有效均通过，否则 False
        with mock.patch.dict(os.environ, self._env_totp()):
            with mock.patch.object(permission.time, "time", return_value=1000), \
                 mock.patch.object(auth_lv4.time, "time", return_value=1000):
                pm = self._pm()
                self.assertFalse(pm.lv3_operation_ok("u"))  # 无凭据无窗口
                self.assertTrue(pm.lv3_operation_ok(
                    "u", credentials={"totp": self._code(1000)}))   # 凭据通道
                self.assertFalse(pm.lv3_operation_ok(
                    "u", credentials={"totp": "000000"}))           # 错码且无窗口
                pm.open_operation_window("u", ttl_seconds=120)      # 窗口通道
                self.assertTrue(pm.lv3_operation_ok("u"))
                self.assertTrue(pm.lv3_operation_ok("u", credentials={}))

    def test_window_state_memory_only(self):
        # 窗口仅内存：不写 identity.json，新实例不继承
        # （按当前真实时间开窗：TOTP 生成/校验同窗确定通过，过期线为真实时刻+TTL）
        with mock.patch.dict(os.environ, self._env_totp()):
            pm = self._pm()
            pm.open_operation_window(
                "u", totp_code=auth_lv4.generate_totp(RFC_SECRET))
        self.assertTrue(pm.operation_window_active("u"))
        self.assertFalse(os.path.exists(PermissionManager.IDENTITY_PATH))
        self.assertFalse(PermissionManager().operation_window_active("u"))

    def test_close_operation_window(self):
        pm = self._pm()
        pm.open_operation_window("u", ttl_seconds=120)
        self.assertTrue(pm.operation_window_active("u"))
        pm.close_operation_window("u")
        self.assertFalse(pm.operation_window_active("u"))


class Lv4MfaTests(PermissionTestBase):
    """Lv.4 双因子（auth_lv4 因子链）：TOTP + 生物认证 AND 语义、未接入提示。"""

    def _env_totp(self):
        return _env_with({auth_lv4.TOTP_SECRET_ENV: RFC_SECRET})

    def test_biometric_unregistered_reports_chinese_hint(self):
        # 未注册生物因子：拒绝 + 明确中文提示串
        pm = self._pm("Lv.4")
        ok, msg = pm.lv4_mfa_check("xun", {"totp": "000000", "biometric": "x"})
        self.assertFalse(ok)
        self.assertIn("生物认证器未接入", msg)
        self.assertIn("生物认证器未接入", pm.last_lv4_message)
        self.assertFalse(pm.lv4_mfa_ok("xun", {"totp": "000000"}))

    def test_mfa_requires_both_factors(self):
        # 缺任一因子（无 totp / 无生物）→ 整体拒绝（生物 mock 只认特定凭据）
        pm = self._pm("Lv.4")
        pm.register_biometric_verifier(lambda cred: cred == "face-id")
        with mock.patch.dict(os.environ, self._env_totp()):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                code = auth_lv4.generate_totp(RFC_SECRET, 1000)
                ok, _ = pm.lv4_mfa_check("xun", {"biometric": "face-id"})  # 缺 totp
                self.assertFalse(ok)
                ok, _ = pm.lv4_mfa_check("xun", {"totp": code})            # 缺生物
                self.assertFalse(ok)
                ok, msg = pm.lv4_mfa_check(
                    "xun", {"totp": code, "biometric": "face-id"})         # 双因子齐全
        self.assertTrue(ok)
        self.assertIn("动态密码校验通过", msg)
        self.assertIn("生物认证通过", msg)

    def test_mfa_fails_with_wrong_totp(self):
        pm = self._pm("Lv.4")
        pm.register_biometric_verifier(lambda cred: True)
        with mock.patch.dict(os.environ, self._env_totp()):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                wrong = auth_lv4.generate_totp(RFC_SECRET, 1000 + 9999)
                ok, msg = pm.lv4_mfa_check("xun", {"totp": wrong, "biometric": "ok"})
        self.assertFalse(ok)
        self.assertIn("动态密码不正确", msg)

    def test_mfa_fails_when_biometric_verifier_returns_false(self):
        pm = self._pm("Lv.4")
        pm.register_biometric_verifier(lambda cred: False)  # mock：生物不通过
        with mock.patch.dict(os.environ, self._env_totp()):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                ok, msg = pm.lv4_mfa_check(
                    "xun", {"totp": auth_lv4.generate_totp(RFC_SECRET, 1000),
                            "biometric": "x"})
        self.assertFalse(ok)
        self.assertIn("生物认证未通过", msg)

    def test_mfa_without_totp_secret_fails_with_degrade_hint(self):
        env = _env_with({})
        env.pop(auth_lv4.TOTP_SECRET_ENV, None)
        pm = self._pm("Lv.4")
        pm.register_biometric_verifier(lambda cred: True)
        with mock.patch.dict(os.environ, env, clear=True):
            ok, msg = pm.lv4_mfa_check("xun", {"totp": "123456", "biometric": "ok"})
        self.assertFalse(ok)
        self.assertIn("降级", msg)


class GrantRevokeTests(PermissionTestBase):
    """Lv.4 授予/撤销：二次确认 + 双因子 → owner 标记落盘；revoke 立即生效。"""

    def _env_totp(self):
        return _env_with({auth_lv4.TOTP_SECRET_ENV: RFC_SECRET})

    def _good_credentials(self):
        return {"totp": auth_lv4.generate_totp(RFC_SECRET, 1000),
                "biometric": "face-id", "confirmed": True}

    def test_grant_without_confirmation_rejected(self):
        pm = self._pm()
        pm.register_biometric_verifier(lambda cred: True)
        with mock.patch.dict(os.environ, self._env_totp()):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                creds = self._good_credentials()
                creds.pop("confirmed")
                msg = pm.grant_lv4("xun", creds)
        self.assertTrue(msg.startswith("❌"), msg)
        self.assertIn("二次确认", msg)
        self.assertIn("root_warning", msg)   # 引导先读类 Root 警告
        self.assertEqual(pm.current_level, "Lv.1")
        self.assertIsNone(pm.owner)

    def test_grant_with_failed_mfa_rejected(self):
        pm = self._pm()
        with mock.patch.dict(os.environ, self._env_totp()):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                # 生物认证器未注册 → 双因子必然失败
                msg = pm.grant_lv4("xun", self._good_credentials())
        self.assertTrue(msg.startswith("❌"), msg)
        self.assertIn("双因子认证未通过", msg)
        self.assertEqual(pm.current_level, "Lv.1")
        self.assertFalse(os.path.exists(PermissionManager.IDENTITY_PATH))

    def test_grant_success_sets_owner_and_persists(self):
        # 【用户指定覆盖④前置】双因子通过 → Lv.4 + owner 落盘
        pm = self._pm()
        pm.register_biometric_verifier(lambda cred: cred == "face-id")
        with mock.patch.dict(os.environ, self._env_totp()):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                msg = pm.grant_lv4("xun", self._good_credentials())
        self.assertTrue(msg.startswith("✅"), msg)
        self.assertEqual(pm.current_level, "Lv.4")
        self.assertEqual(pm.owner, "xun")
        self.assertTrue(pm.is_owner())
        with open(PermissionManager.IDENTITY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["owner"], "xun")
        self.assertEqual(data["current_level"], "Lv.4")
        # roundtrip：新实例读回 Lv.4 + owner
        reloaded = PermissionManager()
        self.assertEqual(reloaded.current_level, "Lv.4")
        self.assertEqual(reloaded.owner, "xun")

    def test_revoke_takes_effect_immediately(self):
        # 【用户指定覆盖】revoke 立即生效：等级回落、owner 清除、危险能力收回
        pm = self._pm()
        pm.register_biometric_verifier(lambda cred: True)
        with mock.patch.dict(os.environ, self._env_totp()):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                self.assertTrue(pm.grant_lv4("xun", self._good_credentials())
                                .startswith("✅"))
                self.assertTrue(pm.has_permission("control_dangerous_devices"))
                msg = pm.revoke_lv4("xun")
        self.assertTrue(msg.startswith("✅"), msg)
        self.assertEqual(pm.current_level, "Lv.3")
        self.assertIsNone(pm.owner)
        self.assertFalse(pm.has_permission("control_dangerous_devices"))
        self.assertFalse(pm.has_permission("system_manage"))
        # 落盘同步：新实例读回已撤销状态
        reloaded = PermissionManager()
        self.assertEqual(reloaded.current_level, "Lv.3")
        self.assertIsNone(reloaded.owner)

    def test_revoke_without_grant_is_noop(self):
        pm = self._pm()
        msg = pm.revoke_lv4("nobody")
        self.assertNotIn("✅", msg)
        self.assertIn("未持有", msg)
        self.assertEqual(pm.current_level, "Lv.1")
        self.assertFalse(os.path.exists(PermissionManager.IDENTITY_PATH))


class ModuleMountTests(unittest.TestCase):
    """模块级默认实例与隔离区私有扩展挂载点（缺省回退默认实例）。"""

    def test_module_default_instance(self):
        self.assertIsInstance(permission.permission_manager, PermissionManager)
        self.assertTrue(callable(permission.permission_manager.has_permission))

    def test_extension_module_absent_falls_back(self):
        # 测试环境无私有扩展 xun_private，应回退内置 PermissionManager 实例
        self.assertEqual(permission.permission_manager.current_level,
                         PermissionManager().current_level)

    def test_new_env_key_registered(self):
        # 新配置键名登记（报主控补 .env.example）
        self.assertEqual(REGISTER_PASSWORD_ENV, "XIAOJU3_REGISTER_PASSWORD")




class CreatorNameTests(unittest.TestCase):
    """专属称呼与命名防重：保留名拦截、设备相关默认称呼、称呼落盘。"""

    def test_reserved_name_rejected_case_insensitive(self):
        for bad in ("XUN", "xun", "Xun", " XUN "):
            ok, msg = permission.validate_claim_name(bad)
            self.assertFalse(ok, bad)
            self.assertIn("创作者署名保护", msg)

    def test_empty_name_rejected(self):
        ok, msg = permission.validate_claim_name("  ")
        self.assertFalse(ok)

    def test_normal_name_accepted(self):
        ok, result = permission.validate_claim_name("小橘的主人")
        self.assertTrue(ok)
        self.assertEqual(result, "小橘的主人")

    def test_default_master_name_depends_on_device_flag(self):
        with mock.patch.dict(os.environ, {"XIAOJU3_CREATOR_DEVICE": "1"}):
            self.assertEqual(permission.default_master_name(), "XUN")
        with mock.patch.dict(os.environ, {"XIAOJU3_CREATOR_DEVICE": ""}):
            self.assertEqual(permission.default_master_name(), "主人")

    def test_claim_name_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self._isolated(tmp):
                pm = self._pm(tmp)
                msg = pm.claim_name("u1", "阿橙")
                self.assertIn("阿橙", msg)
                self.assertEqual(pm.current_level, "Lv.1")
                pm2 = self._pm(tmp)
                self.assertEqual(pm2.display_name, "阿橙")

    def test_claim_name_reserved_blocked_and_not_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self._isolated(tmp):
                pm = self._pm(tmp)
                msg = pm.claim_name("u1", "xun")
                self.assertIn("❌", msg)
                self.assertEqual(pm.display_name, "")
                pm2 = self._pm(tmp)
                self.assertEqual(pm2.display_name, "")

    def test_register_with_name_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self._isolated(tmp), \
                    mock.patch.dict(os.environ, {REGISTER_PASSWORD_ENV: "pw123"}):
                pm = self._pm(tmp)
                self.assertEqual(pm.current_level, "Lv.1")   # 与真实身份状态隔离
                msg = pm.register_user("u1", "pw123", name="客人甲")
                self.assertIn("Lv.2", msg)
                self.assertEqual(pm.display_name, "客人甲")
                self.assertEqual(pm.current_level, "Lv.2")
                pm2 = self._pm(tmp)
                self.assertEqual(pm2.display_name, "客人甲")
                self.assertEqual(pm2.current_level, "Lv.2")

    def test_register_with_reserved_name_aborts(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self._isolated(tmp), \
                    mock.patch.dict(os.environ, {REGISTER_PASSWORD_ENV: "pw123"}):
                pm = self._pm(tmp)
                msg = pm.register_user("u1", "pw123", name="XUN")
                self.assertIn("❌", msg)
                self.assertIn("创作者署名保护", msg)              # 命中保留名拦截而非密码错误
                self.assertEqual(pm.current_level, "Lv.1")   # 注册整体中止
                self.assertEqual(pm.display_name, "")

    @staticmethod
    def _isolated(tmp):
        """整个测试生命周期内把身份文件路径隔离到 tmp：屏蔽真实
        agent_state/identity.json（用户实测可能处于任意等级），保证用例
        从全新 Lv.1 状态开始、落盘也只发生在 tmp。"""
        return mock.patch.object(permission.PermissionManager, "IDENTITY_PATH",
                                 os.path.join(tmp, "identity.json"))

    @staticmethod
    def _pm(tmp, extra_env=None):
        env = {"AGENT_STATE_DIR": tmp}
        if extra_env:
            env.update(extra_env)
        with mock.patch.dict(os.environ, env):
            pm = permission.PermissionManager()
        # 实例属性覆盖身份文件路径：save/load 都走 tmp（load 在 __init__ 已跑，
        # 需要读 tmp 时显式再调一次 load_identity）
        pm.IDENTITY_PATH = os.path.join(tmp, "identity.json")
        return pm


if __name__ == "__main__":
    unittest.main()
