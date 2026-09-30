# -*- coding: utf-8 -*-
"""小橘3号 · 监控仪表盘（Flask，:5003）。

按《功能文档》§9 /《架构设计文档》§2：
- GET /          旧版蓝色单页（内联 HTML，含运行时长与回复来源标签，兼容保留）。
                 已一并处理文档 §3 标注的已知问题：改读新接口嵌套字段
                 {code, data:{cpu, memory, temperature, timestamp}}，让旧版
                 监控真正可用（运行时长由服务端注入的 boot_ts 推算）。
- GET /console   托管新版控制台（index.html + console.js + desktop-pet.js），
                 静态目录为项目根。
- GET /api/status   {code, data:{cpu, memory, temperature, timestamp}}：psutil
                 取值，温度取 sensors_temperatures 首个可用值，失败回退 0.0。
- GET /api/balance  {code, data:{balance, currency, today_usage, is_peak}}：
                 GET CLOUD_BALANCE_URL + Bearer CLOUD_KEY；today_usage 按文档
                 口径恒 0.0（真实消耗统计未接入）；无 KEY / 请求失败回退 0.0
                 并附错误提示。
- POST /api/chat    直连 brain.smart_ask（不经 main.py 路由层、不写 QQ/网页
                 双通道记忆），JSON 入参 {message, history?}，返回
                 {code, data:{reply, source}}；成功问答追加落盘控制台会话
                 历史 history_console.json（与 QQ/网页双通道同口径，
                 50 条滚动截断——功能文档 §12 安全增强 / 界面文档 §10.4 近期项）。
                 回复在返回与落盘前统一经 web_sanitize.sanitize_for_web 净化
                 （face 码→Emoji、image 码→[表情]、其余 CQ 码剥除）——共享
                 大脑链路带回的 QQ 专用 CQ 码不再漏进网页；QQ 通道
                 （main.py /onebot → NapCat）不经此处，发图能力不受影响。
- GET /api/history  {code, data:{messages:[...]}}：控制台聊天历史（role/content，
                 assistant 条目附 source 来源标签），供前端页面加载时渲染。
- DELETE /api/history 清空控制台聊天历史（确认语义由前端 confirm 承担）。
- 静态路由（/console*、/assets*）统一 Cache-Control: no-store——浏览器每次
  刷新都拉取最新 HTML/JS，避免发版后命中旧版 console.js 导致前端修复不生效。

三接口按文档 §9.1 口径均无鉴权（X-API-Key 门禁为规划项 🔜）。
"""
import os
import time

import psutil
import requests
from flask import Flask, jsonify, render_template_string, request, send_from_directory

from brain import load_memory, save_memory, smart_ask  # 直连大脑（架构设计文档 §2：仪表盘 /api/chat 绕过路由层）
from web_sanitize import sanitize_for_web  # Web 出口 CQ 码净化（QQ 通道不经此处）
from xiaoju3 import (AGENT_STATE_DIR, CLOUD_BALANCE_URL, CLOUD_KEY,
                     DASHBOARD_PORT, MAX_MESSAGES)

app = Flask(__name__)

# 项目根目录（新版控制台前端文件与 assets 的静态托管基准）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


@app.after_request
def _no_store_static(resp):
    """静态路由统一 no-store：刷新页面即取最新 JS，行为跨 Werkzeug 版本/代理确定。

    send_from_directory 的默认缓存头随版本/反代而变（可能回落启发式缓存），
    这里对 /console*（控制台页与前端脚本）与 /assets*（吉祥物素材）显式覆盖；
    /api/* 接口响应不套用。
    """
    if request.path.startswith("/console") or request.path.startswith("/assets/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp

# 仪表盘进程启动时间（psutil.boot_time 不可用时"运行时长"兜底基准）
PROCESS_START = int(time.time())


# ============================ 静态托管 ============================

@app.route('/assets/<path:filename>')
def get_assets(filename):
    """桌宠吉祥物等静态资源（assets/ 目录，缺失时 404 为文档已知问题）。"""
    return send_from_directory(os.path.join(PROJECT_ROOT, 'assets'), filename)


@app.route('/console')
def console():
    """新版控制台首页（index.html + console.js + desktop-pet.js）。"""
    return send_from_directory(PROJECT_ROOT, 'index.html')


@app.route('/console/<path:filename>')
def console_static(filename):
    return send_from_directory(PROJECT_ROOT, filename)


# ============================ 工具函数 ============================

def get_cpu_temp():
    """读取 CPU 温度：psutil.sensors_temperatures 取首个可用值，失败回退 0.0。"""
    try:
        temps = psutil.sensors_temperatures()
        for entries in (temps or {}).values():
            for t in entries:
                if getattr(t, "current", None):
                    return float(t.current)
    except Exception:
        pass
    return 0.0


def _boot_ts():
    """系统启动时间戳（旧版页"运行时长"推算基准），失败回退进程启动时间。"""
    try:
        return int(psutil.boot_time())
    except Exception:
        return PROCESS_START


# ============================ 旧版蓝色单页 ============================

@app.route("/")
def index():
    """旧版仪表盘内嵌页（兼容保留）。已改读 /api/status 的嵌套字段，
    修复文档 §3 标注的 data.temp / data.uptime 字段失配问题。"""
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
            const BOOT_TS = {{ boot_ts }}; // 服务端注入的系统启动时间戳（运行时长推算）

            function updateStatus() {
                // 已修复：读取 /api/status 的嵌套字段 {code, data:{cpu, memory, temperature}}
                fetch('/api/status').then(r => r.json()).then(res => {
                    if (res.code !== 200 || !res.data) return;
                    const d = res.data;
                    document.getElementById('cpu-val').innerText = d.cpu.toFixed(1) + '%';
                    document.getElementById('cpu-bar').style.width = d.cpu + '%';
                    document.getElementById('mem-val').innerText = d.memory.toFixed(1) + '%';
                    document.getElementById('mem-bar').style.width = d.memory + '%';
                    document.getElementById('temp-val').innerText = d.temperature.toFixed(1) + '°C';
                    document.getElementById('temp-bar').style.width = Math.min(d.temperature * 2, 100) + '%';
                    let uptimeSec = Math.floor(Date.now()/1000) - BOOT_TS;
                    document.getElementById('uptime-val').innerText = Math.floor(uptimeSec/3600) + 'h ' + Math.floor((uptimeSec%3600)/60) + 'm';
                });
            }
            setInterval(updateStatus, 3000); updateStatus();

            function fetchBalance() {
                // 已修复：读取 /api/balance 的嵌套字段 {code, data:{balance}}
                fetch('/api/balance').then(r => r.json()).then(res => {
                    if (res.code === 200 && res.data) document.getElementById('balance-text').innerText = '¥' + res.data.balance.toFixed(2);
                    else document.getElementById('balance-text').innerText = '查询失败';
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
                }).then(r => r.json()).then(res => addMessage('ai', res.data.reply + ' <br><small>(' + res.data.source + ')</small>'))
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
    ''', boot_ts=_boot_ts())


# ============================ 状态 / 余额 / 聊天 API ============================

# ============================ 控制台聊天历史持久化 ============================
# 功能文档 §12 安全增强 / 界面文档 §10.4 近期项：控制台聊天历史此前仅存页面
# 内存、刷新即清空，现与 QQ/网页双通道同口径落盘 agent_state/history_console.json
# （50 条滚动截断），读写直接复用 brain.load_memory / brain.save_memory。
HISTORY_FILE = os.path.join(AGENT_STATE_DIR, "history_console.json")


def _read_console_history():
    """读取控制台会话历史（role/content JSON 列表，缺失或损坏返回空列表）。"""
    return load_memory(HISTORY_FILE)


def _append_console_history(user_msg, reply, source):
    """成功问答后追加用户消息与回复，滚动保留最近 MAX_MESSAGES=50 条。

    assistant 条目额外携带 source（大脑来源标签），供前端渲染"大脑来源"徽标。
    """
    history = _read_console_history()
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": reply, "source": source})
    if len(history) > MAX_MESSAGES:
        history = history[-MAX_MESSAGES:]
    save_memory(history, HISTORY_FILE)
    return history


def _clear_console_history():
    """清空控制台会话历史（写回空列表；确认语义由前端 confirm 承担）。"""
    save_memory([], HISTORY_FILE)


@app.route("/api/history", methods=["GET"])
def api_history():
    """控制台聊天历史 API：{code, data:{messages:[...]}}（按时间正序）。"""
    return jsonify({"code": 200, "data": {"messages": _read_console_history()}})


@app.route("/api/history", methods=["DELETE"])
def api_history_delete():
    """清空控制台聊天历史：返回清空后的空列表结构。"""
    _clear_console_history()
    return jsonify({"code": 200, "data": {"messages": []}})


@app.route("/api/status")
def api_status():
    """系统状态 API：{code, data:{cpu, memory, temperature, timestamp}}。

    psutil 异常时对应字段回退 0.0，不让接口 500。
    """
    try:
        cpu = float(psutil.cpu_percent(interval=0.5))
    except Exception:
        cpu = 0.0
    try:
        memory = float(psutil.virtual_memory().percent)
    except Exception:
        memory = 0.0
    return jsonify({
        "code": 200,
        "data": {
            "cpu": cpu,
            "memory": memory,
            "temperature": get_cpu_temp(),   # sensors_temperatures 取可用值，失败 0.0
            "timestamp": int(time.time()),
        }
    })


def _balance_fallback(error):
    """余额兜底结构：余额回退 0.0 并附错误提示（前端据此展示失败态）。"""
    return jsonify({
        "code": 500,
        "error": error,
        "data": {"balance": 0.0, "currency": "CNY", "today_usage": 0.0, "is_peak": False},
    })


@app.route("/api/balance")
def api_balance():
    """DeepSeek 余额查询 API：{code, data:{balance, currency, today_usage, is_peak}}。"""
    if not CLOUD_KEY:
        return _balance_fallback("未配置 DEEPSEEK_API_KEY，无法查询余额")
    headers = {"Authorization": f"Bearer {CLOUD_KEY}"}
    try:
        resp = requests.get(CLOUD_BALANCE_URL, headers=headers, timeout=10)
        raw = resp.json()
        if "balance_infos" in raw and len(raw["balance_infos"]) > 0:
            info = raw["balance_infos"][0]
            return jsonify({
                "code": 200,
                "data": {
                    "balance": float(info.get("total_balance", 0)),
                    "currency": info.get("currency", "CNY"),
                    "today_usage": 0.0,   # 文档口径：今日消耗统计未接入，恒 0.0
                    "is_peak": False,
                }
            })
        return _balance_fallback("余额接口返回格式异常")
    except Exception as e:
        return _balance_fallback(f"余额查询失败: {e}")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """聊天 API：直连 brain.smart_ask，返回 {code, data:{reply, source}}。

    不经 main.py 的 handle_message 路由层，也不写 QQ/网页双通道记忆
    （架构设计文档 §2 图注口径）；控制台侧问答成功后落盘
    history_console.json（50 条滚动截断，功能文档 §12 口径）。
    """
    try:
        data = request.get_json(silent=True) or {}
        user_msg = data.get("message", "")
        if not user_msg:
            return jsonify({"code": 400, "error": "消息不能为空"})

        history = data.get("history") or []
        print(f"[香橙派收到消息] {user_msg}")
        reply, source = smart_ask(user_msg, history)
        print(f"[香橙派生成回复] 来源: {source}")
        # 🛡️ Web 出口净化（纵深防御）：smart_ask 共享链路可能带回 QQ 专用 CQ 码
        # （face 表情码 / [CQ:image] 表情包等），网页无法解析——返回与落盘前统一
        # 转换（face→Emoji、image→[表情]、其余剥除），网页永不显示方括号原文；
        # QQ 通道（main.py /onebot → NapCat）不经此处，CQ 发图能力不受影响。
        reply = sanitize_for_web(reply)
        # 历史持久化失败不影响问答返回（尽力落盘）
        try:
            _append_console_history(user_msg, reply, source)
        except Exception as persist_err:
            print(f"[控制台历史落盘失败] {persist_err}")
        return jsonify({
            "code": 200,
            "data": {"reply": reply, "source": source}
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"code": 500, "error": str(e)}), 500


if __name__ == "__main__":
    print(f"🍊 小橘3号监控仪表盘已启动（端口 {DASHBOARD_PORT}）")
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False)
