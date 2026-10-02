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
  <think>/</think> 字面量（推理模型原生标签是游离标签唯一来源）与上游注入
  的"（操作已执行）"占位符，拼装后
  再做成对校验（恰一对标签且在最前），杜绝 "</think>[思考]…" 直出网页
  （内容为捕获文本拼接；模型没输出任何思考时按实际解析出的工具名动态
  生成占位符"[思考] 准备调用 {工具名} 尝试完成操作."，解析不出工具名时
  回退 TOOL_THINKING_PLACEHOLDER 固定占位符）。_wrap_think 成对保证
  （2026-10-01 用户口径强化，修复"你好"网页直出纯文本 <think>）：空思考
  （None/空串/纯空白）注入 CHAT_THINKING_PLACEHOLDER 默认占位符；包装
  完成后按用户指定正则 re.search(r'<think>.*?</think>', final_text,
  re.DOTALL) 做最终门禁——不匹配强制从干净两侧重拼一次，重拼仍不匹配
  退化为剥离全部 think 标签的纯文本（宁可无标签也不出畸形）；模型自吐
  原生 <think> 包装的防重入透传一律先做成对校验，无闭合的开标签（截断
  输出）与空卡片剥净标签后重新包装。全对话强制包装（2026-10-01
  用户指令，显式废止旧"普通聊天零包装零干扰"口径）：系统指令（/clear、
  /coder_auth、/register 等）在 main.py 指令段先行处理并直接返回，不会
  进入 smart_ask——smart_ask 只接收自然语言对话，故凡经 smart_ask 的
  回复一律带 <think> 卡片：解析不出工具 JSON / 工具不在白名单等旁路普通
  回复、URL 总结与熔断退回纯文本路径统一经 _seal_bare_cot 出口——捕获到
  原生 [思考]/[计划] 用原生；出现任意一个裸协议标记（含全角变体）但无
  思考文本的残缺形态回退 TOOL_THINKING_PLACEHOLDER 占位思考（body 取剥离
  裸标记后的剩余正文，剥空由 _wrap_think 正文回补——真实回复从思考卡提升
  回正文——或以"操作已完成。"兜底，绝不允许正文成为"（操作已执行）"；
  body 已以 <think> 开头
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
- MAX_MESSAGES=50 滚动截断在保存侧 save_memory 生效（§4）；smart_ask 侧接线
  前情提要压缩（§10 #2，plugins/context_manager.compress_context）：送模型前
  历史 >20 条 → 旧消息浓缩为约 50 字前情提要（【前情提要】system 条目）+
  最近 10 条明细，替换"长历史原样直送"的硬截断口径；压缩结果按（会话通道
  session_key + 旧消息段指纹）持久化到 agent_state/context_summary.json，
  命中直接复用、历史变化自动失效重压；compress_context 双脑不可用/异常/
  降级摘要 → 回退既有硬截断口径绝不崩溃；缓存文件损坏按无缓存重压。
- 长期记忆接线（§10 #3，agent_state/state_manager.py 的 SQLite long_term.db）：
  smart_ask 入口按关键词规则（我喜欢/我讨厌/我偏好/请记住/记住…）提取关键句
  → save_memory（preference/event）；构造消息时 get_recent_memories(limit=5)
  非空 → 以"以下是关于用户的长期记忆…"系统上下文注入（与 main.py 先行注入
  同前缀，历史已带该条目时不重复注入）；SQLite 损坏/读写异常静默跳过。
- translate_emoji（[EMOJI:标签] → CQ 码图片）已接入回复链（§5 闭环口径）：
  smart_ask 的正常文本回复（普通/总结/工具汇总）返回前统一转换；本地库命中
  → CQ 图片码；未命中 → emoji_manager 用收藏链接兜底下载（assets/emoji/，
  文件名=标签+URL 哈希、扩展名按 Content-Type 推断）；下载仍失败/模块缺席/
  链路异常 → 统一降级纯文本"[表情: 标签]"，绝不崩溃、绝不再返回未转换的
  [EMOJI: 原文；收图自动存链接链路保持不变。
"""
import hashlib
import json
import logging
import os
import re
import socket

import requests
import requests.packages.urllib3.util.connection as urllib3_cn

import xiaoju3
from xiaoju3 import (AGENT_STATE_DIR, CLOUD_KEY, CLOUD_URL, CLOUD_MODEL,
                     MAX_MESSAGES, LOCAL_URL, LOCAL_MODEL, LOCAL_MODEL_SMALL,
                     LOCAL_PROBE_URL, LOCAL_TIMEOUT, USER_CITY, USER_DISTRICT)
from permission import permission_manager
from prompts import SYSTEM_PROMPT
from tools import execute_tool

# 模块日志器：WRAPPED_TEXT 诊断日志走 DEBUG 级别（2026-10-02 用户口径降噪——
# 默认终端不再输出；排查时 logging.getLogger("xiaoju3.brain").setLevel(
# logging.DEBUG) 即可恢复逐条对账）
_LOG = logging.getLogger("xiaoju3.brain")


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

# 裸 CoT 正文剥空占位（历史封口口径，与前端契约字面量一致）：_seal_bare_cot /
# _seal_tool_summary 在 body 剥空时仍注入该占位，但 2026-10-01 用户口径起
# _wrap_think 两侧清洗会把它彻底剥除——绝不允许它顶替真实正文出现在最终产出
# （真实回复从思考卡回补回正文，或以 DEFAULT_BODY_PLACEHOLDER 兜底）。常量
# 保留供其他处引用与跨端字面量锁定测试。
BARE_COT_BODY_PLACEHOLDER = "（操作已执行）"

# 正文双空兜底（2026-10-01 用户口径第三条）：body 与 thinking 清洗后都为空时
# 的简短正文，取代"（操作已执行）"的正文兜底角色
DEFAULT_BODY_PLACEHOLDER = "操作已完成。"

# 回复出口去重（2026-10-02 用户口径，修复本地模型复读）：思考与正文完全相同
# 收敛为"占位卡 + 正文一份"、正文句级连续重复塌缩；句级去重后正文为空时的
# 正文占位符（用户口径示例文案）
DEDUPE_BODY_PLACEHOLDER = "我在呢～"


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

# 最终成对门禁（2026-10-01 用户指定口径）：包装完成后对最终文本 re.search
# 一对完整的 <think>...</think>（DOTALL、不锚定行首的"存在性"判定）——
# 不匹配则强制重拼一次，重拼仍不匹配退化为纯文本（宁可无标签不出畸形）
_THINK_HAS_PAIR_RE = re.compile(r'<think>.*?</think>', re.DOTALL)


def _strip_think_tags(text):
    """剥除文本中全部 <think>/</think> 标签字面量（文本内容保留）。"""
    return _THINK_TAG_RE.sub("", text)


# 上游封口占位符字面量（含前后空白变体）——_wrap_think 两侧清洗一并剥除
# （2026-10-01 用户口径第一条：绝不允许"（操作已执行）"顶替真实正文直出）
_BODY_PLACEHOLDER_RE = re.compile(
    r'\s*' + re.escape(BARE_COT_BODY_PLACEHOLDER) + r'\s*')

# [思考] 标记前缀（正文回补用）：与 _THINK_RE 头部同口径（含全角【】与
# "思考："写法）
_THINK_MARKER_PREFIX_RE = re.compile(r'^\s*[\[【]思考[\]】][:：]?\s*')

# 动态工具占位思考形态（_tool_thinking_placeholder 生成）——注入型占位
# 不参与正文回补
_DYNAMIC_TOOL_THINKING_RE = re.compile(r'^\[思考\] 准备调用 .+? 尝试完成操作。$')


def _strip_body_placeholder(text):
    """剥除文本中全部"（操作已执行）"占位符（含前后空白）。"""
    return _BODY_PLACEHOLDER_RE.sub("", text)


def _is_placeholder_thinking(thinking_text):
    """思考侧是否为注入型占位符（闲聊默认 / 工具固定 / 动态工具名）。

    注入型占位不是模型的真实输出，正文剥空时不参与正文回补（否则占位文案
    会被复制进正文，产生"正在理解你的意图..."正文之类的怪异输出）。
    """
    t = thinking_text.strip()
    return (t == CHAT_THINKING_PLACEHOLDER
            or t == TOOL_THINKING_PLACEHOLDER
            or bool(_DYNAMIC_TOOL_THINKING_RE.match(t)))


def _wrap_think(thinking, body):
    """统一 <think> 包装点：smart_ask 全部文本回复一律经此拼装（消灭手写拼接）。

    产出 f"<think>{thinking}</think>{body}"，六重保证（2026-10-01 用户口径
    两轮强化：绝不允许空 <think>、残缺/游离标签或"（操作已执行）"顶替真实
    正文直出网页）：
    1. 两侧彻底清洗：thinking/body 的 <think>/</think> 标签字面量与上游注入
       的"（操作已执行）"占位符（含前后空白变体）一律剥除（文本内容保留）；
    2. 双空兜底：两侧清洗后都为空 → thinking 注入 CHAT_THINKING_PLACEHOLDER、
       body 注入"操作已完成。"（绝不允许正文成为"（操作已执行）"）；
    3. 空思考兜底：仅 thinking 为 None/空串/纯空白 → 注入
       CHAT_THINKING_PLACEHOLDER 默认占位符，绝不产出空 <think></think>；
    4. 正文回补（实测缺陷修复："（操作已执行）"顶替真实回复）：仅 body 剥空
       而 thinking 含真实内容时，把剥除 [思考] 前缀后的内容提升为正文——原
       真实回复回到正文，思考卡同时保留（产出
       "<think>[思考] ...真实回复...</think>真实回复"形态）。注入型占位思考
       不回补：闲聊占位保持"只有卡片"输出（孤标签修复形态零回退），工具占位
       与含裸标记的多段思考以"操作已完成。"兜底——[计划] 等裸标记绝不借回补
       漏进正文；
    5. 成对规整 + 最终门禁：拼装结果只保留开头 <think> 与其第一个 </think>，
       其余一切游离标签一律剥除；再按用户指定正则
       re.search(r'<think>.*?</think>', final_text, re.DOTALL) 校验，不匹配
       → 从干净的 thinking + body 强制重拼一次；重拼后仍不匹配 → 退化为剥离
       全部 think 标签的纯文本（宁可无标签也不出畸形）；
    6. 出口去重（2026-10-02 用户口径，修复本地模型复读）：思考与正文完全
       相同收敛为"占位卡+正文一份"、正文开头自说自话句剥离、正文句级
       连续重复塌缩、剥空以 DEDUPE_BODY_PLACEHOLDER 兜底（详见
       _dedupe_reply）。
    纯函数：同等输入必有同等输出，可直接单测；None 输入按空串处理。

    出口形态实测口径（2026-10-01，排查"你好"网页只显示纯文本无思维链卡片，
    python 实测结论，固化在 tests/test_brain.py WebExitThinkTagContractTests）：
    本函数最终产出中 <think> 标签完好成对且紧贴正文，两条下发通道各自表现——
    - 仪表盘 /api/chat（直连 smart_ask，返回前过 web_sanitize.sanitize_for_web）：
      sanitize_for_web 只净化 CQ 码（face→Emoji / image→[表情] / 其余剥除），
      实测 <think>/</think> 标签原样存活（思考内混 CQ 码时标签同样完好），
      前端拿到的文本可直接渲染推理卡片；
    - QQ 与旧版网页（main.py _strip_think：
      re.sub(r'<think>.*?</think>', '', DOTALL) 后 strip）：设计上即整块剥除
      思维链（含标签本体），QQ/旧页拿到纯文本正文——这是通道口径差异，
      不是标签丢失。
    结论：若网页只见纯正文无卡片，可排除"后端输出标签被剥"（本函数日志
    WRAPPED_TEXT 即可对账后端实际下发形态），嫌疑收敛在前端渲染分支
    （console.js）或该回复走了剥标出口（QQ/旧页）。
    """
    # ① 两侧彻底清洗：标签字面量 + 上游注入的"（操作已执行）"占位符
    thinking_text = _strip_body_placeholder(
        _strip_think_tags("" if thinking is None else str(thinking)))
    body_text = _strip_body_placeholder(
        _strip_think_tags("" if body is None else str(body)))
    thinking_blank = not thinking_text.strip()
    body_blank = not body_text.strip()
    if thinking_blank and body_blank:
        # ② 双空兜底：默认占位思考 + 简短正文（绝不允许正文成为"（操作已执行）"）
        thinking_text = CHAT_THINKING_PLACEHOLDER
        body_text = DEFAULT_BODY_PLACEHOLDER
    elif thinking_blank:
        # ③ 空思考兜底：只补思考占位符，正文保持调用方原样
        thinking_text = CHAT_THINKING_PLACEHOLDER
    elif body_blank:
        # ④ 正文回补：真实内容被埋进思考卡、正文剥空时提升回正文
        promoted = ""
        if not _is_placeholder_thinking(thinking_text):
            candidate = _THINK_MARKER_PREFIX_RE.sub("", thinking_text)
            if candidate.strip() and not _BARE_COT_MARK_RE.search(candidate):
                promoted = candidate
        if promoted:
            body_text = promoted
        elif thinking_text.strip() != CHAT_THINKING_PLACEHOLDER:
            # 不可回补（工具占位思考 / 多段思考含裸标记）→ 简短正文兜底
            body_text = DEFAULT_BODY_PLACEHOLDER
        # thinking 恰为闲聊占位符（孤标签修复形态）→ 保持"只有卡片"输出
    reply = f"<think>{thinking_text}</think>{body_text}"
    pair = _THINK_PAIR_RE.match(reply)
    if pair is not None:
        # 只保留开头 <think> 与其第一个 </think>，其余一切游离标签一律剥除
        reply = ("<think>" + _strip_think_tags(pair.group(1)) + "</think>"
                 + _strip_think_tags(reply[pair.end():]))
    # 最终门禁（用户指定校验）：搜不到成对标签 → 从干净两侧强制重拼一次
    if not _THINK_HAS_PAIR_RE.search(reply):
        reply = f"<think>{thinking_text}</think>{body_text}"
    if not _THINK_HAS_PAIR_RE.search(reply):
        # 重拼仍不成对：退化为剥离全部 think 标签的纯文本（宁可无标签）
        reply = _strip_think_tags(f"{thinking_text}\n{body_text}").strip()
    # ⑥ 出口去重（2026-10-02 用户口径，修复本地模型复读）：思考与正文完全
    # 相同收敛为"占位卡+正文一份"、正文开头自说自话句剥离、正文句级连续
    # 重复塌缩、剥空占位兜底（详见 _dedupe_reply；零改动时逐字节原样返回）
    reply = _dedupe_reply(reply)
    # 输出诊断日志（2026-10-01 用户口径；2026-10-02 降噪改 DEBUG 级别——
    # 默认终端不再输出，排查时对 "xiaoju3.brain" logger 开 DEBUG 即恢复）：
    # 放在所有清洗/校验/重拼/去重之后、最终 return 之前，记录的即后端实际
    # 下发给前端的最终产出（每条 reply 一行、超 300 字符截断加 "..." 防刷屏）。
    # 部署侧据此直接确认 <think> 标签是否成对出现且紧贴正文。
    _LOG.debug("WRAPPED_TEXT: %s",
               reply[:300] + ("..." if len(reply) > 300 else ""))
    return reply


# ==================== 回复出口去重（2026-10-02 用户口径，修复复读） ====================

# 句级连续重复塌缩正则：捕获"内容 + 句末标点"单元（单元内句末标点可有连跑，
# 如"？？"、"……"），其后的"粘连段 + 空白 + 完全相同单元"重复 2 次及以上
# 塌缩为一份。句末标点集：中英句号/问号/感叹号、分号、省略号、波浪号与换行
# （"等标点"口径）；不含 ASCII 句点——保护小数与代码片段不被切句。粘连段
# 限长 4 字且不含文字/数字/空白/句末标点（emoji、装饰符号等收尾表情）——
# 用户实测例句"我在呢，在呢，有啥需要帮忙的吗？😊"连发两遍（表情隔在两次
# 重复之间）据此塌缩；文字/数字不能作粘连段，防止跨句误并。
_SENT_RUN_RE = re.compile(
    r'([^。！？!?；;\n…～~]+[。！？!?；;\n…～~]+)'
    r'(?:[^\w\s。！？!?；;\n…～~]{0,4}\s*\1)+')


def _collapse_duplicate_sentences(text):
    """正文句级连续去重：同一句话（句末标点切分）连续重复 2 次及以上只留一份。

    纯函数：无连续重复的文本逐字节原样返回（零回归保证）；只处理"连续"
    重复——间隔出现的重复句（A…B…A…B）是有意修辞，不塌缩。
    """
    if not text:
        return text
    return _SENT_RUN_RE.sub(r'\1', text)


# 自说自话句式（2026-10-02 用户口径，QQ 实测模型把心路历程写进正文：
# "又是呼唤我，看来他挺关心我！这次我直接回应，别再问了！在呢在呢..."）。
# 仅匹配句首——正文中部出现同字样（如转述用户原话）不误伤；"他在"这类
# 过宽模式不收（故事型回复开头误伤风险）。
_SELF_TALK_RE = re.compile(
    r'^(?:又是|这次我|看来他|看来她|看来主人|他问我|他挺|主人又在|主人这是'
    r'|既然主人|既然他)')

# 句子切分（自说自话剥离用）：内容 + 句末标点（可有连跑）；收尾无标点的
# 碎片（emoji/尾句）一并成句。findall 全覆盖原文本，"".join 可原样还原。
_SENTENCE_SPLIT_RE = re.compile(r'[^。！？!?；;\n…～~]+[。！？!?；;\n…～~]*')


def _strip_self_talk(body):
    """剥离正文开头的"自说自话"句（心路历程/第三人称指代用户），保留实际回复。

    用户口径（2026-10-02）：正文以"又是/这次我/看来他/他问我/他挺"等句式
    开头的句子是模型内心独白漏出，剥离后只留对用户说的话；按句切分后从
    首句起连续剥离命中句。保守边界：
    - 至少保留一句——全部句子命中（无法区分回复）时原样返回，绝不把真
      回复剥没；
    - 无命中原样返回（逐字节零回归）；只剥开头连续段，正文中部的同字样
      不动。
    纯函数 + 异常安全。
    """
    if not body:
        return body
    try:
        sentences = _SENTENCE_SPLIT_RE.findall(body)
        idx = 0
        while idx < len(sentences) and _SELF_TALK_RE.match(sentences[idx].strip()):
            idx += 1
        if idx == 0 or idx >= len(sentences):
            return body   # 无自说自话 / 全部命中（保守原样）
        return "".join(sentences[idx:])
    except Exception as e:
        print(f"⚠️ 自说自话剥离异常（原样返回）: {e}")
        return body


def _dedupe_reply(reply):
    """回复出口去重（_wrap_think 产出与 _seal_bare_cot 防重入透传统一收口）。

    用户口径（2026-10-02，修复本地模型 qwen2.5:7b 复读）：
    1. <think> 块内文本与正文完全相同（去空白比较）→ 思考卡降级为
       CHAT_THINKING_PLACEHOLDER 默认占位符，正文保留一份真实回复——修复
       "正文和 <think> 块内的内容完全相同"在网页上显示两遍的问题；比较保留
       "[思考] "标记前缀差异，_wrap_think 正文回补设计的
       "<think>[思考] X</think>X"形态（思考含标记、不含标记的正文）不命中，
       零回退；
    2. 自说自话剥离：正文开头连续的"又是/这次我/看来他/他问我/他挺"等
       心路历程句剥离，只留对用户说的话（见 _strip_self_talk）；
    3. 正文句级连续重复（同一句 2 次及以上）塌缩为一份（见
       _collapse_duplicate_sentences）；
    4. 去重确实发生（有内容被塌缩/收敛/剥离）且正文被剥空 → 注入
       DEDUPE_BODY_PLACEHOLDER（"我在呢～"）占位；输入本就空正文的
       "只有卡片"孤标签修复形态（_wrap_think ④ 既有设计）保持原样零回退。
    纯函数 + 异常安全：任何环节异常原样返回输入，绝不影响回复下发。
    """
    text = "" if reply is None else str(reply)
    try:
        stripped = text.lstrip()
        m = _THINK_PAIR_RE.match(stripped)
        if m is None:
            # 退化形态（无成对 think 前缀的纯文本）：自说自话剥离 + 句级去重
            new_text = _strip_self_talk(text)
            new_text = _collapse_duplicate_sentences(new_text)
            if new_text != text and not new_text.strip():
                new_text = DEDUPE_BODY_PLACEHOLDER
            return new_text
        body = stripped[m.end():]
        think_inner = m.group(1)
        changed = False
        # ① 思考与正文完全相同（去空白比较）→ 思考卡降级默认占位符
        if body.strip() and re.sub(r'\s+', '', think_inner) == re.sub(r'\s+', '', body):
            think_inner = CHAT_THINKING_PLACEHOLDER
            changed = True
        # ② 自说自话剥离（QQ 实测模型把心路历程写进正文）
        new_body = _strip_self_talk(body)
        if new_body != body:
            changed = True
        # ③ 正文句级连续去重
        body = new_body
        new_body = _collapse_duplicate_sentences(body)
        if new_body != body:
            changed = True
        # ④ 仅当去重确实发生且正文被剥空才注入占位（输入本就空正文的
        #    "只有卡片"形态保持原样）
        if changed and not new_body.strip():
            new_body = DEDUPE_BODY_PLACEHOLDER
            changed = True
        if not changed:
            return text   # 零改动：原样返回（逐字节不变，零回归）
        return text[:len(text) - len(stripped)] \
            + f"<think>{think_inner}</think>{new_body}"
    except Exception as e:
        print(f"⚠️ 回复去重异常（原样返回）: {e}")
        return text


# ==================== 搜索指代消解（2026-10-02 用户口径） ====================

# 地点敏感的搜索意图关键词（天气/新闻/交通/本地服务类）——裸词（如"今天
# 天气"）交给搜索引擎会被随机定位（用户实测：问天气返回了杭州余杭，实际
# 在长沙天心）
LOCATION_SENSITIVE_KEYWORDS = (
    "天气", "气温", "气候", "下雨", "降雨", "下雪", "降雪", "温度", "多少度",
    "新闻", "资讯", "要闻", "交通", "路况", "限行", "地铁", "公交",
    "附近", "周边", "本地", "美食", "外卖",
)

# 常见地点词表（省级短名 + 直辖市/主要城市，轻量口径）：命中即认为 query
# 已含地点、不再改写；自定义中小城市由 USER_CITY/USER_DISTRICT 配置兜底
_KNOWN_LOCATIONS = (
    "北京", "上海", "天津", "重庆",
    "河北", "山西", "辽宁", "吉林", "黑龙江", "江苏", "浙江", "安徽", "福建",
    "江西", "山东", "河南", "湖北", "湖南", "广东", "海南", "四川", "贵州",
    "云南", "陕西", "甘肃", "青海", "台湾", "内蒙古", "广西", "西藏", "宁夏",
    "新疆", "香港", "澳门",
    "广州", "深圳", "杭州", "南京", "苏州", "武汉", "成都", "西安", "长沙",
    "郑州", "济南", "青岛", "合肥", "福州", "厦门", "南昌", "哈尔滨", "长春",
    "沈阳", "大连", "昆明", "贵阳", "南宁", "海口", "太原", "石家庄", "兰州",
    "西宁", "银川", "呼和浩特", "乌鲁木齐", "拉萨",
)

# 带行政区划后缀的未知地名（"株洲市""湖南省"等，词表外形态）
_ADMIN_SUFFIX_RE = re.compile(r'[\u4e00-\u9fa5]{1,6}(?:省|市|自治区|自治州)')


def _inject_location(query):
    """搜索指代消解：地点敏感类 query 不含地点时补全配置位置。

    用户口径（2026-10-02）：query="今天天气"（USER_CITY=长沙、
    USER_DISTRICT=天心区）→ "长沙天心区今天天气"；只配城市 →
    "长沙今天天气"。不改写的情形：
    - query 已含地点（词表命中 / 带省市后缀 / 含配置的 USER_CITY 或
      USER_DISTRICT——用户说的地点优先，且避免二次叠加）；
    - 非地点敏感类 query（如"如何写Python"）；
    - 位置未配置（USER_CITY 与 USER_DISTRICT 均为空）。
    纯函数 + 异常安全（任何异常原样返回）。
    """
    try:
        q = "" if query is None else str(query)
        if not q.strip():
            return q
        if not any(k in q for k in LOCATION_SENSITIVE_KEYWORDS):
            return q
        if (USER_CITY and USER_CITY in q) or (USER_DISTRICT and USER_DISTRICT in q):
            return q
        if any(loc in q for loc in _KNOWN_LOCATIONS):
            return q
        if _ADMIN_SUFFIX_RE.search(q):
            return q
        location = (str(USER_CITY) + str(USER_DISTRICT)).strip()
        if not location:
            return q
        return location + q
    except Exception as e:
        print(f"⚠️ 搜索指代消解异常（原样返回）: {e}")
        return query


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
    - body 取 _strip_bare_cot 剥离裸标记后的剩余正文，剥空时按历史口径注入
      BARE_COT_BODY_PLACEHOLDER 占位（"宁可隐藏"）——该占位符随后的
      _wrap_think 两侧清洗会剥除：真实回复从思考卡回补回正文，或以
      "操作已完成。"兜底，绝不出现在最终产出；body 已以 <think> 开头
      （模型自包/上游已包）时防重入不再二次包装——但透传前必须成对校验
      （2026-10-01 实测修复：模型自吐无闭合的开标签 <think>，旧代码原样
      透传直出网页，表现为页面显示纯文本 <think>；现成对完整才透传，
      残缺形态剥净标签字面量后按占位思考重新包装，空 <think> 同样不允许）；
    - 封口/注入时各打印一条 [CoT] 终端日志，与工具路径日志口径一致。
    """
    if not _BARE_COT_MARK_RE.search(raw_reply):
        # 普通闲聊：强制注入默认占位符（模型自吐 <think> 原生包装时防重入
        # ——成对且思考非空才原样透传，残缺/空卡片剥净标签后重新包装）
        text = translate_emoji(raw_reply)
        pair = _THINK_PAIR_RE.match(text.lstrip())
        if pair and pair.group(1).strip():
            # 防重入透传（模型自吐完整包装）：出口去重统一收口——模型把
            # 回复原文同时塞进 <think> 和正文（think==body，本地模型复读
            # 实测形态）在此收敛为"占位卡+正文一份"
            return _dedupe_reply(text)
        if pair:
            # 成对但思考为空白（qwen3 非思考形态 <think>\n\n</think>）：
            # 空卡片同样不允许——剥净标签并去掉标签间残留空白后重新包装
            return _force_chat_think(_strip_think_tags(text).strip())
        return _force_chat_think(_strip_think_tags(text))
    print("[CoT] 模型原生输出思考内容")
    thinking = _capture_thinking(raw_reply)
    body = _strip_bare_cot(raw_reply)
    if not thinking:
        # 只有 [行动] 没有思考文本（残缺形态）：思考占位兜底，绝不裸漏
        thinking = TOOL_THINKING_PLACEHOLDER
    if body.startswith("<think>"):
        # 防重入：正文已是 <think> 包装形态——成对且思考非空（模型自包
        # 完整）剥净裸标记后原样透传；残缺（无闭合标签，截断输出）剥掉
        # 标签字面量按捕获思考重新包装，绝不直出畸形 <think>
        pair = _THINK_PAIR_RE.match(body)
        if pair and pair.group(1).strip():
            return _dedupe_reply(translate_emoji(body))
        body = _strip_think_tags(body).lstrip()
    if not body:
        # 历史口径剥空占位：占位符由 _wrap_think 清洗剥除（真实回复回补回
        # 正文，或以"操作已完成。"兜底），绝不出现在最终产出
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
      占位（"宁可隐藏"；占位符由 _wrap_think 清洗剥除——真实回复回补回
      正文或以"操作已完成。"兜底），并打印 [CoT] 终端日志与首轮口径一致。
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
        # 历史口径剥空占位：占位符由 _wrap_think 清洗剥除（真实回复回补回
        # 正文，或以"操作已完成。"兜底），绝不出现在最终产出
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


# ==================== 前情提要压缩接线（§4 / plugins/context_manager） ====================

# 压缩触发阈值 / 压缩时保留的最近明细条数（与 plugins.context_manager.
# compress_context 的 max_messages / keep_recent 契约一致）
COMPRESS_THRESHOLD = 20
COMPRESS_KEEP_RECENT = 10

# 压缩缓存落盘路径（agent_state 隔离区运行数据）：键 = 会话通道
# （session_key），值 = {fingerprint: 旧消息段指纹, summary: 前情提要}。
# 读取失败 / 文件损坏 → 视为无缓存重新压缩；写入失败静默跳过，绝不崩溃。
CONTEXT_SUMMARY_FILE = os.path.join(AGENT_STATE_DIR, "context_summary.json")

# 压缩降级判定标记（与 main._compress_and_save 同口径）：compress_context 在
# 双脑不可用时不抛异常而是返回降级摘要——摘要含这些字样按"压缩失败"处理，
# 回退既有硬截断口径（消息原样直送，保存侧 MAX_MESSAGES=50 截断继续兜底）
_COMPRESS_FAILED_MARKS = ("由于系统原因", "⚠️")

# 前情提要 system 条目固定前缀（与 compress_context / _build_messages 白名单
# / main.py 落盘口径完全一致，保证随历史回灌时不被剔丢）
_SUMMARY_PREFIX = "【前情提要】"


def _history_fingerprint(old_messages):
    """被压缩旧消息段的指纹：内容变化（新增/修改消息）→ 指纹变化 → 缓存失效。"""
    text = "\n".join(f"{m.get('role', '')}:{m.get('content', '')}"
                     for m in old_messages if isinstance(m, dict))
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _load_summary_cache():
    """读压缩缓存；文件缺失 / 损坏 / 读失败一律视为无缓存（返回空字典）。"""
    try:
        with open(CONTEXT_SUMMARY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_summary_cache(cache):
    """压缩缓存落盘；写失败静默跳过（缓存缺失只影响效率，不影响正确性）。"""
    try:
        dirpath = os.path.dirname(CONTEXT_SUMMARY_FILE)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        with open(CONTEXT_SUMMARY_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _compress_history(messages, session_key="default"):
    """前情提要压缩接线（§10 #2）：历史 >20 条 → 旧消息浓缩为约 50 字
    前情提要（【前情提要】system 条目）+ 最近 10 条明细，替换"长历史原样
    直送"的硬截断口径。

    - 压缩结果按 (session_key, 旧消息段指纹) 持久化缓存：指纹相同直接复用
      （避免每轮重复压缩），历史变化（新增消息使指纹变化）自动失效重压；
    - compress_context 抛异常 / 返回降级摘要（双脑不可用）→ 回退既有硬截断
      口径（消息原样直送），绝不崩溃；
    - 历史不足阈值 / 插件缺席 → 原样返回，零额外开销。
    """
    if len(messages) <= COMPRESS_THRESHOLD:
        return messages
    old_segment = messages[1:-COMPRESS_KEEP_RECENT]
    if not old_segment:
        return messages
    fingerprint = _history_fingerprint(old_segment)
    cache = _load_summary_cache()
    entry = cache.get(session_key)
    if (isinstance(entry, dict) and entry.get("fingerprint") == fingerprint
            and isinstance(entry.get("summary"), str)
            and entry["summary"].strip()):
        summary = entry["summary"]
        print(f"🧠 命中前情提要缓存（{session_key}），跳过重复压缩")
    else:
        try:
            from plugins.context_manager import compress_context
            compressed = compress_context(list(messages),
                                          max_messages=COMPRESS_THRESHOLD,
                                          keep_recent=COMPRESS_KEEP_RECENT)
        except Exception as e:
            print(f"⚠️ 前情提要压缩失败，回退既有截断口径: {e}")
            return messages
        summary = ""
        if isinstance(compressed, list):
            for m in compressed:
                if (isinstance(m, dict) and m.get("role") == "system"
                        and str(m.get("content", "")).startswith(_SUMMARY_PREFIX)):
                    summary = str(m["content"])
                    break
        if (not summary.strip()
                or any(mark in summary for mark in _COMPRESS_FAILED_MARKS)):
            # 双脑不可用的降级摘要按失败处理：回退既有硬截断口径，不落缓存
            print("⚠️ 前情提要生成失败（双脑不可用），本轮回退既有截断口径。")
            return messages
        cache[session_key] = {"fingerprint": fingerprint, "summary": summary}
        _save_summary_cache(cache)
        print(f"🧠 前情提要已生成并缓存（{session_key}）：{summary[:60]}")
    # 压缩形态：置顶系统提示词 + 前情提要 system 条目 + 最近明细
    return ([messages[0], {"role": "system", "content": summary}]
            + messages[-COMPRESS_KEEP_RECENT:])


# ------------------------------ 长期记忆接线（§10 #3） ------------------------------

# 关键词规则提取（最稳定口径，与 main.py 的"记住"指令分支互补——该分支在
# 指令段先行拦截并直接回复，消息不会进入 smart_ask，故两侧不会重复落库）：
# - 偏好声明（句首 我喜欢/我不喜欢/我讨厌/我偏好/我偏爱）→ category=preference
# - 记忆嘱托（记住…/请记住…/帮我记住…，冒号标点可省、后面须有内容）→ event
_MEMORY_PREFERENCE_RE = re.compile(
    r'^\s*(?:小橘[3号，,]?\s*)?(我不?喜欢|我讨厌|我偏好|我偏爱)')
_MEMORY_REMEMBER_RE = re.compile(r'(?:请|帮我|麻烦你|麻烦|你)?记住[:：,，、]?\s*\S')
_MEMORY_SENTENCE_SPLIT_RE = re.compile(r'[。！？!?；;\n]+')

# 回答前注入的记忆条数与系统上下文前缀（前缀与 _build_messages 白名单、
# main._inject_long_term_memories 完全一致，保证随历史回灌时不被剔丢）
MEMORY_CONTEXT_LIMIT = 5
MEMORY_CONTEXT_PREFIX = "以下是关于用户的长期记忆"


def _get_state_manager():
    """延迟获取状态外置层单例；模块缺席（ImportError 等）返回 None 不崩溃。"""
    try:
        from agent_state.state_manager import state_manager
        return state_manager
    except Exception:
        return None


def _extract_memory_sentence(message):
    """按句切分用户消息，返回首个命中关键词规则的句子；无命中返回 None。"""
    for sentence in _MEMORY_SENTENCE_SPLIT_RE.split(message or ""):
        text = sentence.strip()
        if not text:
            continue
        if _MEMORY_PREFERENCE_RE.search(text) or _MEMORY_REMEMBER_RE.search(text):
            return text
    return None


def _remember_user_facts(message):
    """长期记忆关键词提取落库：命中规则 → state_manager.save_memory。

    SQLite 损坏 / 读写异常一律静默跳过（不抛出、不崩溃、不阻断对话）；
    状态外置层模块缺席同样静默跳过。
    """
    sentence = _extract_memory_sentence(message)
    if not sentence:
        return
    manager = _get_state_manager()
    if manager is None:
        return
    category = ("preference" if _MEMORY_PREFERENCE_RE.search(sentence)
                else "event")
    try:
        manager.save_memory(category, sentence)
    except Exception as e:
        print(f"⚠️ 长期记忆保存失败（已静默跳过）: {e}")


def _inject_memory_context(messages, limit=MEMORY_CONTEXT_LIMIT):
    """回答前长期记忆注入（§10 #3）：get_recent_memories(limit) 非空 → 以
    "以下是关于用户的长期记忆…"系统上下文插到置顶提示词（及其后的前情提要）
    之后。

    - 历史里已带同前缀条目（main 链路先行注入口径）时不重复注入；
    - SQLite 损坏 / 读取异常 / 记忆为空 → 原样返回，静默跳过不崩溃。
    """
    for m in messages:
        if (isinstance(m, dict) and m.get("role") == "system"
                and str(m.get("content", "")).startswith(MEMORY_CONTEXT_PREFIX)):
            return messages
    manager = _get_state_manager()
    if manager is None:
        return messages
    try:
        rows = manager.get_recent_memories(limit=limit) or []
        lines = "\n".join(f"· [{category}] {content}"
                          for category, content in rows)
    except Exception as e:
        print(f"⚠️ 长期记忆读取失败（已静默跳过）: {e}")
        return messages
    if not lines.strip():
        return messages
    block = {"role": "system",
             "content": MEMORY_CONTEXT_PREFIX + "，回答时可以参考：\n" + lines}
    insert_at = 1
    if (len(messages) > 1 and isinstance(messages[1], dict)
            and str(messages[1].get("content", "")).startswith(_SUMMARY_PREFIX)):
        insert_at = 2  # 前情提要在前，长期记忆紧随其后
    messages.insert(insert_at, block)
    return messages


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


# ==================== 历史轻量清洗（2026-10-02 用户口径，防复读输入） ====================

# 连续相同用户消息收敛阈值：≥3 条才收敛为 1 条（偶发 2 条重复保留，
# 避免误伤用户有意的补充强调）
REPEAT_USER_HISTORY_LIMIT = 3


def _collapse_repeated_user_history(history):
    """历史清洗：连续相同用户消息 ≥REPEAT_USER_HISTORY_LIMIT 条只保留首条。

    用户口径（2026-10-02，修复本地模型被连发重复输入带偏复读）：QQ 里
    "@小橘3号 在吗" 连发多条时，历史里逐条喂给模型会把模型带偏（回复
    同一句话复读）。"连续"指用户消息序列中相邻——中间可夹助手回复
    （连发场景每条之间实际都有回复，严格相邻则规则永不命中）；"完全
    相同"按去首尾空白比较。只剔除多余副本，绝不改动消息内容与顺序；
    历史不足阈值直接原样返回；异常安全（任何异常回退原始历史，绝不
    影响对话主链路）。
    """
    try:
        msgs = list(history or [])
        if len(msgs) < REPEAT_USER_HISTORY_LIMIT:
            return msgs
        user_idx = [i for i, m in enumerate(msgs)
                    if isinstance(m, dict) and m.get("role") == "user"]
        if len(user_idx) < REPEAT_USER_HISTORY_LIMIT:
            return msgs
        drop = set()
        run_start = 0
        for k in range(1, len(user_idx) + 1):
            if (k < len(user_idx)
                    and str(msgs[user_idx[k]].get("content") or "").strip()
                    == str(msgs[user_idx[run_start]].get("content") or "").strip()):
                continue
            # 运行中断（或扫尾）：本次运行长度达阈值 → 只保留首条
            if k - run_start >= REPEAT_USER_HISTORY_LIMIT:
                drop.update(user_idx[run_start + 1:k])
            run_start = k
        if not drop:
            return msgs
        return [m for i, m in enumerate(msgs) if i not in drop]
    except Exception as e:
        print(f"⚠️ 历史去重异常（原样返回）: {e}")
        return list(history or [])


def _build_messages(message, history):
    """组装模型消息：system 提示词置顶 + 历史 + 本条用户消息。

    - history 中的 system 消息一律剔除，保证全列表只有置顶这一条系统提示词；
      例外：主链路注入的【前情提要】、长期记忆与最近设备操作记录上下文
      （架构 §10 #2/#3 接线）以特定前缀标识，允许通过并在去掉前缀后保留；
    - 兼容参考实现口径：调用方可能已把本条用户消息追加进 history 再调用
      （参考 main.py 先 append 再调 smart_ask），此时去重，避免重复；
    - 历史轻量清洗（2026-10-02 用户口径）：连续相同用户消息 ≥3 条只保留
      首条（_collapse_repeated_user_history），防止模型被连发输入带偏复读；
    - 返回新列表，不修改调用方传入的 history。
    """
    messages = [SYSTEM_PROMPT]
    for m in _collapse_repeated_user_history(history):
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

    # 🧠 长期记忆关键词提取（§10 #3）：命中"我喜欢/请记住…"等规则先落库，
    # SQLite 异常静默跳过，绝不影响本轮对话
    _remember_user_facts(message)

    # === 第一步：如果用户输入里有 URL，先抓网页正文（剔除 script/style） ===
    url_match = re.search(r'(https?://[^\s]+)', message)
    messages = _build_messages(message, history)
    # 🗜️ 前情提要压缩接线（§10 #2）：历史 >20 条 → 旧消息浓缩为约 50 字
    # 前情提要 + 最近 10 条明细（结果持久化缓存；失败回退既有硬截断口径）
    messages = _compress_history(messages, session_key)
    # 🧠 长期记忆注入（§10 #3）：最近 5 条记忆以系统上下文形态并入模型消息
    messages = _inject_memory_context(messages)
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
                    # 📍 搜索指代消解（2026-10-02 用户口径）：web_search 的
                    # 裸词 query（"今天天气"）会被搜索引擎随机定位——执行
                    # 前按 .env 配置的 USER_CITY/USER_DISTRICT 补全地点
                    #（用户说的地点优先，_inject_location 已含地点则原样）
                    if (tool_name == "web_search" and isinstance(tool_args, dict)
                            and tool_args.get("query")):
                        located = _inject_location(str(tool_args["query"]))
                        if located != tool_args["query"]:
                            print(f"📍 [搜索] 指代消解: "
                                  f"{tool_args['query']} → {located}")
                            tool_args["query"] = located
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

# [EMOJI:标签] 占位符（translate_emoji 解析与安全封口共用）
_EMOJI_TAG_RE = re.compile(r'\[EMOJI:(.*?)\]')


def translate_emoji(reply):
    """[EMOJI:标签] → CQ 码图片消息（本地无图触发下载，仍无降级纯文本）。

    文档 §5 闭环口径：smart_ask 的正常文本回复（普通/总结/工具汇总）返回前
    统一调用本函数。emoji_manager 函数内延迟导入，缺席时优雅降级：
    - 本地库命中标签 → [CQ:image,file=file://路径]；
    - 未命中 → get_emoji_path 内部用收藏链接兜底下载（架构 §10 #6，落
      assets/emoji/），下载成功即转换成功；
    - 返回 None（库空/下载失败）或链路异常 → 降级纯文本"[表情: 标签]"；
    - 末尾统一安全封口：任何残留 [EMOJI:xxx]（导入失败/异常等）一律转
      "[表情: 标签]"——绝不崩溃、绝不再返回未转换的 [EMOJI: 原文。
    """
    try:
        from emoji_manager import get_emoji_path
    except Exception:
        get_emoji_path = None
    if get_emoji_path is not None:
        try:
            for tag in _EMOJI_TAG_RE.findall(reply):
                emoji_path = get_emoji_path(tag)
                if emoji_path:
                    reply = reply.replace(
                        f"[EMOJI:{tag}]", f"[CQ:image,file=file://{emoji_path}]")
                else:
                    reply = reply.replace(f"[EMOJI:{tag}]", f"[表情: {tag}]")
        except Exception as e:
            print(f"⚠️ 表情转换异常，降级纯文本: {e}")
    # 安全封口：转换链路任何环节漏下的占位符一律转纯文本
    return _EMOJI_TAG_RE.sub(r"[表情: \1]", reply)
