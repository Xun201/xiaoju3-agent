import sys
import re
import requests
import json
import os
from permission import permission_manager
from identity import xiaoju_identity
from flask import Flask, request, render_template_string
sys.path.append('/mnt/agent/workspace')
from config import *
from prompts import SYSTEM_PROMPT
from brain import load_memory, save_memory, smart_ask
from emoji_manager import save_emoji_link

app = Flask(__name__)
awaiting_exit_password = False

# ================= 记忆库隔离 =================
MEMORY_FILE_WEB = "/mnt/agent/memory/history_web.json"
MEMORY_FILE_QQ = "/mnt/agent/memory/history_qq.json"

messages_web = [SYSTEM_PROMPT] + load_memory(MEMORY_FILE_WEB)
messages_qq = [SYSTEM_PROMPT] + load_memory(MEMORY_FILE_QQ)
# ============================================

# ================= 核心内核（统一入口） =================
def handle_message(source, user_id, group_id, message):
    # === 🛡️ 安全退出机制 ===
    global awaiting_exit_password
    if message.strip() in ["/exit", "退出", "关闭"]:
        awaiting_exit_password = True
        return "⚠️ 你正在申请退出小橘3号。请输入退出密码以确认（发送 /cancel 取消）："
    
    if message.strip() == "/cancel" and awaiting_exit_password:
        awaiting_exit_password = False
        return "✅ 已取消退出申请。"
    
    if awaiting_exit_password:
        EXIT_PASSWORD = "orangepi"
        if message.strip() == EXIT_PASSWORD:
            # 创建停止标志，让 start.sh 停止守护
            with open("stop.flag", "w") as f:
                f.write("stop")
            # 强制杀掉当前的 main.py 进程
            import os
            os._exit(0)
        else:
            awaiting_exit_password = False
            return "❌ 密码错误，退出已取消。"
    # === 安全退出机制结束 ===
    # === 🔄 软重启指令 ===
    if message.strip() == "/restart":
        # 我们通过发送一个特殊的退出信号，让外层的 start.sh 脚本自动拉起
        os._exit(0) 
    # === 🛡️ 终极防卡死铁墙 ===
    # 只要包含敏感路径，直接秒回，绝不进入大模型！
    if any(bad in str(message) for bad in ["/etc/passwd", "/etc/shadow", "/root", "/proc", "/sys"]):
        return "抱歉，我无法读取该文件。出于安全和隐私保护，我拒绝访问。"
    # === 🛡️ 门卫系统开始（新版：访客也能用，注册才升级） ===
    # 1. 默认状态：最低权限 Lv.1（访客）
    permission_manager.current_level = "Lv.1"

    # 2. 主动注册请求（升级到 Lv.2）
    if message.startswith("/register"):
        new_name = message.replace("/register", "").strip()
        if new_name:
            reply_text = xiaoju_identity.register_owner(new_name)
            permission_manager.current_level = "Lv.2"
            return reply_text  # 返回注册成功信息，不进入聊天大脑
        else:
            return "请告诉我你的名字，格式：/register 你的名字"

    # 3. 如果已经注册过了，自动赋予 Lv.2（次级权限）
    if xiaoju_identity.is_registered:
        permission_manager.current_level = "Lv.2"

    # === 🛡️ 聊天通道绝对禁止最高权限 ===
    # 任何聊天消息（QQ或网页）都无法激活 Lv.3，最高权限只认本地安全认证
    if "[XUN]" in message:
        return "⚠️ 最高权限只能在安全环境（你的电脑）通过本地认证激活。聊天通道无法授予 Lv.3。"
    # === 拦截结束 ===
    
    # 5. 不管是 Lv.1、Lv.2 还是 Lv.3，都继续往下走，去调用大脑和工具。
    # 如果是 Lv.1 去调 read_file，会被 brain.py 里的权限关卡拦下来。
    # === 🛡️ 门卫系统结束 ===

    # 下面保留你原有的代码（例如 # 3. 调用大脑进行思考...）
    
    # 1. 收集图片表情包（拦截图片消息）
    img_match = re.search(r'\[CQ:image,file=(.*?)\]', message)
    if img_match:
        img_url = img_match.group(1)
        print(f"🖼️ 收到图片，正在保存链接: {img_url}")
        if save_emoji_link(img_url):
            return "收到你的表情啦！已经存进小仓库了😊"
        else:
            return "这个表情我没存下来，下次再试试！"

    # 2. 群聊防刷屏（只有@或关键词才理人）
    if source == 'qq' and group_id:
        trigger_words = ["小橘", "小桔", "橘3号", "橘三号", "AI测试"]
        is_at_me = "[CQ:at,qq=1706205831]" in message
        has_trigger_word = any(word in message for word in trigger_words)
        if not (is_at_me or has_trigger_word):
            return "" # 返回空字符串，代表不回复

    # === 🛡️ 调试：看看 message 到底长什么样 ===
    print(f"\n[DEBUG] message 的类型是: {type(message)}")
    print(f"[DEBUG] message 的内容是: {repr(message)}")
    print("=======================================\n")
    print(f"[LOG] 准备进入大脑，内容为: {message}")
    # 3. 调用大脑进行思考（根据来源，选择不同的记忆库）
    global messages_web, messages_qq
    if source == 'web':
        messages_web.append({"role": "user", "content": message})
        reply, tag = smart_ask(messages_web, message)
        messages_web.append({"role": "assistant", "content": reply})
        save_memory([m for m in messages_web if m["role"] != "system"], MEMORY_FILE_WEB)
    else:
        messages_qq.append({"role": "user", "content": message})
        reply, tag = smart_ask(messages_qq, message)
        messages_qq.append({"role": "assistant", "content": reply})
        save_memory([m for m in messages_qq if m["role"] != "system"], MEMORY_FILE_QQ)
    
    return reply
# =======================================================

# ================= 网页界面 =================
HTML_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>小橘3号 网页控制台</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #1a1a2e; color: #eee; margin: 0; padding: 20px; }
        #chat { height: 70vh; overflow-y: auto; padding: 10px; border: 1px solid #444; border-radius: 10px; background: #16213e; }
        .msg { margin: 10px 0; padding: 10px; border-radius: 10px; max-width: 80%; }
        .user { background: #0f3460; margin-left: auto; text-align: right; }
        .bot { background: #533483; margin-right: auto; }
        .sys { font-size: 0.8em; color: #888; text-align: center; margin: 5px 0; }
        #input-area { display: flex; margin-top: 15px; }
        #input { flex: 1; padding: 12px; border-radius: 20px; border: none; font-size: 16px; background: #eee; }
        #send { padding: 12px 20px; border: none; border-radius: 20px; background: #e94560; color: white; font-size: 16px; margin-left: 10px; }
    </style>
</head>
<body>
    <h2>🤖 小橘3号 控制台</h2>
    <div id="chat"></div>
    <div id="input-area">
        <input type="text" id="input" placeholder="跟小橘3号说点什么..." autofocus>
        <button id="send">发送</button>
    </div>
    <script>
        const chat = document.getElementById('chat');
        const input = document.getElementById('input');
        const send = document.getElementById('send');

        function addMsg(text, cls) {
            const div = document.createElement('div');
            div.className = 'msg ' + cls;
            div.textContent = text;
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        }

        async function sendMsg() {
            const text = input.value.trim();
            if (!text) return;
            input.value = '';
            addMsg(text, 'user');
            addMsg('小橘3号正在思考中...', 'sys');

            try {
                const res = await fetch('/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: text})
                });
                const data = await res.json();
                const sys = document.querySelector('.sys:last-child');
                if (sys) sys.remove();
                addMsg(data.reply, 'bot');
            } catch (e) {
                addMsg('❌ 连接失败，请检查小橘3号是否在运行。', 'sys');
            }
        }

        send.onclick = sendMsg;
        input.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMsg(); });
    </script>
</body>
</html>
'''
# ============================================

# ================= 网页大门 =================
@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message', '')
    if not user_msg: return {"reply": "请说点什么吧！"}
    
    # 交给内核处理
    reply = handle_message('web', 'admin', None, user_msg)
    return {"reply": reply}

# ================= QQ大门 =================
@app.route('/onebot', methods=['POST'])
def onebot_webhook():
    data = request.json

    # ============ 处理“戳一戳”事件 ============
    if data.get('post_type') == 'notice' and data.get('notice_type') == 'poke':
        group_id = data.get('group_id')
        user_id = data.get('user_id')

        print(f"👆 有人在群里戳了戳我！")
        reply = "别戳啦，好痒！😆"
        try:
            if group_id:
                requests.post(f"{NAPCAT_API_URL}/send_group_msg", json={"group_id": group_id, "message": reply}, timeout=10, headers={"Authorization": f"Bearer {NAPCAT_TOKEN}"})
            else:
                requests.post(f"{NAPCAT_API_URL}/send_private_msg", json={"user_id": user_id, "message": reply}, timeout=10, headers={"Authorization": f"Bearer {NAPCAT_TOKEN}"})
        except Exception as e:
            print(f"戳一戳回复失败: {e}")
        return {"status": "ok", "retcode": 0}

    # ============ 处理普通消息 ============
    if data.get('post_type') == 'message':
        msg_type = data.get('message_type')
        user_id = data.get('user_id')
        user_message = data.get('message')
        group_id = data.get('group_id')
        
        # 交给内核处理
        reply = handle_message('qq', user_id, group_id, user_message)
        
        # 如果内核返回了非空回复，才发回QQ
        if reply:
            if msg_type == 'private':
                requests.post(f"{NAPCAT_API_URL}/send_private_msg", json={"user_id": user_id, "message": reply}, timeout=10, headers={"Authorization": f"Bearer {NAPCAT_TOKEN}"})
            elif msg_type == 'group':
                requests.post(f"{NAPCAT_API_URL}/send_group_msg", json={"group_id": group_id, "message": reply}, timeout=10, headers={"Authorization": f"Bearer {NAPCAT_TOKEN}"})
    return {"status": "ok", "retcode": 0}

if __name__ == '__main__':
    print("🌐 小橘3号网页控制台已启动！")
    print("💡 网页访问：http://192.168.31.82:5001")
    app.run(host='0.0.0.0', port=5002)
