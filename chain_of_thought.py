# -*- coding: utf-8 -*-
"""思维链模块（#326）——模型无关 CoT 消毒/归一化/解析。

设计理念（用户原话）：教会各个模型计算打草稿，但各个模型打草稿习惯
不一样，通过整合不同的习惯在一起，让这个方法变得通用。

核心：差异收边缘（VARIANTS 变体表），统一留核心（normalize/strip）。

用法：
    import chain_of_thought as cot
    text = cot.normalize(text)       # 冒号行首标签 → 原生 [思考]/[计划]
    text = cot.strip_pollution(text) # 剥全部变体（XML+方括号+action JSON）
    thinking, body = cot.parse(text) # 解析思考/正文分离

关联：#322（Bug A/B）/坑库 #20（消毒通道不对齐）/#21（测试隔离掩盖断链）
"""
import re

# ==================== VARIANTS 变体表 ====================
# 格式差异只进这里——新模型新格式加一行，主逻辑不变。

# 行首冒号标签 → 原生标记名
COLON_LABEL_RES = [
    (re.compile(r'^\s*思考[：:]\s*(.*)$', re.M), '思考'),
    (re.compile(r'^\s*推理[：:]\s*(.*)$', re.M), '思考'),
    (re.compile(r'^\s*计划[：:]\s*(.*)$', re.M), '计划'),
    (re.compile(r'^\s*步骤[：:]\s*(.*)$', re.M), '计划'),
    (re.compile(r'^\s*Think\s*:\s*(.*)$', re.M | re.I), '思考'),
    (re.compile(r'^\s*Plan\s*:\s*(.*)$', re.M | re.I), '计划'),
]

# 剥除正则（全变体）
STRIP_RES = [
    re.compile(r'<think>.*?</think>', re.DOTALL),           # XML 尖括号
    re.compile(r'\[think\].*?\[/think\]', re.DOTALL | re.I),  # 方括号英文
    re.compile(r'\[思考\].*?\[/思考\]', re.DOTALL),           # 方括号中文
    re.compile(r'\[plan\].*?\[/plan\]', re.DOTALL | re.I),    # 计划方括号
    re.compile(r'\{[^{}]*"action"\s*:[^{}]*\}', re.DOTALL),   # 幻觉 action JSON
]


def normalize(text):
    """行首冒号变体（思考：/推理：/计划：/步骤：/Think:/Plan:）→
    原生 [思考]/[计划] 标记。只动行首带标签的行，正文不受影响。"""
    text = str(text or "")
    for rex, label in COLON_LABEL_RES:
        text = rex.sub(lambda m, lb=label: '[' + lb + '] ' + m.group(1),
                       text)
    return text


def strip_pollution(text):
    """全变体剥除（出口消毒）：XML + 方括号 + action JSON + 工具名键 JSON。
    QQ/控制台共用同口径（坑库 #20：消毒通道不对齐防再犯）。"""
    text = normalize(text)
    for rex in STRIP_RES:
        text = rex.sub('', text)
    return _strip_toolkey_json(text).strip()


def _strip_toolkey_json(text):
    """剥"顶层键=tool_registry 注册工具名"的可解析 JSON 对象（2026-10-14
    冒烟实锤形态 {"ui_tap_element":{...}}——无 action 键+含嵌套，既有
    action regex 双不匹配漏出）。

    防误伤：注册表校验兜底——只剥顶层键命中注册工具名的对象，正文讨论的
    普通 JSON（键非工具名）原样保留。懒加载 tool_registry（单一事实源，
    避免模块加载环）。任何异常原样返回（消毒层绝不抛）。"""
    try:
        import json as _json
        from tool_registry import TOOL_MANIFEST
        names = {t.get("name") for t in TOOL_MANIFEST if t.get("name")}
        decoder = _json.JSONDecoder()
        out, pos, found = [], 0, False
        for brace in re.finditer(r'\{', text):
            if brace.start() < pos:
                continue
            try:
                obj, end = decoder.raw_decode(text[brace.start():])
            except ValueError:
                continue
            if isinstance(obj, dict) and any(k in names for k in obj):
                out.append(text[pos:brace.start()])
                pos = brace.start() + end
                found = True
        if not found:
            return text
        out.append(text[pos:])
        return "".join(out)
    except Exception:
        return text


def parse_thinking_field(message_dict):
    """D1（#326）：Ollama /api/chat 返回的独立 thinking 字段读取。
    R1 类思考模型返回 message.thinking（纯思考，无标签）+ message.content
    （纯答案）。返回 (thinking, content) 二元组，无字段时 thinking=''。
    """
    msg = message_dict or {}
    thinking = str(msg.get('thinking') or '')
    content = str(msg.get('content') or '')
    return thinking, content
