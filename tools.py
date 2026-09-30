# -*- coding: utf-8 -*-
"""小橘3号 · 工具分发层。

按《架构设计文档》§5 与第二阶段 §7 权限新表：唯一入口 execute_tool，
if/elif 逐一分发 12 项白名单工具（11 项 + 新增 system_manage 系统组件装卸），
无注册表；文件读写以 realpath 前缀校验限制在 WORKSPACE 内（防路径逃逸），
read_file 截断 1000 字符。

权限门禁（§7 用户指令新表，覆盖旧"单一 LV3 门禁"口径）：
- web_search：Lv.1 不设限（联网搜索属游客能力）；
- read_file / list_files：Lv.2（旧口径 LV1 可读，用户调整点）；
- adb_tap / adb_swipe：维持 Lv.3（无逐次动态密码要求）；
- write_file：Lv.3 且 lv3_operation_ok（逐次 TOTP 或 /sudo 短 TTL 操作窗口），
  不满足返回中文引导文案；
- control_ha_device：先经 home_tools.is_dangerous_entity 动态分类——普通实体
  需 Lv.2（control_normal_devices），危险实体（门锁/燃气）需 Lv.4 且
  lv4_mfa_ok（动态密码+生物认证双因子）；
- system_manage：Lv.4 且 lv4_mfa_ok 且二次确认（credentials["confirmed"]=True）
  三重门禁，component 名校验防注入，pip 装卸经 subprocess 封装（可 mock）。

execute_tool 向后兼容扩展：execute_tool(tool_name, args, permission_manager,
credentials=None)；credentials 约定键 {"totp", "biometric", "confirmed"}。
"""
import os
import re
import sys
import subprocess

from xiaoju3 import WORKSPACE, AGENT_STATE_DIR
import home_tools
from home_tools import get_ha_devices, control_ha_device
from adb_tools import adb_screenshot, adb_tap, adb_swipe
from vision_tools import vision_tap_element
from android_ui_tools import ui_tap_element
from search_tools import web_search

# 工具白名单（12 项）：与 prompts.py 工具协议一致。
# 注意：brain.TOOL_WHITELIST（大脑入口白名单）需由其所有权人同步追加
# "system_manage" 第 12 项后，system_manage 才可经 smart_ask 链路触发。
TOOL_WHITELIST = [
    "list_files", "read_file", "write_file", "get_ha_devices",
    "control_ha_device", "adb_tap", "adb_swipe", "adb_screenshot",
    "vision_tap_element", "ui_tap_element", "web_search", "system_manage",
    "read_core_memory",
]

# 高危工具集合（语义更新为 §7 新门禁，逐工具门禁见模块 docstring 与
# execute_tool 内实现，不再共用单一 LV3 前置门禁）
DANGER_TOOLS = {"write_file", "adb_tap", "adb_swipe", "control_ha_device"}

# 需 Lv.2 / Lv.3 等级的工具分组（§7 新表）
_LV2_TOOLS = {"read_file", "list_files"}
_LV3_TOOLS = {"write_file", "adb_tap", "adb_swipe"}

# 沙箱越界拒绝文案
_DENY_OUTSIDE = "❌ 安全拒绝：不允许访问工作区以外的文件！"

# 权限门禁拒绝文案（统一口径：❌ 开头 + 原因 + 升级引导）
_DENY_LV2 = ("❌ 安全拒绝：当前权限不足，该操作需要 Lv.2（普通用户）权限。"
             "请先 /register <密码> 注册升级。")
_DENY_LV3 = ("❌ 安全拒绝：当前权限不足，该操作需要 Lv.3（代码编写者）权限。"
             "请先 /coder_auth <动态密码> 升级。")
_DENY_LV3_OPERATION = ("❌ 安全拒绝：写文件属敏感操作，需逐次动态密码校验。"
                       "请先用 /sudo <动态密码> 开启 120 秒操作窗口后重试，"
                       "或在工具凭据中携带 totp 参数重新认证。")
_DENY_LV2_NORMAL_DEVICE = ("❌ 安全拒绝：当前权限不足，控制普通家居设备需要 "
                           "Lv.2（普通用户）权限。请先 /register <密码> 注册升级。")
_DENY_LV4_DANGER_DEVICE = ("❌ 安全拒绝：{entity} 属高危设备（门锁/燃气等），"
                           "控制它需要 Lv.4（主人级）权限。请联系主人完成"
                           "双因子认证后升级，或改由主人亲自操作。")
_DENY_LV4_MFA = ("❌ 安全拒绝：该操作需 Lv.4 双因子认证（动态密码 + 生物认证）"
                 "全部通过，当前认证未通过。")
_DENY_LV4_SYSTEM = ("❌ 安全拒绝：当前权限不足，装卸系统组件需要 "
                    "Lv.4（主人级）权限。请联系主人完成双因子认证后升级。")

# component 名合法字符（防 pip 参数注入；另拒绝以 - 开头的名字）
_COMPONENT_PATTERN = re.compile(r"[A-Za-z0-9._-]+")


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
        if tool_name in _LV2_TOOLS and not permission_manager.has_permission("read_file"):
            return _DENY_LV2
        # ---- Lv.3 门槛：write_file / adb_tap / adb_swipe（维持 Lv.3） ----
        if tool_name in _LV3_TOOLS and not permission_manager.has_permission("write_file"):
            return _DENY_LV3
        # ---- write_file 逐次动态密码门禁（等级通过后再校验操作凭据） ----
        if tool_name == "write_file" and \
                not permission_manager.lv3_operation_ok(credentials=credentials):
            return _DENY_LV3_OPERATION

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
            # §7 动态分类：普通实体 Lv.2 / 危险实体 Lv.4 + 双因子
            if home_tools.is_dangerous_entity(entity_id):
                if not permission_manager.has_permission("control_dangerous_devices"):
                    return _DENY_LV4_DANGER_DEVICE.format(entity=entity_id)
                if not permission_manager.lv4_mfa_ok(credentials=credentials):
                    detail = getattr(permission_manager, "last_lv4_message", "")
                    return _DENY_LV4_MFA + (f"\n{detail}" if detail else "")
            elif not permission_manager.has_permission("control_normal_devices"):
                return _DENY_LV2_NORMAL_DEVICE
            return control_ha_device(entity_id, action,
                                     temperature=args.get("temperature"))

        # === ADB 手机接管工具 ===
        elif tool_name == "adb_screenshot":
            return adb_screenshot()
        elif tool_name == "adb_tap":
            x = args.get("x")
            y = args.get("y")
            if x is None or y is None:
                return "❌ 缺少参数：需要提供 x 和 y 坐标"
            return adb_tap(int(x), int(y))
        elif tool_name == "adb_swipe":
            return adb_swipe(int(args.get("x1")), int(args.get("y1")),
                             int(args.get("x2")), int(args.get("y2")))

        # === 视觉元素点击 ===
        elif tool_name == "vision_tap_element":
            element_name = args.get("element_name")
            if not element_name:
                return "❌ 缺少参数：需要提供 element_name (要点击的文字/图标名称)"
            return vision_tap_element(element_name)

        # === UI 层级精准点击 ===
        elif tool_name == "ui_tap_element":
            element_name = args.get("element_name")
            if not element_name:
                return "❌ 缺少参数：需要提供 element_name (要点击的按钮或图标名称)"
            return ui_tap_element(element_name)

        # === 联网搜索（Lv.1，不设限） ===
        elif tool_name == "web_search":
            query = args.get("query")
            if not query:
                return "❌ 缺少参数：需要提供 query (搜索关键词)"
            return web_search(query, args.get("max_results", 5))

        # === 系统组件一键装卸（Lv.4 三重门禁：等级 + 双因子 + 二次确认） ===
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
            if not permission_manager.lv4_mfa_ok(credentials=credentials):
                detail = getattr(permission_manager, "last_lv4_message", "")
                return _DENY_LV4_MFA + (f"\n{detail}" if detail else "")
            if not credentials.get("confirmed"):
                return ("❌ 安全拒绝：装卸系统组件属类 Root 高危操作，需二次确认："
                        "请确认后携带 confirmed=True 重新执行。")
            return _system_manage(action, component)

        return "未知工具"
    except Exception as e:
        return f"工具执行失败: {e}"
