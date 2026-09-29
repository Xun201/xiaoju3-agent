# -*- coding: utf-8 -*-
import os
import psutil
import requests
from flask import Flask, jsonify, request, render_template_string, send_from_directory
from brain import smart_ask  # 复用你写好的大脑逻辑

app = Flask(__name__)

# 静态资源（大肥鱼图片等）
@app.route('/assets/<path:filename>')
def get_assets(filename):
    return send_from_directory('assets', filename)

# 托管本地的控制台前端文件
@app.route('/console')
def console():
    return send_from_directory('.', 'index.html')

@app.route('/console/<path:filename>')
def console_static(filename):
    return send_from_directory('.', filename)

# 从隔离区读取敏感文件（不再硬编码）
DATA_DIR = "/home/orangepi/xiaoju3_data"
LOG_FILE = os.path.join(DATA_DIR, "logs", "service.log")

def get_cpu_temp():
    """读取香橙派温度"""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read().strip()) / 1000.0
    except Exception:
        return 0.0

@app.route("/")
def index():
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🍊 小橘3号控制台</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
            body { background: #f9fafb; color: #333; height: 100vh; display: flex; overflow: hidden; }
            .left-panel { width: 33.33%; background: #fff; border-right: 1px solid #e5e7eb; display: flex; flex-direction: column; padding: 20px; }
            .left-panel h2 { font-size: 16px; color: #6b7280; margin-bottom: 20px; border-bottom: 1px solid #f3f4f6; padding-bottom: 10px; }
            .status-item { margin-bottom: 20px; }
            .status-item label { display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 8px; }
            .progress-bg { width: 100%; height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden; }
            .progress-bar { height: 100%; background: #3b82f6; border-radius: 4px; width: 0%; transition: width 0.3s; }
            .progress-bar.temp { background: #ef4444; }
            .right-panel { flex: 1; display: flex; flex-direction: column; position: relative; }
            .chat-history { flex: 1; overflow-y: auto; padding: 20px; padding-bottom: 120px; }
            .message { margin-bottom: 20px; display: flex; }
            .message.user { justify-content: flex-end; }
            .message.ai { justify-content: flex-start; }
            .bubble { max-width: 80%; padding: 12px 16px; border-radius: 12px; font-size: 14px; line-height: 1.5; word-break: break-all; }
            .message.user .bubble { background: #3b82f6; color: #fff; border-bottom-right-radius: 2px; }
            .message.ai .bubble { background: #f3f4f6; color: #1f2937; border-bottom-left-radius: 2px; }
            .msg-tools { display: flex; gap: 12px; margin-top: 8px; opacity: 0.6; }
            .msg-tools span { cursor: pointer; font-size: 14px; transition: 0.2s; }
            .msg-tools span:hover { opacity: 1; transform: scale(1.1); }
            .input-area { position: absolute; bottom: 0; left: 0; right: 0; padding: 20px; background: rgba(255,255,255,0.9); backdrop-filter: blur(10px); border-top: 1px solid #e5e7eb; }
            .input-wrapper { display: flex; gap: 10px; background: #fff; border: 1px solid #d1d5db; border-radius: 12px; padding: 10px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }
            .input-wrapper textarea { flex: 1; border: none; outline: none; resize: none; font-size: 14px; height: 24px; font-family: inherit; }
            .input-wrapper button { background: #3b82f6; color: #fff; border: none; border-radius: 8px; padding: 6px 16px; cursor: pointer; font-weight: 500; }
            .input-wrapper button:hover { background: #2563eb; }
            .balance-widget {position: absolute;bottom: 120px;right: 20px;z-index: 999; }
            .balance-widget .whale-icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 24px;
                height: 24px;
            }
            .balance-widget .whale-icon svg {
                transition: transform 0.3s ease;
            }
            .balance-widget:hover .whale-icon svg {
                transform: scale(1.15) rotate(-5deg); /* 鼠标悬停时小鲸鱼会微微放大摇摆 */
            }
        </style>
    </head>
    <body>
        <div class="left-panel">
            <h2>📊 系统监控</h2>
            <div class="status-item">
                <label>CPU 占用 <span id="cpu-val">0%</span></label>
                <div class="progress-bg"><div class="progress-bar" id="cpu-bar"></div></div>
            </div>
            <div class="status-item">
                <label>内存占用 <span id="mem-val">0%</span></label>
                <div class="progress-bg"><div class="progress-bar" id="mem-bar"></div></div>
            </div>
            <div class="status-item">
                <label>CPU 温度 <span id="temp-val">0°C</span></label>
                <div class="progress-bg"><div class="progress-bar temp" id="temp-bar"></div></div>
            </div>
            <div class="status-item">
                <label>运行时长 <span id="uptime-val">0h 0m</span></label>
            </div>
            <div style="margin-top: auto; text-align: center; color: #9ca3af; font-size: 12px;">XUN 专属控制台</div>
        </div>
        <div class="right-panel">
            <div class="chat-history" id="chat-history">
                <div class="message ai">
                    <div>
                        <div class="bubble">🍊 我是小橘3号，随时准备为你服务！</div>
                        <div class="msg-tools">
                            <span title="复制" onclick="copyText(this)">📋</span>
                            <span title="刷新" onclick="refreshMsg(this)">🔄</span>
                            <span title="点赞" onclick="likeMsg(this)">👍</span>
                            <span title="踩" onclick="dislikeMsg(this)">👎</span>
                            <span title="播放" onclick="playMsg(this)">🔊</span>
                            <span title="转发" onclick="forwardMsg(this)">↗️</span>
                        </div>
                    </div>
                </div>
            </div>
            <!-- 右下角余额小挂件 -->
            <div class="balance-widget" onclick="fetchBalance()">
                <div class="whale-icon">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#3b82f6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M19.5 12c-1.4 0-2.6.8-3.2 2H16v-2c0-3.9-3.1-7-7-7S2 8.1 2 12c0 3.3 2.3 6.1 5.4 6.8.6.1 1.2-.3 1.4-.9.2-.5 0-1.1-.5-1.4-1.4-1-2.3-2.6-2.3-4.4 0-2.8 2.2-5 5-5s5 2.2 5 5v2h-2.2c-.6-1.2-1.8-2-3.2-2-2.2 0-4 1.8-4 4s1.8 4 4 4h7c2.2 0 4-1.8 4-4s-1.8-4-4-4zM8 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z"/>
                    </svg>
                </div>
                <span>余额: <b id="balance-text">加载中...</b></span>
            </div>
            <div class="input-area">
                <div class="input-wrapper">
                    <textarea id="user-input" placeholder="给小橘3号发送消息..." rows="1" onkeydown="if(event.key==='Enter' && !event.shiftKey){event.preventDefault();sendMessage()}"></textarea>
                    <button onclick="sendMessage()">发送</button>
                </div>
            </div>
        </div>
        <script>
            function updateStatus() {
                fetch('/api/status').then(r => r.json()).then(data => {
                    document.getElementById('cpu-val').innerText = data.cpu.toFixed(1) + '%';
                    document.getElementById('cpu-bar').style.width = data.cpu + '%';
                    document.getElementById('mem-val').innerText = data.memory.toFixed(1) + '%';
                    document.getElementById('mem-bar').style.width = data.memory + '%';
                    document.getElementById('temp-val').innerText = data.temp.toFixed(1) + '°C';
                    document.getElementById('temp-bar').style.width = Math.min(data.temp * 2, 100) + '%';
                    let uptimeSec = Math.floor(Date.now()/1000) - data.uptime;
                    document.getElementById('uptime-val').innerText = Math.floor(uptimeSec/3600) + 'h ' + Math.floor((uptimeSec%3600)/60) + 'm';
                });
            }
            setInterval(updateStatus, 3000); updateStatus();

            function fetchBalance() {
                fetch('/api/balance').then(r => r.json()).then(data => {
                    if (data.error) document.getElementById('balance-text').innerText = '查询失败';
                    else if (data.balance_infos && data.balance_infos.length > 0) document.getElementById('balance-text').innerText = '¥' + data.balance_infos[0].total_balance;
                    else document.getElementById('balance-text').innerText = '数据异常';
                }).catch(() => { document.getElementById('balance-text').innerText = '网络错误'; });
            }
            setInterval(fetchBalance, 60000); fetchBalance();

            function sendMessage() {
                let input = document.getElementById('user-input');
                let text = input.value.trim();
                if (!text) return;
                addMessage('user', text);
                input.value = '';
                fetch('/api/chat', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: text})
                }).then(r => r.json()).then(data => addMessage('ai', data.reply + ' <br><small>(' + data.source + ')</small>'))
                  .catch(err => addMessage('ai', '⚠️ 请求失败: ' + err));
            }

            function addMessage(role, text) {
                let history = document.getElementById('chat-history');
                let div = document.createElement('div');
                div.className = 'message ' + role;
                div.innerHTML = `<div><div class="bubble">${text}</div>${role === 'ai' ? `<div class="msg-tools"><span onclick="copyText(this)">📋</span><span onclick="refreshMsg(this)">🔄</span><span onclick="likeMsg(this)">👍</span><span onclick="dislikeMsg(this)">👎</span><span onclick="playMsg(this)">🔊</span><span onclick="forwardMsg(this)">↗️</span></div>` : ''}</div>`;
                history.appendChild(div);
                history.scrollTop = history.scrollHeight;
            }
            function copyText(el) { navigator.clipboard.writeText(el.closest('.message').querySelector('.bubble').innerText).then(() => alert('✅ 已复制')); }
            function refreshMsg() { alert('🔄 重新生成功能暂未实现'); }
            function likeMsg(el) { el.innerText = '❤️'; alert('👍 感谢反馈！'); }
            function dislikeMsg(el) { el.innerText = '💔'; alert('👎 收到，我会改进的'); }
            function playMsg(el) { let text = el.closest('.message').querySelector('.bubble').innerText; window.speechSynthesis.speak(new SpeechSynthesisUtterance(text)); }
            function forwardMsg() { alert('↗️ 转发功能暂未实现'); }
        </script>
    </body>
    </html>
    ''')

@app.route("/api/status")
def api_status():
    """系统状态 API"""
    return jsonify({
        "code": 200,
        "data": {
            "cpu": psutil.cpu_percent(interval=0.5),
            "memory": psutil.virtual_memory().percent,
            "temperature": get_cpu_temp(),   # 前端字段名是 temperature，不是 temp
            "timestamp": int(psutil.boot_time()),
        }
    })

@app.route("/api/balance")
def api_balance():
    """DeepSeek 余额查询 API"""
    from xiaoju3 import CLOUD_KEY
    headers = {"Authorization": f"Bearer {CLOUD_KEY}"}
    try:
        resp = requests.get("https://api.deepseek.com/user/balance", headers=headers, timeout=10)
        raw = resp.json()
        if "balance_infos" in raw and len(raw["balance_infos"]) > 0:
            info = raw["balance_infos"][0]
            return jsonify({
                "code": 200,
                "data": {
                    "balance": float(info.get("total_balance", 0)),
                    "currency": info.get("currency", "CNY"),
                    "today_usage": 0.0,
                    "is_peak": False,
                }
            })
        return jsonify({"code": 500, "error": "余额接口返回格式异常"})
    except Exception as e:
        return jsonify({"code": 500, "error": str(e)})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        data = request.json
        user_msg = data.get("message", "")
        if not user_msg:
            return jsonify({"code": 400, "error": "消息不能为空"})
        
        from xiaoju3 import load_memory
        messages = load_memory()
        messages.append({"role": "user", "content": user_msg})
        
        print(f"[香橙派收到消息] {user_msg}")
        reply, source = smart_ask(messages, user_msg)
        print(f"[香橙派生成回复] 来源: {source}")
        return jsonify({
            "code": 200,
            "data": {"reply": reply, "source": source}
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"code": 500, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003, debug=False)