# -*- coding: utf-8 -*-
"""tools 单元测试：§7 权限新表门禁（write_file 逐次 TOTP、control_ha_device
普通/危险动态分类、system_manage 三重门禁、read_file/list_files Lv.2 门槛、
adb 维持 Lv.3、web_search Lv.1 不设限）、沙箱逃逸、参数校验、白名单 12 项。

【用户指定四用例（必须显式覆盖）】见 UserMandatedGateTests：
  ① Lv.2 无法写入文件（write_file 拒绝文案）
  ② Lv.3 能写入文件，但需正确 TOTP（错码拒绝/正确码+窗口内成功）
  ③ Lv.2 无法控制危险设备（is_dangerous_entity=True 实体被拒）
  ④ Lv.4 能控制危险设备，但需动态密码+生物认证模拟（缺任一因子拒绝）

外部模块（home_tools / adb_tools / vision_tools / android_ui_tools）由
并行开发负责，这里用 sys.modules 注入 mock（且先移除真实模块），保证
测试离线、确定，不依赖它们真实存在。注入必须发生在 import tools 之前。
search_tools 为本阶段新增的真实模块（仅依赖 requests），网络一律 mock。
TOTP 用 auth_lv4 RFC 参考密钥（真实时间生成/校验同窗，确定通过）；
env 键 XIAOJU3_TOTP_SECRET 经 mock.patch.dict 注入，用后自动还原。
"""
import os
import sys
import types
import unittest
from unittest import mock
import shutil
import tempfile


# ---------------------------------------------------------------------------
# 注入外部模块 mock（必须在 import tools 之前）
# ---------------------------------------------------------------------------

def _is_dangerous(entity_id):
    """与 home_tools.is_dangerous_entity 同口径的 mock 分类（lock.*/gas/燃气）。"""
    eid = str(entity_id or "")
    lower = eid.lower()
    return lower.split(".", 1)[0] == "lock" or "gas" in lower or "燃气" in eid


def _install_mock_modules():
    for name in ("home_tools", "adb_tools", "vision_tools", "android_ui_tools"):
        sys.modules.pop(name, None)

    home_tools = types.ModuleType("home_tools")
    home_tools.get_ha_devices = lambda: "【mock】设备列表：light.test=on"
    home_tools.control_ha_device = (
        lambda entity_id, action, temperature=None:
        f"【mock】已对 {entity_id} 执行 {action}"
        + (f" 温度{temperature}" if temperature is not None else ""))
    home_tools.is_dangerous_entity = _is_dangerous
    sys.modules["home_tools"] = home_tools

    adb_tools = types.ModuleType("adb_tools")
    adb_tools.adb_screenshot = lambda: "【mock】截图已保存"
    adb_tools.adb_tap = lambda x, y: f"【mock】点击 {x},{y}"
    adb_tools.adb_swipe = lambda x1, y1, x2, y2: f"【mock】滑动 {x1},{y1}->{x2},{y2}"
    sys.modules["adb_tools"] = adb_tools

    vision_tools = types.ModuleType("vision_tools")
    vision_tools.vision_tap_element = lambda name: f"【mock】视觉点击 {name}"
    sys.modules["vision_tools"] = vision_tools

    android_ui_tools = types.ModuleType("android_ui_tools")
    android_ui_tools.ui_tap_element = lambda name: f"【mock】UI 点击 {name}"
    sys.modules["android_ui_tools"] = android_ui_tools


_install_mock_modules()

import tools
import auth_lv4
import search_tools
from permission import PermissionManager

# 归一化绑定：discover 全量下 test_brain 等更早导入的测试文件会先注入一份
# 自己的外围 mock，tools 模块可能已绑定旧版（无 is_dangerous_entity /
# control_ha_device 无 temperature 形参）；这里统一重绑为本文件的 mock，
# 保证"全量 discover"与"单模块运行"行为一致（单模块运行时为等值重绑）。
_mock_ht = sys.modules["home_tools"]
_mock_at = sys.modules["adb_tools"]
_mock_vt = sys.modules["vision_tools"]
_mock_ut = sys.modules["android_ui_tools"]
tools.home_tools = _mock_ht
tools.get_ha_devices = _mock_ht.get_ha_devices
tools.control_ha_device = _mock_ht.control_ha_device
tools.adb_screenshot = _mock_at.adb_screenshot
tools.adb_tap = _mock_at.adb_tap
tools.adb_swipe = _mock_at.adb_swipe
tools.vision_tap_element = _mock_vt.vision_tap_element
tools.ui_tap_element = _mock_ut.ui_tap_element

# RFC 6238 附录 B SHA1 参考密钥（Base32），与 tests/test_auth_lv4.py 同源
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
TOTP_ENV = {auth_lv4.TOTP_SECRET_ENV: RFC_SECRET}


def _totp_now():
    """按当前真实时间生成动态密码（校验同在当前时间 ±1 窗口内，确定通过）。"""
    return auth_lv4.generate_totp(RFC_SECRET)


class ToolsTestBase(unittest.TestCase):
    """公共基座：tempfile 设 WORKSPACE（按参考实现的注入方式），用后还原。"""

    def setUp(self):
        self.ws = tempfile.mkdtemp(prefix="xiaoju3_ws_")
        self._old_ws = tools.WORKSPACE
        tools.WORKSPACE = self.ws

    def tearDown(self):
        tools.WORKSPACE = self._old_ws
        shutil.rmtree(self.ws, ignore_errors=True)

    def _pm(self, level):
        pm = PermissionManager()
        pm.current_level = level
        return pm

    def _pm3_with_window(self):
        """Lv.3 + 已开写操作窗口（等效 /sudo 通道，供沙箱/正常写路径测试）。"""
        pm = self._pm("Lv.3")
        pm.open_operation_window(ttl_seconds=120)
        return pm

    def _pm4_with_bio(self, bio_ok=True):
        """Lv.4 + 已注册生物认证模拟（mock verifier）。"""
        pm = self._pm("Lv.4")
        pm.register_biometric_verifier(lambda cred: bio_ok)
        return pm

    def _lv4_credentials(self, confirmed=True):
        """Lv.4 双因子凭据：TOTP（真实时间生成）+ 生物凭据 + 二次确认标记。"""
        creds = {"totp": _totp_now(), "biometric": "face-id-ok"}
        if confirmed:
            creds["confirmed"] = True
        return creds


class WhitelistTests(ToolsTestBase):
    """白名单 12 项与 DANGER_TOOLS 集合语义。"""

    def test_whitelist_has_twelve_tools(self):
        # §7：11 项 + 新增 system_manage = 12 项
        self.assertEqual(len(tools.TOOL_WHITELIST), 12)
        self.assertEqual(
            sorted(tools.TOOL_WHITELIST),
            sorted(["list_files", "read_file", "write_file", "get_ha_devices",
                    "control_ha_device", "adb_tap", "adb_swipe", "adb_screenshot",
                    "vision_tap_element", "ui_tap_element", "web_search",
                    "system_manage"]))

    def test_danger_tools_constant(self):
        # 旧集合成员不变，门禁语义升级为 §7 新表（见各专项测试）
        self.assertEqual(
            tools.DANGER_TOOLS,
            {"write_file", "adb_tap", "adb_swipe", "control_ha_device"},
        )


class UserMandatedGateTests(ToolsTestBase):
    """【用户指定四用例】权限新表下 write_file / 危险家居的门禁行为。"""

    # ------------------------------------------------------------------ ①
    def test_case1_lv2_cannot_write_file(self):
        # ① Lv.2 无法写入文件：等级拒绝 + 升级引导文案
        pm = self._pm("Lv.2")
        r = tools.execute_tool(
            "write_file", {"filename": "a.txt", "content": "hi"}, pm)
        self.assertTrue(r.startswith("❌ 安全拒绝"), r)
        self.assertIn("当前权限不足", r)
        self.assertIn("Lv.3", r)
        self.assertIn("/coder_auth", r)
        self.assertFalse(os.path.exists(os.path.join(self.ws, "a.txt")))

    # ------------------------------------------------------------------ ②
    def test_case2_lv3_write_needs_correct_totp(self):
        # ② Lv.3 能写入文件，但需正确 TOTP：错码拒绝
        pm = self._pm("Lv.3")
        with mock.patch.dict(os.environ, TOTP_ENV):
            r = tools.execute_tool(
                "write_file", {"filename": "a.txt", "content": "hi"}, pm,
                {"totp": "000000"})
        self.assertTrue(r.startswith("❌ 安全拒绝"), r)
        self.assertIn("逐次动态密码", r)
        self.assertIn("/sudo", r)          # 引导用 /sudo <动态密码> 开窗口
        self.assertFalse(os.path.exists(os.path.join(self.ws, "a.txt")))

    def test_case2_lv3_write_with_correct_totp_credential(self):
        # ② 正确码（凭据通道）→ 写入成功
        pm = self._pm("Lv.3")
        with mock.patch.dict(os.environ, TOTP_ENV):
            r = tools.execute_tool(
                "write_file", {"filename": "a.txt", "content": "数据"}, pm,
                {"totp": _totp_now()})
        self.assertEqual(r, "✅ 文件 a.txt 写入成功！")
        with open(os.path.join(self.ws, "a.txt"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "数据")

    def test_case2_lv3_write_within_open_window(self):
        # ② 正确码（/sudo 窗口通道）→ 窗口内写入成功
        # （按当前真实时间开窗：TOTP 生成/校验同窗确定通过，过期线为真实时刻+TTL）
        pm = self._pm("Lv.3")
        with mock.patch.dict(os.environ, TOTP_ENV):
            msg = pm.open_operation_window(
                ttl_seconds=120, totp_code=auth_lv4.generate_totp(RFC_SECRET))
        self.assertTrue(msg.startswith("✅"), msg)
        r = tools.execute_tool(
            "write_file", {"filename": "b.txt", "content": "窗口内写入"}, pm)
        self.assertEqual(r, "✅ 文件 b.txt 写入成功！")

    # ------------------------------------------------------------------ ③
    def test_case3_lv2_cannot_control_dangerous_device(self):
        # ③ Lv.2 无法控制危险设备（is_dangerous_entity=True 实体被拒）
        pm = self._pm("Lv.2")
        r = tools.execute_tool(
            "control_ha_device",
            {"entity_id": "lock.front_door", "action": "turn_on"}, pm)
        self.assertTrue(r.startswith("❌ 安全拒绝"), r)
        self.assertIn("lock.front_door", r)
        self.assertIn("高危", r)
        self.assertIn("Lv.4", r)

    def test_case3_lv3_also_cannot_control_dangerous_device(self):
        # ③ 延伸：Lv.3 仍未达危险设备门槛（需 Lv.4）
        pm = self._pm("Lv.3")
        r = tools.execute_tool(
            "control_ha_device",
            {"entity_id": "switch.gas_valve", "action": "turn_off"}, pm)
        self.assertTrue(r.startswith("❌ 安全拒绝"), r)
        self.assertIn("Lv.4", r)

    # ------------------------------------------------------------------ ④
    def test_case4_lv4_controls_dangerous_device_with_dual_factor(self):
        # ④ Lv.4 能控制危险设备，但需动态密码+生物认证模拟：
        #    TOTP 正确 + mock 生物因子 True → 成功
        pm = self._pm4_with_bio(bio_ok=True)
        with mock.patch.dict(os.environ, TOTP_ENV):
            r = tools.execute_tool(
                "control_ha_device",
                {"entity_id": "lock.front_door", "action": "turn_on"}, pm,
                self._lv4_credentials())
        self.assertIn("已对 lock.front_door 执行 turn_on", r)

    def test_case4_lv4_dangerous_device_missing_biometric_rejected(self):
        # ④ 缺生物因子（未注册认证器）→ 拒绝且提示"生物认证器未接入"
        pm = self._pm("Lv.4")  # 不注册生物认证器
        with mock.patch.dict(os.environ, TOTP_ENV):
            r = tools.execute_tool(
                "control_ha_device",
                {"entity_id": "lock.front_door", "action": "turn_on"}, pm,
                {"totp": _totp_now()})
        self.assertTrue(r.startswith("❌ 安全拒绝"), r)
        self.assertIn("双因子", r)
        self.assertIn("生物认证器未接入", r)

    def test_case4_lv4_dangerous_device_wrong_totp_rejected(self):
        # ④ 动态密码错误（生物 mock 通过）→ 拒绝
        pm = self._pm4_with_bio(bio_ok=True)
        with mock.patch.dict(os.environ, TOTP_ENV):
            r = tools.execute_tool(
                "control_ha_device",
                {"entity_id": "lock.front_door", "action": "turn_on"}, pm,
                {"totp": "000000", "biometric": "face-id-ok"})
        self.assertTrue(r.startswith("❌ 安全拒绝"), r)
        self.assertIn("双因子", r)


class LevelGateTests(ToolsTestBase):
    """各等级门槛：read_file/list_files Lv.2、adb Lv.3、web_search Lv.1。"""

    def test_read_file_requires_lv2(self):
        # 用户调整点：旧口径 LV1 可读 → 新表 Lv.2 才可读
        pm = self._pm("Lv.1")
        with open(os.path.join(self.ws, "x.txt"), "w", encoding="utf-8") as f:
            f.write("hi")
        r = tools.execute_tool("read_file", {"filename": "x.txt"}, pm)
        self.assertTrue(r.startswith("❌ 安全拒绝：当前权限不足"), r)
        self.assertIn("Lv.2", r)
        self.assertIn("/register", r)
        # Lv.2 起放行
        r2 = tools.execute_tool("read_file", {"filename": "x.txt"},
                                self._pm("Lv.2"))
        self.assertEqual(r2, "hi")

    def test_list_files_requires_lv2(self):
        r = tools.execute_tool("list_files", {}, self._pm("Lv.1"))
        self.assertTrue(r.startswith("❌ 安全拒绝：当前权限不足"), r)
        r2 = tools.execute_tool("list_files", {}, self._pm("Lv.2"))
        self.assertEqual(r2, "（工作区为空）")

    def test_adb_stays_lv3_without_operation_totp(self):
        # adb_tap / adb_swipe 维持 Lv.3，无逐次动态密码要求
        pm = self._pm("Lv.3")
        self.assertIn("点击 10,20",
                      tools.execute_tool("adb_tap", {"x": 10, "y": 20}, pm))
        self.assertIn("滑动 1,2->3,4",
                      tools.execute_tool(
                          "adb_swipe", {"x1": 1, "y1": 2, "x2": 3, "y2": 4}, pm))

    def test_adb_below_lv3_rejected(self):
        for level in ("Lv.1", "Lv.2"):
            pm = self._pm(level)
            r = tools.execute_tool("adb_tap", {"x": 1, "y": 2}, pm)
            self.assertTrue(r.startswith("❌ 安全拒绝：当前权限不足"), (level, r))
            self.assertIn("Lv.3", r)

    def test_gate_precedes_param_check(self):
        # 门禁优先于参数校验：Lv.1 传空参数也应先吃安全拒绝
        r = tools.execute_tool("adb_tap", {}, self._pm("Lv.1"))
        self.assertTrue(r.startswith("❌ 安全拒绝：当前权限不足"))

    def test_web_search_is_lv1_not_danger_tool(self):
        # 联网搜索属 Lv.1（§7 表），不进 DANGER_TOOLS 门禁
        self.assertNotIn("web_search", tools.DANGER_TOOLS)
        with mock.patch.object(tools, "web_search") as mws:
            mws.return_value = "🔍 ok"
            r = tools.execute_tool(
                "web_search", {"query": "q"}, self._pm("Lv.1"))
        self.assertEqual(r, "🔍 ok")


class DeviceControlGateTests(ToolsTestBase):
    """control_ha_device 动态分类门禁与 temperature 透传。"""

    def test_normal_device_requires_lv2(self):
        # 普通实体：Lv.1 拒绝（Lv.2 门槛），Lv.2 放行
        pm = self._pm("Lv.1")
        r = tools.execute_tool(
            "control_ha_device",
            {"entity_id": "light.test", "action": "turn_on"}, pm)
        self.assertTrue(r.startswith("❌ 安全拒绝"), r)
        self.assertIn("Lv.2", r)
        self.assertIn("/register", r)
        r2 = tools.execute_tool(
            "control_ha_device",
            {"entity_id": "light.test", "action": "turn_on"}, self._pm("Lv.2"))
        self.assertIn("已对 light.test 执行 turn_on", r2)

    def test_dangerous_device_classification_via_home_tools(self):
        # 分类走 home_tools.is_dangerous_entity（lock./gas/燃气 → True）
        pm = self._pm("Lv.2")
        for entity in ("lock.front_door", "switch.gas_valve", "sensor.燃气报警"):
            r = tools.execute_tool(
                "control_ha_device",
                {"entity_id": entity, "action": "toggle"}, pm)
            self.assertIn("Lv.4", r, entity)

    def test_dangerous_device_lv4_without_mfa_rejected(self):
        # 危险实体 + Lv.4 但双因子未通过（未注册生物认证器）→ 拒绝
        pm = self._pm("Lv.4")
        with mock.patch.dict(os.environ, TOTP_ENV):
            r = tools.execute_tool(
                "control_ha_device",
                {"entity_id": "lock.front_door", "action": "turn_on"}, pm,
                {"totp": _totp_now()})
        self.assertTrue(r.startswith("❌ 安全拒绝"), r)
        self.assertIn("双因子", r)

    def test_control_ha_device_missing_args(self):
        r = tools.execute_tool("control_ha_device", {}, self._pm("Lv.3"))
        self.assertEqual(r, "❌ 缺少参数：需要提供 entity_id 和 action")

    def test_temperature_passthrough(self):
        # 补 S3 待办：args 中的 temperature 透传给 home_tools.control_ha_device
        pm = self._pm("Lv.2")
        with mock.patch.object(tools, "control_ha_device") as mctrl:
            mctrl.return_value = "✅ ok"
            tools.execute_tool(
                "control_ha_device",
                {"entity_id": "climate.ac", "action": "set_temperature",
                 "temperature": 26}, pm)
        mctrl.assert_called_once_with("climate.ac", "set_temperature",
                                      temperature=26)

    def test_temperature_omitted_passes_none(self):
        pm = self._pm("Lv.2")
        with mock.patch.object(tools, "control_ha_device") as mctrl:
            mctrl.return_value = "✅ ok"
            tools.execute_tool(
                "control_ha_device",
                {"entity_id": "light.test", "action": "turn_on"}, pm)
        mctrl.assert_called_once_with("light.test", "turn_on", temperature=None)


class SystemManageTests(ToolsTestBase):
    """system_manage：三重门禁（Lv.4 + 双因子 + 二次确认）与 component 防注入。"""

    def test_missing_params(self):
        pm = self._pm("Lv.4")
        self.assertEqual(
            tools.execute_tool("system_manage", {}, pm),
            "❌ 缺少参数：需要提供 action (install/uninstall) 和 component (组件名)")
        self.assertEqual(
            tools.execute_tool(
                "system_manage", {"action": "install"}, pm),
            "❌ 缺少参数：需要提供 action (install/uninstall) 和 component (组件名)")

    def test_invalid_action(self):
        pm = self._pm("Lv.4")
        r = tools.execute_tool(
            "system_manage", {"action": "upgrade", "component": "flask"}, pm)
        self.assertTrue(r.startswith("❌ 不支持的 action"), r)

    def test_component_injection_rejected(self):
        # component 名校验：注入形态一律拦截（仅字母数字 ._-，且不得以 - 开头）
        pm = self._pm("Lv.4")
        pm.register_biometric_verifier(lambda cred: True)
        bad_names = ["flask;rm -rf /", "pkg && evil", "a b", "-r", "--index-url",
                     "pkg$(whoami)", "pkg`id`", "../evil", "pkg|x", "包 名",
                     "flask\t"]
        for name in bad_names:
            with mock.patch.dict(os.environ, TOTP_ENV):
                r = tools.execute_tool(
                    "system_manage",
                    {"action": "install", "component": name}, pm,
                    self._lv4_credentials())
            self.assertTrue(r.startswith("❌ 安全拒绝"), (name, r))
            self.assertIn("注入", r)

    def test_requires_lv4(self):
        # 第一重门禁：等级（Lv.3 及以下拒绝）
        pm = self._pm("Lv.3")
        r = tools.execute_tool(
            "system_manage",
            {"action": "install", "component": "flask"}, pm)
        self.assertTrue(r.startswith("❌ 安全拒绝：当前权限不足"), r)
        self.assertIn("Lv.4", r)

    def test_requires_mfa(self):
        # 第二重门禁：双因子（Lv.4 但认证未通过）
        pm = self._pm("Lv.4")
        r = tools.execute_tool(
            "system_manage",
            {"action": "install", "component": "flask"}, pm,
            {"totp": "000000"})
        self.assertTrue(r.startswith("❌ 安全拒绝"), r)
        self.assertIn("双因子", r)

    def test_requires_confirmation(self):
        # 第三重门禁：二次确认标记 credentials["confirmed"]=True
        pm = self._pm4_with_bio(bio_ok=True)
        creds = self._lv4_credentials(confirmed=False)
        with mock.patch.dict(os.environ, TOTP_ENV):
            r = tools.execute_tool(
                "system_manage",
                {"action": "install", "component": "flask"}, pm, creds)
        self.assertTrue(r.startswith("❌ 安全拒绝"), r)
        self.assertIn("二次确认", r)

    def test_install_success_maps_pip_command(self):
        # 三重门禁全通过 → pip install（subprocess 封装，mock 校验命令构造）
        pm = self._pm4_with_bio(bio_ok=True)
        proc = mock.Mock(returncode=0, stderr="", stdout="ok")
        with mock.patch.dict(os.environ, TOTP_ENV), \
                mock.patch.object(tools.subprocess, "run",
                                  return_value=proc) as mrun:
            r = tools.execute_tool(
                "system_manage",
                {"action": "install", "component": "flask"}, pm,
                self._lv4_credentials())
        self.assertEqual(r, "✅ 组件 flask 安装完成！")
        args, kwargs = mrun.call_args
        self.assertEqual(args[0],
                         [sys.executable, "-m", "pip", "install", "flask"])
        self.assertEqual(kwargs["timeout"], 600)

    def test_uninstall_success_maps_pip_command(self):
        pm = self._pm4_with_bio(bio_ok=True)
        proc = mock.Mock(returncode=0, stderr="", stdout="ok")
        creds = self._lv4_credentials()
        with mock.patch.dict(os.environ, TOTP_ENV), \
                mock.patch.object(tools.subprocess, "run",
                                  return_value=proc) as mrun:
            r = tools.execute_tool(
                "system_manage",
                {"action": "uninstall", "component": "playwright"}, pm, creds)
        self.assertEqual(r, "✅ 组件 playwright 卸载完成！")
        args, _ = mrun.call_args
        self.assertEqual(args[0],
                         [sys.executable, "-m", "pip", "uninstall", "-y",
                          "playwright"])

    def test_pip_failure_returns_chinese_error(self):
        pm = self._pm4_with_bio(bio_ok=True)
        proc = mock.Mock(returncode=1, stderr="No matching distribution", stdout="")
        with mock.patch.dict(os.environ, TOTP_ENV), \
                mock.patch.object(tools.subprocess, "run", return_value=proc):
            r = tools.execute_tool(
                "system_manage",
                {"action": "install", "component": "no-such-pkg"}, pm,
                self._lv4_credentials())
        self.assertTrue(r.startswith("❌"), r)
        self.assertIn("No matching distribution", r)

    def test_subprocess_exception_wrapped(self):
        pm = self._pm4_with_bio(bio_ok=True)
        with mock.patch.dict(os.environ, TOTP_ENV), \
                mock.patch.object(tools.subprocess, "run",
                                  side_effect=OSError("boom")):
            r = tools.execute_tool(
                "system_manage",
                {"action": "install", "component": "flask"}, pm,
                self._lv4_credentials())
        self.assertTrue(r.startswith("❌"), r)
        self.assertIn("boom", r)


class SandboxTests(ToolsTestBase):
    """工作区沙箱：realpath 前缀校验，拒绝一切逃逸路径。"""

    def test_read_file_dotdot_escape_rejected(self):
        pm = self._pm("Lv.3")
        for name in ("../secret.txt", "a/../../escape.txt", ".."):
            r = tools.execute_tool("read_file", {"filename": name}, pm)
            self.assertEqual(
                r, "❌ 安全拒绝：不允许访问工作区以外的文件！", name)

    def test_write_file_dotdot_escape_rejected(self):
        # 写路径沙箱：凭据通道内仍拒绝越界（TOTP 已过 → 沙箱把关）
        pm = self._pm("Lv.3")
        with mock.patch.dict(os.environ, TOTP_ENV):
            r = tools.execute_tool(
                "write_file", {"filename": "../evil.txt", "content": "x"}, pm,
                {"totp": _totp_now()})
        self.assertEqual(r, "❌ 安全拒绝：不允许访问工作区以外的文件！")
        self.assertFalse(os.path.exists(
            os.path.join(self.ws, "..", "evil.txt")))

    def test_write_operation_gate_precedes_sandbox(self):
        # 凭据先于路径校验：未携逐次动态密码时，越界路径也不泄露沙箱判定
        pm = self._pm("Lv.3")
        r = tools.execute_tool(
            "write_file", {"filename": "../evil.txt", "content": "x"}, pm)
        self.assertTrue(r.startswith("❌ 安全拒绝"), r)
        self.assertIn("逐次动态密码", r)

    def test_absolute_path_outside_rejected(self):
        outside = tempfile.mkdtemp(prefix="xiaoju3_out_")
        try:
            target = os.path.join(outside, "x.txt")
            pm = self._pm3_with_window()  # Lv.3 + 写操作窗口
            r1 = tools.execute_tool("read_file", {"filename": target}, pm)
            r2 = tools.execute_tool(
                "write_file", {"filename": target, "content": "x"}, pm)
            self.assertEqual(r1, "❌ 安全拒绝：不允许访问工作区以外的文件！")
            self.assertEqual(r2, "❌ 安全拒绝：不允许访问工作区以外的文件！")
            self.assertFalse(os.path.exists(target))
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_sibling_prefix_path_rejected(self):
        # 与工作区同名前缀的兄弟目录（ws_xxx_evil）不是工作区内部，必须拒绝
        parent = os.path.dirname(os.path.abspath(self.ws))
        sibling = os.path.join(
            parent, os.path.basename(self.ws) + "_evil", "x.txt")
        r = tools.execute_tool("read_file", {"filename": sibling}, self._pm("Lv.3"))
        self.assertEqual(r, "❌ 安全拒绝：不允许访问工作区以外的文件！")

    def test_absolute_path_inside_workspace_allowed(self):
        inside = os.path.join(self.ws, "a.txt")
        with open(inside, "w", encoding="utf-8") as f:
            f.write("hello")
        r = tools.execute_tool("read_file", {"filename": inside}, self._pm("Lv.3"))
        self.assertEqual(r, "hello")


class FileToolTests(ToolsTestBase):
    """list_files / read_file / write_file 正常路径（新表等级口径）。"""

    def test_list_files_empty_workspace(self):
        r = tools.execute_tool("list_files", {}, self._pm("Lv.2"))
        self.assertEqual(r, "（工作区为空）")

    def test_list_files(self):
        with open(os.path.join(self.ws, "b.txt"), "w", encoding="utf-8") as f:
            f.write("1")
        with open(os.path.join(self.ws, "a.txt"), "w", encoding="utf-8") as f:
            f.write("2")
        os.makedirs(os.path.join(self.ws, "sub"))
        r = tools.execute_tool("list_files", {}, self._pm("Lv.2"))
        self.assertIn("a.txt", r)
        self.assertIn("b.txt", r)
        self.assertIn("[目录] sub", r)

    def test_write_file_creates_subdir(self):
        r = tools.execute_tool(
            "write_file", {"filename": "sub/dir/a.txt", "content": "内容"},
            self._pm3_with_window())
        self.assertTrue(r.startswith("✅"))
        with open(os.path.join(self.ws, "sub", "dir", "a.txt"),
                  "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "内容")

    def test_read_file_existing(self):
        with open(os.path.join(self.ws, "note.txt"), "w", encoding="utf-8") as f:
            f.write("你好，小橘3号！")
        r = tools.execute_tool("read_file", {"filename": "note.txt"}, self._pm("Lv.2"))
        self.assertEqual(r, "你好，小橘3号！")

    def test_read_file_missing(self):
        r = tools.execute_tool("read_file", {"filename": "nope.txt"}, self._pm("Lv.2"))
        self.assertEqual(r, "文件 nope.txt 不存在。")

    def test_read_file_truncates_to_1000_chars(self):
        with open(os.path.join(self.ws, "long.txt"), "w", encoding="utf-8") as f:
            f.write("橘" * 1500)
        r = tools.execute_tool("read_file", {"filename": "long.txt"}, self._pm("Lv.2"))
        self.assertEqual(len(r), 1000)


class ToolBehaviorTests(ToolsTestBase):
    """其余工具分发行为与异常包装。"""

    def test_unknown_tool(self):
        r = tools.execute_tool("no_such_tool", {}, self._pm("Lv.1"))
        self.assertEqual(r, "未知工具")

    def test_get_ha_devices_passthrough(self):
        r = tools.execute_tool("get_ha_devices", {}, self._pm("Lv.1"))
        self.assertIn("设备列表", r)

    def test_adb_screenshot_passthrough(self):
        r = tools.execute_tool("adb_screenshot", {}, self._pm("Lv.3"))
        self.assertIn("截图", r)

    def test_adb_tap_missing_args(self):
        r = tools.execute_tool("adb_tap", {"x": 1}, self._pm("Lv.3"))
        self.assertEqual(r, "❌ 缺少参数：需要提供 x 和 y 坐标")

    def test_adb_tap_coerces_int(self):
        r = tools.execute_tool(
            "adb_tap", {"x": "12", "y": "34"}, self._pm("Lv.3"))
        self.assertIn("点击 12,34", r)

    def test_adb_swipe_coerces_int(self):
        r = tools.execute_tool(
            "adb_swipe",
            {"x1": "500", "y1": "1500", "x2": "500", "y2": "500"},
            self._pm("Lv.3"))
        self.assertIn("滑动 500,1500->500,500", r)

    def test_vision_tap_element(self):
        pm = self._pm("Lv.3")
        self.assertEqual(
            tools.execute_tool(
                "vision_tap_element", {}, pm),
            "❌ 缺少参数：需要提供 element_name (要点击的文字/图标名称)")
        self.assertIn("视觉点击 设置",
                      tools.execute_tool(
                          "vision_tap_element", {"element_name": "设置"}, pm))

    def test_ui_tap_element(self):
        pm = self._pm("Lv.3")
        self.assertEqual(
            tools.execute_tool("ui_tap_element", {}, pm),
            "❌ 缺少参数：需要提供 element_name (要点击的按钮或图标名称)")
        self.assertIn("UI 点击 设置",
                      tools.execute_tool(
                          "ui_tap_element", {"element_name": "设置"}, pm))

    def test_exception_wrapped(self):
        # 把目录当文件读 → 内部异常被包装，不向外抛
        os.makedirs(os.path.join(self.ws, "adir"))
        r = tools.execute_tool("read_file", {"filename": "adir"}, self._pm("Lv.2"))
        self.assertTrue(r.startswith("工具执行失败: "))

    def test_execute_tool_backward_compatible_three_args(self):
        # 向后兼容：旧三参调用（无 credentials）不报错，门禁按无凭据处理
        r = tools.execute_tool(
            "write_file", {"filename": "a.txt", "content": "x"}, self._pm("Lv.3"))
        self.assertTrue(r.startswith("❌"), r)  # 缺逐次动态密码 → 拒绝


class WebSearchDispatchTests(ToolsTestBase):
    """第 11 项白名单工具 web_search 经 execute_tool 的分发行为。"""

    def test_web_search_dispatches_with_default_max_results(self):
        with mock.patch.object(tools, "web_search") as mws:
            mws.return_value = "🔍 搜索结果"
            r = tools.execute_tool(
                "web_search", {"query": "小橘3号"}, self._pm("Lv.1"))
        self.assertEqual(r, "🔍 搜索结果")
        mws.assert_called_once_with("小橘3号", 5)

    def test_web_search_passes_max_results(self):
        with mock.patch.object(tools, "web_search") as mws:
            tools.execute_tool(
                "web_search", {"query": "q", "max_results": 3}, self._pm("Lv.3"))
        mws.assert_called_once_with("q", 3)

    def test_web_search_missing_query(self):
        r = tools.execute_tool("web_search", {}, self._pm("Lv.1"))
        self.assertEqual(r, "❌ 缺少参数：需要提供 query (搜索关键词)")


class SearchToolsUnitTests(unittest.TestCase):
    """search_tools.web_search：HTML 解析、跳转链接还原、异常中文提示。

    网络一律 mock（第二阶段规范：测试离线可跑）。
    """

    DDG_HTML = """
    <html><body>
    <div class="result results_links results_links_deep web-result">
      <h2 class="result__title">
        <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&rut=abc">小橘3号 <b>官网</b></a>
      </h2>
      <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&rut=abc">这是<b>摘要</b>内容</a>
    </div>
    <div class="result">
      <h2><a class="result__a" href="https://direct.example.com/b">直链结果</a></h2>
      <a class="result__snippet">第二个摘要</a>
    </div>
    </body></html>
    """

    def _resp(self, text):
        resp = mock.Mock()
        resp.text = text
        resp.raise_for_status = mock.Mock()
        return resp

    def test_parser_extracts_title_url_snippet(self):
        parser = search_tools._DDGResultParser()
        parser.feed(self.DDG_HTML)
        parser.close()
        self.assertEqual(len(parser.results), 2)
        first = parser.results[0]
        self.assertEqual(first["title"], "小橘3号 官网")
        self.assertEqual(first["snippet"], "这是摘要内容")
        self.assertEqual(first["url"], "https://example.com/a")
        second = parser.results[1]
        self.assertEqual(second["title"], "直链结果")
        self.assertEqual(second["url"], "https://direct.example.com/b")
        self.assertEqual(second["snippet"], "第二个摘要")

    def test_clean_url_unwraps_ddg_redirect(self):
        self.assertEqual(
            search_tools._clean_url(
                "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fx&rut=1"),
            "https://example.com/x")
        self.assertEqual(
            search_tools._clean_url("https://plain.example.com"),
            "https://plain.example.com")
        self.assertEqual(search_tools._clean_url(""), "")
        self.assertEqual(search_tools._clean_url(None), "")

    def test_web_search_success_format_and_request(self):
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = self._resp(self.DDG_HTML)
            out = search_tools.web_search("小橘3号", max_results=1)

        self.assertIn("🔍 联网搜索「小橘3号」的结果：", out)
        self.assertIn("1. 小橘3号 官网 - 这是摘要内容 链接：https://example.com/a", out)
        self.assertNotIn("直链结果", out)          # max_results=1 截断

        args, kwargs = mr.get.call_args
        self.assertEqual(args[0], search_tools.SEARCH_URL)
        self.assertEqual(kwargs["params"], {"q": "小橘3号"})
        self.assertIn("Mozilla", kwargs["headers"]["User-Agent"])  # UA 伪装
        self.assertEqual(kwargs["timeout"], search_tools.SEARCH_TIMEOUT)
        self.assertLessEqual(kwargs["timeout"], 10)

    def test_web_search_no_results(self):
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = self._resp("<html><body>没有结果</body></html>")
            out = search_tools.web_search("不存在的东西")
        self.assertIn("未搜到", out)

    def test_web_search_empty_query(self):
        self.assertIn("❌", search_tools.web_search("   "))

    def test_web_search_error_returns_chinese_message(self):
        # 异常不向外抛，返回中文错误串（供工具层直接喂回模型）
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.side_effect = OSError("timed out")
            out = search_tools.web_search("查询")
        self.assertTrue(out.startswith("❌ 联网搜索失败"), out)
        self.assertIn("timed out", out)

    def test_web_search_invalid_max_results_falls_back_to_default(self):
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = self._resp(self.DDG_HTML)
            out = search_tools.web_search("q", max_results="abc")
        self.assertIn("直链结果", out)              # 非法条数回退默认 5

    def test_default_max_results_is_five(self):
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = self._resp(self.DDG_HTML)
            out = search_tools.web_search("q")
        self.assertIn("1. 小橘3号 官网", out)
        self.assertIn("2. 直链结果", out)


if __name__ == "__main__":
    unittest.main()
