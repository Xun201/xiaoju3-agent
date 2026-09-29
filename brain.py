import requests
import json
import os
import re
import socket
import sys
import requests.packages.urllib3.util.connection as urllib3_cn
# 从 xiaoju3 导入正确的 CLOUD_KEY，避免因 config.py 缺失导致拿到空值
from xiaoju3 import CLOUD_KEY, CLOUD_URL, CLOUD_MODEL, MAX_MESSAGES, LOCAL_URL, LOCAL_MODEL, LOCAL_TIMEOUT
from tools import execute_tool
from emoji_manager import get_emoji_path

def allowed_gai_family():
    return socket.AF_INET

urllib3_cn.allowed_gai_family = allowed_gai_family

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

def ask_cloud(messages):
    headers = {"Authorization": f"Bearer {CLOUD_KEY}", "Content-Type": "application/json"}
    payload = {"model": CLOUD_MODEL, "messages": messages, "stream": False}
    
    try:
        response = requests.post(CLOUD_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        resp_json = response.json()
        
        # 检查是否存在 choices，如果不存在，就把接口返回的原始错误信息发出来
        if "choices" in resp_json:
            return resp_json["choices"][0]["message"]["content"]
        else:
            # 如果 API 返回了错误（比如模型不对、余额不足），直接显示错误详情
            error_detail = resp_json.get("error", {})
            if isinstance(error_detail, dict):
                msg = error_detail.get("message", "未知错误")
            else:
                msg = str(error_detail)
            return f"⚠️ API接口报错: {msg}"
            
    except Exception as e:
        return f"⚠️ 云端连接异常: {e}"

def smart_ask(messages, user_input):
    # === 第一步：如果用户输入里有 URL，先抓网页 ===
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

    # 🛡️ 自动探测天选5是否在线，不用再去改 True/False
    local_online = False
    try:
        # 尝试连接天选5的 Ollama 端口，超时设为1秒，不卡顿
        requests.get("http://192.168.31.185:11434/", timeout=1)
        local_online = True
        print("🏠 本地大脑（天选5）在线，优先使用本地算力！")
    except Exception:
        print("📡 天选5不在线，直接使用云端大脑...")

    raw_reply = ""
    try:
        if local_online:
            try:
                raw_reply = ask_local(messages)
            except Exception as e:
                print(f"⚠️ 本地大脑连接不稳定（{e}），自动切换云端大脑...")
                raw_reply = ask_cloud(messages)
        else:
            raw_reply = ask_cloud(messages)
    except Exception as e2:
        return f"❌ 大脑连接失败，请检查网络。错误：{e2}", "❌ 失败"

    if not raw_reply:
        return "抱歉，小橘3号刚才脑袋短路了，请再说一遍吧。", "🏠 本地"

    raw_reply = raw_reply.strip()

    # === 第三步：如果是抓网页的，直接返回总结 ===
    if url_match:
        return raw_reply, "🏠 本地 (总结)"

    # === 第四步：解析工具调用（修复核心：用正则强匹配JSON） ===
    # 匹配最外层包含 "tool" 的大括号内容，允许前后有杂散文字
    match = re.search(r'\{.*"tool".*\}', raw_reply, re.DOTALL)
    if match:
        json_str = match.group(0)
        try:
            tool_call = json.loads(json_str)
            tool_name = tool_call.get("tool")
            tool_args = tool_call.get("args", {})
            
            if tool_name in ["list_files", "read_file", "write_file", "get_ha_devices", "control_ha_device", "adb_tap", "adb_swipe", "adb_screenshot", "vision_tap_element", "ui_tap_element"]:
                tool_result = execute_tool(tool_name, tool_args)
                print(f"📄 结果: {tool_result[:200]}...")
                
                # 将工具结果喂回给模型
                messages.append({"role": "assistant", "content": json_str})
                messages.append({"role": "system", "content": f"工具执行结果：{tool_result}\n\n请根据这个结果，用自然语言回答用户，绝对不要再输出 JSON！"})
                
                # ⚠️ 核心修复：工具执行完后，强制使用云端大脑
                try:
                    final_reply = ask_cloud(messages)
                    return final_reply, "☁️ 云端 (工具)"
                except Exception as e:
                    return f"❌ 工具执行后云端汇总失败: {e}", "❌ 失败"
        except Exception as e:
            print(f"⚠️ 工具解析失败，按普通回复处理: {e}")

    return raw_reply, "🏠 本地"

def translate_emoji(reply):
    emoji_matches = re.findall(r'\[EMOJI:(.*?)\]', reply)
    for tag in emoji_matches:
        emoji_path = get_emoji_path(tag)
        if emoji_path:
            reply = reply.replace(f"[EMOJI:{tag}]", f"[CQ:image,file=file://{emoji_path}]")
        else:
            reply = reply.replace(f"[EMOJI:{tag}]", "")
    return reply
