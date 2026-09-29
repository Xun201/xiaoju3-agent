import os
import requests
from dotenv import load_dotenv

# 从隔离区读取环境变量
load_dotenv("/home/orangepi/xiaoju3_data/.env")

HA_URL = os.getenv("HA_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")

headers = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}

def get_ha_states():
    """获取所有智能家居设备的状态（用于让AI了解有哪些设备可以控制）"""
    try:
        response = requests.get(f"{HA_URL}/api/states", headers=headers, timeout=10)
        response.raise_for_status()
        devices = response.json()
        
        summary = []
        for dev in devices:
            entity_id = dev.get("entity_id", "")
            state = dev.get("state", "")
            attributes = dev.get("attributes", {})
            friendly_name = attributes.get("friendly_name", "未知设备")
            
            if any(domain in entity_id for domain in ["input_boolean", "light", "switch", "sensor", "climate", "media_player"]):
                summary.append(f"- {friendly_name} (ID: {entity_id}) 当前状态: {state}")
        
        return "\n".join(summary) if summary else "当前没有发现可控设备。"
    except Exception as e:
        return f"❌ 获取HA设备列表失败: {e}"

def control_ha_device(entity_id, action):
    """控制智能家居设备 action: turn_on, turn_off, toggle"""
    if action not in ["turn_on", "turn_off", "toggle"]:
        return f"❌ 不支持的动作: {action}，仅支持 turn_on, turn_off, toggle"
        
    try:
        url = f"{HA_URL}/api/services/homeassistant/{action}"
        payload = {"entity_id": entity_id}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        return f"✅ 设备 {entity_id} 执行 {action} 成功！"
    except Exception as e:
        return f"❌ 控制设备失败: {e}"