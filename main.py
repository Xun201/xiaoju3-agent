# -*- coding: utf-8 -*-
"""小橘3号 · QQ 接入层业务逻辑模块（纯逻辑，不监听任何端口；由 :5003 宿主调用）。

【架构合并（2026-10-01，用户口径：彻底废弃 5002 端口，全部迁入 5003）】
- 本模块不再创建 Flask app、不再监听任何端口；原 POST /onebot 视图的业务
  处理体原样保留为纯函数 onebot_event(data)，由 :5003 xiaoju3_dashboard.py
  的同名路由调用（webhook 数据结构与处理逻辑一字未改）；直接运行本文件只会
  得到迁移提示（见文末 __main__）。
- 原 GET /（302 跳转 5003/console）随 5002 端口一并废弃：端口不复存在，
  5003 自身的 GET /（旧版蓝色单页）不受影响。
- 心跳 / 多设备守望的启动点随托管权移交：start_background_services() 由
  dashboard 进程启动时调用（原 __main__ 启动点逻辑原样迁入该函数）。
- werkzeug 访问日志过滤器（meta_event 心跳防刷屏）与 HTTP 层同属宿主进程，
  一并迁入 xiaoju3_dashboard.py；本模块只保留 QQ 业务逻辑。

按《架构设计文档》§2 /《功能文档》§2.4、§5 与第二阶段 §7 权限调整：
- POST /onebot：OneBot 11 webhook（LLOneBot 实现；无鉴权保持文档口径，依赖内网环境，§9）。
  私聊直接响应；群聊需 @（CQ 码）或触发词（小橘/小桔/橘3号/橘三号/AI测试）
  才理人，防刷屏；戳一戳彩蛋回应；非 @ 图片消息自动收藏表情链接（emoji_manager）。

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
smart_ask（儿童锁：儿童用户危险家电控制拦截 → 在线成人确认）→
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
import json
import os
import random
import re
import threading
import time

import requests

import brain
import home_tools
from agent_state.state_manager import state_manager
from auth_lv4 import root_warning
from brain import load_memory, reset_tool_fuse, save_memory, smart_ask
from emoji_manager import save_emoji_link
from heartbeat import start_heartbeat
from intent_router import dispatch, route
from migration import PeerWatch
from permission import permission_manager
from plugins.context_manager import compress_context
from prompts import SYSTEM_PROMPT
from tools import execute_tool, get_recent_actions
from xiaoju3 import (AGENT_STATE_DIR, CHILD_LOCK_ENABLED, ONEBOT_API_URL,
                     ONEBOT_TOKEN, TRIGGER_WORDS, WORKSPACE)

# ================= 配置（环境变量优先 → 中立默认值兜底） =================
# OneBot 11 HTTP API（LLOneBot，标准正向 HTTP 端口 3001；NapCat 用户改回
# 3000 即可）：统一配置见 xiaoju3.py（ONEBOT_API_URL / ONEBOT_TOKEN，env
# 兼容回退旧 NAPCAT_* 键），本模块统一经 from xiaoju3 import 使用。

# DeepSeek 分享链接前缀（与 run_link_log.SHARE_PREFIX / plugins.link_logger 一致）
SHARE_PREFIX = "https://chat.deepseek.com/share/"

# 生物认证模拟开关（§7：仅供测试/演示的恒真验证器，生产保持关闭）
BIOMETRIC_SIM_ENV = "XIAOJU3_BIOMETRIC_SIM"

# ================= 儿童锁（2026-10-02 权限重构批次②） =================
CHILD_LOCK_REQUEST_TTL = 300   # 儿童操作请求有效期（秒，5 分钟），超时自动拒绝
ONLINE_ADULT_WINDOW = 300      # "在线成人"判定窗口：最近 5 分钟内有过交互

_last_seen = {}                # {user_id: {"ts": 交互时间, "level": 当时等级}}
_pending_child_requests = {}   # 单队列：同一时刻最多一个待确认请求（内存态）

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



# @机器人提及文本形态（2026-10-02 紧急修复）：LLOneBot 部分版本 raw_message
# 的 @ 为纯文本"@小橘3号 指令"而非 CQ 码，指令精确/前缀匹配全部失效——
# 指令匹配前剥离（按 TRIGGER_WORDS 最长优先交替，避免"小橘"吃掉"小橘3号"）。
# 触发词之外补全名"小橘3号"（实测群里 @ 文本用的是全名）；最长优先交替，
# 避免"小橘"先吃掉"小橘3号"的前两个字。
_AT_BOT_MENTION_RE = re.compile(
    r"@\s*(?:" + "|".join(sorted(set(TRIGGER_WORDS) | {"小橘3号"},
                                 key=len, reverse=True)) + r")")


def _command_text_of(raw_message):
    """指令匹配文本：去 CQ 码 + 去 @机器人提及文本后 strip。

    仅供 handle_message 指令分流匹配使用；模型路径仍用清洗后 message
    （保留原文语义）。两种 @ 形态都覆盖：CQ 码形态（[CQ:at,qq=...]）与
    纯文本形态（"@小橘3号 指令"）。
    """
    text = _strip_cq(raw_message or "")
    return _AT_BOT_MENTION_RE.sub("", text).strip()


def _strip_think(text):
    """剥除 <think>...</think> 思维链包装块（含标签本体，DOTALL 跨行）。

    brain.smart_ask 的工具流程回复会在最前面包装 <think> 推理块，供新版
    网页前端（:5003 控制台）渲染折叠卡片；QQ 发送点（:5003 /onebot →
    OneBot，/send_image 的 CQ 码随回复链路发出同理）必须在发送前剥除——
    QQ 消息保持干净，推理展示只属于新前端。
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


# ================= 儿童锁（2026-10-02 权限重构批次②） =================
# 口径：儿童锁开启（CHILD_LOCK_ENABLED=true）时，被登记为儿童的用户
# （is_adult=False）触发危险家电控制 → 不执行工具，挂起请求并通知在线
# 成人 LV4（最近 5 分钟内有过交互且当时等级 ≥4）；/approve 代为执行（以
# 主人级权限），/deny 或 5 分钟超时 → 拒绝；无在线成人 → 直接拒绝。
# 网页控制台视为成人设备（is_console=True，不适用儿童锁等待）。

def _is_online_adult_lv4(user_id):
    """在线成人 LV4：最近 5 分钟内有过交互且当时等级 ≥ Lv.4。"""
    info = _last_seen.get(str(user_id or ""))
    if not info or time.time() - info.get("ts", 0) > ONLINE_ADULT_WINDOW:
        return False
    try:
        return permission_manager.level_value(info.get("level")) >= 4
    except Exception:
        return False


def _online_adult_lv4_ids():
    """全部在线成人 LV4 的 user_id 列表。"""
    return [uid for uid in list(_last_seen) if _is_online_adult_lv4(uid)]


def _notify_online_adults(text):
    """QQ 私聊所有在线成人 LV4（OneBot send_private_msg；失败仅日志）。"""
    for uid in _online_adult_lv4_ids():
        try:
            payload_uid = int(uid) if str(uid).isdigit() else uid
            requests.post(f"{ONEBOT_API_URL}/send_private_msg",
                          json={"user_id": payload_uid, "message": text},
                          timeout=5)
        except Exception as e:
            print(f"⚠️ [儿童锁] 成人通知失败（{uid}）: {e}")


def _smart_ask_with_child_lock(message, history, session_key, user_id):
    """smart_ask 包装：儿童锁开启时拦截儿童用户的危险家电控制调用。

    - 儿童锁关闭 / 操作者是成人 → 原样走 smart_ask（零开销零改动）；
    - 儿童用户触发危险 domain 控制（control_ha_device 危险实体）→ 工具
      不执行：有在线成人则挂起请求并 QQ 私聊通知（/approve //deny），
      无在线成人则直接返回拒绝文案（模型如实转告主人）；
    - 批准后由 /approve 以主人级权限代为执行（heartbeat 同款临时提权
      模式，执行完恢复）。
    """
    if not CHILD_LOCK_ENABLED or permission_manager.is_adult(user_id):
        res = smart_ask(message, history, session_key=session_key)
        return res[0] if isinstance(res, tuple) else res

    original_execute = brain.execute_tool

    def _child_lock_execute(tool_name, args, pm, credentials=None):
        if (tool_name == "control_ha_device"
                and home_tools.is_dangerous_entity((args or {}).get("entity_id"))):
            desc = (f"{(args or {}).get('action', '控制')} "
                    f"{(args or {}).get('entity_id', '危险设备')}")
            if not _online_adult_lv4_ids():
                print("🛑 [儿童锁] 无在线成人 LV4，直接拒绝儿童危险操作。")
                return "❌ 儿童锁已开启，且无成人 LV4 在线确认，操作已拒绝。"
            token = f"{random.randint(0, 999999):06d}"
            while token in _pending_child_requests:
                token = f"{random.randint(0, 999999):06d}"
            _pending_child_requests.clear()   # 单队列：同一时刻一个请求
            _pending_child_requests[token] = {
                "user_id": user_id,
                "tool_name": tool_name,
                "args": dict(args or {}),
                "desc": desc,
                "expires": time.time() + CHILD_LOCK_REQUEST_TTL,
            }
            _notify_online_adults(f"🔒 儿童操作请求：{desc}，"
                                  "5 分钟内回复 /approve 或 /deny")
            return "🔒 儿童锁已开启：该操作需成人确认，已通知在线成人，请稍等。"
        return original_execute(tool_name, args, pm, credentials)

    brain.execute_tool = _child_lock_execute
    try:
        res = smart_ask(message, history, session_key=session_key)
    finally:
        brain.execute_tool = original_execute
    return res[0] if isinstance(res, tuple) else res


def handle_child_command(message, user_id, is_console=False):
    """/approve //deny 儿童锁裁决（QQ 与网页控制台共用同一处理逻辑）。

    - 网页控制台视为成人设备（is_console=True，跳过在线成人资格校验）；
    - /approve：以主人级权限代为执行挂起操作（heartbeat 同款临时提权）；
    - /deny：拒绝并清空请求；超时请求同样拒绝（懒式判定）。
    返回回复文本；非本命令返回 None。
    """
    text = (message or "").strip()
    if text not in ("/approve", "/deny"):
        return None
    if not is_console and not _is_online_adult_lv4(user_id):
        return "❌ 只有在线成人 LV4 可以裁决儿童操作请求。"
    entry = next(iter(_pending_child_requests.values()), None)         if _pending_child_requests else None
    if entry is None:
        return "ℹ️ 当前没有待确认的儿童操作请求。"
    _pending_child_requests.clear()   # 单队列：裁决即清空（过期同样清空）
    if text == "/deny":
        print("🔒 [儿童锁] 成人已拒绝儿童操作请求。")
        return "✅ 已拒绝该儿童操作请求。"
    if time.time() > entry["expires"]:
        return "❌ 儿童操作请求已超时（5 分钟），已自动拒绝。"
    pm = permission_manager
    prev = pm.current_level
    try:
        pm.current_level = "Lv.4"   # 成人批准 → 以主人级权限代为执行
        result = execute_tool(entry["tool_name"], entry["args"], pm)
    finally:
        pm.current_level = prev
    print(f"🔒 [儿童锁] 成人已批准儿童操作请求：{entry['desc']}")
    return f"✅ 成人已确认，操作已执行：{result}"


def get_creator_name(base_dir=None):
    """创作者署名（xiaoju3_data/creator.json 存在即激活；缺省返回 ""）。

    只表现署名，不授予任何权限（权限由 LV4 决定）。公开版（无隔离区
    文件）返回空串，所有署名位置自动隐藏。base_dir 仅供测试注入临时
    目录（缺省 = 项目根下 xiaoju3_data）。
    """
    base = base_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "xiaoju3_data")
    path = os.path.join(base, "creator.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return str((data or {}).get("name") or "").strip()
    except Exception:
        return ""


def handle_creator_command():
    """/creator 命令：返回创作者署名卡（QQ 与网页控制台共用）。

    creator.json 存在 → 署名卡；缺失 → 开源项目链接。不要求任何权限
    （LV1 也可查）。
    """
    name = get_creator_name()
    if name:
        return f"🦊 小橘3号 · 由 {name} 创造与维护"
    return "🦊 小橘3号 · 开源项目（https://github.com/Xun201/xiaoju3-agent）"


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
    return _smart_ask_with_child_lock(message, history, session_key, user_id)


# ================= 核心内核（统一入口） =================
def handle_location_command(message):
    """位置指令（2026-10-02 隐私口径）：QQ 与网页共用同一处理逻辑。

    - /set_location <城市> [区县] → 写入本地位置记忆
      （agent_state/user_location.json，gitignore 不入库）；
    - /clear_location → 清除位置记录；
    - 命中返回回复文本；未命中返回 None（调用方继续走正常对话链路）。
    位置不上传 GitHub、不写 .env、不传云端（仅天气/本地搜索时用于拼 query）。
    """
    text = (message or "").strip()
    if text.startswith("/set_location"):
        arg = text[len("/set_location"):].strip()
        parts = arg.split()
        if not parts:
            return ("📍 用法：/set_location <城市> [区县]，"
                    "例如：/set_location 长沙 天心区")
        city = parts[0]
        district = parts[1] if len(parts) > 1 else None
        try:
            from agent_state.state_manager import save_user_location
            save_user_location(city, district)
        except Exception as e:
            return f"❌ 位置记录失败: {e}"
        shown = city + (f" {district}" if district else "")
        return (f"✅ 位置已记录：{shown}（仅存本地 agent_state/user_location.json，"
                "可用 /clear_location 清除）")
    if text.startswith("/clear_location"):
        try:
            from agent_state.state_manager import clear_user_location
            clear_user_location()
        except Exception as e:
            return f"❌ 位置记录清除失败: {e}"
        # 🚿 清除静默期（2026-10-02 用户口径）：历史消息里的位置仍会把小
        # 模型带偏（从历史推断位置继续用）——清除后 5 分钟内强制视为位置
        # 未知，确保 AI 重新询问（brain 内存标记，不落盘）
        try:
            import brain
            brain.mark_location_cleared()
            brain.clear_waiting_location()   # 遗留的等待回答窗口一并关闭
        except Exception as mark_err:
            print(f"⚠️ 位置静默期标记失败（不影响清除）: {mark_err}")
        return "✅ 位置记录已清除（本地 agent_state/user_location.json）"
    return None


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

    # 🎯 指令匹配文本（2026-10-02 紧急修复）：去 CQ 码 + 去开头 @机器人
    # 提及文本（LLOneBot 部分版本 raw_message 的 @ 为纯文本形态而非 CQ 码，
    # 实测群里 @小橘3号 + 指令 全部失效落模型）。仅供下方指令分流匹配；
    # 模型路径仍用清洗后 message（保留原文语义）。
    command_text = _command_text_of(raw_message)
    if command_text.startswith("/"):
        print(f"[指令路由] 收到指令: {command_text[:60]}")

    # === 🧹 一键清空记忆（/clear、/reset、清空记忆、重置记忆） ===
    # 精确匹配（清洗后全等）：不误吞更长的 /reset_fuse，也不误伤含"清空记忆"
    # 字样的普通对话。内存列表与磁盘文件双清——只清文件不清内存的话，本会话
    # 记忆并未消失，下一轮 _compress_and_save 又会把旧历史写回文件。
    # 内存仅保留置顶系统提示词（通道历史恒以 system 开头的不变量不破坏）。
    global messages_web, messages_qq
    if command_text in ("/clear", "/reset", "清空记忆", "重置记忆"):
        if source == 'web':
            messages_web[:] = [SYSTEM_PROMPT]
            save_memory([], MEMORY_FILE_WEB)          # 文件内容置空数组 []
        else:
            messages_qq[:] = [SYSTEM_PROMPT]
            save_memory([], MEMORY_FILE_QQ)
        return "✨ 记忆已清空！我现在的大脑非常干净，可以重新开始对话了。"

    user_key = str(user_id)
    # 🔒 儿童锁在线判定数据源：每次交互刷新最近活跃时间与当时等级（在线
    # 成人 = 最近 5 分钟内有过交互且当时等级 ≥ Lv.4）
    _last_seen[user_key] = {"ts": time.time(),
                            "level": permission_manager.current_level}

    # === 📍 位置指令（/set_location /clear_location，QQ 与网页共用逻辑） ===
    # 2026-10-02 隐私口径：位置存本地 agent_state/user_location.json（不写
    # .env、不入库），网页端经 dashboard /api/chat 调同一 helper
    location_reply = handle_location_command(command_text)
    if location_reply is not None:
        return location_reply

    # === ✍️ 创作者署名命令（/creator，QQ 与网页共用，批次②） ===
    # 2026-10-02 修复：QQ 群 @ 消息清洗后残留 "CQ:at,qq=xxx" 前缀，
    # 清洗文本精确匹配失效（实测落模型瞎编）——改用去 CQ 码后的
    # raw_message 精确匹配，群内 @/creator 与私聊 /creator 均命中
    if command_text == "/creator":
        return handle_creator_command()

    # === 🔒 儿童锁裁决（/approve /deny，QQ 与网页共用，批次②） ===
    child_reply = handle_child_command(command_text, user_key)
    if child_reply is not None:
        return child_reply

    # === 🛡️ 指令菜单 ===
    if command_text in ["/help", "菜单", "帮助", "指令"]:
        from plugins.help_menu import get_help_menu
        return get_help_menu(permission_manager.current_level)

    # === 🛡️ Lv.2 注册（§7：env 注册密码校验，等级落盘） ===
    if command_text.startswith("/register"):
        arg = _arg_after(raw_message, "/register").strip()
        parts = arg.split(None, 1)
        password = parts[0] if parts else ""
        name = parts[1].strip() if len(parts) > 1 else None
        return permission_manager.register_user(user_key, password, name=name)

    if command_text.startswith("/name"):
        return permission_manager.claim_name(user_key, _arg_after(raw_message, "/name"))

    # === 🛡️ Lv.3 TOTP 动态密码激活（等级持久化接线，修复"重启回落"） ===
    if command_text.startswith("/coder_auth"):
        return permission_manager.activate_lv3(user_key, _arg_after(raw_message, "/coder_auth"))

    # === 🛡️ /sudo：开启 120 秒写操作窗口（与工具链门禁同为缺省用户口径） ===
    if command_text.startswith("/sudo"):
        code = _arg_after(raw_message, "/sudo")
        if not code:
            return ("用法：/sudo <6位动态密码>——开启 120 秒写操作窗口（Lv.3 已可直接写文件，本指令为兼容保留），"
                    "窗口内写文件/写代码无需逐次输入动态密码。")
        return permission_manager.open_operation_window(None, totp_code=code)

    # === 🛡️ /lv4_auth 两步流：类 Root 警告 → 双因子 confirm 授权 ===
    if command_text.startswith("/lv4_auth"):
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
            # （2026-10-02 权限重构）授权级验证保留；授权后操作不再逐次
            # 验证，操作级双因子会话已随 /confirm 令牌流一并删除
            return permission_manager.grant_lv4(user_key, credentials)
        return "用法：/lv4_auth 查看类 Root 警告；/lv4_auth confirm <6位动态密码> 完成授权。"

    # === 🛡️ /lv4_revoke：撤销主人级权限（立即生效） ===
    if command_text.startswith("/lv4_revoke"):
        return permission_manager.revoke_lv4(user_key)

    # === ⛔ /reset_fuse：防死循环熔断重置（Lv.2+，管理员口径全通道清零） ===
    if command_text.startswith("/reset_fuse"):
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

    # === 🛡️ 发送图片指令（2026-10-02 权限重构：LV4 主人级专属） ===
    if command_text.startswith("/send_image"):
        if permission_manager.level_value() < 4:
            return "❌ 权限不足，发图需要 Lv.4（主人级）权限。请先 /lv4_auth confirm <6位动态密码> 授权。"
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
        # 📍 等待位置回答窗口判定（2026-10-02 排查加固：判定与组合提取
        # 全程 try/except，任何异常不阻塞原 @ 规则）
        waiting_active = False
        city, district = "", ""
        try:
            waiting_active = brain._waiting_location_active()
            if waiting_active:
                city, district = brain._find_city_district(message)
        except Exception as loc_err:
            print(f"⚠️ [位置] 等待窗口/位置组合判定异常: {loc_err}")
        print(f"📨 [群聊] 收到消息: 内容={message[:50]}, "
              f"是否在等待窗口内={waiting_active}, "
              f"是否含位置组合={bool(city)}, 是否含区县={bool(district)}")
        if not (is_at_me or has_trigger_word):
            # 📍 等待位置回答窗口（群聊体验修复）：AI 刚问过位置（5 分钟
            # 窗口内），用户自然回答（"长沙天心区"/只回"长沙"）不再被防
            # 刷屏规则挡掉——消息含城市（区县可选）即放行进正常处理链路
            #（smart_ask 起步提取写入；只回城市时模型会继续追问区县）。
            # 已在 handle_message 内：不 return "" 即为放行（等效递归）
            if waiting_active and city:
                print("📍 [位置] 等待回答窗口内，绕过 @ 判断，尝试提取位置")
            else:
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

# ================= QQ大门（业务体；HTTP 视图宿主于 :5003） =================
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


def onebot_event(data):
    """处理一条 OneBot 11 webhook 事件字典，返回 HTTP JSON 响应体。

    原 :5002 POST /onebot 视图主体原样迁入（架构合并，逻辑一字未改）；
    HTTP 层（JSON 解析、meta_event 心跳日志标记、Flask 路由）由 :5003
    xiaoju3_dashboard.py 的 onebot_webhook 视图承担后调进本函数。
    """
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


# ================= 后台线程启动点（宿主：:5003 dashboard 进程） =================
def start_background_services():
    """启动 QQ 接入层的后台服务线程（原 :5002 __main__ 启动点，随架构合并
    移交 :5003 dashboard 进程在启动时调用；重复调用会重复拉心跳，勿多次调用）。

    - 💓 主动心跳引擎（heartbeat.start_heartbeat daemon 线程）；
    - 👀 多设备互相守望（架构 §8，默认关闭）：env XIAOJU3_PEERS 配置对端
      且 XIAOJU3_WATCH=1 时才启动守护线程（migration.PeerWatch）。
    """
    start_heartbeat()

    if _peer_watch_enabled():
        threading.Thread(target=PeerWatch().watch_loop, daemon=True,
                         name="xiaoju3-peer-watch").start()
        print(f"👀 多设备互相守望已启动（对端：{os.environ['XIAOJU3_PEERS'].strip()}）")


if __name__ == '__main__':
    # 🚧 架构合并（5002 → 5003）：本模块已无 HTTP 入口，直接运行只会得到迁移
    # 提示——QQ webhook 与网页控制台统一由 :5003 xiaoju3_dashboard.py 承载。
    print("🚧 本模块已并入 5003（5002 端口已废弃）：请运行 python xiaoju3_dashboard.py")
    print("💡 QQ webhook 新地址：http://127.0.0.1:5003/onebot（请同步修改 LLOneBot 上报地址）")
