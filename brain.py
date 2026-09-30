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
  工具调用；工具结果以 ❌ 开头时切断重试直接返回拒绝文案（单轮硬拦截）。
- 防死循环熔断（§10 #1，开发日志第四章"小犟3号"事件口径）：❌ 切断只保证
  本轮不把拒绝结果喂回模型；跨轮由 ToolLoopFuse 对同一会话内"同一工具 +
  等价参数被拒"连续计数，达到 TOOL_FUSE_LIMIT（默认 3，环境变量可配）次
  → 强制打断：剥夺工具调用权（不再解析/执行工具 JSON），退回纯文本回复，
  并提示用户如何继续；reset 接口供换话题/管理员指令重置。
- 输入含 URL：先抓网页正文（剔除 script/style 标签）再按"总结网页"并入提问。
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

# 工具白名单：与 tools.py 的 12 项分发、prompts.py 的工具协议一致
# （文档 §5；第二阶段 §10 #5 新增 web_search、§7 权限调整新增 system_manage）
TOOL_WHITELIST = [
    "list_files", "read_file", "write_file", "get_ha_devices",
    "control_ha_device", "adb_tap", "adb_swipe", "adb_screenshot",
    "vision_tap_element", "ui_tap_element", "web_search", "system_manage",
    "read_core_memory",
]


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
    payload = {"model": model or LOCAL_MODEL, "messages": msgs,
               "stream": False, "keep_alive": -1}
    return requests.post(LOCAL_URL, json=payload,
                         timeout=LOCAL_GENERATE_TIMEOUT).json()['message']['content']


def ask_cloud(messages):
    """云端 DeepSeek 兜底。API 报错 / 连接异常时返回 ⚠️ 文案而非抛异常
    （参考实现口径），由 smart_ask 统一判定"双脑全挂"的失败口径。"""
    headers = {"Authorization": f"Bearer {CLOUD_KEY}", "Content-Type": "application/json"}
    payload = {"model": CLOUD_MODEL, "messages": messages, "stream": False}

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
      例外：主链路注入的【前情提要】与长期记忆上下文（架构 §10 #2/#3 接线）
      以特定前缀标识，允许通过并在去掉前缀后保留；
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
            for prefix in ("【前情提要】", "以下是关于用户的长期记忆"):
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
            return f"❌ 抓取网页失败: {e}", "❌ 失败"

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
        return f"❌ 大脑连接失败，请检查网络。错误：{e2}", "❌ 失败"

    raw_reply = raw_reply if isinstance(raw_reply, str) else str(raw_reply)

    # 云端兜底也失联（ask_cloud 把连接异常转成了 ⚠️ 文案）→ 双脑全挂，明确报错
    if raw_reply.startswith("⚠️ 云端连接异常"):
        return f"❌ 大脑连接失败，请检查网络。错误：{raw_reply}", "❌ 失败"

    if not raw_reply:
        return ("抱歉，小橘3号刚才脑袋短路了，请再说一遍吧。",
                "🏠 本地" if used_local else "☁️ 云端")

    raw_reply = raw_reply.strip()
    label = "🏠 本地" if used_local else "☁️ 云端"

    # === 第三步：如果是抓网页的，直接返回总结 ===
    if url_match:
        return translate_emoji(raw_reply), f"{label} (总结)"

    # === 第四步：解析工具调用（核心：用正则强匹配 JSON，允许前后有杂散文字） ===
    if fused:
        # ⛔ 熔断生效中：工具调用权已被剥夺，不再解析/执行工具 JSON，退回纯文本
        return translate_emoji(raw_reply), label

    match = re.search(r'\{.*"tool".*\}', raw_reply, re.DOTALL)
    if match:
        json_str = match.group(0)
        try:
            tool_call = json.loads(json_str)
            tool_name = tool_call.get("tool")
            tool_args = tool_call.get("args", {})

            if tool_name in TOOL_WHITELIST:
                tool_result = execute_tool(tool_name, tool_args, permission_manager)
                print(f"📄 结果: {tool_result[:200]}...")

                # ⛔ 防死循环硬拦截：被拒（❌ 开头）的工具结果不再喂回模型重试，
                # 直接把拒绝文案作为本轮回答返回（单轮内切断）
                if tool_result.startswith("❌"):
                    # 🛡️ 跨轮熔断计数：同一工具 + 等价参数连续被拒 → 强制打断
                    tool_fuse.record_rejection(session_key, tool_name, tool_args)
                    if tool_fuse.is_tripped(session_key):
                        print("⛔ 防死循环熔断触发：连续多次同一操作被拒，已暂停工具使用。")
                        return TOOL_FUSE_NOTICE, "⛔ 熔断"
                    return tool_result, "☁️ 云端 (工具)"

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
                        return f"❌ 工具执行后汇总失败: {e}", "❌ 失败"
                return translate_emoji(final_reply), tool_source
            else:
                print(f"⚠️ 工具 {tool_name} 不在白名单内，已拒绝执行。")
        except Exception as e:
            print(f"⚠️ 工具解析失败，按普通回复处理: {e}")

    return translate_emoji(raw_reply), label


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
