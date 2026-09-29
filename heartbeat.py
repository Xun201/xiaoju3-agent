import time
import json
import re
import threading
from home_tools import get_ha_states, control_ha_device
from brain import ask_cloud

# 记录上一次的环境状态快照
last_sensors = ""

def heartbeat_loop(interval=60):
    global last_sensors
    """自主心跳循环：每隔 N 秒感知环境并决策"""
    print("💓 [心跳] 引擎已启动，正在监听家庭环境...")
    while True:
        time.sleep(interval)
        try:
            # 1. 感知：获取 HA 环境状态
            sensors = get_ha_states()
            
            # 🛡️ 核心优化：如果状态没有变化，直接跳过，不消耗 token！
            if sensors == last_sensors:
                # print("💓 [心跳] 环境无变化，跳过决策。")
                continue
                
            last_sensors = sensors
            print("💓 [心跳] 检测到环境变化，唤醒大脑决策...")
            
            # 2. 决策：判断是否需要干预
            prompt = f"""你是家庭 AI 中枢。当前家庭环境状态如下：
{sensors}

【测试任务】请检查名为 "小橘测试灯" 的设备。如果你发现它的状态是 "off"（关闭），
请必须输出以下 JSON 来把它打开：
{{"tool": "control_ha_device", "args": {{"entity_id": "input_boolean.xiao_ju_ce_shi_deng", "action": "turn_on"}}}}

如果你发现它已经是 "on"（开启），则请只回复"无需干预"四个字，绝不要输出其他内容！"""
            
            decision = ask_cloud([{"role": "user", "content": prompt}])
            print(f"🧠 [心跳] 大脑决策：{decision[:50]}...")
            
            # 3. 执行
            if "无需干预" not in decision:
                match = re.search(r'\{.*"tool".*\}', decision, re.DOTALL)
                if match:
                    tool_call = json.loads(match.group(0))
                    tool_args = tool_call.get("args", {})
                    
                    print(f"⚡ [心跳] 主动执行: {tool_call}")
                    result = control_ha_device(tool_args.get("entity_id"), tool_args.get("action"))
                    print(f"✅ [心跳] 结果：{result}")
        except Exception as e:
            print(f"⚠️ [心跳] 循环异常: {e}")

def start_heartbeat():
    thread = threading.Thread(target=heartbeat_loop, args=(60,), daemon=True)
    thread.start()