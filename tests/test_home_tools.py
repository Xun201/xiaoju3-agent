# -*- coding: utf-8 -*-
"""home_tools 单元测试：全离线，requests 全部 mock。

覆盖：六类实体过滤与非六类剔除、Bearer 认证头、四种 action（turn_on/
turn_off/toggle/set_temperature 温控 §10 #9）的 URL 与 payload、未配置
HA_URL 的错误串、请求异常兜底、结构化 get_ha_states（心跳规则用 §10 #10）、
高危实体分类 is_dangerous_entity（§10 #8）。配置经 home_tools 模块属性
注入（函数调用时读取，import 零副作用）。

注：并行测试模块（test_tools 等）会在 import 期向 sys.modules 注入同名
fake；unittest discover 按字母序导入，本模块可能晚于它们被导入，故先按
真实文件路径加载被测模块，且 mock 一律用 patch.object 绑定真实对象。
"""
import importlib.util
import os
import sys
import unittest
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_real_modules(*names):
    """发现 sys.modules 中同名 fake（无 __file__）时按真实路径重载。"""
    for name in names:
        real_path = os.path.join(_ROOT, f"{name}.py")
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "__file__", None) and \
                os.path.normcase(os.path.abspath(mod.__file__)) == os.path.normcase(real_path):
            continue
        spec = importlib.util.spec_from_file_location(name, real_path)
        real = importlib.util.module_from_spec(spec)
        sys.modules[name] = real
        spec.loader.exec_module(real)


_ensure_real_modules("home_tools")

import home_tools


def _state(entity_id, state, friendly=None):
    return {
        "entity_id": entity_id,
        "state": state,
        "attributes": {"friendly_name": friendly or entity_id},
    }


# 混入六类与非六类实体的样例 /api/states 响应
SAMPLE_STATES = [
    _state("input_boolean.xiao_ju_ce_shi_deng", "off", "小橘测试灯"),
    _state("light.living_room", "on", "客厅灯"),
    _state("switch.plug", "on", "智能插座"),
    _state("sensor.temperature", "26.5", "客厅温度"),
    _state("climate.ac", "cool", "空调"),
    _state("media_player.tv", "playing", "电视"),
    # 以下均不在六类白名单内，应被剔除
    _state("automation.morning", "on", "自动化"),
    _state("person.xun", "home", "家人"),
    _state("camera.front_door", "idle", "门口摄像头"),
    _state("sun.sun", "above_horizon", "太阳"),
    _state("weather.home", "sunny", "天气"),
    _state("zone.home", "0", "家"),
    _state("script.cleanup", "off", "脚本"),
]


class HomeToolsTestBase(unittest.TestCase):
    """公共基座：注入测试用 HA_URL / HA_TOKEN，用后还原。"""

    HA_URL = "http://ha.example:8123"
    HA_TOKEN = "test-ha-token"

    def setUp(self):
        self._old_url = home_tools.HA_URL
        self._old_token = home_tools.HA_TOKEN
        home_tools.HA_URL = self.HA_URL
        home_tools.HA_TOKEN = self.HA_TOKEN

    def tearDown(self):
        home_tools.HA_URL = self._old_url
        home_tools.HA_TOKEN = self._old_token


class GetHaDevicesTests(HomeToolsTestBase):
    """get_ha_devices：六类过滤、Bearer 头、空列表与异常兜底。"""

    def test_filters_to_six_domains(self):
        with mock.patch.object(home_tools.requests, "get") as mget:
            mget.return_value.json.return_value = SAMPLE_STATES
            result = home_tools.get_ha_devices()

        # 六类全部保留
        self.assertIn("小橘测试灯 (ID: input_boolean.xiao_ju_ce_shi_deng) 当前状态: off", result)
        self.assertIn("客厅灯 (ID: light.living_room) 当前状态: on", result)
        self.assertIn("智能插座 (ID: switch.plug) 当前状态: on", result)
        self.assertIn("客厅温度 (ID: sensor.temperature) 当前状态: 26.5", result)
        self.assertIn("空调 (ID: climate.ac) 当前状态: cool", result)
        self.assertIn("电视 (ID: media_player.tv) 当前状态: playing", result)
        # 非六类全部剔除
        for gone in ("automation.morning", "person.xun", "camera.front_door",
                     "sun.sun", "weather.home", "zone.home", "script.cleanup"):
            self.assertNotIn(gone, result)

    def test_requests_get_url_headers_timeout(self):
        with mock.patch.object(home_tools.requests, "get") as mget:
            mget.return_value.json.return_value = SAMPLE_STATES
            home_tools.get_ha_devices()

        mget.assert_called_once_with(
            f"{self.HA_URL}/api/states",
            headers={
                "Authorization": f"Bearer {self.HA_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )

    def test_all_irrelevant_entities_returns_empty_hint(self):
        with mock.patch.object(home_tools.requests, "get") as mget:
            mget.return_value.json.return_value = [_state("person.xun", "home")]
            self.assertEqual(home_tools.get_ha_devices(), "当前没有发现可控设备。")

    def test_request_exception_returns_error_string(self):
        with mock.patch.object(home_tools.requests, "get",
                             side_effect=ConnectionError("refused")):
            result = home_tools.get_ha_devices()
        self.assertTrue(result.startswith("❌ 获取HA设备列表失败: "))

    def test_missing_ha_url_returns_clear_error(self):
        home_tools.HA_URL = ""
        with mock.patch.object(home_tools.requests, "get") as mget:
            result = home_tools.get_ha_devices()
        self.assertTrue(result.startswith("❌ 未配置 HA_URL"))
        self.assertIn("获取设备列表", result)
        mget.assert_not_called()  # 不应发起任何网络请求


class ControlHaDeviceTests(HomeToolsTestBase):
    """control_ha_device：三种 action 的 URL / payload / 认证头。"""

    def test_turn_on(self):
        with mock.patch.object(home_tools.requests, "post") as mpost:
            result = home_tools.control_ha_device("light.living_room", "turn_on")
        self.assertEqual(result, "✅ 设备 light.living_room 执行 turn_on 成功！")
        mpost.assert_called_once_with(
            f"{self.HA_URL}/api/services/homeassistant/turn_on",
            headers={
                "Authorization": f"Bearer {self.HA_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"entity_id": "light.living_room"},
            timeout=10,
        )

    def test_turn_off(self):
        with mock.patch.object(home_tools.requests, "post") as mpost:
            result = home_tools.control_ha_device("switch.plug", "turn_off")
        self.assertEqual(result, "✅ 设备 switch.plug 执行 turn_off 成功！")
        self.assertEqual(
            mpost.call_args.args[0],
            f"{self.HA_URL}/api/services/homeassistant/turn_off")

    def test_toggle(self):
        with mock.patch.object(home_tools.requests, "post") as mpost:
            result = home_tools.control_ha_device("input_boolean.xiao_ju_ce_shi_deng", "toggle")
        self.assertEqual(result, "✅ 设备 input_boolean.xiao_ju_ce_shi_deng 执行 toggle 成功！")
        self.assertEqual(
            mpost.call_args.args[0],
            f"{self.HA_URL}/api/services/homeassistant/toggle")
        self.assertEqual(mpost.call_args.kwargs["json"],
                         {"entity_id": "input_boolean.xiao_ju_ce_shi_deng"})

    def test_unsupported_action_rejected(self):
        with mock.patch.object(home_tools.requests, "post") as mpost:
            result = home_tools.control_ha_device("light.living_room", "dim")
        self.assertEqual(result, "❌ 不支持的动作: dim，仅支持 turn_on, turn_off, toggle, set_temperature")
        mpost.assert_not_called()

    def test_post_exception_returns_error_string(self):
        with mock.patch.object(home_tools.requests, "post",
                             side_effect=ConnectionError("timeout")):
            result = home_tools.control_ha_device("light.living_room", "turn_on")
        self.assertTrue(result.startswith("❌ 控制设备失败: "))

    def test_missing_ha_url_returns_clear_error(self):
        home_tools.HA_URL = ""
        with mock.patch.object(home_tools.requests, "post") as mpost:
            result = home_tools.control_ha_device("light.living_room", "turn_on")
        self.assertTrue(result.startswith("❌ 未配置 HA_URL"))
        self.assertIn("控制设备", result)
        mpost.assert_not_called()


class SetTemperatureTests(HomeToolsTestBase):
    """set_temperature 温控（架构 §10 #9 细粒度："空调调到 26 度"口径）。"""

    def test_set_temperature_posts_climate_service(self):
        with mock.patch.object(home_tools.requests, "post") as mpost:
            result = home_tools.control_ha_device("climate.ac", "set_temperature",
                                                  temperature=26)
        self.assertEqual(result, "✅ 设备 climate.ac 温度已设为 26 度！")
        mpost.assert_called_once_with(
            f"{self.HA_URL}/api/services/climate/set_temperature",
            headers={
                "Authorization": f"Bearer {self.HA_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"entity_id": "climate.ac", "temperature": 26},
            timeout=10,
        )

    def test_set_temperature_without_temperature_rejected(self):
        with mock.patch.object(home_tools.requests, "post") as mpost:
            result = home_tools.control_ha_device("climate.ac", "set_temperature")
        self.assertIn("❌ set_temperature 需要提供 temperature", result)
        mpost.assert_not_called()

    def test_set_temperature_exception_returns_error_string(self):
        with mock.patch.object(home_tools.requests, "post",
                             side_effect=ConnectionError("timeout")):
            result = home_tools.control_ha_device("climate.ac", "set_temperature",
                                                  temperature=26.5)
        self.assertTrue(result.startswith("❌ 控制设备失败: "))

    def test_set_temperature_missing_ha_url(self):
        home_tools.HA_URL = ""
        with mock.patch.object(home_tools.requests, "post") as mpost:
            result = home_tools.control_ha_device("climate.ac", "set_temperature",
                                                  temperature=26)
        self.assertTrue(result.startswith("❌ 未配置 HA_URL"))
        mpost.assert_not_called()


class GetHaStatesTests(HomeToolsTestBase):
    """get_ha_states：结构化六类实体（心跳场景规则引擎的数据源 §10 #10）。"""

    def test_returns_structured_six_domain_states(self):
        with mock.patch.object(home_tools.requests, "get") as mget:
            mget.return_value.json.return_value = SAMPLE_STATES
            states = home_tools.get_ha_states()

        self.assertIsInstance(states, list)
        ids = {s["entity_id"] for s in states}
        self.assertIn("input_boolean.xiao_ju_ce_shi_deng", ids)
        self.assertIn("light.living_room", ids)
        self.assertIn("climate.ac", ids)
        for gone in ("automation.morning", "person.xun", "sun.sun"):
            self.assertNotIn(gone, ids)
        by_id = {s["entity_id"]: s for s in states}
        self.assertEqual(by_id["light.living_room"]["state"], "on")
        self.assertEqual(by_id["light.living_room"]["friendly_name"], "客厅灯")

    def test_missing_ha_url_returns_empty_list_without_request(self):
        home_tools.HA_URL = ""
        with mock.patch.object(home_tools.requests, "get") as mget:
            self.assertEqual(home_tools.get_ha_states(), [])
        mget.assert_not_called()

    def test_request_exception_returns_empty_list(self):
        with mock.patch.object(home_tools.requests, "get",
                             side_effect=ConnectionError("refused")):
            self.assertEqual(home_tools.get_ha_states(), [])


class DangerousEntityTests(unittest.TestCase):
    """is_dangerous_entity（架构 §10 #8）：锁与燃气的分类。"""

    def test_lock_domain_is_dangerous(self):
        self.assertTrue(home_tools.is_dangerous_entity("lock.front_door"))
        self.assertTrue(home_tools.is_dangerous_entity("lock.LOCK_1"))

    def test_gas_keyword_is_dangerous(self):
        self.assertTrue(home_tools.is_dangerous_entity("switch.gas_valve"))
        self.assertTrue(home_tools.is_dangerous_entity("switch.GAS-VALVE"))
        self.assertTrue(home_tools.is_dangerous_entity("switch.燃气总阀"))
        self.assertTrue(home_tools.is_dangerous_entity("binary_sensor.gasleak"))

    def test_normal_entities_are_safe(self):
        for safe in ("light.living_room", "switch.plug", "sensor.temperature",
                     "climate.ac", "input_boolean.xiao_ju_ce_shi_deng",
                     "media_player.tv", ""):
            self.assertFalse(home_tools.is_dangerous_entity(safe), safe)

    def test_none_like_inputs_are_safe(self):
        self.assertFalse(home_tools.is_dangerous_entity(None))

    def test_lookalike_domains_not_flagged(self):
        # "block."/"clock." 域名不是 lock；"vagrant" 不含 gas 字样
        self.assertFalse(home_tools.is_dangerous_entity("block.door"))
        self.assertFalse(home_tools.is_dangerous_entity("clock.wall"))


class DangerExpansionTests(unittest.TestCase):
    """危险判定扩展（2026-10-02 权限重构）：valve/阀 + DANGER_ENTITIES。"""

    def setUp(self):
        self._old = os.environ.pop("DANGER_ENTITIES", None)
        if self._old is not None:
            self.addCleanup(os.environ.__setitem__, "DANGER_ENTITIES", self._old)

    def test_valve_keyword_is_dangerous(self):
        for entity in ("switch.water_valve", "switch.VALVE-1",
                       "switch.燃气阀", "switch.进水阀"):
            self.assertTrue(home_tools.is_dangerous_entity(entity), entity)

    def test_danger_entities_custom_whitelist(self):
        # 精确命中自定义白名单 → 危险（词表外实体亦可声明）
        os.environ["DANGER_ENTITIES"] = ("lock.front_door,"
                                         "switch.induction_cooker")
        try:
            self.assertTrue(
                home_tools.is_dangerous_entity("lock.front_door"))
            self.assertTrue(
                home_tools.is_dangerous_entity("switch.induction_cooker"))
            # 白名单外（即使同前缀）不命中
            self.assertFalse(
                home_tools.is_dangerous_entity("switch.induction_cooker_2"))
        finally:
            os.environ.pop("DANGER_ENTITIES", None)

    def test_danger_entities_whitespace_tolerant(self):
        os.environ["DANGER_ENTITIES"] = " switch.heater , light.x "
        try:
            self.assertTrue(home_tools.is_dangerous_entity("switch.heater"))
            self.assertTrue(home_tools.is_dangerous_entity("light.x"))
            # 白名单外照常安全
            self.assertFalse(home_tools.is_dangerous_entity("switch.other"))
        finally:
            os.environ.pop("DANGER_ENTITIES", None)

    def test_builtin_keywords_still_work_without_env(self):
        # 未配置 DANGER_ENTITIES 时内置关键词照常（lock/gas/valve/燃气/阀）
        self.assertTrue(home_tools.is_dangerous_entity("lock.front_door"))
        self.assertTrue(home_tools.is_dangerous_entity("switch.gas_valve"))
        self.assertTrue(home_tools.is_dangerous_entity("switch.water_valve"))
        self.assertFalse(home_tools.is_dangerous_entity("light.living"))


class ImportSafetyTests(unittest.TestCase):
    """import 本模块零副作用：未配置 HA 时 import 也不崩、不发请求。"""

    def test_module_importable_and_contract_names(self):
        # 模块能被加载到这里即说明 import 期零副作用（不崩、不发请求）；
        # tools.py 顶层 import 的两个名字必须存在
        self.assertTrue(callable(home_tools.get_ha_devices))
        self.assertTrue(callable(home_tools.control_ha_device))
        # 第二阶段新增契约名（S3：温控/危险实体分类/结构化状态）
        self.assertTrue(callable(home_tools.is_dangerous_entity))
        self.assertTrue(callable(home_tools.get_ha_states))


class InputNumberDomainTests(HomeToolsTestBase):
    """input_number 第七类（2026-10-02）：模拟湿度等数值实体纳入感知白名单。"""

    SAMPLE = [
        _state("input_number.mo_ni_shi_du", "45.5", "模拟湿度"),
        _state("sun.sun", "above_horizon", "太阳"),   # 非白名单仍剔除
    ]

    def test_domains_contains_input_number(self):
        self.assertIn("input_number", home_tools.HA_DOMAINS)
        self.assertEqual(len(home_tools.HA_DOMAINS), 7)

    def test_get_ha_devices_includes_input_number(self):
        with mock.patch.object(home_tools.requests, "get") as mget:
            mget.return_value.json.return_value = self.SAMPLE
            result = home_tools.get_ha_devices()
        self.assertIn("模拟湿度 (ID: input_number.mo_ni_shi_du) 当前状态: 45.5", result)
        self.assertNotIn("sun.sun", result)

    def test_get_ha_states_includes_input_number(self):
        with mock.patch.object(home_tools.requests, "get") as mget:
            mget.return_value.json.return_value = self.SAMPLE
            states = home_tools.get_ha_states()
        self.assertIn("input_number.mo_ni_shi_du",
                      [e["entity_id"] for e in states])


if __name__ == "__main__":
    unittest.main()
