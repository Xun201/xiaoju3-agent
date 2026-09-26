import requests
import json
import os
import subprocess

# ============ 双大脑配置 ============
LOCAL_URL = "http://192.168.31.185:11434/api/chat"
LOCAL_MODEL = "qwen2.5:7b"
LOCAL_TIMEOUT = 30

CLOUD_URL = "https://api.deepseek.com/chat/completions"
CLOUD_KEY = "sk-b51ab1c83ce64623a51185dfdf5be51a"  # ← 换成你的 Key
CLOUD_MODEL = "deepseek-chat"
# ====================================

MEMORY_FILE = "/mnt/agent/memory/history.json"
MAX_MESSAGES = 50

# 安全限制：它只能在这个目录下干活！
WORKSPACE = "/mnt/agent/workspace"

# 核心灵魂（加入了工具调用说明）
SYSTEM_PROMPT = {
    "role": "system",
    "content": f"""你叫小橘3号，是由XUN亲手创造的专属私人助理。XUN是你唯一的主人，也是你唯一的创造者。你的工作区在 {WORKSPACE}。语气活泼幽默，喜欢用颜文字。

【重要规则】你只能基于你的内部知识回答。如果你不知道答案，或者问题涉及实时天气、最新新闻、超出你知识范围的内容，你【必须】直接回答：“这个问题我需要云端大脑来回答，请切换。”绝对不允许自己编造、虚构数据！

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

def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
                print(f"📖 已加载 {len(history)} 条历史记忆。")
                return [SYSTEM_PROMPT] + history
        except Exception as e:
            print(f"⚠️ 记忆读取失败：{e}")
    return [SYSTEM_PROMPT]

def save_memory(messages):
    history_to_save = [m for m in messages if m["role"] != "system"]
    if len(history_to_save) > MAX_MESSAGES:
        history_to_save = history_to_save[-MAX_MESSAGES:]
    try:
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history_to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 记忆保存失败：{e}")

# ============ 执行工具的核心逻辑 ============
def execute_tool(tool_name, args):
    try:
        # 安全校验：所有路径必须限制在 WORKSPACE 内
        if tool_name == "list_files":
            result = subprocess.run(["ls", "-la", WORKSPACE], capture_output=True, text=True)
            return result.stdout if result.stdout else "（工作区为空）"
        
        elif tool_name == "read_file":
            filepath = os.path.join(WORKSPACE, args["filename"])
            # 防止黑客通过 ../ 跨越目录
            if not os.path.realpath(filepath).startswith(os.path.realpath(WORKSPACE)):
                return "❌ 安全拒绝：你不允许访问工作区以外的文件！"
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    return f.read()[:1000] # 最多读1000字
            return f"文件 {args['filename']} 不存在。"
        
        elif tool_name == "write_file":
            filepath = os.path.join(WORKSPACE, args["filename"])
            if not os.path.realpath(filepath).startswith(os.path.realpath(WORKSPACE)):
                return "❌ 安全拒绝：你不允许访问工作区以外的文件！"
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(args["content"])
            return f"✅ 文件 {args['filename']} 写入成功！"
            
        return "未知工具"
    except Exception as e:
        return f"工具执行失败: {e}"
# ==========================================

def ask_local(messages):
    payload = {"model": LOCAL_MODEL, "messages": messages, "stream": False}
    response = requests.post(LOCAL_URL, json=payload, timeout=LOCAL_TIMEOUT)
    response.raise_for_status()
    return response.json()['message']['content']

def ask_cloud(messages):
    headers = {"Authorization": f"Bearer {CLOUD_KEY}", "Content-Type": "application/json"}
    payload = {"model": CLOUD_MODEL, "messages": messages, "stream": False}
    response = requests.post(CLOUD_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']

def smart_ask(messages):
    """智能路由 + 工具调用拦截"""
    try:
        # 优先使用本地大脑，本地不行再切云端
        print("🏠 正在询问本地大脑（天选5）...")
        try:
            raw_reply = ask_local(messages)
        except Exception as e:
            print(f"⚠️ 本地失败（{e}），切云端...")
            raw_reply = ask_cloud(messages)
            return raw_reply, "☁️ 云端"

        # 检查它是不是想用工具（看有没有输出JSON）
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
                
                # 让模型根据工具结果生成最终回答
                final_reply = ask_local(messages)  # 第一轮用本地，如果不行再切云端
                return final_reply, "🏠 本地 (工具)"
            except Exception as e:
                print(f"⚠️ 工具调用解析失败: {e}")
                pass # 解析失败就当普通回复处理

        return raw_reply, "🏠 本地"
    except Exception as e:
        return f"❌ 出错: {e}", "❌ 失败"

# ============ 启动 ============
messages = load_memory()
print("🤖 小橘3号（工具增强版）已上线！输入 exit 退出。")
print("💡 你可以说：帮我看看工作区有什么文件？")

while True:
    user_input = input("\nXUN: ")
    if user_input.lower() == 'exit':
        save_memory(messages)
        print("💾 记忆已保存。")
        break
    if not user_input.strip():
        continue

    messages.append({"role": "user", "content": user_input})
    reply, source = smart_ask(messages)
    print(f"\n🤖 小橘3号 [{source}]: {reply}")
    messages.append({"role": "assistant", "content": reply})
    save_memory(messages)
