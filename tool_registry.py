# -*- coding: utf-8 -*-
"""小橘3号 · 统一工具登记表（model_tool 合并钩子的唯一真相）。

按 docs/ARCHITECTURE_BOUNDARY.md §3.3（2026-10-04 拍板①落地）：过去新增一个
模型工具要手工同步 tools.py 白名单、brain.py 白名单（重复清单！）、prompts.py
工具协议、权限分组共三四处；本模块把"声明"收敛为一张 TOOL_MANIFEST——
tools.py 的白名单/权限组、brain.py 的入口白名单、prompts.py 的工具协议段
全部由派生函数生成，一处登记三处自动生效。

条目字段（全部声明式，权限执行仍收口在 tools.execute_tool，本表不做门禁）：
- name：工具名（模型 [行动] JSON 的 tool 值，全局唯一）；
- desc / params / note：工具协议行三段（"N. name - desc。参数：params" +
  note 可选尾注），必须与模型理解口径一致；
- level：权限等级分组（2/3/4 → tools._LV2/_LV3/_LV4_TOOLS；缺省 = 不进
  分组门禁，逐分支门禁或无门禁）；
- dangerous：tools.DANGER_TOOLS 成员（高危集合）；
- is_action：tools.ACTION_TOOLS 成员（操作记录型，成功后记 recent_actions）；
- in_protocol：是否进模型协议/白名单（False = 纯能力声明，如 send_image——
  声明在案但实际门禁在 main.py /send_image 指令，模型不可直接调用）；
- module：实现模块（插件工具必填 = xiaoju3.spec hiddenimports 抄录源，
  动态 import 不被 PyInstaller 静态分析抓到，漏加 = dev 正常、exe 里崩）；
- handler："模块:函数" 字符串（插件模型工具专用）：execute_tool 尾部统一
  分派，importlib 动态解析，形参 = 工具 JSON args 键（intent_router 的
  handler_name 同款先例），返回面向用户的中文文本（❌ 开头 = 失败）。

核心工具（list_files/adb_tap 等）的执行体仍是 tools.execute_tool 既有
if/elif 分支（老代码不动）；本表只接管它们的"声明"。新增插件模型工具 =
本表加一条（含 handler + module）+ spec hiddenimports 加一行，零核心改动；
新增核心工具 = 本表加一条 + execute_tool 加分支。

import 零副作用（纯数据 + 纯函数，零第三方依赖）；派生函数全部接受可选
manifest 参数（默认 TOOL_MANIFEST），测试可传扩展副本验证"一处登记三处
生效"而无需污染真实登记。
"""
import importlib

TOOL_MANIFEST = [
    # ── 工作区文件（Lv.2/Lv.3）──
    {"name": "list_files", "desc": "列出工作区内的所有文件", "params": "无",
     "level": 2},
    {"name": "read_file", "desc": "读取工作区内指定文件的内容",
     "params": "filename", "level": 2},
    {"name": "write_file", "desc": "在工作区内创建一个新文件并写入内容",
     "params": "filename, content", "level": 3, "dangerous": True},
    # ── 智能家居（感知 Lv.1 / 控制 Lv.3+高危）──
    {"name": "get_ha_devices", "desc": "获取所有智能家居设备及其当前状态",
     "params": "无"},
    {"name": "control_ha_device", "desc": "控制家中家电设备（灯/开关/空调/传感器/插座等）——凡是开灯、关灯、调温等家电请求必用此工具",
     "params": "entity_id (设备ID), action (turn_on/turn_off/toggle/set_temperature), "
               "temperature (set_temperature 时的目标温度，数字，如 26)",
     "dangerous": True, "is_action": True},
    # ── ADB 手机接管（全套 Lv.4）──
    {"name": "adb_screenshot", "desc": "截取手机屏幕图片", "params": "无",
     "level": 4},
    {"name": "adb_tap", "desc": "点击手机屏幕坐标",
     "params": "x (横坐标), y (纵坐标)",
     "level": 4, "dangerous": True, "is_action": True},
    {"name": "adb_swipe", "desc": "滑动手机屏幕", "params": "x1, y1, x2, y2",
     "level": 4, "dangerous": True, "is_action": True},
    {"name": "ui_tap_element", "desc": "通过系统底层 UI 解析精准点击手机屏幕元素（仅限手机/平板界面，家电控制禁止用此工具）",
     "params": "element_name (要点击的元素的文字，如 “设置”、“确认”)",
     "level": 4},
    {"name": "vision_tap_element", "desc": "视觉识别点击（仅在 ui_tap_element "
     "失效时备用，仅限手机屏幕）", "params": "element_name", "level": 4},
    # ── 信息与系统能力 ──
    {"name": "web_search", "desc": "联网搜索，检索互联网上的公开信息",
     "params": "query (搜索关键词), max_results (可选，结果条数，默认 5)"},
    {"name": "system_manage", "desc": "一键安装/卸载系统组件（仅 Lv.4 主人级可用）",
     "params": "action (install/uninstall), component (组件名，仅允许字母数字._-)"},
    {"name": "read_core_memory", "desc": "读取核心记忆库（仅 Lv.4 主人级可用）",
     "params": "limit (可选，条数，默认 5)"},
    {"name": "restart_service", "desc": "重启小橘3号自身进程（LV4 主人级专属，"
     "重启后需等待守护进程拉起，期间会短暂离线）", "params": "无", "level": 4},
    # ── 待办提取（Lv.2；2026-10-04 待办提取）──
    {"name": "extract_todos", "desc": "提取 DeepSeek 分享链接里的待办事项并存入"
     "待办清单（后台处理，受理后立即返回）",
     "params": "url（完整分享链接，须以 https://chat.deepseek.com/share/ 开头）",
     "note": "当主人发来分享链接并表达“记下待办/整理清单”类意图时使用",
     "level": 2},
    # ── 非协议能力声明（不进白名单/工具协议，仅权限分组在案）──
    {"name": "send_image", "desc": "QQ 发图（能力声明；实际门禁在 main.py "
     "/send_image 指令，模型不可直接调用）", "params": "无",
     "level": 4, "in_protocol": False},
]


def _entries(manifest=None):
    """条目列表（None = 真实登记表；测试传扩展副本）。"""
    return TOOL_MANIFEST if manifest is None else manifest


def whitelist_names(manifest=None):
    """工具白名单（tools.TOOL_WHITELIST / brain.TOOL_WHITELIST 的唯一来源）：
    in_protocol 条目的 name，按登记序。"""
    return [t["name"] for t in _entries(manifest)
            if t.get("in_protocol", True)]


def level_set(level, manifest=None):
    """权限等级分组（tools._LV2/_LV3/_LV4_TOOLS 的唯一来源）。"""
    return {t["name"] for t in _entries(manifest)
            if t.get("level") == level}


def danger_set(manifest=None):
    """高危工具集合（tools.DANGER_TOOLS 的唯一来源）。"""
    return {t["name"] for t in _entries(manifest)
            if t.get("dangerous", False)}


def action_set(manifest=None):
    """操作记录型工具集合（tools.ACTION_TOOLS 的唯一来源，成功后记
    recent_actions 供指代消解）。"""
    return {t["name"] for t in _entries(manifest)
            if t.get("is_action", False)}


def prompt_tool_lines(manifest=None):
    """工具协议行（prompts.py 工具段唯一来源）："N. name - desc。参数：
    params" + note 尾注，编号按 in_protocol 登记序 1 起连续。"""
    lines = []
    n = 0
    for t in _entries(manifest):
        if not t.get("in_protocol", True):
            continue
        n += 1
        line = f"{n}. {t['name']} - {t['desc']}。参数：{t['params']}"
        if t.get("note"):
            line += f"。{t['note']}。"
        lines.append(line)
    return lines


def find_entry(name, manifest=None):
    """按工具名取条目（无则 None）。"""
    for t in _entries(manifest):
        if t["name"] == name:
            return t
    return None


def plugin_tool_names(manifest=None):
    """插件模型工具名单（handler 字符串条目，execute_tool 尾部统一分派）。"""
    return [t["name"] for t in _entries(manifest) if "handler" in t]


def dispatch_plugin_tool(name, args, manifest=None):
    """插件模型工具统一执行（execute_tool 尾部调用）：importlib 解析
    "模块:函数"，形参 = args 键；加载失败/执行异常一律返回中文 ❌ 串，
    绝不让插件拖垮工具主链。核心工具不走此路径（既有 if/elif 分支）。"""
    entry = find_entry(name, manifest)
    if entry is None or "handler" not in entry:
        return f"❌ 工具 {name} 未在登记表注册处理器。"
    try:
        module_path, func_name = entry["handler"].split(":", 1)
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
    except (ValueError, ImportError, AttributeError):
        return (f"❌ 插件工具 {name} 不可用（处理器加载失败，"
                "请检查依赖安装与打包收录）。")
    try:
        return func(**args)
    except Exception as e:   # 插件崩了给模型一句 ❌，主链照常
        return f"❌ 插件工具 {name} 执行失败: {e}"
