# -*- coding: utf-8 -*-
"""小橘3号 · 自然语言意图路由（架构设计文档 §5/§10 #4、功能文档 §7）。

功能文档 §7 口径：不用记命令，直接说"帮我记一下账""把这段对话导出成
电子书"，它能听懂并调用对应功能。本模块把它升级为独立路由模块，双层设计：

① 规则层（优先、零 token、可离线测试）：意图表 INTENT_PATTERNS 数据驱动
   （name / patterns / extractor / handler_name / negative_patterns），
   正则命中即返回确定性意图；新增意图只加表项，不改路由逻辑。
   意图处理器用延迟字符串引用（如 "plugins.accounting:add_record"），
   由 dispatch() 动态 import 调用——模块解耦，S5 接线零成本。
② 模型层（可选兜底）：规则未命中时走 brain.smart_ask 做意图澄清
   （函数内延迟导入，缺席/异常/解析失败一律优雅降级返回 None，表示
   "不路由，走正常对话"）。默认关闭（未命中本就该回落正常对话，模型
   分类再加一轮会拖慢每条消息），env XIAOJU3_MODEL_ROUTE=1 开启。

=====================================================================
对外接口（供 S5 在 handle_message / /api/chat 接线）：
=====================================================================
from intent_router import route, dispatch

result = route("帮我记一下账")          # -> IntentResult 或 None
if result is not None:
    reply = dispatch(result)            # -> 中文执行结果，直接回给用户

class IntentResult（dataclass）字段：
- name:       意图名（如 "accounting_add" / "export_ebook" / "web_search"）
- args:       从句中抽取的参数字典（键与 handler 函数形参对应）
- confidence: 置信度 0-1（规则层 0.95，模型层 0.6）
- handler:    延迟处理器引用 "模块路径:函数名"
- source:     "rule"（规则层） / "model"（模型层）

route 返回 None 表示不路由、走正常对话（S5 继续 brain.smart_ask 流程）。
接线注记：export_ebook 意图需要会话历史，S5 需把当前通道的历史填进
result.args["history"] 后再 dispatch（详见 plugins/ebook_export.py）。

金额符号口径（测试锁定）：句中出现 收入/进账/收到/赚 等词 → 金额为正
（收入）；出现 花/支出/消费/买/付 等词或无标记 → 金额为负（支出，
记账绝大多数场景是支出）。
import 零副作用，全离线可测（模型层用 mock）。
"""
import dataclasses
import json
import os
import re
import importlib

# 模型层开关的 env 键（默认关闭；"1"/"true"/"on"/"yes" 视为开启）
MODEL_ROUTE_ENV = "XIAOJU3_MODEL_ROUTE"
_MODEL_TRUTHY = ("1", "true", "on", "yes", "y")

# 置信度口径：规则层确定性命中 / 模型层兜底判断
CONFIDENCE_RULE = 0.95
CONFIDENCE_MODEL = 0.6

_RE_FLAGS = re.IGNORECASE

# 金额抽取：带符号数字 + "元"
_AMOUNT_RE = re.compile(r"[+-]?\d+(?:\.\d+)?\s*元")

# 支出 / 收入提示词（金额符号判定；新增词只扩元组，不改逻辑）
_EXPENSE_CUES = ("花", "支出", "消费", "买", "付", "掏", "开销")
_INCOME_CUES = ("收入", "进账", "收到", "到账", "赚", "红包", "工资", "奖金")

# 记账分类关键词推断表（按序首个命中的分类生效；新增只扩表）
_CATEGORY_KEYWORDS = [
    (("早饭", "早餐", "午饭", "午餐", "晚饭", "晚餐", "夜宵", "外卖",
      "奶茶", "咖啡", "聚餐", "吃饭", "餐"), "餐饮"),
    (("地铁", "公交", "打车", "出租车", "网约车", "加油", "停车",
      "车票", "机票", "交通"), "交通"),
    (("房租", "水电", "物业", "燃气费"), "居住"),
    (("超市", "日用品", "纸巾", "洗衣"), "日用"),
    (("电影", "游戏", "唱歌", "旅游", "娱乐"), "娱乐"),
    (("衣服", "鞋子", "穿衣", "服饰"), "服饰"),
    (("看病", "挂号", "医院", "药"), "医疗"),
    (("书", "课程", "学费", "培训"), "教育"),
]


# ==================== 参数抽取器（message, match) -> dict） ====================

def _extract_accounting_add(message, match):
    """记账参数：金额（按支出/收入提示词定符号）+ 分类推断 + 备注。"""
    args = {}
    m = _AMOUNT_RE.search(message)
    if m:
        value = float(m.group(0).replace("元", "").strip())
        if any(cue in message for cue in _INCOME_CUES):
            value = abs(value)          # 收入口径：正数
        else:
            value = -abs(value)         # 支出动词或无标记：默认支出（负数）
        args["amount"] = round(value, 2)
    for keywords, category in _CATEGORY_KEYWORDS:
        hit = next((k for k in keywords if k in message), None)
        if hit:
            args["category"] = category
            args.setdefault("note", hit)  # 备注记下命中的物项词（如"午饭"）
            break
    return args


def _extract_accounting_query(message, match):
    """查账参数：时段——今天/本月有关键词则取，否则全部。"""
    if re.search(r"今天|今日", message):
        return {"period": "today"}
    if re.search(r"这个月|本月|当月", message):
        return {"period": "month"}
    return {"period": "all"}


def _extract_search_args(message, match):
    """搜索参数：触发词之后的部分即 query；触发词在句尾时取其余部分。"""
    strip_chars = " ，,。.:：、？?！!~\n\t"
    query = message[match.end():].strip(strip_chars)
    if not query:
        query = (message[:match.start()] + message[match.end():])\
            .strip(strip_chars)
    return {"query": query} if query else {}


def _extract_ebook_args(message, match):
    """导书参数：书名取书名号/引号内的内容（如《2026 上半年》），缺省无。"""
    m = re.search(r"[《「【](.+?)[》」】]", message)
    return {"title": m.group(1).strip()} if m else {}


# ==================== 意图表（数据驱动：新增意图只加表项） ====================
# 字段：name 意图名 / patterns 正则（表序即优先级，先命中先赢）/
#       extractor 参数抽取 / handler_name 延迟处理器引用 /
#       negative_patterns 排除词（命中则跳过该意图，防误路由）

INTENT_PATTERNS = [
    {
        "name": "export_ebook",
        "desc": "把对话/聊天记录导出成电子书（EPUB）",
        "patterns": [
            r"导出.{0,8}电子书",
            r"(对话|聊天|聊天记录).{0,8}(导出|生成|做成|变成|整理|打包)"
            r".{0,8}(电子书|一本书|成书|epub)",
            r"生成.{0,8}电子书",
            r"(做成|变成|整理成|打包成).{0,8}电子书",
            r"电子书.{0,6}导出",
        ],
        "extractor": _extract_ebook_args,
        "handler_name": "plugins.ebook_export:export_from_history",
    },
    {
        "name": "accounting_query",
        "desc": "查账汇总（这个月花了多少/账单汇总/结余）",
        "patterns": [
            r"花了?多少",
            r"(这个月|本月|当月|今天|今日).{0,10}(花|支出|消费|结余|收支)",
            r"(账|账单|账本|消费|收支).{0,4}(汇总|统计|总结)",
            r"结余|收支",
        ],
        "extractor": _extract_accounting_query,
        "handler_name": "plugins.accounting:summarize",
    },
    {
        "name": "accounting_list",
        "desc": "翻账本记录（账单/记账本/消费记录/查一下账）",
        "patterns": [
            r"账单",
            r"记账本",
            r"账本",
            r"消费记录",
            r"(看看|查一下|查查|翻一下|翻翻|打开).{0,4}账",
            r"查账",
        ],
        "extractor": lambda message, match: {},
        "handler_name": "plugins.accounting:list_records",
    },
    {
        "name": "accounting_add",
        "desc": "记账（记一下账/记一笔/花了 N 元）",
        "patterns": [
            r"记(一下|一笔|个)?账",
            r"记(一笔|一下|个).{0,16}元",
            r"(花了?|支出|消费|付了?)[^0-9元]{0,6}[+-]?\d+(?:\.\d+)?\s*元",
            r"(收入|进账|收到|赚了?)[^0-9元]{0,6}[+-]?\d+(?:\.\d+)?\s*元",
        ],
        "extractor": _extract_accounting_add,
        "handler_name": "plugins.accounting:add_record",
    },
    {
        "name": "web_search",
        "desc": "联网搜索（帮我搜/搜索一下/查一下，抽取 query）",
        "patterns": [
            r"(帮我|请|麻烦)(你)?(联网|上网)?(搜索|搜一下|搜一搜|搜下|搜个|搜)(一下)?",
            r"(联网|上网)(搜索|查)(一下)?",
            r"(搜索|搜一下|搜一搜|搜下)(一下)?",
            r"(帮我|请|麻烦)?查(一下|查看|下)",
            r"(谷歌|百度|必应)一下",
        ],
        "extractor": _extract_search_args,
        "handler_name": "search_tools:web_search",
        # 排除词：文件/家居/手机类请求应走模型工具协议（11 项白名单），
        # 不做搜索直达，避免"查一下工作区文件"之类误路由
        "negative_patterns": [
            r"工作区|文件|设备|灯|空调|开关|插座|截图|屏幕|点击|点一下",
        ],
    },
]

# 预编译（import 期完成，运行期零编译开销；无任何 I/O 副作用）
_COMPILED_PATTERNS = [
    ({**entry,
      "_neg": [re.compile(p, _RE_FLAGS)
               for p in entry.get("negative_patterns", ())]},
     [re.compile(p, _RE_FLAGS) for p in entry["patterns"]])
    for entry in INTENT_PATTERNS
]

# 意图名 → 表项（模型层解析用）
_INTENT_BY_NAME = {entry["name"]: entry for entry in INTENT_PATTERNS}


# ==================== 路由结果与路由入口 ====================

@dataclasses.dataclass
class IntentResult:
    """路由结果（接口用法见模块 docstring，供 S5 接线）。"""

    name: str                       # 意图名
    args: dict                      # 抽取出的参数（对应 handler 形参）
    confidence: float               # 置信度 0-1
    handler: str                    # 延迟处理器引用 "模块路径:函数名"
    source: str = "rule"            # "rule" 规则层 / "model" 模型层


def route(message, context=None):
    """自然语言 → 意图。命中返回 IntentResult，不命中返回 None
    （None = 不路由，走正常对话）。

    message: 用户消息文本；context: 预留给接线层的上下文（如 {"history":
    [...]}，模型层开启时会作为 history 传给 brain.smart_ask）。
    规则层优先（零 token）：INTENT_PATTERNS 按表序逐条匹配，先命中先赢；
    规则未命中时按 env XIAOJU3_MODEL_ROUTE 决定是否走模型层兜底。
    """
    message = "" if message is None else str(message)
    if message.strip():
        for entry, compiled in _COMPILED_PATTERNS:
            match = None
            for regex in compiled:
                m = regex.search(message)
                if not m:
                    continue
                # 排除词命中：跳过该意图（防"查一下工作区文件"误路由）
                if any(neg.search(message) for neg in entry["_neg"]):
                    break
                match = m
                break
            if match is not None:
                args = entry["extractor"](message, match) or {}
                return IntentResult(
                    name=entry["name"],
                    args=args,
                    confidence=entry.get("confidence", CONFIDENCE_RULE),
                    handler=entry["handler_name"],
                    source="rule")
    return _model_route(message, context)


def dispatch(intent):
    """按延迟字符串引用执行意图：动态 import "模块路径:函数名" 并调用。

    intent: IntentResult 或 handler 字符串；任何失败（模块缺席、参数
    不全、handler 抛错）都转 ❌ 开头的中文报错串返回，不向上抛。
    """
    if isinstance(intent, IntentResult):
        handler_name = intent.handler
        args = dict(intent.args or {})
    else:
        handler_name, args = str(intent), {}
    if ":" not in handler_name:
        return f"❌ 意图处理器格式非法（应为 模块:函数）：{handler_name}"
    module_name, _, func_name = handler_name.partition(":")
    try:
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        return func(**args)
    except TypeError as e:
        return f"❌ 意图参数不全或非法，无法执行 {handler_name}：{e}"
    except Exception as e:
        return f"❌ 意图执行失败：{e}"


# ==================== 模型层（可选兜底，默认关闭） ====================

_MODEL_ROUTE_PROMPT = (
    "你是意图分类器。请从这些意图里判断用户消息属于哪一个：{names}。"
    "只输出一行 JSON，不要输出任何其他文字："
    '{{"intent": "意图名", "args": {{"参数名": "值"}}}}；'
    '都不匹配就输出 {{"intent": "none", "args": {{}}}}。'
    "用户消息：{message}"
)


def _model_route_enabled():
    """模型层开关：env XIAOJU3_MODEL_ROUTE 控制，默认关闭。"""
    return os.environ.get(MODEL_ROUTE_ENV, "").strip().lower() in _MODEL_TRUTHY


def _model_route(message, context=None):
    """模型层兜底：规则未命中时走 brain.smart_ask 澄清意图。

    brain 函数内延迟导入——缺席（未部署/测试环境）优雅降级返回 None，
    表示"不路由，走正常对话"；模型异常或回复解析失败同样返回 None。
    """
    if not _model_route_enabled():
        return None
    try:
        import brain  # 延迟导入：缺席降级，不阻断对话主链路
    except Exception:
        return None
    history = None
    if isinstance(context, dict) and context.get("history"):
        history = list(context["history"])
    prompt = _MODEL_ROUTE_PROMPT.format(
        names="、".join(entry["name"] for entry in INTENT_PATTERNS),
        message=message)
    try:
        reply, _source = brain.smart_ask(prompt, history=history)
    except Exception:
        return None
    return _parse_model_reply(reply)


def _parse_model_reply(reply):
    """解析模型层回复中的一行 JSON 意图；意图名不在表内视为不路由。"""
    m = re.search(r"\{.*\}", str(reply or ""), re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    name = str(data.get("intent", "")).strip()
    entry = _INTENT_BY_NAME.get(name)
    if entry is None or name == "none":
        return None
    args = data.get("args")
    return IntentResult(name=name,
                        args=dict(args) if isinstance(args, dict) else {},
                        confidence=CONFIDENCE_MODEL,
                        handler=entry["handler_name"],
                        source="model")
