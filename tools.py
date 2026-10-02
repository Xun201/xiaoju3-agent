# -*- coding: utf-8 -*-
"""小橘3号 · 工具分发层。

按《架构设计文档》§6（2026-10-02 权限重构定稿）：唯一入口 execute_tool，
if/elif 逐一分发 14 项白名单工具（13 项 + 新增 restart_service 自身重启，
Lv.4 专属），无注册表；文件读写以 realpath 前缀校验限制在 WORKSPACE 内
（防路径逃逸），read_file 截断 1000 字符。

权限门禁（§7 用户指令新表 + 2026-09-30 免逐次动态密码指令）：
- web_search：Lv.1 不设限（联网搜索属游客能力）；
- read_file / list_files：Lv.2（旧口径 LV1 可读，用户调整点）；
- adb_tap / adb_swipe / adb_screenshot / ui_tap_element / vision_tap_element：
  Lv.4 主人级门禁（2026-10-02 权限重构：ADB 全套升档，含视觉点击）；
- write_file：Lv.3 等级门禁保留（等级 < 3 仍拒）。已是 Lv.3 直接放行，
  不再要求逐次动态密码（用户指令 2026-09-30：对已认证 Lv.3 用户免逐次
  /sudo，体验连贯）；permission 层 lv3_operation_ok / open_operation_window
  API 保留（/sudo 仍可主动开窗），仅 tools 层不再强制；
- control_ha_device：domain 自动路由（2026-10-02 权限重构定稿）——
  home_tools.is_dangerous_entity（lock/valve/阀/gas/DANGER_ENTITIES 自定义）
  为真 → Lv.4 门禁；六类安全 domain → Lv.3 门禁（安全家居升档）；
  操作级双因子已删除（/lv4_auth 授权级验证保留）；
- system_manage / restart_service：Lv.4 等级门禁（操作级双因子与二次确认
  已删除），component 名校验防注入，pip 装卸经 subprocess 封装（可 mock）；
  restart_service 语义 = 先答复后 2 秒自尽（threading.Timer + os._exit），
  复活链 Linux 为 start.sh 守护、Windows 为 desktop_launcher 监督（批次②）。

execute_tool 向后兼容扩展：execute_tool(tool_name, args, permission_manager,
credentials=None)；credentials 参数保留（历史签名兼容，当前无消费方）。

视觉回退（用户指令 2026-09-30，代码级强制）：ui_tap_element 经 Lv.3 门禁
后调用底层 UI 解析，解析失败（返回串以 ❌ 开头：未找到元素/解析异常/
点击失败）时先做短路检查——VISION_MODEL / VISION_KEY 任一未配置
（None 或空串均按 falsy 判定）→ 直接返回"❌ 未配置视觉模型，无法执行
点击"，绝不调用 vision_tap_element（ADB 截图、云端请求与等待全部避免，
不空跑）；已配置才继续直接调用 vision_tap_element（同 element_name），
全程对模型透明（模型只拿到最终结果，无需多轮对话）；视觉结果原样返回，
若视觉也失败（❌ 开头或错误串含"失败"）在末尾追加 VISION_API_URL /
VISION_KEY 配置检查指引。
防循环：回退只发生一次——vision 结果无论成败都直接返回，绝不再触发
任何重试或二次回退。

上下文记忆（最近设备操作）：control_ha_device / adb_tap / adb_swipe 执行
成功后追加 1 条 {ts, tool, detail} 到 agent_state/recent_actions.json
（只保留最近 5 条，原子写入，异常吞掉绝不影响工具返回值）；读取类工具
（adb_screenshot 等）不记录。get_recent_actions 供接入层注入上下文做指代消解。
"""
import json
import os
import re
import threading
import sys
import subprocess
import time

from xiaoju3 import WORKSPACE, AGENT_STATE_DIR, VISION_MODEL, VISION_KEY
import home_tools
from home_tools import get_ha_devices, control_ha_device
from adb_tools import adb_screenshot, adb_tap, adb_swipe
from vision_tools import vision_tap_element
from android_ui_tools import ui_tap_element
from search_tools import web_search

# 工具白名单（14 项，2026-10-02 权限重构 +restart_service）：与
# prompts.py 工具协议一致。注意：brain.TOOL_WHITELIST（大脑入口白名单）
# 需同步追加，工具才可经 smart_ask 链路触发。
TOOL_WHITELIST = [
    "list_files", "read_file", "write_file", "get_ha_devices",
    "control_ha_device", "adb_tap", "adb_swipe", "adb_screenshot",
    "vision_tap_element", "ui_tap_element", "web_search", "system_manage",
    "read_core_memory", "restart_service",
]

# 高危工具集合（语义更新为 §7 新门禁，逐工具门禁见模块 docstring 与
# execute_tool 内实现，不再共用单一 LV3 前置门禁）
DANGER_TOOLS = {"write_file", "adb_tap", "adb_swipe", "control_ha_device"}

# 需 Lv.2 / Lv.3 / Lv.4 等级的工具分组（2026-10-02 权限重构定稿）
_LV2_TOOLS = {"read_file", "list_files"}
_LV3_TOOLS = {"write_file"}
# Lv.4 主人级工具（2026-10-02 定稿：ADB 全套升 Lv4；send_image 能力声明
# ——其实际门禁在 main.py /send_image 指令（本批不动 main.py，批次②对齐
# 数值）；restart_service 分支见 execute_tool）
_LV4_TOOLS = {"adb_screenshot", "adb_tap", "adb_swipe", "ui_tap_element",
              "vision_tap_element", "send_image", "restart_service"}

# 沙箱越界拒绝文案
_DENY_OUTSIDE = "❌ 安全拒绝：不允许访问工作区以外的文件！"

# 权限门禁拒绝文案（统一口径：❌ 开头 + 原因 + 升级引导）
_DENY_LV2 = ("❌ 安全拒绝：当前权限不足，该操作需要 Lv.2（普通用户）权限。"
             "请先 /register <密码> 注册升级。")
_DENY_LV3 = ("❌ 安全拒绝：当前权限不足，该操作需要 Lv.3（代码编写者）权限。"
             "请先 /coder_auth <动态密码> 升级。")
# （2026-09-30 用户指令）原 write_file 逐次动态密码拒绝文案 _DENY_LV3_OPERATION
# 已随门禁一并移除：Lv.3 等级门禁保留，已是 Lv.3 直接写入；permission 层
# lv3_operation_ok / open_operation_window（/sudo）API 保留、仅 tools 层不再强制。
_DENY_LV2_NORMAL_DEVICE = ("❌ 安全拒绝：当前权限不足，控制普通家居设备需要 "
                           "Lv.2（普通用户）权限。请先 /register <密码> 注册升级。")
_DENY_LV4_DANGER_DEVICE = ("❌ 安全拒绝：{entity} 属高危设备（门锁/燃气等），"
                           "控制它需要 Lv.4（主人级）权限。请联系主人完成"
                           "双因子认证后升级，或改由主人亲自操作。")
# （2026-10-02 权限重构：操作级双因子已删除——Lv.4 等级即放行，提权路径
# 只剩 /lv4_auth 授权级验证；本常量保留供既有测试引用，生产路径不再使用）
_DENY_LV4_MFA = ("❌ 安全拒绝：该操作需 Lv.4 双因子认证（动态密码 + 生物认证）"
                 "全部通过，当前认证未通过。")
_DENY_LV4_ADB = ("❌ 安全拒绝：当前权限不足，ADB 手机接管全套需要 "
                 "Lv.4（主人级）权限。请先 /lv4_auth confirm <动态密码> 授权。")
_DENY_LV4_SYSTEM = ("❌ 安全拒绝：当前权限不足，装卸系统组件需要 "
                    "Lv.4（主人级）权限。请先 /lv4_auth confirm <动态密码> 授权。")

# （2026-09-30 用户指令）视觉回退的"（如持续失败，请检查 .env ...）"指引行
# 已整段删除：vision_tools 返回什么聊天框就收什么，一字不多（指引文案由
# vision_tools 收口为极简串，排查信息只进控制台日志）。

# 视觉未配置短路文案（用户指令 2026-09-30）：VISION_MODEL / VISION_KEY 任一
# 未配置（None 或空串按 falsy/truthy 判定）时，ui_tap_element 回退前直接
# 返回此文案，绝不调用 vision_tap_element（ADB 截图与网络请求全部避免）。
_DENY_VISION_UNCONFIGURED = "❌ 未配置视觉模型，无法执行点击"

# component 名合法字符（防 pip 参数注入；另拒绝以 - 开头的名字）
_COMPONENT_PATTERN = re.compile(r"[A-Za-z0-9._-]+")


def _level_at_least(permission_manager, min_level, fallback_capability):
    """等级数值门禁（§7 继承语义：level >= 门槛即通过）。

    优先按数值等级判定（level_value() >= min_level，语义等价于
    "if level < 门槛: 拒绝"），不受 ACTION_LEVELS 能力键覆盖度影响。
    旧病灶：权限表缺键/改名时 has_permission 对未知键一律 False
    （fail-closed），会把 Lv.3/Lv.4 也拦在普通设备门外（用户报告的
    "Lv.3 控制普通设备被要求升级"根因）。manager 未暴露数值接口时
    回退能力键 has_permission（向后兼容旧式 manager）。
    """
    level_value = getattr(permission_manager, "level_value", None)
    if callable(level_value):
        try:
            return level_value() >= min_level
        except Exception:
            pass
    return permission_manager.has_permission(fallback_capability)


# ==================== 最近设备操作记录（上下文记忆 / 指代消解） ====================

# 记录文件：agent_state/recent_actions.json（基于 xiaoju3.AGENT_STATE_DIR，
# env AGENT_STATE_DIR 可覆盖；测试经 patch tools.RECENT_ACTIONS_FILE 注入
# tmp 目录，绝不触碰真实隔离区数据）
RECENT_ACTIONS_FILE = os.path.join(AGENT_STATE_DIR, "recent_actions.json")

# 只保留最近 5 条（新事件追加在后，超出裁掉最旧）
RECENT_ACTIONS_LIMIT = 5

# 设备操作类工具（写入型，执行成功才记录）；读取类如 adb_screenshot 不算
ACTION_TOOLS = {"control_ha_device", "adb_tap", "adb_swipe"}


def _summarize_action(tool_name, args):
    """紧凑中文摘要，如 "control_ha_device: light.living → turn_on"。"""
    args = args or {}
    if tool_name == "control_ha_device":
        return (f"control_ha_device: {args.get('entity_id', '?')} → "
                f"{args.get('action', '?')}")
    if tool_name == "adb_tap":
        return f"adb_tap: 点击 ({args.get('x')}, {args.get('y')})"
    if tool_name == "adb_swipe":
        return (f"adb_swipe: 从 ({args.get('x1')},{args.get('y1')}) 滑到 "
                f"({args.get('x2')},{args.get('y2')})")
    return f"{tool_name}: {args}"


def record_recent_action(tool_name, args, filepath=None):
    """成功设备操作落盘（上下文记忆）：追加 1 条 {ts, tool, detail}，
    只保留最近 RECENT_ACTIONS_LIMIT 条。

    铁律：记录器任何异常（磁盘/权限/JSON 损坏）一律吞掉并打印警告，
    绝不影响工具返回值；文件损坏时重置为空表重建；写入经临时文件 +
    os.replace 原子替换，不留半截文件。
    """
    path = filepath or RECENT_ACTIONS_FILE
    try:
        entries = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, list):
                    entries = [e for e in loaded if isinstance(e, dict)]
            except Exception:
                entries = []   # JSON 损坏 → 重置空表重建
                print(f"⚠️ 设备操作记录文件损坏，已重置重建: {path}")
        entries.append({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "tool": tool_name,
                        "detail": _summarize_action(tool_name, args)})
        if len(entries) > RECENT_ACTIONS_LIMIT:
            entries = entries[-RECENT_ACTIONS_LIMIT:]
        dirpath = os.path.dirname(path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception as e:
        print(f"⚠️ 记录设备操作失败（不影响工具执行）: {e}")


def get_recent_actions(filepath=None, limit=RECENT_ACTIONS_LIMIT):
    """读取最近设备操作记录（上下文注入用）：缺失/损坏/异常一律返回 []，
    绝不让记忆读取影响主链路。"""
    path = filepath or RECENT_ACTIONS_FILE
    try:
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, list):
            return []
        return [e for e in loaded if isinstance(e, dict)][-limit:]
    except Exception as e:
        print(f"⚠️ 读取设备操作记录失败: {e}")
        return []


def _is_in_workspace(filepath):
    """realpath 前缀校验：目标必须落在工作区目录之内（含子目录边界）。"""
    base = os.path.realpath(WORKSPACE)
    target = os.path.realpath(filepath)
    return target.startswith(base + os.sep)


def _is_private_state_path(filepath):
    """纵深防御：目标落在隔离状态目录（agent_state/，记忆/身份/对话）之内
    即属私有数据，仅 Lv.4（read_private_memory）可访问——即便工作区被误配置
    到状态目录附近，该门也兜底生效。"""
    base = os.path.realpath(AGENT_STATE_DIR)
    target = os.path.realpath(filepath)
    return target == base or target.startswith(base + os.sep)


def _deny_private():
    return "❌ 安全拒绝：记忆、身份与对话等私有数据仅主人级（Lv.4）可访问。"


def _is_valid_component(component):
    """system_manage 组件名校验：仅字母数字 ._- 且不得以 - 开头（防注入）。

    不做静默清洗（不 strip/不过滤后放行）：非规范形态一律拒绝。
    """
    name = str(component or "")
    if not name or name.startswith("-"):
        return False
    return bool(_COMPONENT_PATTERN.fullmatch(name))


def _system_manage(action, component):
    """pip 装卸系统组件（subprocess 封装；测试经 mock 替换 subprocess.run）。

    install -> pip install <component>；uninstall -> pip uninstall -y <component>。
    """
    if action == "install":
        cmd = [sys.executable, "-m", "pip", "install", component]
        verb = "安装"
    else:
        cmd = [sys.executable, "-m", "pip", "uninstall", "-y", component]
        verb = "卸载"
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except Exception as e:
        return f"❌ 组件 {component} {verb}失败: {e}"
    if proc.returncode == 0:
        return f"✅ 组件 {component} {verb}完成！"
    tail = ((proc.stderr or "") + (proc.stdout or "")).strip()[-300:]
    return f"❌ 组件 {component} {verb}失败：{tail}"


def execute_tool(tool_name, args, permission_manager, credentials=None):
    """唯一工具入口（向后兼容扩展）：credentials=None 时按无凭据处理。

    credentials 可选键：{"totp": 动态密码, "biometric": 生物认证凭据,
    "confirmed": 二次确认标记(True)}。
    """
    credentials = credentials or {}
    try:
        # ---- Lv.2 门槛：read_file / list_files（§7 新口径） ----
        # 等级数值门禁（level >= 2 即通过），不受权限表能力键覆盖度影响。
        if tool_name in _LV2_TOOLS and \
                not _level_at_least(permission_manager, 2, "read_file"):
            return _DENY_LV2
        # ---- Lv.3 门槛：write_file / adb_tap / adb_swipe / ui_tap_element ----
        # 免逐次动态密码（用户指令 2026-09-30）：等级数值 >= 3 即直接放行，
        # 无任何动态密码校验，不调用 lv3_operation_ok（/sudo 窗口与 totp
        # 凭据 API 保留，用户仍可主动开窗，但工具门禁不再依赖它）。
        # 采用等级数值判定同时免疫旧病灶：权限表缺键时 has_permission
        # fail-closed 会把 Lv.3/Lv.4 一并拦下（见 _level_at_least docstring）。
        if tool_name in _LV3_TOOLS and \
                not _level_at_least(permission_manager, 3, "write_file"):
            return _DENY_LV3

        # Lv.4 主人级工具门禁（2026-10-02 权限重构：ADB 全套升 Lv4；
        # send_image 为能力声明——其实际门禁在 main.py /send_image 指令）
        if tool_name in _LV4_TOOLS and \
                not _level_at_least(permission_manager, 4, "adb_full"):
            return _DENY_LV4_ADB

        if tool_name == "list_files":
            if _is_private_state_path(WORKSPACE) and \
                    not permission_manager.has_permission("read_private_memory"):
                return _deny_private()
            try:
                names = sorted(os.listdir(WORKSPACE))
            except OSError:
                names = []
            if not names:
                return "（工作区为空）"
            lines = []
            for name in names:
                full = os.path.join(WORKSPACE, name)
                lines.append(("[目录] " if os.path.isdir(full) else "") + name)
            return "\n".join(lines)

        elif tool_name == "read_file":
            filepath = os.path.join(WORKSPACE, args["filename"])
            if not _is_in_workspace(filepath):
                return _DENY_OUTSIDE
            if _is_private_state_path(filepath) and \
                    not permission_manager.has_permission("read_private_memory"):
                return _deny_private()
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    return f.read()[:1000]
            return f"文件 {args['filename']} 不存在。"

        elif tool_name == "read_core_memory":
            # 核心记忆库读取：Lv.4 主人独家（定稿权限表）
            if not permission_manager.has_permission("read_private_memory"):
                return "❌ 安全拒绝：核心记忆库仅主人级（Lv.4）可读取。"
            try:
                limit = max(1, min(20, int(args.get("limit", 5))))
            except (TypeError, ValueError):
                limit = 5
            from agent_state.state_manager import state_manager
            rows = state_manager.get_recent_memories(limit) or []
            if not rows:
                return "（核心记忆库暂无记录）"
            lines = [f"- [{cat}] {content}" for cat, content in rows]
            return f"🧠 核心记忆（最近 {len(lines)} 条）：\n" + "\n".join(lines)

        elif tool_name == "write_file":
            filepath = os.path.join(WORKSPACE, args["filename"])
            if not _is_in_workspace(filepath):
                return _DENY_OUTSIDE
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(args["content"])
            return f"✅ 文件 {args['filename']} 写入成功！"

        # === 智能家居工具 ===
        elif tool_name == "get_ha_devices":
            return get_ha_devices()

        elif tool_name == "control_ha_device":
            entity_id = args.get("entity_id")
            action = args.get("action")
            if not entity_id or not action:
                return "❌ 缺少参数：需要提供 entity_id 和 action"
            # 🧭 domain 自动路由（2026-10-02 权限重构定稿）：危险实体
            # （lock/valve/阀/DANGER_ENTITIES 自定义）→ LV4 门禁；六类安全
            # domain（input_boolean/light/switch/sensor/climate/media_player）
            # → LV3 门禁（安全家居升档）。操作级双因子已删除（/lv4_auth
            # 授权级验证保留；儿童锁确认流批次②接入）。
            if home_tools.is_dangerous_entity(entity_id):
                if not permission_manager.has_permission("control_dangerous_devices"):
                    return _DENY_LV4_DANGER_DEVICE.format(entity=entity_id)
            elif not permission_manager.has_permission("control_normal_devices"):
                return _DENY_LV2_NORMAL_DEVICE
            result = control_ha_device(entity_id, action,
                                       temperature=args.get("temperature"))
            if not str(result).startswith("❌"):
                record_recent_action(tool_name,
                                     {"entity_id": entity_id, "action": action})
            return result

        # === ADB 手机接管工具 ===
        elif tool_name == "adb_screenshot":
            return adb_screenshot()
        elif tool_name == "adb_tap":
            x = args.get("x")
            y = args.get("y")
            if x is None or y is None:
                return "❌ 缺少参数：需要提供 x 和 y 坐标"
            result = adb_tap(int(x), int(y))
            if not str(result).startswith("❌"):
                record_recent_action(tool_name, {"x": x, "y": y})
            return result
        elif tool_name == "adb_swipe":
            result = adb_swipe(int(args.get("x1")), int(args.get("y1")),
                               int(args.get("x2")), int(args.get("y2")))
            if not str(result).startswith("❌"):
                record_recent_action(tool_name, {k: args.get(k)
                                                 for k in ("x1", "y1", "x2", "y2")})
            return result

        # === 视觉元素点击 ===
        elif tool_name == "vision_tap_element":
            element_name = args.get("element_name")
            if not element_name:
                return "❌ 缺少参数：需要提供 element_name (要点击的文字/图标名称)"
            return vision_tap_element(element_name)

        # === UI 层级精准点击（Lv.3；解析失败自动回退视觉模型） ===
        elif tool_name == "ui_tap_element":
            element_name = args.get("element_name")
            if not element_name:
                # 缺参属调用方错误而非 UI 解析失败，直接拒绝、不触发回退
                return "❌ 缺少参数：需要提供 element_name (要点击的按钮或图标名称)"
            result = ui_tap_element(element_name)
            if not str(result).startswith("❌"):
                return result
            # ⚡ 短路检查（用户指令 2026-09-30，回退块最前面）：视觉模型未
            # 配置（VISION_MODEL / VISION_KEY 任一为 None 或空串，按 truthy
            # 判定）→ 直接返回固定文案，不调用 vision_tap_element——
            # ADB 截图、云端请求与等待全部避免，不空跑。
            if not VISION_MODEL or not VISION_KEY:
                return _DENY_VISION_UNCONFIGURED
            # 🔁 视觉回退（代码级强制，用户指令）：UI 解析失败（未找到元素/
            # 解析异常/点击失败，统一表现为 ❌ 开头）时不再把"找不到元素"
            # 交回模型自行决策（避免多轮对话与"需要我试试吗"式追问），直接
            # 调用视觉模型，全程对模型透明：模型只拿到最终结果。
            # 防循环：回退只发生一次——vision 结果无论成败都直接返回，
            # 绝不再触发任何重试或二次回退。
            print(f"🔁 [视觉回退] UI 解析失败，自动调用视觉模型: {element_name}")
            # 2026-09-30 用户指令：不再追加任何配置指引行——vision_tools 的
            # 返回串已收口为极简文案，这里原样透传，聊天框一字不多
            return str(vision_tap_element(element_name))

        # === 联网搜索（Lv.1，不设限） ===
        elif tool_name == "web_search":
            query = args.get("query")
            if not query:
                return "❌ 缺少参数：需要提供 query (搜索关键词)"
            return web_search(query, args.get("max_results", 5))

        # === 系统组件一键装卸（Lv.4 等级门禁；操作级双因子已删，2026-10-02） ===
        elif tool_name == "system_manage":
            action = args.get("action")
            component = args.get("component")
            if not action or not component:
                return "❌ 缺少参数：需要提供 action (install/uninstall) 和 component (组件名)"
            if action not in ("install", "uninstall"):
                return f"❌ 不支持的 action: {action}，仅支持 install / uninstall"
            if not _is_valid_component(component):
                return ("❌ 安全拒绝：组件名非法（仅允许字母、数字、点、下划线、"
                        "连字符，且不得以 - 开头），疑似注入已拦截！")
            if not permission_manager.has_permission("system_manage"):
                return _DENY_LV4_SYSTEM
            return _system_manage(action, component)

        # === 重启自身（Lv.4 专属，2026-10-02 新增） ===
        elif tool_name == "restart_service":
            # 复活链：Linux start.sh 守护循环 2 秒自动拉起；Windows 形态由
            # desktop_launcher.py 监督线程负责（批次②）。禁止重启操作系统：
            # 本工具无任何目标参数、无系统级调用面，只退出自身 Python 进程。
            result = ("✅ 重启指令已受理，小橘3号将在 2 秒后重启，"
                      "稍候再叫我哦~")
            timer = threading.Timer(2.0, os._exit, args=(0,))
            timer.daemon = False   # 回复先经 Flask 刷出，再执行退出
            timer.start()
            return result

        return "未知工具"
    except Exception as e:
        return f"工具执行失败: {e}"
