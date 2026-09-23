import requests
import json
import os
import re
import socket
import sys
sys.path.append('/mnt/agent/workspace')
from config import *
from tools import execute_tool
from emoji_manager import get_emoji_path

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
                tool_args = tool_call.get("args", {})
                if tool_name not in ["list_files", "read_file", "write_file"]:
                    return raw_reply, "🏠 本地"
                print(f"🔧 执行工具: {tool_name}，参数: {tool_args}")
                tool_result = execute_tool(tool_name, tool_args)
                print(f"📄 结果: {tool_result[:200]}...")
                messages.append({"role": "assistant", "content": json_str})
                messages.append({"role": "system", "content": f"工具执行结果：{tool_result}"})
                final_reply = ask_local(messages)
                if final_reply.strip().startswith("{"):
                     final_reply = ask_cloud(messages)
                return final_reply, "🏠 本地 (工具)"
            except Exception as e:
                print(f"⚠️ 工具解析失败: {e}")
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
