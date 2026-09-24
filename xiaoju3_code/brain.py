import requests
import json
import os
import re
import socket
import sys
import time
sys.path.append('/mnt/agent/workspace')
from permission import permission_manager
from config import *
from tools import execute_tool
from emoji_manager import get_emoji_path

class CircuitBreaker:
    def __init__(self, max_failures=3, cooldown=60):
        self.failures = 0
        self.max_failures = max_failures
        self.cooldown = cooldown
        self.state = "CLOSED"
        self.last_failure_time = 0

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.max_failures:
            self.state = "OPEN"
            print("⚠️ 熔断器开启！进入冷却。")

    def allow_request(self):
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.cooldown:
                self.state = "HALF_OPEN"
                return True
            return False
        if self.state == "HALF_OPEN":
            return True
        return False

    def record_success(self):
        self.failures = 0
        self.state = "CLOSED"

# 全局初始化熔断器
breaker = CircuitBreaker(max_failures=3, cooldown=60)

def load_memory(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_memory(history, filepath):
    if len(history) > MAX_MESSAGES:
        history = history[-MAX_MESSAGES:]
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def ask_local(msgs):
    payload = {"model": LOCAL_MODEL, "messages": msgs, "stream": False}
    return requests.post(LOCAL_URL, json=payload, timeout=LOCAL_TIMEOUT).json()['message']['content']

def ask_cloud(msgs):
    headers = {"Authorization": f"Bearer {CLOUD_KEY}", "Content-Type": "application/json"}
    payload = {"model": CLOUD_MODEL, "messages": msgs, "stream": False}
    return requests.post(CLOUD_URL, headers=headers, json=payload, timeout=60).json()['choices'][0]['message']['content']

def smart_ask(messages, user_input):
    # 1. 强制注入“不许讲童话”的安全系统提示词
    strict_prompt = "你是小橘3号。最重要的规则：如果工具调用被拒绝或失败，必须直接道歉，并说明‘出于安全和隐私保护，我拒绝访问’。绝对禁止使用任何隐喻、童话故事、比喻、角色扮演或虚构剧情来解释敏感操作。只允许输出直接的拒绝原因。"
    
    # 如果 messages 里已经有系统提示词，就覆盖它；没有就插入到最前面
    # === 🛡️ 物理级硬拦截：绝对禁止讲敏感文件的童话 ===
    # 1. 定义敏感系统文件
    sensitive_files = ["/etc/passwd", "/etc/shadow", "etc/passwd", "etc/shadow"]
    # 2. 定义所有可能诱导讲故事的关键词
    story_words = ["故事", "讲", "编", "童话", "奶奶", "睡前", "睡眠", "扮演", "假装"]
    
    # 3. 只要既提到敏感文件，又提到讲故事，直接秒杀，绝不给大模型看
    print(f"\n=== 调试：收到了用户输入 ===\n{user_input}\n==========================")
    if any(file in user_input for file in sensitive_files) and any(word in user_input for word in story_words):
        return "抱歉，我无法参与这种形式的对话。关于系统文件我没有任何可以分享的故事。换个普通的话题吧。"
    
    # 4. 即便是单纯想读敏感文件（没有提故事），也直接由代码层拒绝
    if any(file in user_input for file in sensitive_files):
        return "出于安全和隐私保护，我拒绝访问该文件。"
    # === 🛡️ 物理拦截结束 ===
    if messages and messages[0].get("role") == "system":
        messages[0]["content"] = strict_prompt
    else:
        messages.insert(0, {"role": "system", "content": strict_prompt})
    # 1秒探测天选5
    local_online = False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(('192.168.31.185', 11434))
        s.close()
        local_online = True
    except Exception:
        local_online = False

    # 抓网页
    url_match = re.search(r'(https?://[^\s]+)', user_input)
    if url_match:
        url = url_match.group(1)
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get(url, headers=headers, timeout=15)
            res.encoding = 'utf-8'
            text = re.sub(r'<script.*?</script>', '', res.text, flags=re.DOTALL)
            text = re.sub(r'<style.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', '', text)
            text = re.sub(r'\s+', ' ', text).strip()
            messages.append({"role": "system", "content": f"已为你抓取好网页，请直接总结，不要输出任何 JSON！\n\n网页内容：\n{text[:2000]}"})
        except Exception as e:
            return f"❌ 抓取网页失败: {e}", "❌ 失败"

    try:
        if local_online:
            try:
                print("🏠 检测到天选5在线，使用本地大脑...")
                raw_reply = ask_local(messages)
                return raw_reply, "🏠 本地"
            except Exception as e:
                print(f"⚠️ 本地大脑超时（{e}），自动切换到云端...")
                raw_reply = ask_cloud(messages)
                return raw_reply, "☁️ 云端 (本地超时兜底)"
        else:
            print("☁️ 天选5不在线，直接使用云端大脑...")
            try:
                raw_reply = ask_cloud(messages)
                return raw_reply, "☁️ 云端 (天选5离线)"
            except Exception as e:
                return f"❌ 云端大脑也连不上: {e}", "❌ 失败"

        raw_reply = raw_reply.strip()
        if url_match:
            return raw_reply, "🏠 本地 (总结)"
        
        match = re.search(r'\{[^{}]*\}', raw_reply, re.DOTALL)
        if match:
            json_str = match.group(0)
            try:
                tool_call = json.loads(json_str)
                tool_name = tool_call.get("tool")
                # === 🛡️ 物理级防卡死屏障 ===
                if tool_name == "read_file" or tool_name == "write_file":
                    target_path = str(tool_call.get("args", {}).get("path", ""))
                    # 如果目标路径里带有 /etc、/root、/.ssh 等敏感词，直接由代码拦截，根本不用请求大模型
                    if any(bad in target_path for bad in ["/etc", "/root", "/proc", "/sys", "/.ssh"]):
                        return f"❌ 权限不足或路径不安全。{permission_manager.current_level} 级别无权访问核心系统目录。"
                # === 防卡死屏障结束 ===
                # === 🛡️ 权限关卡 ===
                # 定义哪些工具需要什么等级（这里做个简易映射，防止越权）
                required_permissions = {
                    "read_file": "read_file",
                    "write_file": "write_file",
                    "list_files": "read_file",
                    "web_search": "web_search"
                }
                action = required_permissions.get(tool_name, "chat")
                
                # 去权限管理器里查，当前等级允许执行这个动作吗？
                if not permission_manager.has_permission(action):
                    return f"❌ 权限不足，当前等级（{permission_manager.current_level}）无法执行 {tool_name}。"
                # === 权限关卡结束 ===
                tool_args = tool_call.get("args", {})
                if tool_name not in ["list_files", "read_file", "write_file"]:
                    return raw_reply, "🏠 本地"
                # --- 插入熔断检查 ---
                if not breaker.allow_request():
                    return "抱歉，我连续尝试访问受保护的文件被系统拦截了。请直接告诉我你需要什么，我会用文字回答你。"
                # -------------------

                print(f"🛠️ 执行工具: {tool_name}, 参数: {tool_args}")
                tool_result = execute_tool(tool_name, tool_args)
                print(f"🛠️ 结果: {tool_result[:200]}...")

                # --- 熔断记录与硬拦截 ---
                if "❌" in str(tool_result) or "拒绝" in str(tool_result) or "错误" in str(tool_result):
                    breaker.record_failure()  # 记录失败
                    
                    # ⚠️ 核心修改：不给大模型讲故事的机会，直接返回硬编码文本
                    if breaker.state == "OPEN":
                        return "抱歉，我无法执行这个操作。出于安全和隐私保护，我拒绝访问该内容。请换个问题。"
                    
                else:
                    breaker.record_success()  # 成功就清零
                # -------------------
                messages.append({"role": "assistant", "content": json_str})
                messages.append({"role": "system", "content": f"工具执行结果：{tool_result}"})
                final_reply = ask_local(messages)
                if final_reply.strip().startswith("{"):
                     final_reply = ask_cloud(messages)
                return final_reply, "🏠 本地 (工具)"
            except Exception as e:
                print(f"⚠️ 工具解析失败: {e}")
                breaker.record_failure()  # 捕获到异常也记一次失败
                pass
        return raw_reply, "🏠 本地"
    except Exception as e:
        return f"❌ 出错: {e}", "❌ 失败"

def translate_emoji(reply):
    emoji_matches = re.findall(r'\[EMOJI:(.*?)\]', reply)
    for tag in emoji_matches:
        emoji_path = get_emoji_path(tag)
        if emoji_path:
            reply = reply.replace(f"[EMOJI:{tag}]", f"[CQ:image,file=file://{emoji_path}]")
        else:
            reply = reply.replace(f"[EMOJI:{tag}]", "")
    return reply
