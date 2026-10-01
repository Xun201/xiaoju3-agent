# -*- coding: utf-8 -*-
"""小橘3号 · 接入层主程序（纯 QQ webhook + API 网关，Flask :5002；网页统一 :5003）。

按《架构设计文档》§2 /《功能文档》§2.4、§5 与第二阶段 §7 权限调整：
- 5002 旧版网页已废弃（内置深色聊天页 GET / 与 POST /chat API 由 :5003
  xiaoju3_dashboard.py 新版控制台取代）：GET / 一律 302 跳转
  http://127.0.0.1:5003/console；POST /chat 路由已删除，防止误用旧页测试。
- POST /onebot：OneBot 11 webhook（LLOneBot 实现；无鉴权保持文档口径，依赖内网环境，§9）。
  私聊直接响应；群聊需 @（CQ 码）或触发词（小橘/小桔/橘3号/橘三号/AI测试）
  才理人，防刷屏；戳一戳彩蛋回应；非 @ 图片消息自动收藏表情链接（emoji_manager）。
- GET /api/health：迁移守望探测端点（migration.health_bp 一行接入，架构 §8）。

指令族（§7 用户新权限表，覆盖旧"固定认证码"口径）：
- /register <密码> [称呼]：Lv.2 注册（env XIAOJU3_REGISTER_PASSWORD，落盘；称呼不得占用创造者保留名）。
- /name <称呼>：设置/修改自称称呼（创造者保留名不可占用）。
- /coder_auth <6位动态密码>：TOTP 激活 Lv.3（等级持久化接线，修复"重启回落"）。
- /sudo <6位动态密码>：开启 120 秒写操作窗口（Lv.3 已可直接写文件，本窗口作为兼容保留）。
- /lv4_auth：两步流——先发 /lv4_auth 看类 Root 警告，再 /lv4_auth confirm <TOTP>
  携双因子凭据授权；/lv4_revoke 撤销（立即生效）。全程不落任何密钥。
- /gen_log 限 Lv.3+；/send_image 需等级 ≥ Lv.3（修复 Lv.4 主人被拒）。
- /reset_fuse（Lv.2+）：重置防死循环熔断；新会话首条消息自动重置该通道熔断。
- /confirm <6位令牌>：高危设备（门锁/燃气）二次确认令牌流。
- /clear、/reset、清空记忆、重置记忆：一键清空当前通道会话记忆
  （内存列表 + 磁盘 history_web.json / history_qq.json 双清，文件置空数组 []）。

大脑链路编排（架构 §10）：意图路由（命中直达，未命中透传 smart_ask）→
长期记忆注入系统上下文 → 最近设备操作记录注入（指代消解，空记录不注入）→
smart_ask（危险实体拒绝捕获 → Lv.4+MFA 发确认令牌）→
前情提要压缩（>20 条浓缩为 ≤50 字前情提要并入历史头部，50 条硬上限，失败回退
纯截断）→ 双通道落盘。

安全口径：
- 等级持久化经 permission.save_identity()（agent_state/identity.json），与 §7
  用户指令一致；操作窗口 / 确认令牌 / 双因子会话仅内存，不落任何密钥。
- /send_image 需等级 ≥ Lv.3 且 realpath 前缀校验限制在 WORKSPACE 内
  （与 tools.py 同口径），以 CQ 码 [CQ:image,file=file://...] 随回复链路发图。
- 确认令牌流只对"已通过等级 + 双因子门禁后挂起"的操作生效，/confirm 重新走
  execute_tool 完整门禁——无任何绕过权限门的路径。
- /gen_log 后台线程执行 run_link_log，不阻塞聊天。
"""
import logging
import os
import random
import re
import threading
import time

import requests
from flask import Flask, redirect, request

import brain
import home_tools
from agent_state.state_manager import state_manager
from auth_lv4 import root_warning
from brain import load_memory, reset_tool_fuse, save_memory, smart_ask
from emoji_manager import save_emoji_link
from heartbeat import start_heartbeat
from intent_router import dispatch, route
from migration import PeerWatch, health_bp
from permission import permission_manager
from plugins.context_manager import compress_context
from prompts import SYSTEM_PROMPT
from tools import execute_tool, get_recent_actions
from xiaoju3 import (AGENT_STATE_DIR, ONEBOT_API_URL, ONEBOT_TOKEN,
                     TRIGGER_WORDS, WORKSPACE)

app = Flask(__name__)
# 🛡️ 迁移守望探测端点（架构 §8，migration docstring 接入示例：一行注册）
app.register_blueprint(health_bp)

# ================= 访问日志刷屏抑制（/onebot 心跳事件） =================
# 用户口径：LLOneBot 心跳（meta_event 的 heartbeat/lifecycle 等高频事件）每次
# POST /onebot 都打一条 werkzeug 访问日志，长期运行刷屏。心跳与消息事件同为
# POST /onebot，访问日志行无法区分——视图内对 meta_event 事件打一次性线程
# 标记，过滤器据此只拦截心跳那一次请求的访问日志；消息类 /onebot 日志保留。
# 拦截（filter 返回 False）而非"降为 DEBUG"的取舍见
# xiaoju3_dashboard.py 注释：werkzeug 3.x 自挂 NOTSET 级 handler，降级 DEBUG
# 仍会被输出；直接拦截跨日志配置行为确定。
_onebot_meta_local = threading.local()   # 当前线程是否正处理 meta_event 心跳类事件


class _HeartbeatAccessFilter(logging.Filter):
    """meta_event 心跳请求的 werkzeug 访问日志拦截器（一次性线程标记）。"""

    def filter(self, record):
        if getattr(_onebot_meta_local, "is_meta_event", False):
            _onebot_meta_local.is_meta_event = False   # 标记一次性：仅覆盖本次请求
            return False
        return True


logging.getLogger("werkzeug").setLevel(logging.INFO)   # 保底：非拦截访问日志保持可见
logging.getLogger("werkzeug").addFilter(_HeartbeatAccessFilter())

# ================= 配置（环境变量优先 → 中立默认值兜底） =================
# OneBot 11 HTTP API（LLOneBot，标准正向 HTTP 端口 3001；NapCat 用户改回
# 3000 即可）：统一配置见 xiaoju3.py（ONEBOT_API_URL / ONEBOT_TOKEN，env
# 兼容回退旧 NAPCAT_* 键），本模块统一经 from xiaoju3 import 使用。

# DeepSeek 分享链接前缀（与 run_link_log.SHARE_PREFIX / plugins.link_logger 一致）
SHARE_PREFIX = "https://chat.deepseek.com/share/"

# 生物认证模拟开关（§7：仅供测试/演示的恒真验证器，生产保持关闭）
BIOMETRIC_SIM_ENV = "XIAOJU3_BIOMETRIC_SIM"

# ================= 高危设备二次确认令牌流（§7 + 架构 §6/§10 #8） =================
CONFIRM_TOKEN_TTL = 300   # 确认令牌有效期（秒，5 分钟），一次性用后即焚
MFA_SESSION_TTL = 300     # Lv.4 双因子会话有效期（秒）：窗口内已验的动态密码可复用

# 内存态（均不落盘、不含任何密钥明文——totp 为用户输入的 6 位动态密码本身）
_pending_confirms = {}    # {token: {"user_id","tool_name","args","expires"}}
_mfa_sessions = {}        # {user_id: {"totp": 动态密码, "ts": 校验通过时间}}

# ================= 记忆库隔离（双通道，§4） =================
MEMORY_FILE_WEB = os.path.join(AGENT_STATE_DIR, "history_web.json")
MEMORY_FILE_QQ = os.path.join(AGENT_STATE_DIR, "history_qq.json")

messages_web = [SYSTEM_PROMPT] + load_memory(MEMORY_FILE_WEB)
messages_qq = [SYSTEM_PROMPT] + load_memory(MEMORY_FILE_QQ)
# ============================================


def _onebot_headers():
    """OneBot API 请求头（Bearer 认证；未配置令牌时与参考口径一致传空）。"""
    return {"Authorization": f"Bearer {ONEBOT_TOKEN}"}


def _peer_watch_enabled():
    """多设备互相守望开关（架构 §8，默认关闭）：
    env XIAOJU3_PEERS 配置了对端 且 XIAOJU3_WATCH=1 时才开启。"""
    return bool(os.environ.get("XIAOJU3_PEERS", "").strip()) and \
        os.environ.get("XIAOJU3_WATCH", "").strip() == "1"


def _is_in_workspace(filepath):
    """realpath 前缀校验：目标必须落在工作区目录之内（与 tools.py 同口径）。"""
    base = os.path.realpath(WORKSPACE)
    target = os.path.realpath(filepath)
    return target.startswith(base + os.sep)


def _arg_after(raw_message, command):
    """提取指令后的参数原文（剔除 CQ 码）。

    取清洗前原文：标点清洗会剥掉 URL 的 : . 、路径盘符与扩展名点，导致
    链接前缀校验 / 图片路径 / 密码参数失效。
    """
    if command not in raw_message:
        return ""
    tail = raw_message.split(command, 1)[-1]
    return re.sub(r'\[CQ:[^\]]*\]', '', tail).strip()


def _strip_cq(text):
    """去掉 CQ 码（@ 提及码不参与意图识别 / 触发词匹配）。"""
    return re.sub(r'\[CQ:[^\]]*\]', '', text).strip()


def _strip_think(text):
    """剥除 <think>...</think> 思维链包装块（含标签本体，DOTALL 跨行）。

    brain.smart_ask 的工具流程回复会在最前面包装 <think> 推理块，供新版
    网页前端（:5003 控制台）渲染折叠卡片；QQ 发送点（/onebot → OneBot，
    /send_image 的 CQ 码随回复链路发出同理）必须在发送前剥除——QQ 消息
    保持干净，推理展示只属于新前端。
    """
    return re.sub(r'<think>.*?</think>', '', str(text or ""), flags=re.DOTALL).strip()


# ================= 权限指令族辅助（§7） =================

def _ensure_biometric_sim():
    """env XIAOJU3_BIOMETRIC_SIM=1 时注册恒真生物认证模拟验证器。

    ⚠️ 仅供测试/演示：恒真回调模拟"生物认证通过"，不代表真实生物识别硬件；
    生产环境请接入真实验证器（permission.register_biometric_verifier）或
    保持该环境变量关闭。幂等：重复调用只覆盖同一回调。
    """
    if os.environ.get(BIOMETRIC_SIM_ENV, "").strip() == "1":
        permission_manager.register_biometric_verifier(lambda credential: True)


def _mfa_session_ok(user_id):
    """Lv.4 双因子会话是否有效：5 分钟内完成过 TOTP 校验且当前 MFA 复验通过。"""
    sess = _mfa_sessions.get(user_id)
    if not sess or time.time() - sess["ts"] > MFA_SESSION_TTL:
        return False
    return permission_manager.lv4_mfa_ok(
        user_id, {"totp": sess["totp"], "biometric": "biometric"})


def _issue_confirm_token(user_id, tool_name, args):
    """生成一次性 6 位确认令牌并挂起操作（内存表，5 分钟过期）。"""
    while True:
        token = f"{random.randint(0, 999999):06d}"
        if token not in _pending_confirms:
            break
    _pending_confirms[token] = {
        "user_id": user_id,
        "tool_name": tool_name,
        "args": dict(args or {}),
        "expires": time.time() + CONFIRM_TOKEN_TTL,
    }
    return token


def _handle_confirm(user_id, token):
    """高危设备操作二次确认：令牌校验 → 一次性焚毁 → 携凭据重新执行。

    安全口径：挂起动作在创建时已通过"等级 + 双因子"门禁；/confirm 只对
    挂起表内的动作生效，且 execute_tool 会重新走完整权限门禁（等级、
    双因子、实体危险分类）——不存在绕过权限门的路径。
    """
    token = str(token or "").strip()
    if not re.fullmatch(r"\d{6}", token):
        return "用法：/confirm <6位数字令牌>——确认执行高危设备操作。"
    entry = _pending_confirms.get(token)
    if entry is None:
        return "❌ 确认令牌无效或已被使用，请重新发起高危设备操作。"
    if entry["user_id"] != user_id:
        return "❌ 该确认令牌不属于当前用户，已忽略。"
    _pending_confirms.pop(token, None)   # 一次性：校验通过即焚毁（过期同样焚毁）
    if time.time() > entry["expires"]:
        return "❌ 确认令牌已过期（有效期 5 分钟），请重新发起高危设备操作。"
    credentials = {"confirmed": True, "biometric": "biometric"}
    sess = _mfa_sessions.get(user_id)
    if sess:
        credentials["totp"] = sess["totp"]   # 窗口内已验动态密码
    return execute_tool(entry["tool_name"], entry["args"], permission_manager,
                        credentials=credentials)


def _smart_ask_with_danger_confirm(message, history, session_key, user_id):
    """smart_ask 包装：捕获本轮被拒的危险实体（门锁/燃气）控制调用。

    brain 的工具链路不携带凭据，高危设备控制在 execute_tool 处必然被拒；
    若用户已是 Lv.4 且双因子会话有效，则挂起该操作并发放一次性确认令牌，
    用户 /confirm 后携凭据重执行；其余情况原样返回拒绝文案（不发放令牌）。
    """
    captured = {}
    original_execute = brain.execute_tool

    def _capturing_execute(tool_name, args, pm, credentials=None):
        result = original_execute(tool_name, args, pm, credentials)
        if (tool_name == "control_ha_device" and isinstance(result, str)
                and result.startswith("❌")
                and home_tools.is_dangerous_entity((args or {}).get("entity_id"))):
            captured["tool_name"] = tool_name
            captured["args"] = dict(args or {})
        return result

    brain.execute_tool = _capturing_execute
    try:
        res = smart_ask(message, history, session_key=session_key)
    finally:
        brain.execute_tool = original_execute

    reply = res[0] if isinstance(res, tuple) else res
    if "tool_name" in captured and \
            permission_manager.level_value() >= 4 and _mfa_session_ok(user_id):
        token = _issue_confirm_token(user_id, captured["tool_name"], captured["args"])
        entity = (captured["args"] or {}).get("entity_id", "该设备")
        reply = (f"🔐 {entity} 属高危设备（门锁/燃气类），已按主人级权限挂起该操作。\n"
                 f"回复 /confirm {token} 执行（令牌 5 分钟内有效，一次性使用）。")
    return reply


# ================= 大脑链路编排（架构 §10 #2/#3/#4） =================

def _inject_long_term_memories(history):
    """长期记忆注入（架构 §10 #3）：进入 smart_ask 前取最近 3 条长期记忆，
    以"以下是关于用户的长期记忆"为中文前缀拼入系统上下文；空则不拼。"""
    try:
        memories = state_manager.get_recent_memories(3)
    except Exception as e:
        print(f"⚠️ 读取长期记忆失败: {e}")
        memories = []
    if not memories:
        return history
    lines = "\n".join(f"· [{category}] {content}" for category, content in memories)
    block = {"role": "system",
             "content": f"以下是关于用户的长期记忆，回答时可以参考：\n{lines}"}
    if history and isinstance(history[0], dict) and history[0].get("role") == "system":
        return [history[0], block] + list(history[1:])
    return [block] + list(history)


def _inject_recent_actions(history):
    """最近设备操作注入（指代消解上下文）：进入 smart_ask 前取最近 5 条设备
    操作记录，以"以下是最近的设备操作记录"为中文前缀拼入系统上下文；
    空记录（无文件/读取异常）不拼。范围说明：仪表盘 /api/chat 直连
    smart_ask 不经本链路，不在注入范围。"""
    try:
        actions = get_recent_actions()
    except Exception as e:
        print(f"⚠️ 读取设备操作记录失败: {e}")
        actions = []
    if not actions:
        return history
    lines = "\n".join(f"· {a.get('detail', '')}" for a in actions)
    block = {"role": "system",
             "content": (f"以下是最近的设备操作记录（最新在最后），主人提到"
                         f"\"它/再一次/刚才那个\"等指代时可据此解析：\n{lines}")}
    if history and isinstance(history[0], dict) and history[0].get("role") == "system":
        return [history[0], block] + list(history[1:])
    return [block] + list(history)


def _compress_and_save(messages, filepath):
    """前情提要压缩落盘（架构 §10 #2）：>20 条时把旧消息浓缩为 ≤50 字前情提要
    并入历史头部；仍保留 50 条硬上限；压缩失败（双脑不可用）回退纯截断。"""
    try:
        compressed = compress_context(messages)
        if compressed is not messages:
            summary = compressed[1].get("content", "") if len(compressed) > 1 else ""
            if ("【前情提要】" in summary and "⚠️" not in summary
                    and "由于系统原因" not in summary):
                messages[:] = compressed   # 原地替换，保持通道列表引用不变
            else:
                print("⚠️ 前情提要生成失败（双脑不可用），本轮回退纯截断。")
    except Exception as e:
        print(f"⚠️ 上下文压缩异常，回退纯截断: {e}")
    # 只剥置顶系统提示词，保留【前情提要】system 条目随历史落盘（重启不丢）
    persist = [m for i, m in enumerate(messages)
               if not (i == 0 and isinstance(m, dict) and m.get("role") == "system")]
    save_memory(persist, filepath)


def _brain_reply(source, message, messages, user_id, new_session=False):
    """进入大脑前的主链路编排，返回回复文本。

    ① 新会话首条消息（历史为空）自动重置该通道熔断计数（防残留熔断）；
    ② 意图路由：route 命中 → dispatch 直达（export_ebook 注入通道历史）；
       route 返回 None 或 dispatch 失败 → 透传原 smart_ask 链路，绝不吞消息；
    ③ 长期记忆注入系统上下文；
    ④ 最近设备操作记录注入（指代消解上下文，空记录不注入）；
    ⑤ smart_ask（危险设备确认令牌捕获包装）。
    """
    session_key = source
    if new_session:
        reset_tool_fuse(session_key)

    # 意图路由按清洗前原文识别（保留标点与小数点，"12.5元"不被清洗破坏）
    intent = None
    try:
        intent = route(_strip_cq(message))
    except Exception as e:
        print(f"⚠️ 意图路由异常，走正常对话: {e}")
    if intent is not None:
        if intent.name == "export_ebook" and "history" not in (intent.args or {}):
            # 电子书导出需要会话历史：把当前通道的非 system 消息填进参数
            intent.args["history"] = [m for m in messages
                                      if isinstance(m, dict) and m.get("role") != "system"]
        try:
            dispatched = dispatch(intent)
        except Exception as e:
            print(f"⚠️ 意图执行异常，走正常对话: {e}")
            dispatched = None
        if dispatched and not (isinstance(dispatched, str) and dispatched.startswith("❌")):
            return str(dispatched)

    history = _inject_long_term_memories(messages)
    history = _inject_recent_actions(history)
    return _smart_ask_with_danger_confirm(message, history, session_key, user_id)


# ================= 核心内核（统一入口） =================
def handle_message(source, user_id, group_id, message, self_qq=None):
    """所有消息（QQ/网页）都统一交给这个函数处理。

    self_qq: 本机机器人的 QQ 号（OneBot 事件自带 self_id），用于群聊 @ 判定；
    缺省时退化为"消息含任意 CQ:at 即视为 @"（无法识别被@对象时的宽容口径）。
    """
    if isinstance(message, list):
        message = "".join([seg.get("data", {}).get("text", "") for seg in message if seg.get("type") == "text"])

    raw_message = message or ""

    # 🛡️ 输入标准化清洗：去除首尾空格、中文/英文标点，防止大模型过度思考
    message = re.sub(r'[，。！？、；：""《》【】\[\],.?!;:"\'<>]', '', raw_message).strip()

    # 如果清洗后为空，直接返回
    if not message:
        return "（你发了一条空消息）"

    # === 🧹 一键清空记忆（/clear、/reset、清空记忆、重置记忆） ===
    # 精确匹配（清洗后全等）：不误吞更长的 /reset_fuse，也不误伤含"清空记忆"
    # 字样的普通对话。内存列表与磁盘文件双清——只清文件不清内存的话，本会话
    # 记忆并未消失，下一轮 _compress_and_save 又会把旧历史写回文件。
    # 内存仅保留置顶系统提示词（通道历史恒以 system 开头的不变量不破坏）。
    global messages_web, messages_qq
    if message in ("/clear", "/reset", "清空记忆", "重置记忆"):
        if source == 'web':
            messages_web[:] = [SYSTEM_PROMPT]
            save_memory([], MEMORY_FILE_WEB)          # 文件内容置空数组 []
        else:
            messages_qq[:] = [SYSTEM_PROMPT]
            save_memory([], MEMORY_FILE_QQ)
        return "✨ 记忆已清空！我现在的大脑非常干净，可以重新开始对话了。"

    user_key = str(user_id)

    # === 🛡️ 指令菜单 ===
    if message in ["/help", "菜单", "帮助", "指令"]:
        from plugins.help_menu import get_help_menu
        return get_help_menu(permission_manager.current_level)

    # === 🛡️ Lv.2 注册（§7：env 注册密码校验，等级落盘） ===
    if message.startswith("/register"):
        arg = _arg_after(raw_message, "/register").strip()
        parts = arg.split(None, 1)
        password = parts[0] if parts else ""
        name = parts[1].strip() if len(parts) > 1 else None
        return permission_manager.register_user(user_key, password, name=name)

    if message.startswith("/name"):
        return permission_manager.claim_name(user_key, _arg_after(raw_message, "/name"))

    # === 🛡️ Lv.3 TOTP 动态密码激活（等级持久化接线，修复"重启回落"） ===
    if message.startswith("/coder_auth"):
        return permission_manager.activate_lv3(user_key, _arg_after(raw_message, "/coder_auth"))

    # === 🛡️ /sudo：开启 120 秒写操作窗口（与工具链门禁同为缺省用户口径） ===
    if message.startswith("/sudo"):
        code = _arg_after(raw_message, "/sudo")
        if not code:
            return ("用法：/sudo <6位动态密码>——开启 120 秒写操作窗口（Lv.3 已可直接写文件，本指令为兼容保留），"
                    "窗口内写文件/写代码无需逐次输入动态密码。")
        return permission_manager.open_operation_window(None, totp_code=code)

    # === 🛡️ /lv4_auth 两步流：类 Root 警告 → 双因子 confirm 授权 ===
    if message.startswith("/lv4_auth"):
        _ensure_biometric_sim()
        rest = _arg_after(raw_message, "/lv4_auth")
        if not rest:
            # 第一步：类 Root 警告（敏感操作清单 + 后果 + 撤销途径），等待确认
            return (root_warning(print_warning=False)
                    + "\n\n理解并接受上述风险后，请发送 /lv4_auth confirm <6位动态密码> 完成双因子授权。")
        if rest.startswith("confirm"):
            totp = rest[len("confirm"):].strip()
            # 带明细校验：生物认证器未接入时透传"生物认证器未接入"明细
            ok, detail = permission_manager.lv4_mfa_check(
                user_key, {"totp": totp, "biometric": "biometric"})
            if not ok:
                return f"❌ Lv.4 双因子认证未通过：\n{detail}"
            credentials = {"confirmed": True, "totp": totp, "biometric": "biometric"}
            result = permission_manager.grant_lv4(user_key, credentials)
            if result.startswith("✅"):
                # 记录双因子会话（供高危设备确认令牌流复用"窗口内已验"动态密码）
                _mfa_sessions[user_key] = {"totp": totp, "ts": time.time()}
            return result
        return "用法：/lv4_auth 查看类 Root 警告；/lv4_auth confirm <6位动态密码> 完成授权。"

    # === 🛡️ /lv4_revoke：撤销主人级权限（立即生效） ===
    if message.startswith("/lv4_revoke"):
        result = permission_manager.revoke_lv4(user_key)
        if result.startswith("✅"):
            # 撤销立即生效：双因子会话一并失效（确认令牌流随之不可用）
            _mfa_sessions.pop(user_key, None)
        return result

    # === 🛡️ /confirm：高危设备二次确认令牌核销 ===
    if message.startswith("/confirm"):
        return _handle_confirm(user_key, _arg_after(raw_message, "/confirm"))

    # === ⛔ /reset_fuse：防死循环熔断重置（Lv.2+，管理员口径全通道清零） ===
    if message.startswith("/reset_fuse"):
        if permission_manager.level_value() < 2:
            return "❌ 权限不足，该指令需要 Lv.2（普通用户）权限。请先 /register <密码> 注册升级。"
        reset_tool_fuse()
        return "✅ 防死循环熔断计数已重置，工具调用权限已恢复。"

    # === 📝 全自动日志提取（§7：/gen_log 限 Lv.3+，不足只引导不执行） ===
    if "/gen_log" in message:
        if permission_manager.level_value() < 3:
            return ("❌ 权限不足，开发日志提取需要 Lv.3（代码编写者）权限。\n"
                    "请先发送 /coder_auth <6位动态密码> 升级后再试。")
        # 从清洗前原文提取链接：标点清洗会剥掉 URL 里的 : . 等字符，导致前缀校验失效
        log_url = _arg_after(raw_message, "/gen_log")

        if not log_url.startswith(SHARE_PREFIX):
            return "⚠️ 请提供正确的 DeepSeek 分享链接，格式：/gen_log https://chat.deepseek.com/share/..."

        def run_log_extraction(target_url):
            print(f"🚀 收到指令，开始后台提取链接: {target_url}")
            try:
                import run_link_log
                run_link_log.run_link_log(target_url)
            except Exception as e:
                print(f"⚠️ 提取任务后台报错: {e}")

        threading.Thread(target=run_log_extraction, args=(log_url,), daemon=True).start()
        return "🔄 收到链接啦！小橘3号正在后台努力阅读和总结（大约需要1分钟）。完成后日志会自动保存到 dev_logs 文件夹里！"

    # === 🛡️ 发送图片指令（§7：等级 ≥ Lv.3 即通过，修复 Lv.4 主人被拒） ===
    if message.startswith("/send_image"):
        if permission_manager.level_value() < 3:
            return "❌ 权限不足，请先发送 /coder_auth <6位动态密码> 升级到 Lv.3（代码编写者）。"
        # 从清洗前原文提取路径（清洗会剥掉盘符冒号与扩展名里的点）
        img_path = raw_message.split("/send_image", 1)[-1].strip()
        if not img_path:
            return "❌ 请提供图片路径，格式：/send_image <图片路径>"
        if not os.path.exists(img_path):
            return f"❌ 图片不存在：{img_path}"
        if not _is_in_workspace(img_path):
            return "❌ 只能发送项目工作区内的图片。"

        # CQ 码发图：随回复链路交回 OneBot 实现端解析发送
        return f"[CQ:image,file=file://{img_path}]"

    # 1. 收集图片表情包（拦截非 @ 的图片消息，仅存链接不下载——文档 §5 口径）
    if "[CQ:image" in raw_message and "[CQ:at" not in raw_message:
        img_match = re.search(r'\[CQ:image,file=(.*?)\]', raw_message)
        if img_match:
            img_url = img_match.group(1).strip()
            if img_url:
                print(f"🖼️ 收到图片，正在保存链接: {img_url}")
                if save_emoji_link(img_url):
                    return "收到你的表情啦！已经存进小仓库了😊"
                else:
                    return "这个表情我没存下来，下次再试试！"

    # 2. 群聊防刷屏（只有@或触发词才理人）
    if source == 'qq' and group_id:
        if self_qq:
            is_at_me = f"[CQ:at,qq={self_qq}]" in raw_message
        else:
            is_at_me = "[CQ:at" in raw_message
        has_trigger_word = any(word in message for word in TRIGGER_WORDS)
        if not (is_at_me or has_trigger_word):
            return ""

    # 3. 长期记忆"记住"触发词（架构 §10 #3）：落 SQLite 并回复确认
    remember_match = re.search(r"(?:帮我|请|麻烦|你)*记住[:：,，、]?\s*(.+)", _strip_cq(raw_message))
    if remember_match:
        memory_content = remember_match.group(1).strip()
        if memory_content:
            try:
                state_manager.save_memory("user", memory_content)
                return f"好的，我记住了：{memory_content}（已存入长期记忆库）"
            except Exception as e:
                return f"❌ 长期记忆保存失败：{e}"

    # 4. 调用大脑进行思考（根据来源，选择不同的记忆库；
    #    messages_web / messages_qq 已在清空记忆段声明 global，整个函数生效）
    if source == 'web':
        is_new_session = len(messages_web) <= 1   # 历史为空 = 新会话首条消息
        messages_web.append({"role": "user", "content": message})
        reply = _brain_reply('web', message, messages_web, user_key,
                             new_session=is_new_session)
        if not reply:
            reply = "抱歉，我脑袋突然卡壳了，请再说一遍吧。"
        messages_web.append({"role": "assistant", "content": reply})
        _compress_and_save(messages_web, MEMORY_FILE_WEB)
        state_manager.save_conversation("web", messages_web)
    else:
        is_new_session = len(messages_qq) <= 1
        messages_qq.append({"role": "user", "content": message})
        reply = _brain_reply('qq', message, messages_qq, user_key,
                             new_session=is_new_session)
        if not reply:
            reply = "抱歉，我脑袋突然卡壳了，请再说一遍吧。"
        messages_qq.append({"role": "assistant", "content": reply})
        _compress_and_save(messages_qq, MEMORY_FILE_QQ)
        state_manager.save_conversation("qq", messages_qq)

    return reply
# =======================================================

# ================= 网页大门 =================
@app.route('/')
def index():
    # 🚧 5002 旧版网页已废弃（内置深色聊天页 + POST /chat API 由 :5003
    # xiaoju3_dashboard.py 新版控制台取代）：根路径一律 302 跳转新版控制台，
    # 防止误在 5002 旧页测试造成误判。
    return redirect("http://127.0.0.1:5003/console", 302)

# ================= QQ大门 =================
def _rebuild_raw_message(data):
    """raw_message 缺失/为空时从 message 字段重建文本（LLOneBot 兼容）。

    OneBot 11 消息段数组格式：拼接 type=="text" 段的 data.text，并按 CQ 码
    惯例还原 at / image 段（[CQ:at,qq=...] / [CQ:image,file=...]），保持既有
    触发词 / @ 判定与图片收藏逻辑可用；message 为字符串时直接使用；其余类型
    （缺失 / None）返回空串。任何段结构异常都不抛错（逐段容错跳过）。
    """
    message = data.get("message")
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        parts = []
        for seg in message:
            try:
                if not isinstance(seg, dict):
                    continue
                seg_data = seg.get("data") or {}
                seg_type = str(seg.get("type") or "")
                if seg_type == "text":
                    parts.append(str(seg_data.get("text") or ""))
                elif seg_type == "at":
                    parts.append(f"[CQ:at,qq={seg_data.get('qq', '')}]")
                elif seg_type == "image":
                    parts.append(f"[CQ:image,file={seg_data.get('file', '')}]")
            except Exception:
                continue   # 单段异常不影响整体重建
        return "".join(parts)
    return ""


@app.route('/onebot', methods=['POST'])
def onebot_webhook():
    data = request.get_json(silent=True) or {}

    # 🔇 心跳类高频事件（meta_event 的 heartbeat/lifecycle/connect）先打一次性
    # 线程标记：本次请求的 werkzeug 访问日志由 _HeartbeatAccessFilter 拦截
    # （防刷屏）；消息类 /onebot 日志不受影响。
    if data.get('post_type') == 'meta_event':
        _onebot_meta_local.is_meta_event = True

    # 🎁 彩蛋：戳一戳
    if data.get('post_type') == 'notice' and data.get('notice_type') == 'poke':
        group_id = data.get('group_id')
        user_id = data.get('user_id')
        print("👆 有人戳了戳我！")
        reply = "别戳啦，好痒！😆"
        try:
            if group_id:
                requests.post(f"{ONEBOT_API_URL}/send_group_msg", json={"group_id": group_id, "message": reply},
                              timeout=10, headers=_onebot_headers())
            else:
                requests.post(f"{ONEBOT_API_URL}/send_private_msg", json={"user_id": user_id, "message": reply},
                              timeout=10, headers=_onebot_headers())
        except Exception as e:
            print(f"戳一戳回复失败: {e}")
            print("❌ 无法连接至 OneBot 服务，请确认 LLOneBot 是否已启动，"
                  "且 .env 中的端口配置是否正确（默认通常为 3001）。")
        return {"status": "ok", "retcode": 0}

    # 🛡️ LLOneBot 兼容：post_type 缺失时按 message 事件宽容处理（部分实现
    # 不上报该字段）；meta_event 等其余事件原样忽略。
    if data.get('post_type', 'message') != 'message':
        return {"status": "ok", "retcode": 0}

    # 🛡️ 任何字段异常不崩（如 sender 结构损坏 / message 类型异常）：统一
    # 兜底返回 ok，不让单条 webhook 事件拖垮接入层主流程。
    try:
        user_id = (data.get('sender') or {}).get('user_id')
        raw_message = data.get('raw_message')
        if not raw_message:
            raw_message = _rebuild_raw_message(data)
        group_id = data.get('group_id')
        self_id = data.get('self_id')
        self_qq = str(self_id) if self_id is not None else None

        reply = handle_message('qq', user_id, group_id, raw_message or "", self_qq=self_qq)
        # 🧠 QQ 消息保持干净：剥除 <think> 思维链包装块（推理卡片只在网页前端展示）
        reply = _strip_think(reply)
        print(f"🐛 准备发送回复，内容为: {reply}")

        if reply:
            try:
                api_endpoint = "send_group_msg" if group_id else "send_private_msg"
                payload = {"message": reply}
                if group_id:
                    payload["group_id"] = group_id
                else:
                    payload["user_id"] = user_id

                requests.post(f"{ONEBOT_API_URL}/{api_endpoint}", json=payload,
                              timeout=10, headers=_onebot_headers())
            except Exception as e:
                print(f"❌ 发送QQ消息失败: {e}")
                print("❌ 无法连接至 OneBot 服务，请确认 LLOneBot 是否已启动，"
                      "且 .env 中的端口配置是否正确（默认通常为 3001）。")
    except Exception as e:
        print(f"⚠️ /onebot 事件处理异常（已忽略，不阻断 webhook）: {e}")

    return {"status": "ok", "retcode": 0}


if __name__ == '__main__':
    print("🤖 小橘3号接入层已启动（纯 QQ webhook + API 网关，:5002）！")
    print("💡 网页控制台已统一到 :5003：http://127.0.0.1:5003/console"
          "（本端口根路径自动 302 跳转）")

    # 💓 启动主动心跳引擎
    start_heartbeat()

    # 👀 多设备互相守望（架构 §8，默认关闭）：env XIAOJU3_PEERS 配置对端
    # 且 XIAOJU3_WATCH=1 时才启动守护线程（migration.PeerWatch）
    if _peer_watch_enabled():
        threading.Thread(target=PeerWatch().watch_loop, daemon=True,
                         name="xiaoju3-peer-watch").start()
        print(f"👀 多设备互相守望已启动（对端：{os.environ['XIAOJU3_PEERS'].strip()}）")

    app.run(host='0.0.0.0', port=5002, debug=False)
