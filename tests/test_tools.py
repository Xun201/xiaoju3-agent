# -*- coding: utf-8 -*-
"""tools 单元测试：§7 权限新表门禁（write_file 免逐次动态密码——2026-09-30
用户指令取消逐次 /sudo，Lv.3 等级门禁保留、control_ha_device 普通/危险动态
分类、system_manage 三重门禁、read_file/list_files Lv.2 门槛、adb 维持 Lv.3、
web_search Lv.1 不设限）、沙箱逃逸、参数校验、白名单 12 项；
ui_tap_element 解析失败 → 代码级强制回退 vision_tap_element（用户指令，
见 VisionFallbackTests：ui 失败必回退、双失败补配置指引、ui 成功不调
vision、Lv.3 门禁先于回退、回退只发生一次）+ 未配置短路检查（见
VisionShortCircuitTests：VISION_MODEL / VISION_KEY 任一为空/None → 直接
返回"❌ 未配置视觉模型，无法执行点击"，vision 绝不被调用）。

【用户指定四用例（必须显式覆盖）】见 UserMandatedGateTests：
  ① Lv.2 无法写入文件（write_file 拒绝文案）
  ② Lv.3 能写入文件，无需 TOTP 直接成功（2026-09-30 用户指令取消逐次
    动态密码要求，原"需正确 TOTP"口径作废；等级门禁保留）
  ③ Lv.2 无法控制危险设备（is_dangerous_entity=True 实体被拒）
  ④ Lv.4 能控制危险设备，但需动态密码+生物认证模拟（缺任一因子拒绝）

外部模块（home_tools / adb_tools / vision_tools / android_ui_tools）由
并行开发负责，这里用 sys.modules 注入 mock（且先移除真实模块），保证
测试离线、确定，不依赖它们真实存在。注入必须发生在 import tools 之前。
search_tools 为本阶段新增的真实模块（仅依赖 requests），网络一律 mock。
TOTP 用 auth_lv4 RFC 参考密钥（真实时间生成/校验同窗，确定通过）；
env 键 XIAOJU3_TOTP_SECRET 经 mock.patch.dict 注入，用后自动还原。
"""
import contextlib
import io
import json
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
    """注入 tools.py 的外围依赖 mock（必须在 import tools 之前）。

    返回注入前的 sys.modules 快照：import tools 并显式重绑后由调用方还原，
    避免污染同一进程中随后加载、需要真实模块的其它测试
    （如 test_main → heartbeat 需要真实 home_tools.get_ha_states）。
    """
    saved = {}
    for name in ("home_tools", "adb_tools", "vision_tools", "android_ui_tools"):
        saved[name] = sys.modules.get(name, _MISSING)
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

    return saved


_MISSING = object()
_SAVED_MODULES = _install_mock_modules()

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

# tools 已完成导入且各入口显式重绑到 mock：还原 sys.modules，避免污染随后
# 加载的其它测试模块（test_main → heartbeat 需要真实 home_tools）；
# 本文件的测试统一走 tools.* 重绑属性，行为不受还原影响。
for _name, _old in _SAVED_MODULES.items():
    if _old is _MISSING:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _old

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
        # 最近设备操作记录同样注入 tmp：设备操作类测试不会写真实 agent_state
        self.actions_file = os.path.join(self.ws, "recent_actions.json")
        self._old_actions_file = tools.RECENT_ACTIONS_FILE
        tools.RECENT_ACTIONS_FILE = self.actions_file

    def tearDown(self):
        tools.WORKSPACE = self._old_ws
        tools.RECENT_ACTIONS_FILE = self._old_actions_file
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

    def test_whitelist_has_thirteen_tools(self):
        # §7：12 项 + 新增 read_core_memory = 13 项
        self.assertEqual(len(tools.TOOL_WHITELIST), 13)
        self.assertEqual(
            sorted(tools.TOOL_WHITELIST),
            sorted(["list_files", "read_file", "write_file", "get_ha_devices",
                    "control_ha_device", "adb_tap", "adb_swipe", "adb_screenshot",
                    "vision_tap_element", "ui_tap_element", "web_search",
                    "system_manage", "read_core_memory"]))

    def test_danger_tools_constant(self):
        # 旧集合成员不变，门禁语义升级为 §7 新表（见各专项测试）
        self.assertEqual(
            tools.DANGER_TOOLS,
            {"write_file", "adb_tap", "adb_swipe", "control_ha_device"},
        )


class UserMandatedGateTests(ToolsTestBase):
    """【用户指定四用例】权限新表下 write_file / 危险家居的门禁行为。

    用例②口径（2026-09-30 用户指令）：Lv.3 免逐次动态密码，直接写入。
    """

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
    def test_case2_lv3_write_file_without_totp_succeeds(self):
        # ② Lv.3 能写入文件，无需 TOTP 直接成功。
        #    【口径变更 2026-09-30 用户指令】write_file 的逐次动态密码门禁
        #    取消（免逐次 /sudo），原"Lv.3 需正确 TOTP 才能写入"口径作废；
        #    Lv.3 等级门禁本身保留（< Lv.3 仍拒，见用例①）。
        pm = self._pm("Lv.3")
        r = tools.execute_tool(
            "write_file", {"filename": "a.txt", "content": "hi"}, pm)
        self.assertEqual(r, "✅ 文件 a.txt 写入成功！")
        with open(os.path.join(self.ws, "a.txt"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "hi")

    def test_case2_lv3_write_wrong_totp_credential_still_succeeds(self):
        # ② 口径变更回归锁：错码凭据也不再阻断写入（tools 层已不校验操作
        #    凭据；旧口径本用例返回"❌ 逐次动态密码"拒绝）。permission 层
        #    lv3_operation_ok / open_operation_window API 保留未删，仅不再
        #    被 tools 强制。
        pm = self._pm("Lv.3")
        with mock.patch.dict(os.environ, TOTP_ENV):
            r = tools.execute_tool(
                "write_file", {"filename": "a.txt", "content": "数据"}, pm,
                {"totp": "000000"})
        self.assertEqual(r, "✅ 文件 a.txt 写入成功！")
        with open(os.path.join(self.ws, "a.txt"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "数据")

    def test_case2_lv3_write_within_open_window_still_succeeds(self):
        # ② 兼容路径（原"/sudo 窗口通道"用例）：窗口 API 保留，用户仍可
        #    主动 /sudo 开窗，窗口内写入照常成功；窗口不再是被强制的门禁，
        #    而是可选通道（无凭据无窗口亦成功，见上）。
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


class Lv3SudoFreeGateTests(ToolsTestBase):
    """【根治回归锁】Lv.3 免 /sudo（2026-09-30 用户指令）。

    - adb_tap / ui_tap_element / write_file 在 Lv.3 时：等级数值 >= 3 即直接
      放行——无 /sudo 窗口、无凭据、无任何动态密码校验（lv3_operation_ok
      零调用，用"被调用即失败"的绊线 mock 锁定）；
    - 门禁按等级数值判定，权限表缺键 fail-closed 也不会把 Lv.3 拦下
      （与 control_ha_device 普通设备门禁同口径的病灶免疫）；
    - Lv.2 三者全部拒绝，且拒绝文案不含任何 /sudo 字样、只引导
      /coder_auth 升级（文案口径锁定：不给模型复读旧口径的机会）。
    """

    def _no_lv3_operation_check(self):
        """绊线打桩：lv3_operation_ok 一旦被 execute_tool 调用即抛错
        （经 execute_tool 异常包装表现为"工具执行失败: ..."，后续断言必败）。"""
        return mock.patch.object(
            PermissionManager, "lv3_operation_ok",
            side_effect=AssertionError("Lv.3 不应校验动态密码"))

    def test_lv3_adb_tap_direct_success(self):
        # Lv.3 + 无窗口 + 无凭据 → adb_tap 直接成功
        pm = self._pm("Lv.3")
        self.assertFalse(pm.operation_window_active())
        with self._no_lv3_operation_check():
            r = tools.execute_tool("adb_tap", {"x": 3, "y": 9}, pm)
        self.assertIn("点击 3,9", r)

    def test_lv3_ui_tap_element_direct_success(self):
        # Lv.3 + 无窗口 + 无凭据 → ui_tap_element 直接成功（回退链可达）
        pm = self._pm("Lv.3")
        self.assertFalse(pm.operation_window_active())
        with self._no_lv3_operation_check(), \
                mock.patch.object(tools, "ui_tap_element",
                                  return_value="✅ 已点击【设置】"):
            r = tools.execute_tool(
                "ui_tap_element", {"element_name": "设置"}, pm)
        self.assertEqual(r, "✅ 已点击【设置】")

    def test_lv3_write_file_direct_success(self):
        # Lv.3 + 无窗口 + 无凭据 → write_file 直接成功（既有口径的绊线版）
        pm = self._pm("Lv.3")
        self.assertFalse(pm.operation_window_active())
        with self._no_lv3_operation_check():
            r = tools.execute_tool(
                "write_file", {"filename": "c.txt", "content": "免sudo写入"}, pm)
        self.assertEqual(r, "✅ 文件 c.txt 写入成功！")
        with open(os.path.join(self.ws, "c.txt"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "免sudo写入")

    def test_lv3_gate_is_numeric_level_semantics(self):
        # 病灶免疫回归：门禁按等级数值判定（>= 3 即通过），权限表缺键/
        # has_permission fail-closed 也不会把 Lv.3 拦下
        class _BrokenTablePM:
            _ORDER = {"Lv.1": 1, "Lv.2": 2, "Lv.3": 3, "Lv.4": 4}

            def __init__(self, level):
                self.current_level = level

            def level_value(self, level=None):
                return self._ORDER.get(level or self.current_level, 0)

            def has_permission(self, action):
                return False   # 旧表缺键 → 一律 False（fail-closed）

        pm = _BrokenTablePM("Lv.3")
        self.assertIn("点击 7,7",
                      tools.execute_tool("adb_tap", {"x": 7, "y": 7}, pm))
        r = tools.execute_tool(
            "write_file", {"filename": "n.txt", "content": "x"}, pm)
        self.assertTrue(r.startswith("✅"), r)
        with mock.patch.object(tools, "ui_tap_element",
                               return_value="✅ UI 点击"):
            r2 = tools.execute_tool(
                "ui_tap_element", {"element_name": "设置"}, pm)
        self.assertEqual(r2, "✅ UI 点击")
        # 数值不达门槛（Lv.1）仍拒绝
        r3 = tools.execute_tool(
            "adb_tap", {"x": 1, "y": 1}, _BrokenTablePM("Lv.1"))
        self.assertTrue(r3.startswith("❌ 安全拒绝"), r3)

    def test_lv2_rejections_carry_no_sudo_wording(self):
        # Lv.2 三者全部拒绝；文案口径锁定：只引导 /coder_auth 升级，
        # 拒绝文案不含任何 /sudo 字样
        pm = self._pm("Lv.2")
        with mock.patch.object(tools, "ui_tap_element") as mui:
            results = [
                tools.execute_tool(
                    "write_file", {"filename": "a.txt", "content": "x"}, pm),
                tools.execute_tool("adb_tap", {"x": 1, "y": 2}, pm),
                tools.execute_tool(
                    "ui_tap_element", {"element_name": "设置"}, pm),
            ]
        mui.assert_not_called()   # 门禁先于 UI 解析
        for r in results:
            self.assertTrue(r.startswith("❌ 安全拒绝"), r)
            self.assertIn("Lv.3", r)
            self.assertIn("/coder_auth", r)
            self.assertNotIn("/sudo", r)


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

    def test_normal_device_lv2_lv3_lv4_all_allowed(self):
        # §7 继承语义回归：普通实体 Lv.2/Lv.3/Lv.4 全放行（语义等价
        # "if level < 2: reject"）——用户报告的 "Lv.3 控制普通设备被拒" 用例
        for level in ("Lv.2", "Lv.3", "Lv.4"):
            r = tools.execute_tool(
                "control_ha_device",
                {"entity_id": "light.test", "action": "turn_on"},
                self._pm(level))
            self.assertIn("已对 light.test 执行 turn_on", r, level)

    def test_normal_device_gate_is_numeric_level_semantics(self):
        # 病灶回归：has_permission 对未知能力键 fail-closed（permission.py
        # ACTION_LEVELS 缺键/旧表时返回 False），曾把 Lv.3/Lv.4 一并拦在
        # 普通设备门外。门禁改为按等级数值判定后不受表键缺失影响。
        class _BrokenTablePM:
            """模拟 ACTION_LEVELS 缺 control_normal_devices 键的 manager。"""
            _ORDER = {"Lv.1": 1, "Lv.2": 2, "Lv.3": 3, "Lv.4": 4}

            def __init__(self, level):
                self.current_level = level

            def level_value(self, level=None):
                return self._ORDER.get(level or self.current_level, 0)

            def has_permission(self, action):
                return False   # 旧表无该能力键 → 一律 False（fail-closed）

        for level in ("Lv.2", "Lv.3", "Lv.4"):
            r = tools.execute_tool(
                "control_ha_device",
                {"entity_id": "light.test", "action": "turn_on"},
                _BrokenTablePM(level))
            self.assertIn("已对 light.test 执行 turn_on", r, level)
        # Lv.1 仍拒绝（数值门槛未放松）
        r = tools.execute_tool(
            "control_ha_device",
            {"entity_id": "light.test", "action": "turn_on"},
            _BrokenTablePM("Lv.1"))
        self.assertTrue(r.startswith("❌ 安全拒绝"), r)

    def test_normal_device_gate_falls_back_to_capability(self):
        # 向后兼容：仅暴露 has_permission 的旧式 manager（无 level_value）
        # 回退能力键判定——键在则 Lv.2+ 语义放行，键缺则 fail-closed 拒绝
        class _CapOnlyPM:
            def __init__(self, table):
                self._table = table

            def has_permission(self, action):
                return self._table.get(action, False)

        healthy = tools.execute_tool(
            "control_ha_device",
            {"entity_id": "light.test", "action": "turn_on"},
            _CapOnlyPM({"control_normal_devices": True}))
        self.assertIn("已对 light.test 执行 turn_on", healthy)
        broken = tools.execute_tool(
            "control_ha_device",
            {"entity_id": "light.test", "action": "turn_on"}, _CapOnlyPM({}))
        self.assertTrue(broken.startswith("❌ 安全拒绝"), broken)

    def test_dangerous_gate_untouched_by_normal_fix(self):
        # 危险实体门禁原样（一丝不放松）：即使普通分支改为数值判定，
        # 危险分支仍走能力键 + 双因子——表键缺失时 fail-closed（安全方向）
        class _BrokenTablePM:
            _ORDER = {"Lv.1": 1, "Lv.2": 2, "Lv.3": 3, "Lv.4": 4}

            def __init__(self, level):
                self.current_level = level

            def level_value(self, level=None):
                return self._ORDER.get(level or self.current_level, 0)

            def has_permission(self, action):
                return False

        r = tools.execute_tool(
            "control_ha_device",
            {"entity_id": "lock.front_door", "action": "turn_on"},
            _BrokenTablePM("Lv.4"))
        self.assertTrue(r.startswith("❌ 安全拒绝"), r)
        self.assertIn("高危", r)

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
        # 写路径沙箱：Lv.3 免逐次密码后沙箱把关不放松，越界一律拒绝
        pm = self._pm("Lv.3")
        r = tools.execute_tool(
            "write_file", {"filename": "../evil.txt", "content": "x"}, pm)
        self.assertEqual(r, "❌ 安全拒绝：不允许访问工作区以外的文件！")
        self.assertFalse(os.path.exists(
            os.path.join(self.ws, "..", "evil.txt")))

    def test_level_gate_precedes_sandbox(self):
        # 等级门先于路径校验：Lv.2 未过 write_file 等级门时，越界路径也不
        # 泄露沙箱判定（逐次动态密码门禁已由用户指令取消，等级门保留）
        pm = self._pm("Lv.2")
        r = tools.execute_tool(
            "write_file", {"filename": "../evil.txt", "content": "x"}, pm)
        self.assertTrue(r.startswith("❌ 安全拒绝：当前权限不足"), r)
        self.assertIn("/coder_auth", r)

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
        # 向后兼容：旧三参调用（无 credentials）不报错；Lv.3 免逐次动态
        # 密码后直接写入成功（credentials 仅 Lv.4 双因子路径继续消费）
        r = tools.execute_tool(
            "write_file", {"filename": "a.txt", "content": "x"}, self._pm("Lv.3"))
        self.assertEqual(r, "✅ 文件 a.txt 写入成功！")


class VisionFallbackTests(ToolsTestBase):
    """ui_tap_element 解析失败 → 代码级强制回退 vision_tap_element（用户指令）。

    回退对模型透明：模型只拿到最终结果，无需多轮决策；回退前有未配置
    短路检查（见 VisionShortCircuitTests），故本类 _run 统一注入非空
    VISION_MODEL / VISION_KEY——tools.py 于 import 时绑定配置值，env 补丁
    不影响已绑定值，须经 mock.patch.object 注入（自动还原）；vision 失败
    时原样返回 vision_tools 的极简错误串，不再追加任何配置指引（2026-09-30
    用户指令：聊天框一字不多，指引只存在于控制台日志）；回退只发生
    一次（vision 失败不再触发任何重试）；Lv.3 门禁先于回退。
    打桩只替换 tools 模块上的 ui/vision 入口（mock.patch.object 自动还原），
    不触碰 vision_tools / android_ui_tools 内部实现（并行子代理所有）。
    """

    UI_FAIL = "❌ UI 层级中未找到【设置】，请确认它目前在屏幕上可见。"
    UI_OK = "✅ 已点击【设置】"
    VISION_OK = "✅ 已通过视觉识别点击【设置】"
    VISION_FAIL = "❌ 视觉模型调用失败: 403 Forbidden"

    def _run(self, ui_return, vision_return, level="Lv.3", args=None):
        """打桩 ui/vision 后执行 ui_tap_element，返回 (结果, ui mock, vision mock)。

        同时注入非空 VISION_MODEL / VISION_KEY，避免被未配置短路拦住。
        """
        pm = self._pm(level)
        with contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(tools, "ui_tap_element",
                                  return_value=ui_return) as mui, \
                mock.patch.object(tools, "vision_tap_element",
                                  return_value=vision_return) as mvis, \
                mock.patch.object(tools, "VISION_MODEL",
                                  "qwen-vl-max-latest"), \
                mock.patch.object(tools, "VISION_KEY", "sk-test-ok"):
            r = tools.execute_tool("ui_tap_element",
                                   args if args is not None
                                   else {"element_name": "设置"}, pm)
        return r, mui, mvis

    def test_ui_failure_falls_back_to_vision(self):
        # UI 解析失败 → 直接调 vision（同 element_name），vision 结果原样返回
        r, mui, mvis = self._run(self.UI_FAIL, self.VISION_OK)
        self.assertEqual(r, self.VISION_OK)
        self.assertNotIn("未找到", r)
        mui.assert_called_once_with("设置")
        mvis.assert_called_once_with("设置")   # 防循环：回退恰好一次

    def test_ui_and_vision_both_failure_returns_vision_string_verbatim(self):
        # 视觉也失败（❌ 开头错误串）→ 原样返回 vision 极简错误串，
        # 不再追加"如持续失败，请检查 .env ..."指引（2026-09-30 用户指令）
        r, _, _ = self._run(self.UI_FAIL, self.VISION_FAIL)
        self.assertEqual(r, self.VISION_FAIL)
        self.assertNotIn("如持续失败", r)
        self.assertNotIn("请检查", r)
        self.assertNotIn("VISION_API_URL", r)
        self.assertNotIn("VISION_KEY", r)

    def test_ui_success_never_calls_vision(self):
        # UI 解析成功 → 原样返回，vision 绝不被调用
        r, mui, mvis = self._run(self.UI_OK, self.VISION_OK)
        self.assertEqual(r, self.UI_OK)
        self.assertNotIn("VISION_API_URL", r)
        mvis.assert_not_called()

    def test_lv3_gate_precedes_fallback(self):
        # Lv.2 直接拒（门禁先于回退），ui 与 vision 都不被调用
        r, mui, mvis = self._run(self.UI_FAIL, self.VISION_OK, level="Lv.2")
        self.assertTrue(r.startswith("❌ 安全拒绝"), r)
        self.assertIn("Lv.3", r)
        self.assertIn("/coder_auth", r)
        mui.assert_not_called()
        mvis.assert_not_called()

    def test_vision_non_cross_error_string_returned_verbatim(self):
        # vision 透传截图链路错误（非 ❌ 开头但含"失败"）→ 原样返回，不补指引
        r, _, _ = self._run(self.UI_FAIL, "截图失败：设备未连接")
        self.assertEqual(r, "截图失败：设备未连接")
        self.assertNotIn("如持续失败", r)
        self.assertNotIn("VISION_API_URL", r)

    def test_missing_param_does_not_fallback(self):
        # 缺 element_name 属调用方错误，直接拒绝、不触发视觉回退
        r, _, mvis = self._run(self.UI_FAIL, self.VISION_OK, args={})
        self.assertEqual(
            r, "❌ 缺少参数：需要提供 element_name (要点击的按钮或图标名称)")
        mvis.assert_not_called()


class VisionShortCircuitTests(ToolsTestBase):
    """视觉回退短路检查（用户指令 2026-09-30）：VISION_MODEL / VISION_KEY
    任一未配置（None 或空串均按 falsy 判定）→ ui_tap_element 失败后直接
    返回"❌ 未配置视觉模型，无法执行点击"，绝不调用 vision_tap_element——
    ADB 截图、云端请求与等待全部避免，不空跑。

    tools.py 于 import 时绑定配置值（from xiaoju3 import VISION_MODEL,
    VISION_KEY），故经 mock.patch.object(tools, ...) 注入空值/None（自动
    还原）；vision 入口打桩为 Mock，断言零调用即证明零网络请求。
    """

    UI_FAIL = "❌ UI 层级中未找到【设置】，请确认它目前在屏幕上可见。"
    SHORT_CIRCUIT = "❌ 未配置视觉模型，无法执行点击"

    def _run(self, vision_model="", vision_key=""):
        """UI 必失败 + vision 打桩 + 注入空/None 视觉配置后执行 ui_tap_element。"""
        pm = self._pm("Lv.3")
        with contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(tools, "ui_tap_element",
                                  return_value=self.UI_FAIL) as mui, \
                mock.patch.object(tools, "vision_tap_element") as mvis, \
                mock.patch.object(tools, "VISION_MODEL", vision_model), \
                mock.patch.object(tools, "VISION_KEY", vision_key):
            r = tools.execute_tool("ui_tap_element",
                                   {"element_name": "设置"}, pm)
        return r, mui, mvis

    def test_vision_model_empty_short_circuits_before_vision_call(self):
        # VISION_MODEL 为空串 → 立即短路返回，vision 绝不被调用
        r, mui, mvis = self._run(vision_model="", vision_key="sk-test-ok")
        self.assertEqual(r, self.SHORT_CIRCUIT)
        mui.assert_called_once_with("设置")   # UI 解析先发生并失败
        mvis.assert_not_called()              # 短路：零视觉调用、零网络请求

    def test_vision_key_empty_short_circuits_before_vision_call(self):
        # 仅 VISION_KEY 为空 → 同样短路（任一未配置即拦）
        r, _, mvis = self._run(vision_model="qwen-vl-max-latest", vision_key="")
        self.assertEqual(r, self.SHORT_CIRCUIT)
        mvis.assert_not_called()

    def test_none_config_values_also_short_circuit(self):
        # config 值可能为 None：truthy 判定下 None 同样拦截
        r, _, mvis = self._run(vision_model=None, vision_key=None)
        self.assertEqual(r, self.SHORT_CIRCUIT)
        mvis.assert_not_called()

    def test_short_circuit_message_is_exact_without_extra_hint(self):
        # 短路文案固定，不追加 VISION_API_URL 配置指引（未走视觉链路）
        r, _, _ = self._run()
        self.assertEqual(r, self.SHORT_CIRCUIT)

    def test_configured_vision_still_falls_back(self):
        # 对照：配置齐全时不会被短路拦住，照常走视觉回退
        pm = self._pm("Lv.3")
        with contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(tools, "ui_tap_element",
                                  return_value=self.UI_FAIL), \
                mock.patch.object(tools, "vision_tap_element",
                                  return_value="✅ 已通过视觉识别点击【设置】") as mvis, \
                mock.patch.object(tools, "VISION_MODEL",
                                  "qwen-vl-max-latest"), \
                mock.patch.object(tools, "VISION_KEY", "sk-test-ok"):
            r = tools.execute_tool("ui_tap_element",
                                   {"element_name": "设置"}, pm)
        self.assertEqual(r, "✅ 已通过视觉识别点击【设置】")
        mvis.assert_called_once_with("设置")


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




class PrivateDataGateTests(unittest.TestCase):
    """私有数据纵深门：agent_state 路径仅 Lv.4 可访问；read_core_memory Lv.4 独家。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xiaoju3_tools_priv_")
        ws = os.path.join(self.tmp, "ws")
        state = os.path.join(ws, "agent_state")
        os.makedirs(state, exist_ok=True)
        with open(os.path.join(state, "identity.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        self._old = tools.WORKSPACE, tools.AGENT_STATE_DIR
        tools.WORKSPACE = ws
        tools.AGENT_STATE_DIR = state

    def tearDown(self):
        tools.WORKSPACE, tools.AGENT_STATE_DIR = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lv2_cannot_read_private_state(self):
        pm = PermissionManager()
        pm.current_level = "Lv.2"
        result = tools.execute_tool("read_file", {"filename": "agent_state/identity.json"}, pm)
        self.assertIn("❌", result)
        self.assertIn("Lv.4", result)

    def test_lv3_cannot_read_private_state(self):
        pm = PermissionManager()
        pm.current_level = "Lv.3"
        result = tools.execute_tool("read_file", {"filename": "agent_state/identity.json"}, pm)
        self.assertIn("❌", result)

    def test_lv4_can_read_private_state(self):
        pm = PermissionManager()
        pm.current_level = "Lv.4"
        result = tools.execute_tool("read_file", {"filename": "agent_state/identity.json"}, pm)
        self.assertNotIn("❌ 安全拒绝", result)

    def test_list_files_private_workspace_denied_below_lv4(self):
        pm = PermissionManager()
        pm.current_level = "Lv.3"
        old_ws = tools.WORKSPACE
        tools.WORKSPACE = tools.AGENT_STATE_DIR   # 工作区被误配到状态目录：门兜底
        try:
            result = tools.execute_tool("list_files", {}, pm)
            self.assertIn("❌", result)
        finally:
            tools.WORKSPACE = old_ws

    def test_read_core_memory_lv4_only(self):
        pm_low = PermissionManager()
        pm_low.current_level = "Lv.3"
        result = tools.execute_tool("read_core_memory", {}, pm_low)
        self.assertIn("❌", result)
        self.assertIn("Lv.4", result)

    def test_read_core_memory_lv4_reads_recent(self):
        pm = PermissionManager()
        pm.current_level = "Lv.4"
        result = tools.execute_tool("read_core_memory", {"limit": 3}, pm)
        # state_manager 全局单例在真实 AGENT_STATE_DIR 上建库；能取到格式化文本即可
        self.assertTrue(result.startswith("🧠 核心记忆") or "暂无记录" in result)


class RecentActionRecorderTests(ToolsTestBase):
    """最近设备操作记录（上下文记忆/指代消解基座）：成功写入并裁到 5 条、
    失败操作不写、记录器异常不影响工具返回值、损坏文件自愈重建、
    读取类工具（adb_screenshot）不记录。"""

    def _read_entries(self):
        with open(self.actions_file, encoding="utf-8") as f:
            return json.load(f)

    def _seed(self, count):
        """预置 count 条旧记录（detail 带序号，验证裁剪方向）。"""
        entries = [{"ts": f"2026-01-01 00:00:{i:02d}", "tool": "adb_tap",
                    "detail": f"adb_tap: 旧记录{i}"} for i in range(count)]
        with open(self.actions_file, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False)
        return entries

    def test_successful_control_ha_device_recorded(self):
        pm = self._pm("Lv.2")
        result = tools.execute_tool(
            "control_ha_device", {"entity_id": "light.living", "action": "turn_on"}, pm)
        self.assertIn("turn_on", result)
        entries = self._read_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(set(entries[0]), {"ts", "tool", "detail"})
        self.assertEqual(entries[0]["tool"], "control_ha_device")
        self.assertEqual(entries[0]["detail"],
                         "control_ha_device: light.living → turn_on")
        self.assertTrue(entries[0]["ts"])

    def test_successful_adb_tap_and_swipe_recorded(self):
        pm = self._pm("Lv.3")
        tools.execute_tool("adb_tap", {"x": 100, "y": 200}, pm)
        tools.execute_tool("adb_swipe", {"x1": 1, "y1": 2, "x2": 3, "y2": 4}, pm)
        entries = self._read_entries()
        self.assertEqual([e["tool"] for e in entries], ["adb_tap", "adb_swipe"])
        self.assertEqual(entries[0]["detail"], "adb_tap: 点击 (100, 200)")
        self.assertEqual(entries[1]["detail"],
                         "adb_swipe: 从 (1,2) 滑到 (3,4)")

    def test_keeps_only_latest_five(self):
        self._seed(5)
        tools.execute_tool("adb_tap", {"x": 9, "y": 9}, self._pm("Lv.3"))
        entries = self._read_entries()
        self.assertEqual(len(entries), 5)
        # 超出裁掉最旧：旧记录0 被裁，旧记录1 成为最旧
        self.assertEqual(entries[0]["detail"], "adb_tap: 旧记录1")
        # 新事件追加在最后
        self.assertEqual(entries[-1]["tool"], "adb_tap")
        self.assertEqual(entries[-1]["detail"], "adb_tap: 点击 (9, 9)")

    def test_failed_operation_not_recorded(self):
        # Lv.1 被 adb 门禁拒绝：连记录文件都不产生
        result = tools.execute_tool("adb_tap", {"x": 1, "y": 2}, self._pm("Lv.1"))
        self.assertIn("❌", result)
        self.assertFalse(os.path.exists(self.actions_file))
        # 已有记录时，失败操作不追加
        self._seed(2)
        denied = tools.execute_tool(
            "control_ha_device", {"entity_id": "lock.door", "action": "unlock"},
            self._pm("Lv.1"))
        self.assertIn("❌", denied)
        self.assertEqual(len(self._read_entries()), 2)

    def test_recorder_failure_does_not_affect_tool_result(self):
        # 记录器内部磁盘异常（os.replace 原子替换失败）必须被吞掉：
        # 工具返回值与不装记录器时完全一致
        with mock.patch.object(tools.os, "replace",
                               side_effect=OSError("disk full")):
            result = tools.execute_tool("adb_tap", {"x": 5, "y": 6}, self._pm("Lv.3"))
        self.assertEqual(result, "【mock】点击 5,6")

    def test_corrupted_file_self_heals(self):
        with open(self.actions_file, "w", encoding="utf-8") as f:
            f.write("{这不是JSON")
        result = tools.execute_tool("adb_tap", {"x": 7, "y": 8}, self._pm("Lv.3"))
        self.assertEqual(result, "【mock】点击 7,8")   # 工具照常成功
        entries = self._read_entries()
        self.assertEqual(len(entries), 1)              # 损坏表重置重建
        self.assertEqual(entries[0]["detail"], "adb_tap: 点击 (7, 8)")

    def test_screenshot_read_only_not_recorded(self):
        tools.execute_tool("adb_screenshot", {}, self._pm("Lv.1"))
        self.assertFalse(os.path.exists(self.actions_file))

    def test_atomic_write_leaves_no_tmp_file(self):
        tools.execute_tool("adb_tap", {"x": 1, "y": 1}, self._pm("Lv.3"))
        self.assertTrue(os.path.exists(self.actions_file))
        self.assertFalse(os.path.exists(self.actions_file + ".tmp"))

    def test_record_creates_parent_dirs(self):
        path = os.path.join(self.ws, "deep", "dir", "recent_actions.json")
        tools.record_recent_action("adb_tap", {"x": 1, "y": 2}, filepath=path)
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
        self.assertEqual(entries[0]["detail"], "adb_tap: 点击 (1, 2)")

    def test_get_recent_actions_reader(self):
        # 缺失 → 空列表；损坏 → 空列表不抛异常
        self.assertEqual(tools.get_recent_actions(), [])
        with open(self.actions_file, "w", encoding="utf-8") as f:
            f.write("broken")
        self.assertEqual(tools.get_recent_actions(), [])
        # 只回最近 5 条（最新在最后）
        self._seed(7)
        actions = tools.get_recent_actions()
        self.assertEqual(len(actions), 5)
        self.assertEqual(actions[-1]["detail"], "adb_tap: 旧记录6")


if __name__ == "__main__":
    unittest.main()
