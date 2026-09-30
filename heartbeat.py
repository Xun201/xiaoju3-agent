# -*- coding: utf-8 -*-
"""小橘3号 · 主动服务心跳。

按《架构设计文档》§7 / 功能文档 §8.2 / §8.4，第二阶段路线图 §10 #10
（传感器场景联动）与 #14（心跳决策本地化）：

1. 状态感知：每 60 秒（xiaoju3.HEARTBEAT_INTERVAL）轮询 Home Assistant
   /api/states（经 home_tools.get_ha_devices 六类过滤），与上次快照比对
   ——无变化直接跳过，不消耗 token（延续原文档省 token 哲学）。
2. 场景规则优先（§10 #10，先规则后大模型——规则命中就不耗 token）：
   apply_scene_rules 纯函数（上一轮结构化快照 diff 本轮快照 → 动作列表）：
   ① 回家开灯：binary_sensor.* 人形/门窗传感器（状态值含 on/home 视为
     "在家/触发"）从 off→on，且当前有灯（light.*）为 off → 生成开灯控制；
   ② 空气干燥开加湿器：湿度 sensor（entity_id/名称含 humidity/湿度）
     低于阈值（默认 40，env XIAOJU3_HUMIDITY_THRESHOLD 可覆盖），且存在
     含"加湿/humidifier"的 switch/轻设备（switch/light/input_boolean）为
     off → 开启。
   规则只生成 turn_on 开启类动作、不涉及高危实体（lock/燃气见
   home_tools.is_dangerous_entity，不在规则范围内）。
3. 规则未命中才唤醒大脑：本地优先决策（§10 #14 兑现"心跳决策回归本地
   优先决策"）——先 brain.ask_local（延迟导入），异常热切换 ask_cloud，
   来源标签记录于 heartbeat.last_decision_source；从决策中正则提取工具
   JSON 并经 tools.execute_tool 直接执行。

两种形态：
- 独立运行：python heartbeat.py
- 线程宿主：start_heartbeat() 以 daemon 线程拉起 heartbeat_loop

感知（文本 / 结构化）/ 决策 / 执行四个环节均可注入替换（sense_fn /
sense_states_fn / ask_fn / execute_fn），heartbeat_once 支持单轮离线单测；
注入自定义文本感知而未注入结构化感知时跳过规则引擎（保持离线可测）。
ask_fn 兼容两种返回：str（来源未知）或 (决策文本, 来源标签) 二元组。
"""
import json
import os
import re
import threading
import time

from xiaoju3 import HEARTBEAT_INTERVAL
from home_tools import get_ha_devices, get_ha_states

# 上一轮的文本快照（无变化即跳过，不耗 token）与结构化快照（场景规则 diff 用）
last_sensors = ""
last_states = []
# 最近一次大模型决策的来源标签（"🏠 本地" / "☁️ 云端"；规则命中时为 "📋 本地规则"）
last_decision_source = ""

# 湿度阈值默认值（功能文档 §8.4："空气太干就开加湿器"），env 可覆盖
DEFAULT_HUMIDITY_THRESHOLD = 40.0
HUMIDITY_THRESHOLD_ENV = "XIAOJU3_HUMIDITY_THRESHOLD"


def reset_snapshot():
    """清空快照（测试 / 重置用）。"""
    global last_sensors, last_states, last_decision_source
    last_sensors = ""
    last_states = []
    last_decision_source = ""


def _default_sense():
    """感知：获取 HA 六类实体状态摘要（文本）。"""
    return get_ha_devices()


def _default_sense_states():
    """感知：获取 HA 六类实体结构化状态（场景规则 diff 用），异常返回 []。"""
    try:
        states = get_ha_states()
        return states if isinstance(states, list) else []
    except Exception:
        return []


def _default_ask(messages):
    """决策：本地优先（§10 #14 心跳决策本地化）——先 brain.ask_local，
    异常热切换 ask_cloud。返回 (决策文本, 来源标签)。
    brain 由并行模块提供，延迟导入（未就绪时报错并转云端，均失败则异常
    由 heartbeat_once 捕获）。"""
    import brain
    try:
        return brain.ask_local(messages), "🏠 本地"
    except Exception as e:
        print(f"⚠️ [心跳] 本地决策失败（{e}），自动转云端决策...")
        return brain.ask_cloud(messages), "☁️ 云端"


def _default_execute(tool_name, args):
    """执行：心跳为系统级主动服务（功能文档 §8.2 权限口径：系统），
    以系统身份（Lv.3）走统一工具层 tools.execute_tool，保留高危门禁链路。"""
    from tools import execute_tool
    from permission import PermissionManager
    pm = PermissionManager()
    pm.current_level = "Lv.3"
    return execute_tool(tool_name, args, pm)


# ==================== 紧急豁免机制（危险传感器报警 → 强制关闭） ====================
# 定稿口径：当 HA 的危险传感器（煤气/烟雾/水浸等）报警时，心跳引擎绕过所有
# 权限限制，对关联的危险设备直接发送 turn_off（只准关不准开）；每次豁免必须
# 打印日志并 QQ 推送通知主人。物理机械开关优先级永远高于软件控制。

_EMERGENCY_SENSOR_PAT = re.compile(r"gas|smoke|flood|leak|燃气|煤气|烟雾|水浸|漏水", re.IGNORECASE)
_EMERGENCY_ALARM_STATES = {"on", "alarm", "triggered", "gas", "smoke", "leak", "wet"}


def notify_master(text):
    """QQ 推送通知主人（NapCat send_private_msg；未配置则仅日志，不抛错）。"""
    api = (os.environ.get("NAPCAT_API_URL", "") or "http://127.0.0.1:3000").rstrip("/")
    owner = (os.environ.get("XIAOJU3_OWNER_QQ", "") or "").strip()
    if not owner:
        print("📨 [紧急豁免] 未配置 XIAOJU3_OWNER_QQ，跳过 QQ 推送（仅记录日志）。")
        return False
    try:
        import requests
        requests.post(f"{api}/send_private_msg",
                      json={"user_id": owner, "message": text}, timeout=5)
        print("📨 已推送 QQ 通知主人（紧急豁免）。")
        return True
    except Exception as e:
        print(f"⚠️ [紧急豁免] QQ 推送失败（不影响豁免动作）: {e}")
        return False


def _is_emergency_sensor(entity_id, state):
    """是否处于报警状态的危险传感器（煤气/烟雾/水浸类）。

    限定 binary_sensor./sensor. 域 + 实体名匹配 + 报警态——避免把名字里带
    gas 的开关/阀门设备本身误判为报警源。
    """
    eid = (entity_id or "").lower()
    if not (eid.startswith("binary_sensor.") or eid.startswith("sensor.")):
        return False
    if not _EMERGENCY_SENSOR_PAT.search(eid):
        return False
    return str(state or "").strip().lower() in _EMERGENCY_ALARM_STATES


def _emergency_targets(sensor_entity, states):
    """与报警传感器关联的危险设备：优先共享名称词元（如同属厨房），
    无词元交集时回退为全部危险设备（宁多关不漏关；只发 turn_off）。
    报警传感器自身永不作为关闭目标。"""
    import home_tools
    tokens = {t for t in re.split(r"[_\W]+", (sensor_entity or "").lower()) if t}
    dangerous = [e.get("entity_id") for e in states
                 if home_tools.is_dangerous_entity(e.get("entity_id", ""))
                 and e.get("entity_id") != sensor_entity]
    shared = [d for d in dangerous
              if tokens & {t for t in re.split(r"[_\W]+", (d or "").lower()) if t}]
    return shared or dangerous


def emergency_check(states, verbose=True):
    """紧急豁免主入口：扫描结构化状态，报警即强制关闭关联危险设备。

    - 绕过 tools.execute_tool 权限门禁，直接调 home_tools.control_ha_device；
    - 只允许 turn_off，代码级禁止 turn_on；
    - 每次豁免打印日志并 QQ 推送通知主人。
    返回豁免动作说明文本；无报警返回 None。
    """
    triggered = [(e.get("entity_id", ""), e.get("state", "")) for e in (states or [])
                 if _is_emergency_sensor(e.get("entity_id", ""), e.get("state", ""))]
    if not triggered:
        return None

    from home_tools import control_ha_device
    logs = []
    for sensor_id, state in triggered:
        targets = _emergency_targets(sensor_id, states)
        if not targets:
            continue
        for dev in targets:
            print(f"🚨 [紧急豁免] {sensor_id} 报警（state={state}）："
                  f"绕过权限限制，强制关闭危险设备 {dev}（只准关不准开）")
            try:
                result = control_ha_device(dev, "turn_off")
            except Exception as e:
                result = f"❌ 下发失败: {e}"
            logline = f"🚨 紧急豁免：{sensor_id} 报警 → 强制关闭 {dev} → {result}"
            print(logline)
            logs.append(logline)
            notify_master(f"🚨 小橘3号紧急豁免：{sensor_id} 报警（{state}），"
                          f"已强制关闭 {dev}。结果：{result}")
    return "\n".join(logs) if logs else None


# ==================== 传感器场景规则引擎（§10 #10，纯函数） ====================

def _humidity_threshold():
    """湿度阈值：env XIAOJU3_HUMIDITY_THRESHOLD 调用时读取（便于测试注入），
    非法值回退默认 40。"""
    try:
        return float(os.environ.get(HUMIDITY_THRESHOLD_ENV,
                                    str(DEFAULT_HUMIDITY_THRESHOLD)))
    except (TypeError, ValueError):
        return DEFAULT_HUMIDITY_THRESHOLD


def _is_present(state):
    """binary_sensor 状态是否视为"在家/触发"（状态值含 on/home；not_home/away 视为离家）。"""
    s = str(state).lower()
    if "not_home" in s or "away" in s:
        return False
    return ("on" in s) or ("home" in s)


def _is_humidifier(entity):
    """是否加湿器类轻设备（entity_id / friendly_name 含 加湿/humidifier）。"""
    eid = str(entity.get("entity_id", "")).lower()
    name = str(entity.get("friendly_name", "")).lower()
    return ("加湿" in name) or ("加湿" in eid) or \
           ("humidifier" in eid) or ("humidifier" in name)


def _humidity_value(entity):
    """湿度传感器的数值；非湿度实体或状态不可转 float 返回 None。"""
    eid = str(entity.get("entity_id", "")).lower()
    name = str(entity.get("friendly_name", "")).lower()
    if ("humidity" not in eid and "湿度" not in eid
            and "humidity" not in name and "湿度" not in name):
        return None
    try:
        return float(str(entity.get("state", "")))
    except (TypeError, ValueError):
        return None


def apply_scene_rules(prev_states, curr_states, humidity_threshold=None):
    """场景规则引擎（纯函数）：上一轮快照 diff 本轮快照 → 动作列表。

    参数为结构化实体列表 [{entity_id, state, friendly_name}]（prev 可为
    空列表=首轮，无上一轮参照时不触发"变化型"规则①）；返回动作列表：
    [{"tool": "control_ha_device", "args": {"entity_id": ..., "action": "turn_on"}}]

    规则表 DEFAULT_SCENE_RULES：
    ① 回家开灯：binary_sensor.* 人形/门窗传感器 off→on（变化型，需 prev）
       且当前有灯（light.*）为 off → 逐盏开启；
    ② 空气干燥开加湿器：湿度 sensor < 阈值（默认 40，env
       XIAOJU3_HUMIDITY_THRESHOLD 可覆盖）且含"加湿/humidifier"的
       switch/轻设备为 off → 开启（当前状态型，调用方保证仅在快照变化时
       才调用本函数）。
    规则命中由 heartbeat_once 直接执行（不耗 token）；规则只产 turn_on
    开启类动作，不涉及高危实体。
    """
    if humidity_threshold is None:
        humidity_threshold = _humidity_threshold()
    curr = [e for e in (curr_states or []) if isinstance(e, dict)]
    prev = {str(e.get("entity_id")): e
            for e in (prev_states or []) if isinstance(e, dict)}

    actions = []

    # 当前为 off 的灯（规则①素材）
    lights_off = [str(e.get("entity_id")) for e in curr
                  if str(e.get("entity_id", "")).startswith("light.")
                  and str(e.get("state")) == "off"]

    coming_home = False
    for e in curr:
        eid = str(e.get("entity_id", ""))

        # 规则①：回家开灯（人形/门窗传感器 off→on，需有上一轮参照）
        if eid.startswith("binary_sensor.") and eid in prev \
                and not _is_present(prev[eid].get("state")) \
                and _is_present(e.get("state")):
            coming_home = True

        # 规则②：空气干燥开加湿器
        humidity = _humidity_value(e)
        if humidity is not None and humidity < humidity_threshold:
            for h in curr:
                hid = str(h.get("entity_id", ""))
                if _is_humidifier(h) and str(h.get("state")) == "off" \
                        and not hid.startswith(("sensor.", "climate.", "media_player.")):
                    actions.append({"tool": "control_ha_device",
                                    "args": {"entity_id": hid, "action": "turn_on"}})

    if coming_home:
        for lid in lights_off:
            actions.append({"tool": "control_ha_device",
                            "args": {"entity_id": lid, "action": "turn_on"}})

    # 去重（同一实体同一动作只保留一条）
    seen, unique = set(), []
    for a in actions:
        key = (a["args"]["entity_id"], a["args"]["action"])
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return unique


# ==================== 心跳主流程 ====================

def build_decision_prompt(sensors):
    """内置决策规则（参考实现口径：当前为测试灯规则原型）。"""
    return f"""你是家庭 AI 中枢。当前家庭环境状态如下：
{sensors}

【测试任务】请检查名为 "小橘测试灯" 的设备。如果你发现它的状态是 "off"（关闭），
请必须输出以下 JSON 来把它打开：
{{"tool": "control_ha_device", "args": {{"entity_id": "input_boolean.xiao_ju_ce_shi_deng", "action": "turn_on"}}}}

如果你发现它已经是 "on"（开启），则请只回复"无需干预"四个字，绝不要输出其他内容！"""


def heartbeat_once(sense_fn=None, ask_fn=None, execute_fn=None,
                   sense_states_fn=None, verbose=True):
    """单轮心跳：感知 → 比对快照 →（有变化才）场景规则 → 大模型决策 → 执行。

    返回本轮动作说明；快照无变化返回 None（不调大脑、不消耗 token）。
    场景规则命中时直接执行规则动作并返回结果（不调大模型，0 token）；
    ask_fn 可返回 str 或 (决策文本, 来源标签)，来源记录于
    last_decision_source。注入自定义文本感知而未注入结构化感知时跳过
    规则引擎（保持离线可测）。
    """
    sense = sense_fn or _default_sense
    ask = ask_fn or _default_ask
    execute = execute_fn or _default_execute
    if sense_states_fn is not None:
        states_fn = sense_states_fn
    elif sense_fn is None:
        states_fn = _default_sense_states
    else:
        states_fn = None  # 注入文本感知但未给结构化感知：跳过规则引擎

    global last_sensors, last_states, last_decision_source
    try:
        # 1. 感知：获取 HA 环境状态
        sensors = sense()

        # 🛡️ 核心优化：如果状态没有变化，直接跳过，不消耗 token！
        if sensors == last_sensors:
            return None

        last_sensors = sensors
        if verbose:
            print("💓 [心跳] 检测到环境变化，唤醒决策...")

        # 2. 场景规则优先：命中直接执行，不耗 token（§10 #10）
        if states_fn is not None:
            states = states_fn()
            if isinstance(states, list):
                # 🚨 紧急豁免：危险传感器报警 → 绕过权限强制关闭关联危险设备
                # （优先级最高，先于一切场景规则与大模型决策）
                emergency = emergency_check(states, verbose=verbose)
                if emergency:
                    last_decision_source = "🚨 紧急豁免"
                    return emergency
                actions = apply_scene_rules(last_states, states)
                last_states = states
                if actions:
                    if verbose:
                        print(f"📋 [心跳] 场景规则命中 {len(actions)} 条动作"
                              "（本地规则，0 token），直接执行...")
                    results = [str(execute(a["tool"], a["args"])) for a in actions]
                    if verbose:
                        for r in results:
                            print(f"⚡ [心跳] 规则动作结果：{r}")
                    last_decision_source = "📋 本地规则"
                    return "\n".join(results)
            elif verbose:
                print("⚠️ [心跳] 结构化状态不可用，本轮跳过场景规则。")

        # 3. 大模型决策：本地优先，异常转云端（§10 #14）
        decision_raw = ask([{"role": "user", "content": build_decision_prompt(sensors)}])
        if isinstance(decision_raw, tuple) and len(decision_raw) >= 2:
            decision, source = decision_raw[0], decision_raw[1]
        else:
            decision, source = decision_raw, ""
        last_decision_source = source
        if verbose:
            print(f"🧠 [心跳] 大脑决策[{source or '来源未知'}]：{str(decision)[:50]}...")

        # 4. 执行
        decision = str(decision)
        if "无需干预" in decision:
            return "无需干预"

        match = re.search(r'\{.*"tool".*\}', decision, re.DOTALL)
        if not match:
            if verbose:
                print("⚠️ [心跳] 决策中未解析到工具 JSON，跳过执行。")
            return "未解析到工具 JSON"

        tool_call = json.loads(match.group(0))
        tool_args = tool_call.get("args", {})

        if verbose:
            print(f"⚡ [心跳] 主动执行: {tool_call}")
        result = execute(tool_call.get("tool"), tool_args)
        if verbose:
            print(f"✅ [心跳] 结果：{result}")
        return result
    except Exception as e:
        if verbose:
            print(f"⚠️ [心跳] 循环异常: {e}")
        return f"⚠️ 循环异常: {e}"


def heartbeat_loop(interval=None, sense_fn=None, ask_fn=None, execute_fn=None,
                   sense_states_fn=None, max_rounds=None):
    """自主心跳循环：每隔 N 秒感知环境并决策（参考实现口径：先休眠再感知）。

    max_rounds 仅供测试限定轮数；生产传 None 无限循环。
    """
    if interval is None:
        interval = HEARTBEAT_INTERVAL
    print("💓 [心跳] 引擎已启动，正在监听家庭环境...")
    rounds = 0
    while True:
        time.sleep(interval)
        heartbeat_once(sense_fn=sense_fn, ask_fn=ask_fn, execute_fn=execute_fn,
                       sense_states_fn=sense_states_fn)
        rounds += 1
        if max_rounds is not None and rounds >= max_rounds:
            break


def start_heartbeat(interval=None):
    """线程宿主形态：以 daemon 线程启动心跳循环。"""
    if interval is None:
        interval = HEARTBEAT_INTERVAL
    thread = threading.Thread(target=heartbeat_loop, args=(interval,), daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    heartbeat_loop()
