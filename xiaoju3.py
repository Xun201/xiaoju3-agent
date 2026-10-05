#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小橘3号 · 终端 CLI 与统一配置源。

按《架构设计文档》§3.6：本地/云端地址与模型、记忆上限、工作区等配置
统一定义于本文件顶部；CLOUD_KEY 等密钥经环境变量从隔离区 .env 读取，
不入仓库。CLI 交互全部位于 `if __name__ == "__main__":` 内，保证其他
模块 `from xiaoju3 import ...` 时零副作用。
"""
import os
import re
import shutil

import paths  # 双根路径锚（docs/EXE_PACKAGING_PLAN.md §1）：数据根=可写持久，非 frozen 与项目根同值

# ---------------------------------------------------------------------------
# .env 加载器（stdlib 极简实现）：项目根 .env 中 KEY=VALUE 注入环境变量，
# 已存在的环境变量优先，不被覆盖。
# ---------------------------------------------------------------------------


# 敏感配置隔离区：.env 统一放在数据根的 xiaoju3_data/ 下（与 Linux 端一致），
# 路径基于双根的 DATA_ROOT 推导（非 frozen 即项目根），Windows / Linux 通用，
# 不写死任何绝对路径。
ENV_FILE = os.path.join(paths.DATA_ROOT,
                        "xiaoju3_data", ".env")
# 迁移期兼容：旧版把 .env 放在项目根，存在时仍可读取（并提示迁移）
_LEGACY_ENV_FILE = os.path.join(paths.DATA_ROOT, ".env")

# .env 写入白名单（安装器方案步 A2）：与 .env.example 键集严格一致（tests/
# test_first_run.py 防漂移锚锁定），越界键一律拒绝——防任意配置覆盖。
# 键集来源：.env.example 实测 39 键（2026-10-03）；增删 .env.example 键时
# 必须同步本集合（测试会红）。
ENV_WRITE_ALLOWLIST = frozenset({
    "DEEPSEEK_API_KEY", "LOCAL_URL", "LOCAL_PROBE_URL", "LOCAL_MODEL",
    "CLOUD_URL", "CLOUD_MODEL", "WEB_API_KEY", "HA_URL", "HA_TOKEN",
    "VISION_MODEL", "VISION_KEY", "VISION_API_URL", "TOOL_FUSE_LIMIT",
    "LOCAL_GENERATE_TIMEOUT", "XIAOJU3_ACCOUNT_BOOK", "XIAOJU3_MODEL_ROUTE",
    "XIAOJU3_TOTP_SECRET", "XIAOJU3_REGISTER_PASSWORD", "PEER_DEVICE_URL",
    "XIAOJU3_PEERS", "XIAOJU3_HUMIDITY_THRESHOLD", "XIAOJU3_BIOMETRIC_SIM",
    "XIAOJU3_WATCH", "SEARCH_ENGINE", "SERPER_API_KEY", "TAVILY_API_KEY",
    "USER_CITY", "USER_DISTRICT", "XIAOJU3_PERSONALITY", "NAPCAT_DIR",
    "DANGER_ENTITIES", "CHILD_LOCK_ENABLED", "DEVICE_TIER",
    "LOCAL_MODEL_SMALL", "XIAOJU3_CREATOR_DEVICE", "XIAOJU3_OWNER_QQ",
    "ONEBOT_API_URL", "ONEBOT_TOKEN", "TTS_VOICE",
})


def _quote_env_value(value):
    """写入值加引号策略：空串或含空白/#/引号的值包双引号（_load_env_file
    读取端会剥首尾引号，往返无损）；引导键集（key/URL/城市）不含引号。"""
    v = str(value).strip()
    if v == "" or any(ch in v for ch in (" ", "\t", "#", '"', "'")):
        return f'"{v}"'
    return v


def save_env_file(updates, path=None, backup=True):
    """写 .env（首装引导/设置变更专用，安装器方案步 A2）——与
    _load_env_file 只读加载对称的**唯一**写入入口。

    四条防线：
    1. 白名单：updates 里非 ENV_WRITE_ALLOWLIST 的键一律拒绝（进 skipped
       返回，不抛错——调用方决定如何提示），防任意配置覆盖；
    2. 单槽备份：backup=True 且文件已存在时先轮换为 <path>.bak（不积累
       密钥副本，敏感面最小）；
    3. 原子落盘：写 <path>.tmp 后 os.replace（Windows 原子），写失败清理
       tmp 并抛原 OSError——绝不留半截 .env 毒化下次启动；
    4. 增量合并：逐行保留未提及键与注释/顺序（行级替换，非全量重写），
       新键追加文件尾；同值重复写内容逐字节不变（幂等）。

    并发口径：写者收敛为 desktop 角色引导/设置 UI 单点，launcher/dashboard
    终生不写；跨进程竞态取"最后写入者胜"（详见 INSTALLER_STEP_A_DESIGN §2.4）。

    返回 (written_keys, skipped_keys, backup_path_or_None)。
    写失败抛 OSError（调用方必须提示用户，绝不静默）。
    """
    if path is None:
        path = ENV_FILE
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    written, skipped, clean = [], [], {}
    for key, value in dict(updates or {}).items():
        k = str(key).strip()
        if k in ENV_WRITE_ALLOWLIST:
            clean[k] = _quote_env_value(value)
            written.append(k)
        else:
            skipped.append(k)

    backup_path = None
    if backup and os.path.exists(path):
        backup_path = path + ".bak"
        shutil.copy2(path, backup_path)

    lines = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    key_re = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
    seen = set()
    out = []
    for line in lines:
        m = key_re.match(line)
        if m and m.group(1) in clean:
            out.append(f"{m.group(1)}={clean[m.group(1)]}")
            seen.add(m.group(1))
        else:
            out.append(line)
    for key in clean:
        if key not in seen:
            out.append(f"{key}={clean[key]}")

    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + ("\n" if out else ""))
        os.replace(tmp, path)
    except OSError:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise
    return written, skipped, backup_path


def _load_env_file(path=None):
    """极简 .env 加载器：KEY=VALUE 注入环境变量，已存在的环境变量优先。

    - 默认读隔离区 ENV_FILE（xiaoju3_data/.env）；隔离区不存在而旧根目录 .env
      存在时回退读取并打印一次性迁移提示；
    - 加固：utf-8-sig（容忍记事本保存的 BOM）、跳过 "export " 前缀、
      键值两侧空白与成对引号剥除。
    """
    if path is None:
        if os.path.exists(ENV_FILE):
            path = ENV_FILE
        elif os.path.exists(_LEGACY_ENV_FILE):
            path = _LEGACY_ENV_FILE
            print("⚠️ 检测到旧版根目录 .env：请迁移到 xiaoju3_data/.env"
                  "（隔离区）。本次仍按旧路径读取。")
        else:
            return
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


_load_env_file()

# ---------------------------------------------------------------------------
# 统一配置（全部可被环境变量覆盖；默认值为中立值，不指向任何内网地址）
# ---------------------------------------------------------------------------

# 本地 Ollama
LOCAL_URL = os.environ.get("LOCAL_URL", "http://127.0.0.1:11434/api/chat")
LOCAL_PROBE_URL = os.environ.get("LOCAL_PROBE_URL", "http://127.0.0.1:11434/")
LOCAL_MODEL = os.environ.get("LOCAL_MODEL", "qwen2.5:7b")
# 本地探测超时（秒），文档 §3：约 1 秒
LOCAL_TIMEOUT = float(os.environ.get("LOCAL_TIMEOUT", "1"))

# 云端 DeepSeek（密钥只从环境变量/.env 读取，不入仓库）
CLOUD_URL = os.environ.get("CLOUD_URL", "https://api.deepseek.com/chat/completions")
CLOUD_MODEL = os.environ.get("CLOUD_MODEL", "deepseek-chat")
CLOUD_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

# 云端余额查询端点（监控仪表盘用）
CLOUD_BALANCE_URL = os.environ.get(
    "CLOUD_BALANCE_URL", "https://api.deepseek.com/user/balance"
)

# 视觉模型（安卓视觉点击用）
VISION_MODEL = os.environ.get("VISION_MODEL", "")
VISION_KEY = os.environ.get("VISION_KEY", "")
# 视觉模型 API Base URL：阿里云新版百炼业务空间 Key 需填专属域名
# （如 https://<空间ID>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1），
# 未配置时回退 DashScope 旧通用地址。
# 前缀自动容错（2026-09-30 用户指令）：值 strip 后不以 http:// 或 https://
# 开头（大小写不敏感）则自动补 https:// 前缀，防裸域名/漏写前缀导致
# SDK base_url 解析失败；空值（含纯空白）仍走缺省 DashScope 地址。
_VISION_API_URL_RAW = os.environ.get("VISION_API_URL", "").strip()
if _VISION_API_URL_RAW.lower().startswith(("http://", "https://")):
    VISION_API_URL = _VISION_API_URL_RAW
elif _VISION_API_URL_RAW:
    VISION_API_URL = "https://" + _VISION_API_URL_RAW
else:
    VISION_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# OneBot 11 HTTP API（QQ 接入层 webhook 回发消息用；2026-10-01 迁移至
# LLOneBot，标准正向 HTTP 端口 3001，NapCat 用户改回 3000 即可）。
# env 优先读 ONEBOT_API_URL / ONEBOT_TOKEN，兼容回退旧 NAPCAT_* 键；
# 令牌未配置时为空（与参考口径一致，Bearer 头传空）。
ONEBOT_API_URL = (os.environ.get("ONEBOT_API_URL", "").strip()
                  or os.environ.get("NAPCAT_API_URL", "").strip()
                  or "http://127.0.0.1:3001")
ONEBOT_TOKEN = (os.environ.get("ONEBOT_TOKEN", "").strip()
                or os.environ.get("NAPCAT_TOKEN", "").strip())

# 工作区（文件读写沙箱根目录，惰性创建）
# PROJECT_ROOT 保名重定义（方案 §1.1）：= paths.DATA_ROOT（数据根）——
# WORKSPACE / AGENT_STATE_DIR 等派生锚随之归位；非 frozen 下两根同值，行为不变。
PROJECT_ROOT = paths.DATA_ROOT
WORKSPACE = os.environ.get("WORKSPACE", os.path.join(PROJECT_ROOT, "workspace"))

# 会话记忆
MAX_MESSAGES = int(os.environ.get("MAX_MESSAGES", "50"))

# 版本号（单一事实源，安装器方案步 A1：/api/status 下发、前端徽标、
# build_exe.bat 构建时抓取注入 spec/Inno——手写处仅此一处）
XIAOJU3_VERSION = "1.0.4"

# 状态目录（会话记忆 / 身份 / 长期记忆库）
AGENT_STATE_DIR = os.environ.get(
    "AGENT_STATE_DIR", os.path.join(PROJECT_ROOT, "agent_state")
)

# 网页控制台 API Key（POST /chat 校验 X-API-Key）
WEB_API_KEY = os.environ.get("WEB_API_KEY", "changeme-xiaoju3")

# Home Assistant
HA_URL = os.environ.get("HA_URL", "")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

# 用户默认位置（搜索指代消解用，2026-10-02：weather/新闻等裸词 query 补全
# 地点，brain._inject_location 消费；用户在对话里说的地点优先于本配置）
USER_CITY = os.environ.get("USER_CITY", "")
USER_DISTRICT = os.environ.get("USER_DISTRICT", "")

# 赤狐性格开关与浓度（2026-10-02：off=纯通用助手 / low=精简 / medium=完整
# （默认）/ high=强化；prompts 按档位动态拼装【赤狐性格设定】段，硬规则
# 各段不受档位影响）
XIAOJU3_PERSONALITY = os.environ.get("XIAOJU3_PERSONALITY", "medium")

# NapCat 安装目录（2026-10-02：统一启动器无黑框静默拉起 QQ 接入层用；
# Windows-only——POSIX（香橙派）NapCat 由部署侧另行管理）
NAPCAT_DIR = os.environ.get("NAPCAT_DIR", "D:\\NapCat")

# 儿童锁（2026-10-02 权限重构批次②）：true 时被登记为儿童的用户
# （identity.json is_adults）执行危险家电操作需在线成人 LV4 确认
CHILD_LOCK_ENABLED = os.environ.get("CHILD_LOCK_ENABLED", "false").lower() == "true"

# 心跳轮询间隔（秒），文档 §7：60 秒
HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "60"))

# 5003 监控仪表盘端口
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "5003"))

# 前端 TTS 音色（可选，留空则由浏览器自动选择；仪表盘 /api/status 下发 tts_voice）
TTS_VOICE = os.environ.get("TTS_VOICE", "")

# 硬件自适应路由（high=游戏本/满血：本地大模型优先、汇总走本地；medium=普通本/
# 混合：本地小模型优先、汇总走云端；low=轻薄本/开发板/云端优先：跳过本地探测）
# auto（默认）= 经 hardware_profiler 自动探测硬件并缓存结果
DEVICE_TIER = os.environ.get("DEVICE_TIER", "auto")

# medium 档使用的本地小模型
LOCAL_MODEL_SMALL = os.environ.get("LOCAL_MODEL_SMALL", "qwen2.5:0.5b")

# QQ 群聊触发词（文档 §2.3 / 界面文档 §2.3）
TRIGGER_WORDS = ["小橘", "小桔", "橘3号", "橘三号", "AI测试"]


def ensure_workspace():
    """确保工作区目录存在（惰性创建）。"""
    os.makedirs(WORKSPACE, exist_ok=True)
    return WORKSPACE


# ---------------------------------------------------------------------------
# 终端 CLI（架构设计文档 §2/§3：与 brain.py 平行的一套 ask_local/ask_cloud/
# smart_ask 实现，云端最多 3 次重试）。本区所有函数仅在
# `if __name__ == "__main__":` 的 REPL 中被调用，import 本模块零副作用。
# ---------------------------------------------------------------------------
import json
import time

import requests

# CLI 本地生成超时（秒）：顶部 LOCAL_TIMEOUT（1 秒）仅用于在线探测口径，
# 本地生成更耗时，参考实现取 30 秒。
CLI_LOCAL_TIMEOUT = float(os.environ.get("CLI_LOCAL_TIMEOUT", "30"))

# CLI 会话记忆：与 history_qq / history_web 并行的终端通道（已入 .gitignore）。
# 跨组契约（2026-10-01）：文件统一为 agent_state/history_terminal.json，
# 格式与 main.py 通道 history_web.json 完全一致（brain.save_memory 口径：
# 纯 [{role, content}] JSON 列表）；网页控制台
# GET /api/history?source=terminal 直接读取本文件展示终端聊天记录。
CLI_MEMORY_FILE = os.path.join(AGENT_STATE_DIR, "history_terminal.json")


def _fallback_system_prompt():
    """参考 CLI 的精简系统提示词（prompts.py 缺席时的兜底）。

    主人称呼动态取自权限模块（仅创造者设备为创造者名，其余泛称"主人"），
    公开代码不得把创造者名硬编码为全局默认主人名。
    """
    try:
        from permission import default_master_name as _dmn
        master = _dmn()
    except Exception:
        master = "主人"
    return {
        "role": "system",
        "content": f"""你叫小橘3号，是由{master}的专属私人助理。{master}是你唯一的主人。你的工作区在 {WORKSPACE}。语气活泼幽默，喜欢用颜文字。

【重要规则】你只能基于你的内部知识回答。如果你不知道答案，或者问题涉及实时天气、最新新闻、超出你知识范围的内容，你【必须】直接回答："这个问题我需要云端大脑来回答，请切换。"绝对不允许自己编造、虚构数据！

【工具调用规则】你拥有以下工具，可以帮{master}管理文件：
1. list_files - 列出工作区内的所有文件。参数：无
2. read_file - 读取工作区内指定文件的内容。参数：filename (文件名)
3. write_file - 在工作区内创建一个新文件并写入内容。参数：filename (文件名), content (文件内容)

如果你需要使用工具，请【只输出】一行 JSON，不要有任何其他文字！格式必须严格如下：
{{"tool": "list_files", "args": {{}}}}
{{"tool": "read_file", "args": {{"filename": "test.txt"}}}}
{{"tool": "write_file", "args": {{"filename": "test.txt", "content": "hello"}}}}

如果不需要使用工具，就直接正常回答{master}。"""
    }


def _get_system_prompt():
    """CLI 系统提示词：优先项目统一版 prompts.SYSTEM_PROMPT（10 项工具协议）。"""
    try:
        import prompts
        return prompts.SYSTEM_PROMPT
    except Exception:
        return _fallback_system_prompt()


def load_memory():
    """启动时读取 CLI 会话历史（参考实现：system 提示词 + 历史）。"""
    if os.path.exists(CLI_MEMORY_FILE):
        try:
            with open(CLI_MEMORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
                print(f"📖 已加载 {len(history)} 条历史记忆。")
                return [_get_system_prompt()] + history
        except Exception as e:
            print(f"⚠️ 记忆读取失败：{e}")
    return [_get_system_prompt()]


def save_memory(messages):
    """退出/每轮后保存会话，滚动保留最近 MAX_MESSAGES 条（不含 system）。

    落盘口径与 brain.save_memory（history_web.json 通道）逐字对齐：纯
    [{role, content}] JSON 列表、ensure_ascii=False、indent=2。写入经
    临时文件 + os.replace 原子替换（与 tools.record_recent_action 同法，
    不留半截文件）；任何异常只打警告，绝不中断对话。
    """
    history_to_save = [m for m in messages if m.get("role") != "system"]
    if len(history_to_save) > MAX_MESSAGES:
        history_to_save = history_to_save[-MAX_MESSAGES:]
    tmp_path = None
    try:
        os.makedirs(AGENT_STATE_DIR, exist_ok=True)
        tmp_path = CLI_MEMORY_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(history_to_save, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, CLI_MEMORY_FILE)
    except Exception as e:
        # 半成品清理：替换失败时删除残留 .tmp，避免污染隔离区
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        print(f"⚠️ 记忆保存失败：{e}")


def _builtin_execute_tool(tool_name, args):
    """内置文件工具三件套（参考 CLI 的平行实现，跨平台版）。

    统一工具层 tools.py 缺席时的兜底；安全口径与 tools.py 一致：
    realpath 前缀校验限制在 WORKSPACE 内，read_file 截断 1000 字符。
    """
    try:
        base = os.path.realpath(WORKSPACE)

        if tool_name == "list_files":
            try:
                names = sorted(os.listdir(WORKSPACE))
            except OSError:
                names = []
            return "\n".join(names) if names else "（工作区为空）"

        elif tool_name == "read_file":
            filepath = os.path.join(WORKSPACE, args["filename"])
            # 防止通过 ../ 跨越目录
            if not os.path.realpath(filepath).startswith(base + os.sep):
                return "❌ 安全拒绝：你不允许访问工作区以外的文件！"
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    return f.read()[:1000]  # 最多读 1000 字
            return f"文件 {args['filename']} 不存在。"

        elif tool_name == "write_file":
            filepath = os.path.join(WORKSPACE, args["filename"])
            if not os.path.realpath(filepath).startswith(base + os.sep):
                return "❌ 安全拒绝：你不允许访问工作区以外的文件！"
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(args["content"])
            return f"✅ 文件 {args['filename']} 写入成功！"

        return "未知工具"
    except Exception as e:
        return f"工具执行失败: {e}"


def execute_tool(tool_name, args):
    """CLI 工具执行：优先接入统一工具层 tools.execute_tool（10 项白名单 +
    LV3 高危门禁，架构设计文档 §5 唯一入口）；统一工具层缺席时（如依赖
    未部署）回退内置文件三件套，保持参考 CLI 可独立运行。"""
    try:
        from tools import execute_tool as _unified_execute
        from permission import permission_manager
        return _unified_execute(tool_name, args, permission_manager)
    except ImportError:
        return _builtin_execute_tool(tool_name, args)
    except Exception as e:
        return f"工具执行失败: {e}"


def _master_label():
    """REPL 输入提示的主人称呼（延迟导入，保持 import 零副作用）。"""
    try:
        from permission import default_master_name
        return default_master_name()
    except Exception:
        return "用户"


def ask_local(messages):
    """本地 Ollama 推理（与 brain.ask_local 同构）。

    keep_alive=-1：模型常驻显存/内存，避免每次请求重新加载导致 5-8 秒卡顿。
    """
    payload = {"model": LOCAL_MODEL, "messages": messages,
               "stream": False, "keep_alive": -1}
    response = requests.post(LOCAL_URL, json=payload, timeout=CLI_LOCAL_TIMEOUT)
    response.raise_for_status()
    return response.json()["message"]["content"]


def ask_cloud(messages):
    """云端 DeepSeek 兜底，最多重试 3 次（架构设计文档 §3.5）。"""
    headers = {"Authorization": f"Bearer {CLOUD_KEY}", "Content-Type": "application/json"}
    payload = {"model": CLOUD_MODEL, "messages": messages, "stream": False}

    for attempt in range(3):
        try:
            response = requests.post(CLOUD_URL, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            resp_json = response.json()

            if "choices" in resp_json:
                return resp_json["choices"][0]["message"]["content"]
            else:
                error_detail = resp_json.get("error", {}).get("message", "未知错误")
                return f"⚠️ API返回错误：{error_detail}"

        except Exception as e:
            print(f"⚠️ 真实 API 报错 (第 {attempt + 1} 次尝试): {e}")
            if attempt == 2:  # 第 3 次仍失败，返回优雅提示
                return "⚠️ 云端大脑开小差了，请稍后再试~"
            time.sleep(2)  # 休息 2 秒后重试


def smart_ask(messages):
    """终端版智能路由 + 工具调用拦截（本地优先，异常热切换云端）。"""
    try:
        # 优先使用本地大脑，本地不行再切云端
        print("🏠 正在询问本地大脑...")
        try:
            raw_reply = ask_local(messages)
        except Exception as e:
            print(f"⚠️ 本地失败（{e}），切云端...")
            raw_reply = ask_cloud(messages)
            return raw_reply, "☁️ 云端"

        # 检查它是不是想用工具（看有没有输出 JSON）
        raw_reply = raw_reply.strip()
        if raw_reply.startswith("{") and raw_reply.endswith("}"):
            try:
                tool_call = json.loads(raw_reply)
                tool_name = tool_call.get("tool")
                tool_args = tool_call.get("args", {})
                print(f"🔧 小橘3号正在使用工具: {tool_name}...")
                tool_result = execute_tool(tool_name, tool_args)
                print(f"📄 工具返回结果: {tool_result[:200]}...")

                # 将工具结果喂回给模型，让它组织语言回答
                messages.append({"role": "assistant", "content": raw_reply})
                messages.append({"role": "system", "content": f"工具执行结果：{tool_result}"})

                final_reply = ask_local(messages)
                return final_reply, "🏠 本地 (工具)"
            except Exception as e:
                print(f"⚠️ 工具调用解析失败: {e}")
                pass  # 解析失败就当普通回复处理

        return raw_reply, "🏠 本地"
    except Exception as e:
        return f"❌ 出错: {e}", "❌ 失败"


def _current_level():
    """当前权限等级（permission_manager 缺席时回退 Lv.1）。"""
    try:
        from permission import permission_manager
        return permission_manager.current_level
    except Exception:
        return "Lv.1"


def _get_help_menu():
    """按当前权限等级渲染指令菜单（功能文档 §2.4）。

    优先使用 help_menu 插件（与 QQ/网页端同源）；插件缺席时内置兜底菜单。
    """
    level = _current_level()
    try:
        from plugins.help_menu import get_help_menu
        return get_help_menu(level)
    except Exception:
        return (
            "📋 小橘3号 指令菜单\n\n"
            "【基础指令】\n"
            "· /help 或 菜单/帮助/指令：查看此菜单\n"
            "· /gen_log <DeepSeek分享链接>：抓取链接自动生成开发日志\n"
            "· /todo_from_link <DeepSeek分享链接>：抓取链接自动记待办\n"
            "· /todos：查看待办清单（/todos done <编号> 标记完成）\n"
            "· /exit：保存记忆并退出\n\n"
            "---\n"
            f"你当前的权限等级：{level}\n"
            "如需升级权限，请使用上面对应的指令。"
        )


def _run_gen_log(url):
    """处理 /gen_log <分享链接>：校验前缀后交 run_link_log 编排（功能文档 §6）。"""
    if not url.startswith("https://chat.deepseek.com/share/"):
        print("⚠️ 请提供正确的 DeepSeek 分享链接，格式：/gen_log https://chat.deepseek.com/share/...")
        return
    print("🔄 收到链接！小橘3号开始抓取与总结（大约需要 1 分钟），完成后日志自动保存到 dev_logs/ ...")
    try:
        import run_link_log
        run_link_log.run_link_log(url)
    except Exception as e:
        print(f"❌ 日志生成失败：{e}")


def main():
    """终端 REPL 入口：/help 菜单、/gen_log 日志生成、/exit 退出。"""
    messages = load_memory()
    print("🤖 小橘3号（终端版）已上线！输入 /help 查看菜单，/exit 退出。")
    print("💡 你可以说：帮我看看工作区有什么文件？")

    while True:
        try:
            user_input = input(f"\n{_master_label()}: ")
        except (EOFError, KeyboardInterrupt):
            print()
            save_memory(messages)
            print("💾 记忆已保存。")
            break

        text = user_input.strip()
        if text.lower() in ("exit", "/exit"):
            save_memory(messages)
            print("💾 记忆已保存。")
            break
        if not text:
            continue

        # 内置指令：指令菜单（/help 或 菜单/帮助/指令）
        if text in ("/help", "菜单", "帮助", "指令"):
            print(_get_help_menu())
            continue

        # 内置指令：开发日志自动生成（/gen_log <分享链接>）
        if text.startswith("/gen_log"):
            _run_gen_log(text.split("/gen_log", 1)[-1].strip())
            continue

        messages.append({"role": "user", "content": text})
        reply, source = smart_ask(messages)
        print(f"\n🤖 小橘3号 [{source}]: {reply}")
        messages.append({"role": "assistant", "content": reply})
        save_memory(messages)


if __name__ == "__main__":
    raise SystemExit(main())
