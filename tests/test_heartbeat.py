# -*- coding: utf-8 -*-
"""heartbeat 单元测试：单轮逻辑全离线（感知 / 决策 / 执行全部注入 mock）。

覆盖（第二阶段 §10 #10 / #14）：
- 快照比对 → 决策 → 提取 JSON → 执行的单轮主线；
- 决策本地优先：默认链路先 brain.ask_local，异常热切换 ask_cloud，
  来源标签记录于 last_decision_source（ask_fn 兼容 str / (文本, 标签)）；
- 场景规则引擎：①回家开灯 ②空气干燥开加湿器（命中/不命中、阈值 env
  XIAOJU3_HUMIDITY_THRESHOLD 生效、首轮无参照不触发变化型规则）；
- 规则命中直接执行不调大模型（0 token）；未命中才走大脑；
- 注入自定义文本感知而未注入结构化感知时跳过规则（离线可测）；
- 循环入口 heartbeat_loop / start_heartbeat 可 mock、可单轮。

brain 未就绪时用 patch.dict(sys.modules) 注入 FakeBrain（自动还原）；
并行测试模块（test_tools 等）会在 import 期向 sys.modules 注入同名 fake，
unittest discover 按字母序导入，本模块可能晚于它们被导入，故先按真实
文件路径加载 home_tools / heartbeat，保证被测对象与依赖绑定真实实现。
"""
import importlib.util
import os
import sys
import types
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


_ensure_real_modules("home_tools", "heartbeat")

import heartbeat
import xiaoju3


def _state(entity_id, state, friendly=""):
    return {"entity_id": entity_id, "state": state, "friendly_name": friendly}


class HeartbeatBase(unittest.TestCase):
    """公共基座：每轮测试前后清空快照，避免跨用例串扰。"""

    def setUp(self):
        heartbeat.reset_snapshot()

    def tearDown(self):
        heartbeat.reset_snapshot()


class SingleRoundTests(HeartbeatBase):
    """heartbeat_once 单轮逻辑：快照比对 → 决策 → 提取 JSON → 执行。"""

    def test_first_round_with_change_calls_brain_and_executes(self):
        ask = mock.MagicMock(return_value=(
            '收到，环境有变化。{"tool": "control_ha_device", "args": '
            '{"entity_id": "input_boolean.xiao_ju_ce_shi_deng", "action": "turn_on"}} '
            '已执行开灯。'))
        execute = mock.MagicMock(return_value="✅ 设备 ... 执行 turn_on 成功！")

        result = heartbeat.heartbeat_once(
            sense_fn=lambda: "- 小橘测试灯 (ID: input_boolean.xiao_ju_ce_shi_deng) 当前状态: off",
            ask_fn=ask, execute_fn=execute)

        # 决策被调用，且提示词携带内置测试灯规则
        ask.assert_called_once()
        prompt = ask.call_args.args[0][0]["content"]
        self.assertIn("小橘测试灯", prompt)
        self.assertIn("input_boolean.xiao_ju_ce_shi_deng", prompt)
        self.assertIn("无需干预", prompt)

        # 正则提取 JSON 后直接执行
        execute.assert_called_once_with(
            "control_ha_device",
            {"entity_id": "input_boolean.xiao_ju_ce_shi_deng", "action": "turn_on"})
        self.assertEqual(result, "✅ 设备 ... 执行 turn_on 成功！")

    def test_ask_returning_tuple_records_source(self):
        # ask_fn 返回 (决策文本, 来源标签)：来源同步记录（§10 #14）
        ask = mock.MagicMock(return_value=("无需干预", "🏠 本地"))
        result = heartbeat.heartbeat_once(sense_fn=lambda: "A", ask_fn=ask)
        self.assertEqual(result, "无需干预")
        self.assertEqual(heartbeat.last_decision_source, "🏠 本地")

    def test_no_change_skips_brain(self):
        ask = mock.MagicMock(return_value="无需干预")
        execute = mock.MagicMock()
        sensors = "- 灯 (ID: light.a) 当前状态: on"
        sense = lambda: sensors

        first = heartbeat.heartbeat_once(sense_fn=sense, ask_fn=ask, execute_fn=execute)
        self.assertEqual(first, "无需干预")
        ask.assert_called_once()
        execute.assert_not_called()

        # 第二轮快照无变化：直接跳过，不调大脑、不消耗 token
        second = heartbeat.heartbeat_once(sense_fn=sense, ask_fn=ask, execute_fn=execute)
        self.assertIsNone(second)
        ask.assert_called_once()  # 仍只有第一轮那一次
        execute.assert_not_called()

    def test_no_change_first_round_skips_entirely(self):
        # 模块快照初始为 ""，与空快照一致时首轮即跳过
        ask = mock.MagicMock()
        result = heartbeat.heartbeat_once(
            sense_fn=lambda: "", ask_fn=ask, execute_fn=mock.MagicMock())
        self.assertIsNone(result)
        ask.assert_not_called()

    def test_decision_without_tool_json_returns_hint(self):
        ask = mock.MagicMock(return_value="温度正常，但我不需要操作任何设备。")
        execute = mock.MagicMock()
        result = heartbeat.heartbeat_once(
            sense_fn=lambda: "状态A", ask_fn=ask, execute_fn=execute)
        self.assertEqual(result, "未解析到工具 JSON")
        execute.assert_not_called()

    def test_no_intervention_short_circuits(self):
        # 决策回复"无需干预"时即使含有大括号也不执行
        ask = mock.MagicMock(return_value="无需干预（无 { } 内容）")
        execute = mock.MagicMock()
        result = heartbeat.heartbeat_once(
            sense_fn=lambda: "状态B", ask_fn=ask, execute_fn=execute)
        self.assertEqual(result, "无需干预")
        execute.assert_not_called()

    def test_sense_exception_wrapped_not_raised(self):
        ask = mock.MagicMock()

        def boom():
            raise ConnectionError("HA 掉线")

        result = heartbeat.heartbeat_once(sense_fn=boom, ask_fn=ask)
        self.assertIn("⚠️ 循环异常", result)
        ask.assert_not_called()

    def test_snapshot_persists_across_rounds(self):
        ask = mock.MagicMock(return_value="无需干预")
        # 状态 A 出现两次 → 只有第一轮调大脑
        heartbeat.heartbeat_once(sense_fn=lambda: "A", ask_fn=ask)
        heartbeat.heartbeat_once(sense_fn=lambda: "A", ask_fn=ask)
        self.assertEqual(ask.call_count, 1)
        # 状态变化为 B → 再次唤醒大脑
        heartbeat.heartbeat_once(sense_fn=lambda: "B", ask_fn=ask)
        self.assertEqual(ask.call_count, 2)
        # 快照停留在 B
        self.assertEqual(heartbeat.last_sensors, "B")

    def test_reset_snapshot_clears_state(self):
        heartbeat.heartbeat_once(sense_fn=lambda: "A", ask_fn=mock.MagicMock(return_value="无需干预"))
        self.assertEqual(heartbeat.last_sensors, "A")
        heartbeat.reset_snapshot()
        self.assertEqual(heartbeat.last_sensors, "")


class LocalFirstDecisionTests(HeartbeatBase):
    """默认决策链路：本地优先（§10 #14），异常热切换云端，来源标注同步。"""

    def test_default_ask_prefers_local(self):
        fake_brain = types.ModuleType("brain")
        fake_brain.ask_local = mock.MagicMock(return_value="无需干预")
        fake_brain.ask_cloud = mock.MagicMock(return_value="不应被调用")
        with mock.patch.dict(sys.modules, {"brain": fake_brain}):
            result = heartbeat.heartbeat_once(sense_fn=lambda: "A")
        self.assertEqual(result, "无需干预")
        fake_brain.ask_local.assert_called_once()
        fake_brain.ask_cloud.assert_not_called()
        self.assertEqual(heartbeat.last_decision_source, "🏠 本地")
        messages = fake_brain.ask_local.call_args.args[0]
        self.assertEqual(messages[0]["role"], "user")
        self.assertIn("家庭 AI 中枢", messages[0]["content"])

    def test_default_ask_falls_back_to_cloud_on_local_error(self):
        fake_brain = types.ModuleType("brain")
        fake_brain.ask_local = mock.MagicMock(side_effect=ConnectionError("ollama 掉线"))
        fake_brain.ask_cloud = mock.MagicMock(return_value="无需干预")
        with mock.patch.dict(sys.modules, {"brain": fake_brain}):
            result = heartbeat.heartbeat_once(sense_fn=lambda: "A")
        self.assertEqual(result, "无需干预")
        fake_brain.ask_cloud.assert_called_once()
        self.assertEqual(heartbeat.last_decision_source, "☁️ 云端")

    def test_local_decision_with_tool_json_executes(self):
        decision = ('{"tool": "control_ha_device", "args": '
                    '{"entity_id": "input_boolean.xiao_ju_ce_shi_deng", "action": "turn_on"}}')
        fake_brain = types.ModuleType("brain")
        fake_brain.ask_local = mock.MagicMock(return_value=decision)
        execute = mock.MagicMock(return_value="✅ 执行成功")
        with mock.patch.dict(sys.modules, {"brain": fake_brain}):
            result = heartbeat.heartbeat_once(sense_fn=lambda: "A",
                                              execute_fn=execute)
        execute.assert_called_once_with(
            "control_ha_device",
            {"entity_id": "input_boolean.xiao_ju_ce_shi_deng", "action": "turn_on"})
        self.assertEqual(result, "✅ 执行成功")
        self.assertEqual(heartbeat.last_decision_source, "🏠 本地")


class SceneRuleEngineTests(HeartbeatBase):
    """场景规则引擎纯函数（§10 #10）：快照 diff → 动作列表。"""

    def test_rule1_coming_home_turns_on_off_lights(self):
        prev = [_state("binary_sensor.motion", "off", "人形传感器"),
                _state("light.living_room", "off", "客厅灯")]
        curr = [_state("binary_sensor.motion", "on", "人形传感器"),
                _state("light.living_room", "off", "客厅灯")]
        actions = heartbeat.apply_scene_rules(prev, curr)
        self.assertEqual(actions, [{"tool": "control_ha_device",
                                    "args": {"entity_id": "light.living_room",
                                             "action": "turn_on"}}])

    def test_rule1_door_sensor_transition_triggers(self):
        # 门窗传感器（binary_sensor，off=关 on=开）同样可触发回家开灯
        prev = [_state("binary_sensor.door", "off"), _state("light.hall", "off")]
        curr = [_state("binary_sensor.door", "on"), _state("light.hall", "off")]
        actions = heartbeat.apply_scene_rules(prev, curr)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["args"]["entity_id"], "light.hall")

    def test_rule1_no_trigger_when_stay_on(self):
        # 传感器持续 on（非 off→on 变化）→ 不触发
        prev = [_state("binary_sensor.motion", "on"), _state("light.a", "off")]
        curr = [_state("binary_sensor.motion", "on"), _state("light.a", "off")]
        self.assertEqual(heartbeat.apply_scene_rules(prev, curr), [])

    def test_rule1_no_trigger_when_no_off_light(self):
        prev = [_state("binary_sensor.motion", "off")]
        curr = [_state("binary_sensor.motion", "on"), _state("light.a", "on")]
        self.assertEqual(heartbeat.apply_scene_rules(prev, curr), [])

    def test_rule1_first_round_without_prev_no_trigger(self):
        # 首轮无上一轮参照（prev 为空）：变化型规则不触发，防启动误开灯
        curr = [_state("binary_sensor.motion", "on"), _state("light.a", "off")]
        self.assertEqual(heartbeat.apply_scene_rules([], curr), [])

    def test_rule1_not_home_states_do_not_trigger(self):
        # not_home → home 类状态（含 home 字样视为在家；not_home/away 视为离家）
        prev = [_state("binary_sensor.presence", "not_home"), _state("light.a", "off")]
        curr = [_state("binary_sensor.presence", "home"), _state("light.a", "off")]
        actions = heartbeat.apply_scene_rules(prev, curr)
        self.assertEqual(len(actions), 1)

    def test_rule2_humidity_below_threshold_turns_on_humidifier(self):
        curr = [_state("sensor.humidity", "35", "客厅湿度"),
                _state("switch.jiashiqi", "off", "卧室加湿器")]
        actions = heartbeat.apply_scene_rules([], curr)
        self.assertEqual(actions, [{"tool": "control_ha_device",
                                    "args": {"entity_id": "switch.jiashiqi",
                                             "action": "turn_on"}}])

    def test_rule2_english_humidifier_naming(self):
        curr = [_state("sensor.humidity", "30"), _state("switch.humidifier", "off")]
        actions = heartbeat.apply_scene_rules([], curr)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["args"]["entity_id"], "switch.humidifier")

    def test_rule2_no_trigger_when_humidity_high(self):
        curr = [_state("sensor.humidity", "55"), _state("switch.humidifier", "off")]
        self.assertEqual(heartbeat.apply_scene_rules([], curr), [])

    def test_rule2_no_trigger_when_humidifier_already_on(self):
        curr = [_state("sensor.humidity", "35"), _state("switch.humidifier", "on")]
        self.assertEqual(heartbeat.apply_scene_rules([], curr), [])

    def test_rule2_no_trigger_when_no_humidifier_device(self):
        curr = [_state("sensor.humidity", "35"), _state("switch.plug", "off")]
        self.assertEqual(heartbeat.apply_scene_rules([], curr), [])

    def test_humidity_threshold_env_overrides(self):
        curr = [_state("sensor.humidity", "35"), _state("switch.humidifier", "off")]
        base_env = dict(os.environ)
        base_env.pop(heartbeat.HUMIDITY_THRESHOLD_ENV, None)
        # 默认阈值 40：35 命中
        with mock.patch.dict(os.environ, base_env, clear=True):
            self.assertEqual(len(heartbeat.apply_scene_rules([], curr)), 1)
        # env 阈值 30：35 不再命中（env 调用时读取，patch.dict 自动还原）
        env30 = dict(base_env)
        env30[heartbeat.HUMIDITY_THRESHOLD_ENV] = "30"
        with mock.patch.dict(os.environ, env30, clear=True):
            self.assertEqual(heartbeat.apply_scene_rules([], curr), [])
        # env 阈值 50：湿度 45 命中（低于阈值才算干）
        env50 = dict(base_env)
        env50[heartbeat.HUMIDITY_THRESHOLD_ENV] = "50"
        with mock.patch.dict(os.environ, env50, clear=True):
            curr50 = [_state("sensor.humidity", "45"), _state("switch.humidifier", "off")]
            self.assertEqual(len(heartbeat.apply_scene_rules([], curr50)), 1)

    def test_invalid_threshold_env_falls_back_to_default(self):
        base_env = dict(os.environ)
        base_env.pop(heartbeat.HUMIDITY_THRESHOLD_ENV, None)
        base_env[heartbeat.HUMIDITY_THRESHOLD_ENV] = "not-a-number"
        with mock.patch.dict(os.environ, base_env, clear=True):
            curr = [_state("sensor.humidity", "35"), _state("switch.humidifier", "off")]
            self.assertEqual(len(heartbeat.apply_scene_rules([], curr)), 1)

    def test_explicit_threshold_param_wins(self):
        curr = [_state("sensor.humidity", "35"), _state("switch.humidifier", "off")]
        self.assertEqual(heartbeat.apply_scene_rules([], curr, humidity_threshold=20), [])

    def test_rules_dedupe_actions(self):
        # 两个湿度传感器同时低于阈值：同一加湿器只生成一条动作
        curr = [_state("sensor.humidity", "30"), _state("sensor.bedroom_humidity", "33"),
                _state("switch.humidifier", "off")]
        actions = heartbeat.apply_scene_rules([], curr)
        self.assertEqual(len(actions), 1)

    def test_rules_only_emit_turn_on_for_safe_entities(self):
        # 规则动作恒为 turn_on，且不会命中高危实体（lock/燃气不在规则范围）
        curr = [_state("sensor.humidity", "20"), _state("lock.front_door", "off"),
                _state("switch.gas_valve", "off")]
        actions = heartbeat.apply_scene_rules([], curr)
        for a in actions:
            self.assertEqual(a["args"]["action"], "turn_on")
            self.assertNotIn("gas", a["args"]["entity_id"])


class HeartbeatRuleIntegrationTests(HeartbeatBase):
    """heartbeat_once 与规则引擎集成：命中不耗 token，未命中才走大脑。"""

    def test_rule_hit_executes_without_llm(self):
        heartbeat.last_states = [_state("sensor.humidity", "55"),
                                 _state("switch.humidifier", "off")]
        ask = mock.MagicMock()
        execute = mock.MagicMock(return_value="✅ 设备 switch.humidifier 执行 turn_on 成功！")
        states = [_state("sensor.humidity", "35", "客厅湿度"),
                  _state("switch.humidifier", "off", "加湿器")]

        result = heartbeat.heartbeat_once(
            sense_fn=lambda: "- 有变化 -",
            sense_states_fn=lambda: states,
            ask_fn=ask, execute_fn=execute)

        execute.assert_called_once_with(
            "control_ha_device", {"entity_id": "switch.humidifier", "action": "turn_on"})
        ask.assert_not_called()  # 规则命中：不耗 token
        self.assertIn("turn_on 成功", result)
        self.assertEqual(heartbeat.last_decision_source, "📋 本地规则")
        self.assertEqual(heartbeat.last_states, states)  # 结构化快照已更新

    def test_rule_miss_falls_back_to_llm(self):
        ask = mock.MagicMock(return_value="无需干预")
        execute = mock.MagicMock()
        states = [_state("sensor.humidity", "60"), _state("switch.humidifier", "off")]

        result = heartbeat.heartbeat_once(
            sense_fn=lambda: "- 有变化 -",
            sense_states_fn=lambda: states,
            ask_fn=ask, execute_fn=execute)

        ask.assert_called_once()
        execute.assert_not_called()
        self.assertEqual(result, "无需干预")

    def test_injected_text_sense_without_states_skips_rules(self):
        # 注入自定义文本感知而未注入结构化感知：跳过规则引擎，直接走大脑
        ask = mock.MagicMock(return_value="无需干预")
        result = heartbeat.heartbeat_once(
            sense_fn=lambda: "- 文本快照 -", ask_fn=ask)
        ask.assert_called_once()
        self.assertEqual(result, "无需干预")

    def test_states_fetch_failure_falls_back_to_llm(self):
        # 结构化感知返回非列表（获取失败）→ 跳过规则，走大脑
        ask = mock.MagicMock(return_value="无需干预")
        result = heartbeat.heartbeat_once(
            sense_fn=lambda: "- 有变化 -",
            sense_states_fn=lambda: "❌ HA 掉线",
            ask_fn=ask)
        ask.assert_called_once()
        self.assertEqual(result, "无需干预")


class DefaultWiringTests(HeartbeatBase):
    """默认链路：感知走 get_ha_devices / get_ha_states；brain 延迟导入。"""

    def test_default_sense_uses_get_ha_devices(self):
        with mock.patch.object(heartbeat, "get_ha_devices",
                               return_value="- 灯 (ID: light.a) 当前状态: on") as msense, \
             mock.patch.object(heartbeat, "get_ha_states", return_value=[]), \
             mock.patch.object(heartbeat, "_default_ask", return_value="无需干预") as mask, \
             mock.patch.object(heartbeat, "_default_execute") as mexe:
            result = heartbeat.heartbeat_once()

        msense.assert_called_once()
        mask.assert_called_once()
        mexe.assert_not_called()
        self.assertEqual(result, "无需干预")

    def test_default_sense_states_uses_get_ha_states(self):
        with mock.patch.object(heartbeat, "get_ha_devices", return_value="变化"), \
             mock.patch.object(heartbeat, "get_ha_states",
                               return_value=[_state("sensor.humidity", "35"),
                                             _state("switch.humidifier", "off")]) as mstates, \
             mock.patch.object(heartbeat, "_default_execute",
                               return_value="✅ 执行成功") as mexe:
            result = heartbeat.heartbeat_once()
        mstates.assert_called_once()
        # 默认链路同样规则命中即执行、不调大脑（_default_ask 未被打桩也不该被调）
        mexe.assert_called_once_with(
            "control_ha_device", {"entity_id": "switch.humidifier", "action": "turn_on"})
        self.assertIn("执行成功", result)

    def test_default_execute_goes_through_tools_layer(self):
        """默认执行走统一工具层 tools.execute_tool（系统身份 Lv.3）。"""
        decision = ('{"tool": "control_ha_device", "args": '
                    '{"entity_id": "input_boolean.xiao_ju_ce_shi_deng", "action": "turn_on"}}')
        with mock.patch.object(heartbeat, "_default_execute",
                               return_value="✅ 执行成功") as mexe:
            result = heartbeat.heartbeat_once(sense_fn=lambda: "A", ask_fn=lambda m: decision)
        mexe.assert_called_once_with(
            "control_ha_device",
            {"entity_id": "input_boolean.xiao_ju_ce_shi_deng", "action": "turn_on"})
        self.assertEqual(result, "✅ 执行成功")


class LoopTests(HeartbeatBase):
    """heartbeat_loop / start_heartbeat：循环入口可 mock、可单测单轮。"""

    def test_loop_single_round_sleep_then_sense(self):
        ask = mock.MagicMock(return_value="无需干预")
        manager = mock.MagicMock()
        sleep = mock.MagicMock()
        manager.attach_mock(sleep, "sleep")

        with mock.patch.object(heartbeat.time, "sleep", sleep):
            heartbeat.heartbeat_loop(interval=3, sense_fn=lambda: "A",
                                     ask_fn=ask, execute_fn=mock.MagicMock(),
                                     max_rounds=1)

        ask.assert_called_once()
        # 参考实现口径：先休眠再感知（sleep 先于本轮决策）
        self.assertEqual(manager.mock_calls[0][0], "sleep")
        sleep.assert_called_once_with(3)

    def test_loop_default_interval_from_config(self):
        with mock.patch.object(heartbeat.time, "sleep") as msleep:
            heartbeat.heartbeat_loop(sense_fn=lambda: "", max_rounds=1)
        msleep.assert_called_once_with(xiaoju3.HEARTBEAT_INTERVAL)

    def test_loop_multiple_rounds(self):
        states = iter(["A", "B"])
        ask = mock.MagicMock(return_value="无需干预")
        with mock.patch.object(heartbeat.time, "sleep"):
            heartbeat.heartbeat_loop(interval=0, sense_fn=lambda: next(states),
                                     ask_fn=ask, max_rounds=2)
        self.assertEqual(ask.call_count, 2)

    def test_start_heartbeat_runs_daemon_thread(self):
        loop = mock.MagicMock()
        with mock.patch.object(heartbeat, "heartbeat_loop", loop):
            thread = heartbeat.start_heartbeat(interval=1)
            thread.join(timeout=5)
        self.assertTrue(thread.daemon)
        loop.assert_called_once_with(1)


class DecisionPromptTests(HeartbeatBase):
    """内置决策提示词（参考实现口径：测试灯规则）。"""

    def test_prompt_contains_test_lamp_rule(self):
        prompt = heartbeat.build_decision_prompt("- 快照内容 -")
        self.assertIn("- 快照内容 -", prompt)
        self.assertIn("小橘测试灯", prompt)
        self.assertIn("control_ha_device", prompt)
        self.assertIn("无需干预", prompt)




class EmergencyExemptionTests(unittest.TestCase):
    """紧急豁免：危险传感器报警 → 绕过权限强制 turn_off + 日志 + QQ 推送。"""

    def setUp(self):
        self._old_snapshot = dict(heartbeat.last_states) if heartbeat.last_states else None
        heartbeat.reset_snapshot()

    def tearDown(self):
        heartbeat.reset_snapshot()
        if self._old_snapshot is not None:
            heartbeat.last_states = self._old_snapshot

    @staticmethod
    def _states(gas="on"):
        return [
            {"entity_id": "binary_sensor.kitchen_gas", "state": gas},
            {"entity_id": "lock.front_door", "state": "locked"},
            {"entity_id": "switch.kitchen_gas_valve", "state": "on"},
            {"entity_id": "light.living", "state": "off"},
        ]

    def test_no_alarm_returns_none(self):
        self.assertIsNone(heartbeat.emergency_check(self._states(gas="off")))

    def test_gas_alarm_forces_turn_off_on_associated_device(self):
        with mock.patch.object(heartbeat, "notify_master") as mnotify,                 mock.patch("home_tools.control_ha_device") as mctl:
            mctl.return_value = "✅ 已关闭"
            result = heartbeat.emergency_check(self._states())
        self.assertIsNotNone(result)
        entity = mctl.call_args.args[0]
        action = mctl.call_args.args[1]
        self.assertEqual(action, "turn_off")          # 只准关不准开
        self.assertIn("gas_valve", entity)            # 关联词元优先
        mnotify.assert_called_once()                  # 必推送通知

    def test_alarm_never_turns_on(self):
        with mock.patch.object(heartbeat, "notify_master"),                 mock.patch("home_tools.control_ha_device") as mctl:
            mctl.return_value = "✅"
            heartbeat.emergency_check(self._states())
        for c in mctl.call_args_list:
            self.assertEqual(c.args[1], "turn_off")

    def test_no_association_shuts_all_dangerous(self):
        states = [{"entity_id": "binary_sensor.gas_leak", "state": "on"},
                  {"entity_id": "lock.front_door", "state": "locked"},
                  {"entity_id": "light.living", "state": "off"}]
        with mock.patch.object(heartbeat, "notify_master"),                 mock.patch("home_tools.control_ha_device") as mctl:
            mctl.return_value = "✅"
            heartbeat.emergency_check(states)
        targets = [c.args[0] for c in mctl.call_args_list]
        self.assertEqual(targets, ["lock.front_door"])   # 无词元交集→全部危险设备；灯不涉及

    def test_heartbeat_once_priority_over_rules(self):
        """心跳单轮：紧急豁免优先于场景规则与大模型决策。"""
        states = self._states()
        with mock.patch.object(heartbeat, "notify_master"), \
                mock.patch("home_tools.control_ha_device") as mctl, \
                mock.patch.object(heartbeat, "apply_scene_rules") as mrules, \
                mock.patch.object(heartbeat, "_default_ask", return_value="无需干预"), \
                mock.patch.object(heartbeat, "_default_sense_states", return_value=states):
            mctl.return_value = "✅ 已关闭"
            mrules.return_value = []
            result = heartbeat.heartbeat_once(verbose=False)
        self.assertIsNotNone(result)
        self.assertIn("紧急豁免", result)
        mctl.assert_called()                           # 豁免动作已执行

    def test_notify_master_without_owner_qq_skips(self):
        with mock.patch.dict(os.environ, {"XIAOJU3_OWNER_QQ": ""}),                 mock.patch("requests.post") as mpost:
            ok = heartbeat.notify_master("测试")
        self.assertFalse(ok)
        mpost.assert_not_called()


if __name__ == "__main__":
    unittest.main()
