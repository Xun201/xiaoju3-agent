# -*- coding: utf-8 -*-
"""auth_lv4 单元测试：全离线。

覆盖：
- TOTP（RFC 6238）已知向量（RFC 附录 B SHA1 密钥向量取末 6 位，与
  mod 10^6 数学等价）、±1 窗口边界、坏密钥/坏码不抛异常；
- 可插拔因子链 AND 语义、BiometricFactor 未接入/注册/异常分支、
  TOTPFactor 未配置密钥降级提示（env patch 注入）；
- 类 Root 警告文案要素、未 ack 拒绝授权、未认证拒绝授权、revoke 生效、
  JSON 快照 roundtrip（tmp 目录）；
- provisioning_uri otpauth:// 形态。

配置键 XIAOJU3_TOTP_SECRET 全部经 mock.patch.dict(os.environ) 注入，
用后自动还原，不做 sys.modules 永久注入。
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth_lv4

# RFC 6238 附录 B SHA1 参考密钥："12345678901234567890"（ASCII）的 Base32
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


def _env_without_totp():
    """去掉 XIAOJU3_TOTP_SECRET 的完整环境副本（配合 patch.dict clear=True）。"""
    env = dict(os.environ)
    env.pop(auth_lv4.TOTP_SECRET_ENV, None)
    return env


class TOTPVectorTests(unittest.TestCase):
    """TOTP 生成与 RFC 6238 已知向量对齐（纯 stdlib 实现，30s 步长 SHA1）。"""

    def test_rfc6238_known_vectors_8_digits(self):
        # RFC 6238 附录 B：SHA1、8 位、参考密钥下的已知值
        self.assertEqual(auth_lv4.generate_totp(RFC_SECRET, 59, digits=8), "94287082")
        self.assertEqual(auth_lv4.generate_totp(RFC_SECRET, 1111111109, digits=8), "07081804")

    def test_rfc6238_known_vectors_6_digits(self):
        # 6 位 = 31 位截断值 mod 10^6，数学上等于 8 位值的末 6 位
        cases = [(59, "287082"), (1111111109, "081804"), (1111111111, "050471"),
                 (1234567890, "005924"), (2000000000, "279037")]
        for ts, code in cases:
            self.assertEqual(auth_lv4.generate_totp(RFC_SECRET, ts), code,
                             f"t={ts} 应为 {code}")

    def test_output_is_six_digit_string(self):
        for ts in (0, 30, 59, 1234567890):
            code = auth_lv4.generate_totp(RFC_SECRET, ts)
            self.assertIsInstance(code, str)
            self.assertEqual(len(code), 6)
            self.assertTrue(code.isdigit())

    def test_lowercase_and_spacing_secret_tolerated(self):
        lower = auth_lv4.generate_totp(RFC_SECRET.lower().replace("GEZ", "gez "), 59)
        self.assertEqual(lower, "287082")

    def test_step_boundary_changes_code(self):
        self.assertNotEqual(auth_lv4.generate_totp(RFC_SECRET, 59),
                            auth_lv4.generate_totp(RFC_SECRET, 89))


class TOTPVerifyWindowTests(unittest.TestCase):
    """±1 窗口边界：本步长与前后各一步长通过，隔两个步长拒绝。"""

    BASE_TS = 1000

    def test_current_and_adjacent_steps_pass(self):
        code = auth_lv4.generate_totp(RFC_SECRET, self.BASE_TS)
        for ts in (self.BASE_TS, self.BASE_TS - 30, self.BASE_TS + 30):
            self.assertTrue(auth_lv4.verify_totp(RFC_SECRET, code, ts),
                            f"t={ts}（±1 窗口内）应通过")

    def test_two_steps_away_rejected(self):
        code = auth_lv4.generate_totp(RFC_SECRET, self.BASE_TS)
        for ts in (self.BASE_TS - 60, self.BASE_TS + 60):
            self.assertFalse(auth_lv4.verify_totp(RFC_SECRET, code, ts),
                             f"t={ts}（±2 窗口外）应拒绝")

    def test_window_can_be_widened(self):
        code = auth_lv4.generate_totp(RFC_SECRET, self.BASE_TS)
        self.assertTrue(auth_lv4.verify_totp(RFC_SECRET, code,
                                             self.BASE_TS + 60, window=2))

    def test_bad_inputs_return_false_not_raise(self):
        self.assertFalse(auth_lv4.verify_totp(RFC_SECRET, None, 1000))
        self.assertFalse(auth_lv4.verify_totp(RFC_SECRET, "", 1000))
        self.assertFalse(auth_lv4.verify_totp(RFC_SECRET, "12345", 1000))  # 位数不足
        self.assertFalse(auth_lv4.verify_totp(RFC_SECRET, "abcdef", 1000))
        self.assertFalse(auth_lv4.verify_totp("!!不是Base32!!", "123456", 1000))


class TOTPFactorTests(unittest.TestCase):
    """TOTPFactor：未配置密钥降级、正确/错误码、构造注入优先。"""

    def test_missing_env_secret_degrades_with_chinese_hint(self):
        factor = auth_lv4.TOTPFactor()
        with mock.patch.dict(os.environ, _env_without_totp(), clear=True):
            ok, msg = factor.verify("123456")
        self.assertFalse(ok)
        self.assertIn(auth_lv4.TOTP_SECRET_ENV, msg)
        self.assertIn("降级", msg)

    def test_env_secret_correct_code_passes(self):
        env = _env_without_totp()
        env[auth_lv4.TOTP_SECRET_ENV] = RFC_SECRET
        code = auth_lv4.generate_totp(RFC_SECRET, 1000)
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                ok, msg = auth_lv4.TOTPFactor().verify(code)
        self.assertTrue(ok)
        self.assertIn("通过", msg)

    def test_env_secret_wrong_code_fails(self):
        env = _env_without_totp()
        env[auth_lv4.TOTP_SECRET_ENV] = RFC_SECRET
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                ok, msg = auth_lv4.TOTPFactor().verify("000000" if
                                                       auth_lv4.generate_totp(RFC_SECRET, 1000) != "000000" else "000001")
        self.assertFalse(ok)
        self.assertIn("❌", msg)

    def test_invalid_base32_secret_degrades(self):
        env = _env_without_totp()
        env[auth_lv4.TOTP_SECRET_ENV] = "!!!非法密钥!!!"
        with mock.patch.dict(os.environ, env, clear=True):
            ok, msg = auth_lv4.TOTPFactor().verify("123456")
        self.assertFalse(ok)

    def test_constructor_secret_overrides_env(self):
        code = auth_lv4.generate_totp(RFC_SECRET, 1000)
        env = _env_without_totp()
        env[auth_lv4.TOTP_SECRET_ENV] = "GEZDGNBVGY3TQOJQ"  # 不同的短密钥
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(auth_lv4.time, "time", return_value=1000):
                ok, _ = auth_lv4.TOTPFactor(secret=RFC_SECRET).verify(code)
        self.assertTrue(ok)

    def test_totp_configured_reflects_env(self):
        with mock.patch.dict(os.environ, _env_without_totp(), clear=True):
            self.assertFalse(auth_lv4.totp_configured())
        env = _env_without_totp()
        env[auth_lv4.TOTP_SECRET_ENV] = RFC_SECRET
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertTrue(auth_lv4.totp_configured())


class BiometricFactorTests(unittest.TestCase):
    """BiometricFactor：默认未接入、注册回调后生效、回调异常不外抛。"""

    def test_unregistered_reports_not_connected(self):
        ok, msg = auth_lv4.BiometricFactor().verify("任何凭据")
        self.assertFalse(ok)
        self.assertIn("生物认证器未接入", msg)

    def test_registered_verifier_true_passes(self):
        factor = auth_lv4.BiometricFactor()
        factor.register_verifier(lambda cred: cred == "face-id-xyz")
        ok, msg = factor.verify("face-id-xyz")
        self.assertTrue(ok)
        self.assertIn("通过", msg)

    def test_registered_verifier_false_fails(self):
        factor = auth_lv4.BiometricFactor(verifier=lambda cred: False)
        ok, msg = factor.verify("whatever")
        self.assertFalse(ok)
        self.assertIn("未通过", msg)

    def test_verifier_exception_wrapped(self):
        def boom(cred):
            raise RuntimeError("硬件拔了")
        ok, msg = auth_lv4.BiometricFactor(verifier=boom).verify("x")
        self.assertFalse(ok)
        self.assertIn("异常", msg)
        self.assertIn("硬件拔了", msg)


class _StaticFactor(auth_lv4.Factor):
    """脚本化假因子：verify 结果由构造注入。"""

    def __init__(self, name, ok, msg=""):
        self.name = name
        self._ok = ok
        self._msg = msg or ("✅ 通过" if ok else "❌ 不通过")

    def verify(self, credential):
        return self._ok, self._msg


class FactorChainTests(unittest.TestCase):
    """因子链 AND 语义：全部已注册因子依次通过才算通过。"""

    def test_all_factors_pass_is_ok(self):
        mgr = auth_lv4.LV4AuthManager(factors=[_StaticFactor("a", True),
                                               _StaticFactor("b", True)])
        ok, detail = mgr.authenticate("u", {"a": "x", "b": "y"})
        self.assertTrue(ok)
        self.assertIn("[a]", detail)
        self.assertIn("[b]", detail)

    def test_any_factor_failing_fails_chain(self):
        mgr = auth_lv4.LV4AuthManager(factors=[_StaticFactor("a", True),
                                               _StaticFactor("b", False, "❌ 令牌过期")])
        ok, detail = mgr.authenticate("u", {})
        self.assertFalse(ok)
        self.assertIn("令牌过期", detail)

    def test_missing_credential_counts_as_failure(self):
        factor = auth_lv4.TOTPFactor(secret=RFC_SECRET)
        mgr = auth_lv4.LV4AuthManager(factors=[factor])
        ok, _ = mgr.authenticate("u", {})  # 未提供 totp 凭据
        self.assertFalse(ok)

    def test_empty_chain_rejected(self):
        ok, msg = auth_lv4.LV4AuthManager(factors=[]).authenticate("u", {})
        self.assertFalse(ok)
        self.assertIn("未注册", msg)

    def test_default_chain_is_totp(self):
        mgr = auth_lv4.LV4AuthManager()
        self.assertEqual(len(mgr.factors), 1)
        self.assertEqual(mgr.factors[0].name, "totp")

    def test_register_factor_appends(self):
        mgr = auth_lv4.LV4AuthManager()
        mgr.register_factor(auth_lv4.BiometricFactor())
        self.assertEqual([f.name for f in mgr.factors], ["totp", "biometric"])

    def test_totp_plus_biometric_and_semantics(self):
        code = auth_lv4.generate_totp(RFC_SECRET, 1000)
        bio = auth_lv4.BiometricFactor()
        mgr = auth_lv4.LV4AuthManager(factors=[auth_lv4.TOTPFactor(secret=RFC_SECRET), bio])
        with mock.patch.object(auth_lv4.time, "time", return_value=1000):
            # 生物认证未接入 → 即使动态密码正确也整体失败
            ok, detail = mgr.authenticate("u", {"totp": code})
            self.assertFalse(ok)
            self.assertIn("生物认证器未接入", detail)
            # 注册后全部通过 → AND 成立
            bio.register_verifier(lambda cred: True)
            ok, _ = mgr.authenticate("u", {"totp": code, "biometric": "ok"})
            self.assertTrue(ok)


class ProvisioningUriTests(unittest.TestCase):
    """provisioning_uri：otpauth:// 形态与参数。"""

    def test_uri_shape_and_params(self):
        uri = auth_lv4.provisioning_uri(account="XUN", issuer="xiaoju3-agent",
                                        secret=RFC_SECRET)
        self.assertTrue(uri.startswith("otpauth://totp/"))
        self.assertIn("xiaoju3-agent%3AXUN", uri)
        self.assertIn(f"secret={RFC_SECRET}", uri)
        self.assertIn("issuer=xiaoju3-agent", uri)
        self.assertIn("digits=6", uri)
        self.assertIn("period=30", uri)
        self.assertIn("algorithm=SHA1", uri)

    def test_reads_env_secret(self):
        env = _env_without_totp()
        env[auth_lv4.TOTP_SECRET_ENV] = RFC_SECRET
        with mock.patch.dict(os.environ, env, clear=True):
            uri = auth_lv4.provisioning_uri()
        self.assertIn(RFC_SECRET, uri)

    def test_unconfigured_returns_empty(self):
        with mock.patch.dict(os.environ, _env_without_totp(), clear=True):
            self.assertEqual(auth_lv4.provisioning_uri(), "")


class RootWarningTests(unittest.TestCase):
    """root_warning：敏感操作清单 + 后果 + 二次确认 + 撤销途径。"""

    def test_warning_contains_required_elements(self):
        text = auth_lv4.root_warning(print_warning=False)
        for keyword in ("LV4", "Root", "写文件", "代码", "门锁", "燃气",
                        "ADB", "手机", "删除数据", "后果", "二次确认",
                        "acknowledge_risk", "revoke_lv4"):
            self.assertIn(keyword, text, f"警告文案缺少要素：{keyword}")

    def test_warning_prints_and_returns(self):
        buf = __import__("io").StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            text = auth_lv4.root_warning(print_warning=True)
        finally:
            sys.stdout = old
        self.assertEqual(text, auth_lv4.ROOT_WARNING)
        self.assertIn("类 Root 权限警告", buf.getvalue())


class GrantFlowTests(unittest.TestCase):
    """授予/撤销流程：未 ack 拒绝、未认证拒绝、通过后授予、revoke 生效。"""

    def _mgr(self):
        return auth_lv4.LV4AuthManager(factors=[_StaticFactor("totp", True)])

    def test_grant_without_ack_rejected(self):
        mgr = self._mgr()
        mgr.authenticate("xun", {})
        msg = mgr.grant_lv4("xun")
        self.assertIn("❌", msg)
        self.assertIn("二次确认", msg)
        self.assertFalse(mgr.is_lv4("xun"))

    def test_grant_without_auth_rejected(self):
        mgr = self._mgr()
        mgr.acknowledge_risk("xun")
        msg = mgr.grant_lv4("xun")
        self.assertIn("❌", msg)
        self.assertIn("多因素认证", msg)
        self.assertFalse(mgr.is_lv4("xun"))

    def test_authenticate_failure_does_not_mark_authenticated(self):
        mgr = auth_lv4.LV4AuthManager(factors=[_StaticFactor("totp", False)])
        ok, _ = mgr.authenticate("xun", {})
        self.assertFalse(ok)
        mgr.acknowledge_risk("xun")
        self.assertIn("❌", mgr.grant_lv4("xun"))
        self.assertFalse(mgr.is_lv4("xun"))

    def test_full_flow_grant_and_revoke(self):
        mgr = self._mgr()
        mgr.acknowledge_risk("xun")
        ok, _ = mgr.authenticate("xun", {"totp": "123456"})
        self.assertTrue(ok)
        msg = mgr.grant_lv4("xun")
        self.assertIn("✅", msg)
        self.assertIn("save_identity", msg)  # 接口约定提示落盘
        self.assertTrue(mgr.is_lv4("xun"))

        msg = mgr.revoke_lv4("xun")
        self.assertIn("✅", msg)
        self.assertFalse(mgr.is_lv4("xun"))

    def test_revoke_requires_reauth(self):
        mgr = self._mgr()
        mgr.acknowledge_risk("xun")
        mgr.authenticate("xun", {})
        mgr.grant_lv4("xun")
        mgr.revoke_lv4("xun")
        # 撤销后认证记录同步清除：不重新认证不能再授予
        self.assertIn("❌", mgr.grant_lv4("xun"))

    def test_revoke_without_grant_is_noop(self):
        mgr = self._mgr()
        msg = mgr.revoke_lv4("nobody")
        self.assertNotIn("✅", msg)
        self.assertIn("未持有", msg)


class SnapshotTests(unittest.TestCase):
    """可选 JSON 快照：save/load roundtrip（tmp 目录，用后即弃）。"""

    def test_snapshot_roundtrip(self):
        mgr = auth_lv4.LV4AuthManager(factors=[_StaticFactor("totp", True)])
        mgr.acknowledge_risk("xun")
        mgr.authenticate("xun", {})
        mgr.grant_lv4("xun")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "lv4_snapshot.json")
            self.assertEqual(mgr.save_snapshot(path), path)

            fresh = auth_lv4.LV4AuthManager(factors=[_StaticFactor("totp", True)])
            self.assertFalse(fresh.is_lv4("xun"))
            self.assertTrue(fresh.load_snapshot(path))
            self.assertTrue(fresh.is_lv4("xun"))
            self.assertIn("xun", fresh.acknowledged)

    def test_snapshot_disabled_by_default(self):
        mgr = auth_lv4.LV4AuthManager()
        self.assertIsNone(mgr.save_snapshot())  # 未配置路径 → 无操作
        self.assertFalse(mgr.load_snapshot())


class ModuleWiringTests(unittest.TestCase):
    """模块级单例与便捷入口、import 零副作用。"""

    def test_singleton_and_wrappers(self):
        self.assertIsInstance(auth_lv4.lv4_manager, auth_lv4.LV4AuthManager)
        # 便捷入口委托单例（用唯一 id，测试后清理）
        uid = "wrapper-test-user"
        try:
            auth_lv4.lv4_manager.acknowledged.add(uid)
            auth_lv4.lv4_manager._authenticated.add(uid)
            self.assertIn("✅", auth_lv4.grant_lv4(uid))
            self.assertTrue(auth_lv4.is_lv4(uid))
            self.assertIn("✅", auth_lv4.revoke_lv4(uid))
            self.assertFalse(auth_lv4.is_lv4(uid))
        finally:
            auth_lv4.lv4_manager.granted.discard(uid)
            auth_lv4.lv4_manager._authenticated.discard(uid)
            auth_lv4.lv4_manager.acknowledged.discard(uid)

    def test_config_key_name(self):
        self.assertEqual(auth_lv4.TOTP_SECRET_ENV, "XIAOJU3_TOTP_SECRET")

    def test_importable_and_contract_names(self):
        for name in ("generate_totp", "verify_totp", "provisioning_uri",
                     "Factor", "TOTPFactor", "BiometricFactor",
                     "LV4AuthManager", "root_warning", "grant_lv4", "revoke_lv4"):
            self.assertTrue(callable(getattr(auth_lv4, name)), name)


if __name__ == "__main__":
    unittest.main()
