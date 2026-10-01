# -*- coding: utf-8 -*-
"""小橘3号 · 双脑决策层（本地优先决策）。

按《架构设计文档》§3：
- 每条消息先花约 1 秒（LOCAL_TIMEOUT）探测本地 Ollama（LOCAL_PROBE_URL），
  在线走 ask_local；探测失败或本地调用异常时自动热切换云端 DeepSeek
  （ask_cloud），过程对用户透明，回复附来源标签（"🏠 本地"/"☁️ 云端"）。
- 工具协议：无 function calling，提示词（prompts.SYSTEM_PROMPT）要求模型
  "只输出一行 JSON" → 正则提取 → 11 项白名单校验 → tools.execute_tool 执行
  （LV3 高危门禁在工具层）→ 工具结果喂回模型生成自然语言回答。汇总轮
  本地优先（§10 #14：先试 ask_local，异常/不可用自动转 ask_cloud），
  来源标签如实标注（"🏠 本地 (工具)"/"☁️ 云端 (工具)"）。每轮最多一次
  工具调用；工具结果以 ❌ 开头时切断重试直接返回拒绝文案（单轮硬拦截，
  execute_tool 抛异常同样转 ❌ 文案切断，保证 <think> 包装不漏）。
- 防死循环熔断（§10 #1，开发日志第四章"小犟3号"事件口径）：❌ 切断只保证
  本轮不把拒绝结果喂回模型；跨轮由 ToolLoopFuse 对同一会话内"同一工具 +
  等价参数被拒"连续计数，达到 TOOL_FUSE_LIMIT（默认 3，环境变量可配）次
  → 强制打断：剥夺工具调用权（不再解析/执行工具 JSON），退回纯文本回复，
  并提示用户如何继续；reset 接口供换话题/管理员指令重置。
- 思维链展示（<think> 包装，DeepSeek 式推理卡片契约，前端并行组同口径）：
  提示词要求模型工具调用按"[思考] → [计划] → [行动]"结构输出；smart_ask
  对首轮回复用正则分别捕获 [思考] 与 [计划] 文本（到下一个标记 / "{" /
  串尾为止，DOTALL，可只捕获其一）；凡本轮解析出工具 JSON 且执行
  （含 ❌ 切断与熔断通知），最终 reply 最前面一律包装 <think>...</think>
  ——统一经 _wrap_think 拼装：thinking/body 两侧先剥除模型自吐的
  <think>/</think> 字面量（推理模型原生标签是游离标签唯一来源），拼装后
  再做成对校验（恰一对标签且在最前），杜绝 "</think>[思考]…" 直出网页
  （内容为捕获文本拼接；模型没输出任何思考时按实际解析出的工具名动态
  生成占位符"[思考] 准备调用 {工具名} 尝试完成操作."，解析不出工具名时
  回退 TOOL_THINKING_PLACEHOLDER 固定占位符）。全对话强制包装（2026-10-01
  用户指令，显式废止旧"普通聊天零包装零干扰"口径）：系统指令（/clear、
  /coder_auth、/register 等）在 main.py 指令段先行处理并直接返回，不会
  进入 smart_ask——smart_ask 只接收自然语言对话，故凡经 smart_ask 的
  回复一律带 <think> 卡片：解析不出工具 JSON / 工具不在白名单等旁路普通
  回复、URL 总结与熔断退回纯文本路径统一经 _seal_bare_cot 出口——捕获到
  原生 [思考]/[计划] 用原生；出现任意一个裸协议标记（含全角变体）但无
  思考文本的残缺形态回退 TOOL_THINKING_PLACEHOLDER 占位思考（body 取剥离
  裸标记后的剩余正文，剥空用"（操作已执行）"占位；body 已以 <think> 开头
  则防重入不再二次包装，绝不裸漏 JSON 载荷）；无任何标记的普通闲聊注入
  CHAT_THINKING_PLACEHOLDER 默认占位符（"[思考] 正在理解你的意图..."，
  闲聊没调工具，文案不出现"调用工具"字样）；抓取失败/双脑全挂/空回复等
  固定文案同样经 _force_chat_think 注入默认占位符——前端必定渲染思维链
  卡片。
  工具流程回退分支封口（2026-10-01 用户实测"帮我点击蓝牙"漏点，穷举
  封死）：ui_tap_element 失败自动回退 vision_tap_element、视觉点击成功
  （非 ❌）时，汇总轮模型在最终回答里复读的裸 [思考]/[计划]/[行动] 统一
  经 _seal_tool_summary 封口——捕获文本并入首轮推理卡片（两轮思考一张
  卡），正文只留干净自然语言；❌ 切断路径的工具返回串（个别工具会把模型
  原文拼进错误串）同样先 _strip_bare_cot 剥净再包装。smart_ask 全部 11 条
  return 路径的逐条封口扫描由 tests/test_brain.py 的 BareCotLeakSweepTests
  固化守护（新增返回路径必须同步登记）。
  注入兜底占位符 / 捕获到原生思考时各打印一条 [CoT] 终端日志，
  供部署侧确认思维链来源。JSON 提取先按原贪婪
  正则整体匹配，失败时回退逐 "{" 起点 raw_decode 扫描——CoT 文本里混入
  的花括号内容绝不干扰工具 JSON 提取，且全程不抛异常。
- 输入含 URL：先抓网页正文（剔除 script/style 标签）再按"总结网页"并入提问。
- 采样温度 LLM_TEMPERATURE（默认 0.7，env LLM_TEMPERATURE 可覆盖）统一注入
  两个后端，让回复语气更自然拟人；两家 schema 不同，落点也不同：
  Ollama /api/chat 必须放 options.temperature（顶层无效），DeepSeek
  /chat/completions 用顶层 temperature。
- MAX_MESSAGES=50 滚动截断在保存侧 save_memory 生效（§4）。
- translate_emoji（[EMOJI:标签] → CQ 码图片）已接入回复链（§5 闭环口径）：
  smart_ask 的正常文本回复（普通/总结/工具汇总）返回前统一转换；
  emoji_manager 函数内延迟导入，缺席时优雅降级。
"""
import json
import os
import re
import socket

import requests
import requests.packages.urllib3.util.connection as urllib3_cn

import xiaoju3
from xiaoju3 import (CLOUD_KEY, CLOUD_URL, CLOUD_MODEL, MAX_MESSAGES,
                     LOCAL_URL, LOCAL_MODEL, LOCAL_MODEL_SMALL, LOCAL_PROBE_URL,
                     LOCAL_TIMEOUT)
from permission import permission_manager
from prompts import SYSTEM_PROMPT
from tools import execute_tool


# 与参考实现一致：强制 IPv4 解析，避免部分主机的 IPv6 解析卡顿
def _allowed_gai_family():
    return socket.AF_INET


try:
    urllib3_cn.allowed_gai_family = _allowed_gai_family
except Exception:
    pass

# 本地生成超时（秒）：顶部 LOCAL_TIMEOUT（1 秒）仅是在线探测口径，本地生成
# 更耗时，与参考实现一致取 30 秒。
LOCAL_GENERATE_TIMEOUT = float(os.environ.get("LOCAL_GENERATE_TIMEOUT", "30"))

# 云端生成 / 网页抓取超时与正文截断长度（参考实现口径）
CLOUD_TIMEOUT = 30
FETCH_TIMEOUT = 15
FETCH_MAX_CHARS = 2000

# 拟人化采样温度（用户指令 temperature=0.7：略高的发散度让回复更自然口语化）。
# env LLM_TEMPERATURE 可覆盖；解析失败（非数字）回退默认值。
DEFAULT_TEMPERATURE = 0.7

try:
    LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", DEFAULT_TEMPERATURE))
except (TypeError, ValueError):
    LLM_TEMPERATURE = DEFAULT_TEMPERATURE

# 工具白名单：与 tools.py 的 12 项分发、prompts.py 的工具协议一致
# （文档 §5；第二阶段 §10 #5 新增 web_search、§7 权限调整新增 system_manage）
TOOL_WHITELIST = [
    "list_files", "read_file", "write_file", "get_ha_devices",
    "control_ha_device", "adb_tap", "adb_swipe", "adb_screenshot",
    "vision_tap_element", "ui_tap_element", "web_search", "system_manage",
    "read_core_memory",
]


# ==================== CoT 思考提取（<think> 包装，前端推理卡片契约） ====================

# 模型没输出任何 [思考]/[计划] 时的固定思考占位符（解析不出工具名时的兜底，
# 与前端契约字面量一致）
TOOL_THINKING_PLACEHOLDER = "[思考] 已按计划执行工具调用。"

# 普通闲聊（无工具调用、无原生思考）的默认思考占位符（2026-10-01 用户口径
# "强制所有自然语言对话展示思维链卡片"；闲聊没调工具，文案不出现"调用工具"
# 字样，与前端推理卡片契约字面量一致）
CHAT_THINKING_PLACEHOLDER = "[思考] 正在理解你的意图..."


def _tool_thinking_placeholder(tool_name):
    """无 CoT 时的 [思考] 占位符：按本轮实际解析出的工具名动态生成。

    让推理卡片至少向主人展示"准备调用什么工具"（如 ui_tap_element /
    adb_tap），而不是一句与操作无关的空话；解析不出工具名（空值等）时
    回退 TOOL_THINKING_PLACEHOLDER 固定占位符。<think> 包装机制本身零改动。
    """
    name = str(tool_name).strip() if tool_name else ""
    if name:
        return f"[思考] 准备调用 {name} 尝试完成操作。"
    return TOOL_THINKING_PLACEHOLDER

# [思考]/[计划] 段捕获：内容到下一个标记（[计划]/[行动]）、"{" 或串尾为止
# （DOTALL 跨行；兼容全角【】变体与"标记："写法）。"{" 终止符保证思考文本
# 绝不会把工具 JSON 吞进推理展示。
_THINK_RE = re.compile(
    r'[\[【]思考[\]】][:：]?\s*(.*?)(?=[\[【]计划[\]】]|[\[【]行动[\]】]|\{|$)',
    re.DOTALL)
_PLAN_RE = re.compile(
    r'[\[【]计划[\]】][:：]?\s*(.*?)(?=[\[【]行动[\]】]|\{|$)',
    re.DOTALL)


def _capture_thinking(raw_reply):
    """捕获模型首轮回复中的 [思考] / [计划] 推理文本（保留标记字面量）。

    两个都捕获或捕获其一均可；都没有（或只有空白）返回空串，由调用方
    回退 TOOL_THINKING_PLACEHOLDER 默认占位符。捕获按标记切分、与 JSON
    提取互不耦合（终止符含 "{"，思考文本不会吞进工具 JSON）。
    """
    parts = []
    think = _THINK_RE.search(raw_reply)
    if think and think.group(1).strip():
        parts.append("[思考] " + think.group(1).strip())
    plan = _PLAN_RE.search(raw_reply)
    if plan and plan.group(1).strip():
        parts.append("[计划] " + plan.group(1).strip())
    return "\n".join(parts)


# <think>/</think> 标签字面量（大小写不敏感、容忍标签内空白/属性变体）。
# DeepSeek-R1 一类推理模型的原生输出常自带这些字面量：混进 [思考] 文本被
# _capture_thinking 捕获、或随汇总轮回复进入 body，都会在最终 reply 里
# 形成游离标签——前端非贪婪正则截到第一个 </think> 后把余文原文直出
# （网页出现 "</think>[思考]…" 即此来源），故包装前一律剥除。
_THINK_TAG_RE = re.compile(r'</?think(?:\s[^>]*)?>', re.IGNORECASE)

# 成对校验：最终 reply 必须以 <think> 开头、至第一个 </think> 闭合（DOTALL）
_THINK_PAIR_RE = re.compile(r'^<think>(.*?)</think>', re.DOTALL)


def _strip_think_tags(text):
    """剥除文本中全部 <think>/</think> 标签字面量（文本内容保留）。"""
    return _THINK_TAG_RE.sub("", text)


def _wrap_think(thinking, body):
    """统一 <think> 包装点：工具流程四处返回一律经此拼装（消灭手写拼接）。

    产出 f"<think>{thinking}</think>{body}"，带三重防游离标签保障：
    1. thinking 侧清洗：模型自吐的 <think>/</think> 字面量先剥除
       （防嵌套/防游离闭合标签混进推理卡片内容）；
    2. body 侧清洗：模型复读进最终回复文本的标签字面量同样剥除
       （文本内容保留，只去标签）；
    3. 成对校验（后置保障）：拼装结果必须以 <think> 开头且全文恰一对
       标签——清洗后仍游离的（清洗正则被未来改动遗漏时）直接剥除重建，
       保证前端正则（成对 <think>...</think> 非贪婪匹配）总能命中。
    纯函数：同等输入必有同等输出，可直接单测；None 输入按空串处理。
    """
    thinking_text = _strip_think_tags("" if thinking is None else str(thinking))
    body_text = _strip_think_tags("" if body is None else str(body))
    reply = f"<think>{thinking_text}</think>{body_text}"
    pair = _THINK_PAIR_RE.match(reply)
    if pair is None:
        # 完全不成对（理论不可达的兜底）：剥光全部标签字面量后按空思考重建
        return "<think></think>" + _strip_think_tags(reply)
    # 只保留开头 <think> 与其第一个 </think>，其余一切游离标签一律剥除
    return ("<think>" + _strip_think_tags(pair.group(1)) + "</think>"
            + _strip_think_tags(reply[pair.end():]))


def _extract_tool_json(raw_reply):
    """从模型回复中提取工具 JSON 原文（不含 CoT 思考文本），取不到返回 None。

    先按历史贪婪正则整体匹配并验证可解析（既有行为完全不变）；验证失败时
    （例如 [思考] 文本里混入花括号内容，贪婪匹配把两段拼在一起导致解析
    失败）回退到逐个 "{" 起点 raw_decode 扫描，返回第一个含 "tool" 键的
    可解析 JSON 对象原文。全程 try/except 兜底，绝不抛异常。
    """
    match = re.search(r'\{.*"tool".*\}', raw_reply, re.DOTALL)
    if match:
        try:
            json.loads(match.group(0))
            return match.group(0)
        except Exception:
            pass
    try:
        decoder = json.JSONDecoder()
        for brace in re.finditer(r'\{', raw_reply):
            start = brace.start()
            try:
                obj, end = decoder.raw_decode(raw_reply[start:])
            except ValueError:
                continue
            if isinstance(obj, dict) and "tool" in obj:
                return raw_reply[start:start + end]
    except Exception:
        pass
    return None


# [行动] 剥离（裸 CoT 封口用，与前端 console.js BARE_ACTION_RE 同口径）：
# 标记一律剥离；其后若跟以 { 起头的单行 JSON 工具载荷（prompts 协议硬性
# 口径"[行动] 行必须且只能是一行合法 JSON"），载荷一并剥离（[^\n] 不跨行）
_BARE_ACTION_RE = re.compile(r'\s*[\[【]行动[\]】](?:[ \t]*\{[^\n]*)?')

# 裸 CoT 正文剥空占位（与前端契约字面量一致）：剥离裸标记后无自然语言
# 正文时使用，绝不把过程原文漏给用户
BARE_COT_BODY_PLACEHOLDER = "（操作已执行）"

# 裸 CoT 标记探测（含全角【】变体）：只要出现任意一个协议标记即触发封口。
# 单独列出是因为 _capture_thinking 只认"有内容的 [思考]/[计划]"——模型只
# 输出 "[行动] {JSON}"（或标记后无内容）的残缺形态捕获为空，旧判定会整段
# 裸漏（含工具 JSON 原文）。
_BARE_COT_MARK_RE = re.compile(r'[\[【](?:思考|计划|行动)[\]】]')


def _strip_bare_cot(raw_reply):
    """剥离裸 [思考]/[计划] 段与 [行动] 行（含行内 JSON 载荷），返回剩余正文。

    思考/计划段与 _capture_thinking 同边界口径（到下一标记 / "{" / 串尾为
    止，DOTALL 跨行）；[行动] 与其后的单行 JSON 载荷一并剥离——与前端
    splitThinkBlock 的裸标记扫描收敛一致。纯函数，可直接单测。
    """
    text = _THINK_RE.sub("", raw_reply)
    text = _PLAN_RE.sub("", text)
    text = _BARE_ACTION_RE.sub("", text)
    return text.strip()


def _force_chat_think(body):
    """普通闲聊 / 固定文案口径的强制包装：无原生思考时注入默认占位符。

    2026-10-01 用户口径"强制所有自然语言对话展示思维链卡片"：普通闲聊
    （无工具调用）与抓取失败/双脑全挂/空回复等固定文案没有原生 [思考]
    文本可捕获，统一注入 CHAT_THINKING_PLACEHOLDER 默认占位符，保证前端
    必定渲染思维链卡片；[CoT] 终端日志与工具路径占位符日志口径一致。
    """
    print("[CoT] 已注入默认占位符（无原生思考）")
    return _wrap_think(CHAT_THINKING_PLACEHOLDER, body)


def _seal_bare_cot(raw_reply):
    """全对话强制包装出口：smart_ask 自然语言回复一律带 <think> 卡片。

    用户口径（2026-10-01"强制所有自然语言对话展示思维链卡片"，显式废止旧
    "普通聊天零包装零干扰"）：系统指令（/clear、/coder_auth、/register 等）
    在 main.py 指令段先行处理并直接返回，不会进入 smart_ask，故此处无需
    （也不应）做指令判别。凡经 smart_ask 的回复一律包装：
    - 捕获到 [思考]/[计划] 文本 → 原生思考进推理卡片；
    - 只有 [行动]（或标记后无内容、捕获为空）→ 回退 TOOL_THINKING_PLACEHOLDER
      占位思考——残缺形态同样不许把标记与 JSON 载荷漏给用户；
    - 无任何标记（普通闲聊，含 URL 总结/熔断退回/旁路普通回复）→ 注入
      CHAT_THINKING_PLACEHOLDER 默认占位符（闲聊没调工具，占位文案不出现
      "调用工具"字样）；
    - body 取 _strip_bare_cot 剥离裸标记后的剩余正文，剥空时用
      BARE_COT_BODY_PLACEHOLDER 占位（"宁可隐藏"）；body 已以 <think> 开头
      （模型自包/上游已包）时防重入，只剥净裸标记不再二次包装（无标记的
      普通闲聊同理：模型自吐 <think> 原生包装时原样透传）；
    - 封口/注入时各打印一条 [CoT] 终端日志，与工具路径日志口径一致。
    """
    if not _BARE_COT_MARK_RE.search(raw_reply):
        # 普通闲聊：强制注入默认占位符（模型自吐 <think> 原生包装时防重入
        # 原样透传——前端照样渲染卡片，不二次包）
        if raw_reply.lstrip().startswith("<think>"):
            return translate_emoji(raw_reply)
        return _force_chat_think(translate_emoji(raw_reply))
    print("[CoT] 模型原生输出思考内容")
    thinking = _capture_thinking(raw_reply)
    body = _strip_bare_cot(raw_reply)
    if body.startswith("<think>"):
        # 防重入：正文已是 <think> 包装形态，剥净裸标记后原样返回
        return translate_emoji(body)
    if not thinking:
        # 只有 [行动] 没有思考文本（残缺形态）：思考占位兜底，绝不裸漏
        thinking = TOOL_THINKING_PLACEHOLDER
    if not body:
        body = BARE_COT_BODY_PLACEHOLDER
    return _wrap_think(thinking, translate_emoji(body))


def _seal_tool_summary(thinking, final_reply):
    """工具汇总轮裸 CoT 封口（ui_tap→vision 回退分支实测漏点，穷举封死）。

    用户实测"帮我点击蓝牙"漏点根因：ui_tap_element 失败自动回退
    vision_tap_element、视觉点击成功（非 ❌）时，汇总轮把工具结果喂回模型，
    模型在最终自然语言回答里仍按 [思考] → [计划] → [行动] 协议习惯复读裸
    CoT——首轮 thinking 包装只包住首轮推理，汇总轮的裸标记随 body 直出网页。
    在既有 _wrap_think 之前对汇总轮输出做同口径封口：
    - 无裸标记 → 既有行为零改动（转表情后 _wrap_think，<think> 标签字面量
      仍由 _wrap_think 剥除）；
    - 有裸标记 → 汇总轮捕获的思考文本并入首轮推理卡片（两轮思考一张卡），
      body 取剥离裸标记后的剩余正文，剥空注入 BARE_COT_BODY_PLACEHOLDER
      占位（"宁可隐藏"），并打印 [CoT] 终端日志与首轮口径一致。
    """
    reply_text = "" if final_reply is None else str(final_reply)
    body = _strip_bare_cot(reply_text)
    if body == reply_text.strip():
        # 汇总轮无裸标记：既有行为零改动
        return _wrap_think(thinking, translate_emoji(reply_text))
    extra = _capture_thinking(reply_text)
    if extra:
        thinking = ((thinking + "\n") if thinking else "") + extra
    print("[CoT] 模型原生输出思考内容")
    if not body:
        body = BARE_COT_BODY_PLACEHOLDER
    return _wrap_think(thinking, translate_emoji(body))


# ==================== 防死循环熔断（§10 #1 / 开发日志第四章） ====================

# 熔断阈值：同一会话内"同一工具 + 等价参数被拒"连续次数上限（可配置）
TOOL_FUSE_LIMIT = max(1, int(os.environ.get("TOOL_FUSE_LIMIT", "3")))

# 熔断触发后给用户的中文提示（说明已暂停工具使用及如何继续）
TOOL_FUSE_NOTICE = ("⛔ 小橘3号连续多次尝试同一被拒绝的操作，为防止死循环，"
                    "已暂时收回工具调用权限，先用纯文本和你聊。"
                    "你可以换个话题，或请管理员重置后继续使用工具。")

# 熔断期间注入给模型的系统提示：禁止再输出工具 JSON，退回纯文本
TOOL_FUSE_SYSTEM_NOTE = ("【系统提示】工具调用权限已因连续失败被暂时收回，"
                         "本轮请直接用自然语言回答用户，"
                         "绝对不要输出任何 JSON 或工具调用！")


def _canonical_args(args):
    """参数指纹归一化：键排序、叶子值统一转字符串（3 与 "3" 视为等价）。"""
    if isinstance(args, dict):
        return {str(k): _canonical_args(args[k]) for k in sorted(args, key=str)}
    if isinstance(args, (list, tuple)):
        return [_canonical_args(v) for v in args]
    return str(args)


class ToolLoopFuse:
    """跨轮防死循环熔断器（"小犟3号"事件：JSON 死循环复读的代码级拦截）。

    - 以会话（session_key）为单位，对"同一工具 + 等价参数被拒（❌ 结果）"
      做连续计数；换工具/换参数或一次成功执行都会让"连续"归零；
    - 连续达到 TOOL_FUSE_LIMIT 次 → 熔断：剥夺工具调用权，退回纯文本回复；
    - 熔断后 execute_tool 不再被调用，直到显式 reset（用户换话题 /
      管理员指令触发，接线由 main.py 侧完成）。
    """

    def __init__(self, limit=None):
        self.limit = TOOL_FUSE_LIMIT if limit is None else int(limit)
        self._streaks = {}     # session_key -> 连续被拒计数
        self._last = {}        # session_key -> 最近一次被拒指纹
        self._tripped = set()  # 已熔断的会话

    @staticmethod
    def fingerprint(tool_name, args):
        """工具调用指纹：(工具名, 归一化参数 JSON)。"""
        return (tool_name,
                json.dumps(_canonical_args(args or {}),
                           ensure_ascii=False, sort_keys=True))

    def record_rejection(self, session_key, tool_name, args):
        """记录一次被拒工具调用，返回当前连续计数；达到阈值即触发熔断。"""
        fp = self.fingerprint(tool_name, args)
        if self._last.get(session_key) == fp:
            self._streaks[session_key] = self._streaks.get(session_key, 0) + 1
        else:
            self._streaks[session_key] = 1
            self._last[session_key] = fp
        if self._streaks[session_key] >= self.limit:
            self._tripped.add(session_key)
        return self._streaks[session_key]

    def record_success(self, session_key):
        """一次成功执行（结果非 ❌）打断"连续"计数。"""
        self._streaks[session_key] = 0
        self._last[session_key] = None

    def is_tripped(self, session_key):
        return session_key in self._tripped

    def reset(self, session_key=None):
        """重置熔断状态：session_key=None 清空全部会话（管理员口径）。"""
        if session_key is None:
            self._streaks.clear()
            self._last.clear()
            self._tripped.clear()
        else:
            self._streaks.pop(session_key, None)
            self._last.pop(session_key, None)
            self._tripped.discard(session_key)


# 模块级熔断器：接入层（main.py）可按通道传 session_key（QQ/网页/仪表盘）
tool_fuse = ToolLoopFuse()


def reset_tool_fuse(session_key=None):
    """熔断重置接口：供 main.py 的管理员指令 / 换话题逻辑调用。"""
    tool_fuse.reset(session_key)


# ============================ 会话记忆（§4） ============================

def load_memory(filepath):
    """从磁盘读取会话历史（role/content JSON 列表），缺失或损坏返回空列表。"""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_memory(history, filepath):
    """会话落盘：滚动保留最近 MAX_MESSAGES=50 条（架构设计文档 §4）。"""
    if len(history) > MAX_MESSAGES:
        history = history[-MAX_MESSAGES:]
    try:
        dirpath = os.path.dirname(filepath)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ============================ 双脑推理（§3） ============================

def ask_local(msgs, model=None):
    """本地 Ollama 推理（/api/chat）。异常向上抛，由 smart_ask 热切换云端。

    model 缺省用 LOCAL_MODEL（high 档大模型）；medium 档传 LOCAL_MODEL_SMALL
    （硬件自适应路由，qwen2.5:0.5b 一类小模型）。
    """
    # keep_alive=-1：模型常驻显存/内存，避免每次请求重新加载导致 5-8 秒卡顿
    # temperature 放 options 内：Ollama /api/chat 的 schema 要求采样参数
    # 全部收在 options 里，放顶层不生效
    payload = {"model": model or LOCAL_MODEL, "messages": msgs,
               "stream": False, "keep_alive": -1,
               "options": {"temperature": LLM_TEMPERATURE}}
    return requests.post(LOCAL_URL, json=payload,
                         timeout=LOCAL_GENERATE_TIMEOUT).json()['message']['content']


def ask_cloud(messages):
    """云端 DeepSeek 兜底。API 报错 / 连接异常时返回 ⚠️ 文案而非抛异常
    （参考实现口径），由 smart_ask 统一判定"双脑全挂"的失败口径。"""
    headers = {"Authorization": f"Bearer {CLOUD_KEY}", "Content-Type": "application/json"}
    # temperature 顶层字段：DeepSeek /chat/completions 的 schema（与 Ollama 不同）
    payload = {"model": CLOUD_MODEL, "messages": messages, "stream": False,
               "temperature": LLM_TEMPERATURE}

    try:
        response = requests.post(CLOUD_URL, headers=headers, json=payload,
                                 timeout=CLOUD_TIMEOUT)
        response.raise_for_status()
        resp_json = response.json()

        # 检查是否存在 choices，如果不存在，就把接口返回的原始错误信息发出来
        if "choices" in resp_json:
            return resp_json["choices"][0]["message"]["content"]

        # 如果 API 返回了错误（比如模型不对、余额不足），直接显示错误详情
        error_detail = resp_json.get("error", {})
        if isinstance(error_detail, dict):
            msg = error_detail.get("message", "未知错误")
        else:
            msg = str(error_detail)
        return f"⚠️ API接口报错: {msg}"

    except Exception as e:
        return f"⚠️ 云端连接异常: {e}"


def probe_local():
    """探测本地 Ollama 是否在线：约 1 秒超时（LOCAL_TIMEOUT），不阻塞对话。"""
    try:
        requests.get(LOCAL_PROBE_URL, timeout=LOCAL_TIMEOUT)
        return True
    except Exception:
        return False


# ==================== 硬件自适应路由（high / medium / low） ====================

_VALID_TIERS = ("high", "medium", "low")
_TIER_CACHE = None  # DEVICE_TIER=auto 时的进程内探测缓存（只探一次）


def _resolve_tier():
    """解析硬件档位：显式值优先，auto（默认）经 hardware_profiler 探测并缓存。

    - xiaoju3.DEVICE_TIER 每次动态读取（便于测试与运行期覆盖）；
    - 非法值按 auto 处理；探测异常降级 medium（混合模式最稳妥）。
    """
    tier = (getattr(xiaoju3, "DEVICE_TIER", "auto") or "auto").strip().lower()
    if tier in _VALID_TIERS:
        return tier
    global _TIER_CACHE
    if _TIER_CACHE is None:
        try:
            import hardware_profiler
            _TIER_CACHE = hardware_profiler.detect_tier()
        except Exception:
            _TIER_CACHE = "medium"
    return _TIER_CACHE if _TIER_CACHE in _VALID_TIERS else "medium"


def _reset_tier_cache():
    """重置 auto 档探测缓存（供测试与运行期硬件变化后重新探测）。"""
    global _TIER_CACHE
    _TIER_CACHE = None


def _local_model_for(tier):
    """档位 → 本地模型：high 用大模型，medium 用小模型，low 不会走本地。"""
    return LOCAL_MODEL if tier == "high" else LOCAL_MODEL_SMALL


def _build_messages(message, history):
    """组装模型消息：system 提示词置顶 + 历史 + 本条用户消息。

    - history 中的 system 消息一律剔除，保证全列表只有置顶这一条系统提示词；
      例外：主链路注入的【前情提要】、长期记忆与最近设备操作记录上下文
      （架构 §10 #2/#3 接线）以特定前缀标识，允许通过并在去掉前缀后保留；
    - 兼容参考实现口径：调用方可能已把本条用户消息追加进 history 再调用
      （参考 main.py 先 append 再调 smart_ask），此时去重，避免重复；
    - 返回新列表，不修改调用方传入的 history。
    """
    messages = [SYSTEM_PROMPT]
    for m in history or []:
        if not isinstance(m, dict):
            continue
        role, content = m.get("role"), m.get("content") or ""
        if role == "system":
            for prefix in ("【前情提要】", "以下是关于用户的长期记忆",
                           "以下是最近的设备操作记录"):
                if content.startswith(prefix):
                    messages.append({"role": "system", "content": content})
                    break
            continue
        messages.append({"role": role, "content": content})
    if not (messages[-1]["role"] == "user" and messages[-1]["content"] == message):
        messages.append({"role": "user", "content": message})
    return messages


def smart_ask(message, history=None, session_key="default"):
    """双脑决策入口：本地优先，异常热切换云端。返回 (回复, 来源标签) 二元组。

    message: 本条用户消息文本；history: 历史 role/content 消息列表（可含
    system 提示词与/或已追加的本条用户消息，内部会自动去重置顶）；
    session_key: 熔断计数会话键（同一用户会话传同一键即可；QQ/网页/仪表盘
    可按通道区分，缺省共用 "default"）。
    """
    message = "" if message is None else str(message)

    # === 第一步：如果用户输入里有 URL，先抓网页正文（剔除 script/style） ===
    url_match = re.search(r'(https?://[^\s]+)', message)
    messages = _build_messages(message, history)
    if url_match:
        url = url_match.group(1)
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT)
            res.encoding = 'utf-8'
            text = re.sub(r'<script.*?</script>', '', res.text, flags=re.DOTALL)
            text = re.sub(r'<style.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', '', text)
            text = re.sub(r'\s+', ' ', text).strip()
            messages.append({"role": "system",
                             "content": f"已为你抓取好网页，请直接总结，不要输出任何 JSON！\n\n网页内容：\n{text[:FETCH_MAX_CHARS]}"})
        except Exception as e:
            # 🧠 全对话强制包装：固定失败文案同样注入默认占位符（前端必出卡片）
            return _force_chat_think(f"❌ 抓取网页失败: {e}"), "❌ 失败"

    # ⛔ 防死循环熔断：已熔断的会话先剥夺本轮工具调用权——注入系统提示
    # 让模型直接纯文本回答；后续也不再解析/执行任何工具 JSON
    fused = tool_fuse.is_tripped(session_key)
    if fused:
        messages.append({"role": "system", "content": TOOL_FUSE_SYSTEM_NOTE})

    # 🧭 硬件自适应路由：按 DEVICE_TIER 决定本地/云端优先级与模型档位
    tier = _resolve_tier()
    if tier == "low":
        # low：跳过本地探测（省 1 秒等待），直接依赖云端
        local_online = False
        print("📱 低配模式（low）：跳过本地探测，直接使用云端大脑。")
    else:
        # 🛡️ 自动探测本地大脑是否在线，不用再去改 True/False
        local_online = probe_local()
        if local_online:
            if tier == "medium":
                print(f"🧩 混合模式（medium）：本地大脑在线，优先使用小模型 {LOCAL_MODEL_SMALL}。")
            else:
                print("🏠 本地大脑在线，优先使用本地算力！")
        else:
            print("📡 本地大脑不在线，直接使用云端大脑...")

    raw_reply = ""
    used_local = False
    try:
        if local_online:
            try:
                raw_reply = ask_local(messages, model=_local_model_for(tier))
                used_local = True
            except Exception as e:
                print(f"⚠️ 本地大脑连接不稳定（{e}），自动切换云端大脑...")
                raw_reply = ask_cloud(messages)
        else:
            raw_reply = ask_cloud(messages)
    except Exception as e2:
        # 🧠 全对话强制包装：双脑全挂文案同样注入默认占位符
        return _force_chat_think(f"❌ 大脑连接失败，请检查网络。错误：{e2}"), "❌ 失败"

    raw_reply = raw_reply if isinstance(raw_reply, str) else str(raw_reply)

    # 云端兜底也失联（ask_cloud 把连接异常转成了 ⚠️ 文案）→ 双脑全挂，明确报错
    if raw_reply.startswith("⚠️ 云端连接异常"):
        return (_force_chat_think(f"❌ 大脑连接失败，请检查网络。错误：{raw_reply}"),
                "❌ 失败")

    if not raw_reply:
        # 🧠 全对话强制包装：空回复道歉文案同样注入默认占位符
        return (_force_chat_think("抱歉，小橘3号刚才脑袋短路了，请再说一遍吧。"),
                "🏠 本地" if used_local else "☁️ 云端")

    raw_reply = raw_reply.strip()
    label = "🏠 本地" if used_local else "☁️ 云端"

    # === 第三步：如果是抓网页的，直接返回总结 ===
    if url_match:
        # 🧠 裸 CoT 封口：总结文本若带模型原生 [思考]/[计划]，包装成卡片不裸漏
        return _seal_bare_cot(raw_reply), f"{label} (总结)"

    # === 第四步：解析工具调用（核心：用正则强匹配 JSON，允许前后有杂散文字） ===
    if fused:
        # ⛔ 熔断生效中：工具调用权已被剥夺，不再解析/执行工具 JSON，退回纯文本
        #（裸 CoT 封口同样生效：模型若仍输出 [思考]/[计划]，包装成卡片不裸漏）
        return _seal_bare_cot(raw_reply), label

    json_str = _extract_tool_json(raw_reply)
    if json_str:
        try:
            tool_call = json.loads(json_str)
            tool_name = tool_call.get("tool")
            tool_args = tool_call.get("args", {})

            if tool_name in TOOL_WHITELIST:
                # 🧠 思维链捕获：本轮有工具调用，最终 reply 统一在最前面包装
                # <think>推理文本</think>；模型没输出思考时按实际工具名动态
                # 生成占位符（解析不出工具名回退固定占位符）。
                # [CoT] 终端日志（各一处、简短）：便于部署侧一眼确认思维链
                # 到底走了"模型原生输出"还是"兜底占位符"注入。
                thinking = _capture_thinking(raw_reply)
                if thinking:
                    print("[CoT] 模型原生输出思考内容")
                else:
                    thinking = _tool_thinking_placeholder(tool_name)
                    print("[CoT] 已注入兜底占位符")
                try:
                    tool_result = execute_tool(tool_name, tool_args, permission_manager)
                except Exception as tool_err:
                    # 🛡️ 工具执行抛异常（依赖缺失/子进程崩溃等）同样按 ❌ 切断
                    # 口径返回：[CoT] 日志已打印，走下方 ❌ 硬拦截路径保证
                    # <think> 包装完整，绝不把裸 CoT 原文漏成普通回复
                    tool_result = f"❌ 工具执行异常: {tool_err}"
                print(f"📄 结果: {tool_result[:200]}...")

                # ⛔ 防死循环硬拦截：被拒（❌ 开头）的工具结果不再喂回模型重试，
                # 直接把拒绝文案作为本轮回答返回（单轮内切断）
                if tool_result.startswith("❌"):
                    # 🛡️ 跨轮熔断计数：同一工具 + 等价参数连续被拒 → 强制打断
                    tool_fuse.record_rejection(session_key, tool_name, tool_args)
                    if tool_fuse.is_tripped(session_key):
                        print("⛔ 防死循环熔断触发：连续多次同一操作被拒，已暂停工具使用。")
                        return _wrap_think(thinking, TOOL_FUSE_NOTICE), "⛔ 熔断"
                    # 🧠 裸 CoT 防御性封口：❌ 文案主体是工具层固定中文，但个别
                    # 工具（如 vision_tap_element 解析失败）会把模型原文拼进
                    # 返回串——剥净可能混入的裸标记再包装，绝不直出网页
                    return (_wrap_think(thinking, _strip_bare_cot(tool_result)),
                            "☁️ 云端 (工具)")

                # ✅ 成功执行会打断"连续被拒"计数
                tool_fuse.record_success(session_key)

                # 将工具结果喂回给模型，让它组织语言回答
                messages.append({"role": "assistant", "content": json_str})
                messages.append({"role": "system",
                                 "content": f"工具执行结果：{tool_result}\n\n请根据这个结果，用自然语言回答用户，绝对不要再输出 JSON！"})

                # 🏠 汇总轮（§10 #14 + 硬件自适应）：high 档本地优先，
                # medium/low 档固定走云端，来源标签如实标注
                tool_source = "☁️ 云端 (工具)"
                final_reply = ""
                if tier == "high" and local_online:
                    try:
                        final_reply = ask_local(messages, model=_local_model_for(tier))
                    except Exception as e:
                        print(f"⚠️ 本地汇总失败（{e}），自动转云端汇总...")
                if isinstance(final_reply, str) and final_reply.strip():
                    tool_source = "🏠 本地 (工具)"
                else:
                    try:
                        final_reply = ask_cloud(messages)
                    except Exception as e:
                        return _wrap_think(thinking, f"❌ 工具执行后汇总失败: {e}"), "❌ 失败"
                # 🧠 <think> 包装 + 汇总轮裸 CoT 封口（_seal_tool_summary）：
                # 先转表情再包推理块（新前端解析渲染折叠卡片；QQ 与旧版网页
                # 出口由 main.py 剥除）；统一走 _wrap_think 防游离标签
                #（thinking/body 两侧清洗 + 成对校验）。汇总轮模型复读的裸
                # [思考]/[计划]/[行动] 并入推理卡片，绝不随正文直出（用户
                # 实测"帮我点击蓝牙"回退分支漏点，2026-10-01 穷举封死）
                return _seal_tool_summary(thinking, final_reply), tool_source
            else:
                print(f"⚠️ 工具 {tool_name} 不在白名单内，已拒绝执行。")
        except Exception as e:
            print(f"⚠️ 工具解析失败，按普通回复处理: {e}")

    # 🧠 全对话强制包装：JSON 解析失败/工具不在白名单等旁路走到普通回复——
    # 捕获到原生 [思考]/[计划] 用原生思考包装；无任何标记的普通闲聊在
    # _seal_bare_cot 内注入默认占位符，前端必定渲染思维链卡片
    return _seal_bare_cot(raw_reply), label


# ==================== 表情包（§5，已接入回复链） ====================

def translate_emoji(reply):
    """[EMOJI:标签] → CQ 码图片消息。

    文档 §5 闭环口径：smart_ask 的正常文本回复（普通/总结/工具汇总）返回前
    统一调用本函数，使表情库配图随回复真正发出。表情库模块 emoji_manager
    由并行侧维护，这里函数内延迟导入，缺席时优雅降级（原样返回，
    不阻断回复链）；标签未命中时移除占位符，不留痕迹。
    """
    try:
        from emoji_manager import get_emoji_path
    except Exception:
        return reply
    for tag in re.findall(r'\[EMOJI:(.*?)\]', reply):
        emoji_path = get_emoji_path(tag)
        if emoji_path:
            reply = reply.replace(f"[EMOJI:{tag}]", f"[CQ:image,file=file://{emoji_path}]")
        else:
            reply = reply.replace(f"[EMOJI:{tag}]", "")
    return reply
