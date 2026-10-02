# -*- coding: utf-8 -*-
"""小橘3号 · Home Assistant REST 工具。

按《架构设计文档》§7 / 功能文档 §8.1 / §8.4：
- get_ha_devices()：拉取 /api/states，只保留 input_boolean / light / switch /
  sensor / climate / media_player / input_number 七类实体，输出文本摘要供大脑感知设备。
- get_ha_states()：同一份数据的结构化版本（[{entity_id, state,
  friendly_name}]），供心跳场景规则引擎做快照 diff（架构 §10 #10）。
- control_ha_device(entity_id, action, temperature=None)：turn_on / turn_off /
  toggle 走 /api/services/homeassistant/{action}；set_temperature（§10 #9
  细粒度控制："空调调到 26 度"口径）走 /api/services/climate/set_temperature，
  payload {entity_id, temperature}，需同时传 temperature。既有两参调用完全
  向后兼容。注：统一工具层 tools.py 目前以 (entity_id, action) 两参调用，
  工具 JSON args 中的 temperature 透传需工具层/接线方同步。
- is_dangerous_entity(entity_id)：高危实体分类（§10 #8——锁 lock.* 与燃气
  [含 "gas"/"燃气" 字样] → True）。二次确认令牌交互流由接线方（main.py/S5）
  实现：判定高危 → 向用户索要确认令牌 → 通过后才调用 control_ha_device。

HA_URL / HA_TOKEN 统一来自 xiaoju3 配置（.env → 环境变量优先），Bearer 认证，
凭证不入仓库。未配置 HA_URL 时函数内返回清晰中文错误串，import 本模块零副作用
（tools.py 顶层 import 本模块）。
"""
import os

import requests

from xiaoju3 import HA_URL, HA_TOKEN

# 可感知实体七类（参考实现口径：域名与 entity_id 做子串匹配）；
# input_number 为 2026-10-02 新增第七类（模拟湿度 input_number.mo_ni_shi_du
# 等数值实体供心跳感知与场景规则读取；仅感知，control_ha_device 无该域控制）
HA_DOMAINS = ["input_boolean", "light", "switch", "sensor", "climate",
              "media_player", "input_number"]

_UNSET_HA = "❌ 未配置 HA_URL（Home Assistant 地址），无法{0}。请先在 .env 或环境变量中设置 HA_URL 与 HA_TOKEN。"


def _headers():
    """Bearer 认证请求头（调用时读取模块级配置，便于测试注入）。"""
    return {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }


def get_ha_devices():
    """获取所有智能家居设备的状态（用于让AI了解有哪些设备可以控制）"""
    if not HA_URL:
        return _UNSET_HA.format("获取设备列表")
    try:
        response = requests.get(f"{HA_URL}/api/states", headers=_headers(), timeout=10)
        response.raise_for_status()
        devices = response.json()

        summary = []
        for dev in devices:
            entity_id = dev.get("entity_id", "")
            state = dev.get("state", "")
            attributes = dev.get("attributes", {})
            friendly_name = attributes.get("friendly_name", "未知设备")

            if any(domain in entity_id for domain in HA_DOMAINS):
                summary.append(f"- {friendly_name} (ID: {entity_id}) 当前状态: {state}")

        return "\n".join(summary) if summary else "当前没有发现可控设备。"
    except Exception as e:
        return f"❌ 获取HA设备列表失败: {e}"


def get_ha_states():
    """获取六类实体的结构化状态列表（心跳场景规则引擎用）。

    返回 [{"entity_id", "state", "friendly_name"}]（state 统一转字符串）；
    未配置 HA_URL / 请求异常时返回 []（离线降级，不抛异常）。
    """
    if not HA_URL:
        return []
    try:
        response = requests.get(f"{HA_URL}/api/states", headers=_headers(), timeout=10)
        response.raise_for_status()
        devices = response.json()
        states = []
        for dev in devices:
            entity_id = dev.get("entity_id", "")
            if any(domain in entity_id for domain in HA_DOMAINS):
                states.append({
                    "entity_id": entity_id,
                    "state": str(dev.get("state", "")),
                    "friendly_name": str(dev.get("attributes", {}).get("friendly_name", "")),
                })
        return states
    except Exception:
        return []


def is_dangerous_entity(entity_id):
    """危险实体判定（2026-10-02 权限重构扩展口径）。

    - 门锁：entity_id 域名为 lock.*；
    - 阀类：entity_id 含 gas / valve（不区分大小写）或 燃气 / 阀 字样；
    - 自定义：精确命中 DANGER_ENTITIES 环境变量白名单（逗号分隔的自定义
      危险实体 ID，延迟读取 env，与 HA_URL 同风格，如
      DANGER_ENTITIES=lock.front_door,switch.induction_cooker）。
    返回 True 表示危险（LV4 门禁）；其余（六类安全 domain）为安全（LV3）。
    """
    eid = str(entity_id or "")
    if eid.lower().split(".", 1)[0] == "lock":
        return True
    lower = eid.lower()
    if ("gas" in lower) or ("valve" in lower) or ("燃气" in eid) or ("阀" in eid):
        return True
    try:
        for item in os.environ.get("DANGER_ENTITIES", "").split(","):
            item = item.strip()
            if item and eid == item:
                return True
    except Exception:
        pass
    return False


def control_ha_device(entity_id, action, temperature=None):
    """控制智能家居设备（既有 (entity_id, action) 两参调用向后兼容）。

    action:
    - turn_on / turn_off / toggle：通用服务 /api/services/homeassistant/{action}；
    - set_temperature：climate 温控（§10 #9 "空调调到 26 度"口径），需同时传
      temperature（数字目标温度），走 /api/services/climate/set_temperature，
      payload {"entity_id": ..., "temperature": ...}。
    """
    if not HA_URL:
        return _UNSET_HA.format("控制设备")

    if action == "set_temperature":
        if temperature is None:
            return "❌ set_temperature 需要提供 temperature（目标温度），例如 temperature=26。"
        try:
            url = f"{HA_URL}/api/services/climate/set_temperature"
            payload = {"entity_id": entity_id, "temperature": temperature}
            response = requests.post(url, headers=_headers(), json=payload, timeout=10)
            response.raise_for_status()
            return f"✅ 设备 {entity_id} 温度已设为 {temperature} 度！"
        except Exception as e:
            return f"❌ 控制设备失败: {e}"

    if action not in ["turn_on", "turn_off", "toggle"]:
        return (f"❌ 不支持的动作: {action}，"
                "仅支持 turn_on, turn_off, toggle, set_temperature")

    try:
        url = f"{HA_URL}/api/services/homeassistant/{action}"
        payload = {"entity_id": entity_id}
        response = requests.post(url, headers=_headers(), json=payload, timeout=10)
        response.raise_for_status()
        return f"✅ 设备 {entity_id} 执行 {action} 成功！"
    except Exception as e:
        return f"❌ 控制设备失败: {e}"
