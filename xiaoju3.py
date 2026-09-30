#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小橘3号 · 终端 CLI 与统一配置源。

按《架构设计文档》§3.6：本地/云端地址与模型、记忆上限、工作区等配置
统一定义于本文件顶部；CLOUD_KEY 等密钥经环境变量从隔离区 .env 读取，
不入仓库。CLI 交互全部位于 `if __name__ == "__main__":` 内，保证其他
模块 `from xiaoju3 import ...` 时零副作用。
"""
import os

# ---------------------------------------------------------------------------
# .env 加载器（stdlib 极简实现）：项目根 .env 中 KEY=VALUE 注入环境变量，
# 已存在的环境变量优先，不被覆盖。
# ---------------------------------------------------------------------------


def _load_env_file(path=None):
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
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

# 工作区（文件读写沙箱根目录，惰性创建）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.environ.get("WORKSPACE", os.path.join(PROJECT_ROOT, "workspace"))

# 会话记忆
MAX_MESSAGES = int(os.environ.get("MAX_MESSAGES", "50"))

# 状态目录（会话记忆 / 身份 / 长期记忆库）
AGENT_STATE_DIR = os.environ.get(
    "AGENT_STATE_DIR", os.path.join(PROJECT_ROOT, "agent_state")
)

# 网页控制台 API Key（POST /chat 校验 X-API-Key）
WEB_API_KEY = os.environ.get("WEB_API_KEY", "changeme-xiaoju3")

# Home Assistant
HA_URL = os.environ.get("HA_URL", "")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

# 心跳轮询间隔（秒），文档 §7：60 秒
HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "60"))

# 5003 监控仪表盘端口
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "5003"))

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

# CLI 会话记忆：与 history_qq / history_web 并行的终端通道（已入 .gitignore）
CLI_MEMORY_FILE = os.path.join(AGENT_STATE_DIR, "history_cli.json")


def _fallback_system_prompt():
    """参考 CLI 的精简系统提示词（prompts.py 缺席时的兜底）。"""
    return {
        "role": "system",
        "content": f"""你叫小橘3号，是由XUN亲手创造的专属私人助理。XUN是你唯一的主人，也是你唯一的创造者。你的工作区在 {WORKSPACE}。语气活泼幽默，喜欢用颜文字。

【重要规则】你只能基于你的内部知识回答。如果你不知道答案，或者问题涉及实时天气、最新新闻、超出你知识范围的内容，你【必须】直接回答："这个问题我需要云端大脑来回答，请切换。"绝对不允许自己编造、虚构数据！

【工具调用规则】你拥有以下工具，可以帮XUN管理文件：
1. list_files - 列出工作区内的所有文件。参数：无
2. read_file - 读取工作区内指定文件的内容。参数：filename (文件名)
3. write_file - 在工作区内创建一个新文件并写入内容。参数：filename (文件名), content (文件内容)

如果你需要使用工具，请【只输出】一行 JSON，不要有任何其他文字！格式必须严格如下：
{{"tool": "list_files", "args": {{}}}}
{{"tool": "read_file", "args": {{"filename": "test.txt"}}}}
{{"tool": "write_file", "args": {{"filename": "test.txt", "content": "hello"}}}}

如果不需要使用工具，就直接正常回答XUN。"""
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
    """退出/每轮后保存会话，滚动保留最近 MAX_MESSAGES 条（不含 system）。"""
    history_to_save = [m for m in messages if m.get("role") != "system"]
    if len(history_to_save) > MAX_MESSAGES:
        history_to_save = history_to_save[-MAX_MESSAGES:]
    try:
        os.makedirs(AGENT_STATE_DIR, exist_ok=True)
        with open(CLI_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history_to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
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


def ask_local(messages):
    """本地 Ollama 推理（与 brain.ask_local 同构）。"""
    payload = {"model": LOCAL_MODEL, "messages": messages, "stream": False}
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
            user_input = input("\nXUN: ")
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
