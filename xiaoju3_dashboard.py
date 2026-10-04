# -*- coding: utf-8 -*-
"""小橘3号 · 监控仪表盘（Flask，:5003）。

按《功能文档》§9 /《架构设计文档》§2：
- GET /          旧版蓝色单页（内联 HTML，含运行时长与回复来源标签，兼容保留）。
                 已一并处理文档 §3 标注的已知问题：改读新接口嵌套字段
                 {code, data:{cpu, memory, temperature, timestamp}}，让旧版
                 监控真正可用（运行时长由服务端注入的 boot_ts 推算）。
- GET /console   托管新版控制台（index.html + console.js + desktop-pet.js），
                 静态目录为项目根。
- GET /api/status   {code, data:{cpu, memory, temperature, timestamp, tts_voice}}：
                 psutil 取 cpu/memory；温度三平台优先级（用户口径，修复 psutil
                 在 Windows 读不到恒 0 的问题）：① psutil sensors →
                 ② Windows wmi（MSAcpi_ThermalZoneTemperature，开尔文×10 转摄氏）
                 → ③ Linux/香橙派 /sys/class/thermal（÷1000），全部失败返回
                 字符串 "暂无温度"；tts_voice 为前端 TTS 音色（.env TTS_VOICE，
                 与组 B 前端契约）。
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
                 扩展契约（2026-10-01 跨组钉死）：?source=terminal 读取
                 agent_state/history_terminal.json（终端 CLI 通道，R3 写入端
                 xiaoju3.CLI_MEMORY_FILE），文件缺失返回空列表；缺省仍为
                 history_console.json（现状不变）。
- DELETE /api/history 清空控制台聊天历史（确认语义由前端 confirm 承担）。
- POST /api/tts     Edge-TTS 语音合成（用户口径：人类少女音、免费无 Key）：
                 JSON {text, voice?} → audio/mpeg 音频流；edge_tts 延迟导入，
                 服务端未安装 → 501 JSON 中文提示（不让 import 崩溃）；
                 默认音色 zh-CN-XiaoxiaoNeural（晓晓·温柔女声）。
- GET /api/tts      Edge-TTS 自然女声音色表（EDGE_VOICES 常量，前端参考）。

【QQ 接入层并入（2026-10-01 架构合并：彻底废弃 5002 端口）】
- POST /onebot     OneBot 11 webhook（LLOneBot 上报，原 :5002 main.py 路由
                 原样迁入）：视图只做 JSON 解析 + meta_event 心跳日志标记，
                 业务处理一字未改地调 main.onebot_event（think 剥离、触发词/@、
                 图片收藏、戳一戳、LLOneBot 容错均在 main 纯逻辑模块内）。
- GET /api/health  迁移守望探测端点（migration.health_bp 一行注册，随 :5002
                 一并迁入本进程）。
- 💓 心跳 / 多设备守望：dashboard 直接运行（__main__）时经
                 main.start_background_services() 拉起（原 main.py 启动点）。
- 访问日志刷屏抑制：werkzeug logger 挂 _PollAccessFilter（/api/status、
  /api/balance、/api/history 轮询）与 _HeartbeatAccessFilter（/onebot
  meta_event 心跳，原 main.py 过滤器迁入），各自拦截，其余照常输出。

三接口按文档 §9.1 口径均无鉴权（X-API-Key 门禁为规划项 🔜）。
"""
import glob
import logging
import os
import re
import threading
import time

import main  # QQ 接入层业务逻辑模块（架构合并：webhook 业务体宿主于此进程）
import paths  # 双根路径锚（方案 §1）：资源根=静态托管基准，非 frozen 与项目根同值
import psutil
import requests
from flask import Flask, Response, jsonify, render_template_string, request, send_from_directory

from agent_state.state_manager import state_manager  # 待办清单存储（2026-10-04）
from brain import load_memory, save_memory, smart_ask  # 直连大脑（架构设计文档 §2：仪表盘 /api/chat 绕过路由层）
from migration import health_bp  # 迁移守望探测端点（架构 §8，原 :5002 注册点迁入）
from plugins import todo_extractor  # 最近提取任务状态（待办卡片"⏳ 正在阅读"）
from web_sanitize import sanitize_for_web  # Web 出口 CQ 码净化（QQ 通道不经此处）
from xiaoju3 import (AGENT_STATE_DIR, CLOUD_BALANCE_URL, CLOUD_KEY,
                     DASHBOARD_PORT, MAX_MESSAGES, TTS_VOICE,
                     XIAOJU3_VERSION)

app = Flask(__name__)
# 🛡️ 迁移守望探测端点（架构 §8，migration docstring 接入示例：一行注册；
# 原 :5002 main.py 注册点随架构合并迁入）
app.register_blueprint(health_bp)

# 资源根（保名重定义，方案 §1.2）：新版控制台前端文件与 assets 的静态托管基准——
# frozen 下为 _MEIPASS（datas 只读），非 frozen 与项目根同值，行为不变
PROJECT_ROOT = paths.RESOURCE_ROOT


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


# ============================ 访问日志刷屏抑制 ============================
# 用户口径：/api/status（前端 2s 轮询）、/api/balance（余额 60s 轮询）与
# /api/history（终端记录标签页轮询，GET 带 ?source= 等任意参数）的 werkzeug
# 访问日志高频刷屏，予以屏蔽；/api/chat、/onebot、/api/tts、/console 等
# 其余照常输出。
# 实现取舍（对任务建议"降为 DEBUG"的修正）：werkzeug 3.x 首次打日志时会
# 给 logger 自挂 NOTSET 级 StreamHandler（见 werkzeug/_internal._log），
# 而 logger 级别只在 emit 入口把关、不约束 handler——被降级的 DEBUG 记录
# 仍会经 handler 输出。故本过滤器对轮询路径的记录直接返回 False（拦截，
# 等效"任何日志级别下不可见"）；setLevel(INFO) 保底：确保非拦截访问日志
# 在无宿主日志配置时仍按 INFO 正常输出。
_QUIET_LOG_PREFIXES = ("/api/status", "/api/balance", "/api/history")


class _PollAccessFilter(logging.Filter):
    """高频轮询路径（/api/status、/api/balance、/api/history）的 werkzeug
    访问日志拦截器。"""

    # 访问日志行形如：'127.0.0.1 - - [01/Oct/2026 12:00:00] "GET /api/status HTTP/1.1" 200 -'
    _REQUEST_LINE_RE = re.compile(r'"[A-Z]+ (\S+)(?: HTTP/[^"]*)?"')

    def filter(self, record):
        match = self._REQUEST_LINE_RE.search(record.getMessage())
        if match:
            path = match.group(1).split("?", 1)[0]   # 剥查询串只比对路径
            if path.startswith(_QUIET_LOG_PREFIXES):
                return False   # 拦截（取舍说明见上方注释）
        return True


_werkzeug_logger = logging.getLogger("werkzeug")
_werkzeug_logger.setLevel(logging.INFO)   # 保底（取舍说明见上方注释）
_werkzeug_logger.addFilter(_PollAccessFilter())

# ==================== /onebot 心跳事件访问日志抑制（原 :5002 main.py 迁入） ====================
# 用户口径：LLOneBot 心跳（meta_event 的 heartbeat/lifecycle 等高频事件）每次
# POST /onebot 都打一条 werkzeug 访问日志，长期运行刷屏。心跳与消息事件同为
# POST /onebot，访问日志行无法区分——视图内对 meta_event 事件打一次性线程
# 标记，过滤器据此只拦截心跳那一次请求的访问日志；消息类 /onebot 日志保留。
# 拦截（filter 返回 False）而非"降为 DEBUG"的取舍见 _PollAccessFilter 上方
# 注释：werkzeug 3.x 自挂 NOTSET 级 handler，降级 DEBUG 仍会被输出；直接拦截
# 跨日志配置行为确定。
_onebot_meta_local = threading.local()   # 当前线程是否正处理 meta_event 心跳类事件


class _HeartbeatAccessFilter(logging.Filter):
    """meta_event 心跳请求的 werkzeug 访问日志拦截器（一次性线程标记）。"""

    def filter(self, record):
        if getattr(_onebot_meta_local, "is_meta_event", False):
            _onebot_meta_local.is_meta_event = False   # 标记一次性：仅覆盖本次请求
            return False
        return True


_werkzeug_logger.addFilter(_HeartbeatAccessFilter())


# ============================ 静态托管 ============================

@app.route('/assets/<path:filename>')
def get_assets(filename):
    """桌宠吉祥物等静态资源（assets/ 目录，缺失时 404 为文档已知问题）。"""
    return send_from_directory(os.path.join(PROJECT_ROOT, 'assets'), filename)


@app.route('/console')
def console():
    """新版控制台首页（index.html + console.js + desktop-pet.js）。

    防缓存终极方案（2026-10-01 用户指令）：返回前给 index.html 中引用的
    前端脚本自动追加时间戳版本参数（console.js?v=<文件mtime>）——文件每次
    更新版本号随之变化，浏览器必然拉取最新 JS，无需手动改版本号；
    叠加 after_request 的 no-store 头双保险。
    """
    html_path = os.path.join(PROJECT_ROOT, 'index.html')
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()
    except OSError:
        return send_from_directory(PROJECT_ROOT, 'index.html')

    def _mtime_ver(name):
        try:
            return str(int(os.path.getmtime(os.path.join(PROJECT_ROOT, name))))
        except OSError:
            return '0'

    html = html.replace('src="/console/desktop-pet.js"',
                        f'src="/console/desktop-pet.js?v={_mtime_ver("desktop-pet.js")}"')
    html = html.replace('src="/console/console.js"',
                        f'src="/console/console.js?v={_mtime_ver("console.js")}"')
    return html


@app.route('/console/<path:filename>')
def console_static(filename):
    return send_from_directory(PROJECT_ROOT, filename)


# ============================ 工具函数 ============================

# 温度读取失败/平台不支持时 /api/status 的占位文案（用户口径，替换旧恒 0.0）
NO_TEMP_TEXT = "暂无温度"


def _temp_from_psutil():
    """温度优先级①：psutil.sensors_temperatures 跨平台首选（Linux/香橙派
    直接可用；Windows 上 psutil 未实现该方法，抛 NotImplementedError 后
    自然落到下一优先级）。无可用值返回 None。"""
    try:
        temps = psutil.sensors_temperatures()
        for entries in (temps or {}).values():
            for t in entries:
                if getattr(t, "current", None):
                    return float(t.current)
    except Exception:
        pass
    return None


def _temp_from_wmi():
    """温度优先级②（Windows）：WMI MSAcpi_ThermalZoneTemperature 的
    CurrentTemperature 为开尔文×10，转换摄氏度 = (值 / 10) - 273.15。
    wmi 为 Windows 专用依赖（requirements.txt）：函数内延迟导入，未安装 /
    非 Windows / 无传感器或权限不足（多数设备该命名空间需管理员）时返回
    None 优雅跳过，绝不让 import 崩溃。"""
    try:
        import wmi  # 延迟导入：未装 / 非 Windows 优雅跳过
    except Exception:
        return None
    try:
        zones = wmi.WMI(namespace="root/wmi").MSAcpi_ThermalZoneTemperature()
        for zone in zones:
            current = getattr(zone, "CurrentTemperature", None)
            if current:
                return float(current) / 10.0 - 273.15
    except Exception:
        pass
    return None


def _temp_from_sys_thermal():
    """温度优先级③（Linux/香橙派）：/sys/class/thermal/thermal_zone*/temp
    单位为毫摄氏度，÷1000 转摄氏度；按路径序取第一个可解析的有效值，
    读不到/非数字（驱动未就绪）跳过继续。无可用 zone 返回 None。"""
    for path in sorted(glob.glob("/sys/class/thermal/thermal_zone*/temp")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            if raw:
                return float(raw) / 1000.0   # 毫摄氏度 → 摄氏度
        except (OSError, ValueError):
            continue
    return None


def get_cpu_temp():
    """读取 CPU 温度（用户口径三平台优先级）：
    ① psutil.sensors_temperatures → ② Windows wmi → ③ Linux /sys/class/thermal。
    读取失败或平台不支持返回字符串 "暂无温度"（替换旧恒 0.0）；成功返回
    float 摄氏度。"""
    for reader in (_temp_from_psutil, _temp_from_wmi, _temp_from_sys_thermal):
        value = reader()
        if value is not None:
            return float(value)
    return NO_TEMP_TEXT


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
                    // 温度数值走进度条；"暂无温度"（字符串占位）直接展示、进度条归零
                    if (typeof d.temperature === 'number') {
                        document.getElementById('temp-val').innerText = d.temperature.toFixed(1) + '°C';
                        document.getElementById('temp-bar').style.width = Math.min(d.temperature * 2, 100) + '%';
                    } else {
                        document.getElementById('temp-val').innerText = d.temperature;
                        document.getElementById('temp-bar').style.width = '0%';
                    }
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
# 终端 CLI 通道历史（跨组契约 2026-10-01：写端为 xiaoju3.CLI_MEMORY_FILE，
# R3 终端 REPL 每轮落盘；本模块只读展示，文件缺失回退空列表）
TERMINAL_HISTORY_FILE = os.path.join(AGENT_STATE_DIR, "history_terminal.json")


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
    """聊天历史 API：{code, data:{messages:[...]}}（按时间正序）。

    source 参数（2026-10-01 跨组钉死契约，组 R3 终端记录展示依赖）：
    - 缺省：控制台聊天历史 history_console.json（现状不变）；
    - source=terminal：终端 CLI 通道 history_terminal.json（文件缺失返回
      空列表，接口恒 200）；格式与控制台通道一致（纯 [{role, content}]）。
    """
    if (request.args.get("source") or "").strip().lower() == "terminal":
        return jsonify({"code": 200, "data": {"messages": load_memory(TERMINAL_HISTORY_FILE)}})
    return jsonify({"code": 200, "data": {"messages": _read_console_history()}})


@app.route("/api/history", methods=["DELETE"])
def api_history_delete():
    """清空控制台聊天历史：返回清空后的空列表结构。"""
    _clear_console_history()
    return jsonify({"code": 200, "data": {"messages": []}})


@app.route("/api/status")
def api_status():
    """系统状态 API：{code, data:{cpu, memory, temperature, timestamp, tts_voice,
    version, creator}}。

    psutil 异常时 cpu/memory 回退 0.0，不让接口 500；temperature 走三平台
    读取链（get_cpu_temp），全失败返回 "暂无温度"；tts_voice 供前端 TTS
    音色选择（组 B 前端契约）；version 为程序版本（安装器方案步 A1，
    源头 xiaoju3.XIAOJU3_VERSION）。
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
            "temperature": get_cpu_temp(),   # 三平台读取链，失败 "暂无温度"
            "timestamp": int(time.time()),
            "tts_voice": TTS_VOICE,          # 前端 TTS 音色（组 B 前端消费）
            "version": XIAOJU3_VERSION,      # 程序版本（步 A1，前端标题徽标）
            "creator": main.get_creator_name() or None,   # 创作者署名（批次②）
        }
    })


@app.route("/api/todos")
def api_todos():
    """待办清单 API（2026-10-04 待办提取，docs/TODO_EXTRACT_DESIGN.md §6）：
    {code, data:{todos, pending_count, done_count, last_job}}。

    todos 含全部状态（前端自行分组渲染）；last_job 为最近一次链接提取任务
    状态（todo_extractor 单槽，无任务时 None），卡片据此显示"⏳ 正在阅读"。
    """
    todos = state_manager.get_todos(limit=200)   # 尾巴 G：卡片全量口径（旧默认 50 会截断）
    pending_count = sum(1 for t in todos if t["status"] == "pending")
    return jsonify({
        "code": 200,
        "data": {
            "todos": todos,
            "pending_count": pending_count,
            "done_count": len(todos) - pending_count,
            "last_job": todo_extractor.last_job(),
        }
    })


@app.route("/api/todos/<int:todo_id>/done", methods=["POST"])
def api_todo_done(todo_id):
    """标记待办完成。安全注记（设计稿 §6 如实口径）：dashboard 现绑
    0.0.0.0（§11 遗留④加固候选未落地），LAN 内可匿名调本端点——影响面=
    标记待办完成（低危）；127.0.0.1 加固落地后自动收窄。"""
    todo = state_manager.complete_todo(todo_id)
    if not todo:
        return jsonify({"code": 404, "data": {"ok": False}}), 404
    return jsonify({"code": 200, "data": {"ok": True, "todo": todo}})


@app.route("/api/todos/<int:todo_id>/reopen", methods=["POST"])
def api_todo_reopen(todo_id):
    """把已完成待办翻回未完成（2026-10-04 尾巴 1：复选框取消钩；
    与 done 端点对称的低危写端点，安全口径同 api_todo_done）。"""
    todo = state_manager.reopen_todo(todo_id)
    if not todo:
        return jsonify({"code": 404, "data": {"ok": False}}), 404
    return jsonify({"code": 200, "data": {"ok": True, "todo": todo}})


@app.route("/api/todos/<int:todo_id>/priority", methods=["POST"])
def api_todo_priority(todo_id):
    """设置待办优先级（2026-10-04 尾巴 C：前端 P0/P1/P2 pill；
    低危写端点，安全口径同 api_todo_done；非法 priority 归一 P1）。"""
    body = request.get_json(silent=True) or {}
    todo = state_manager.set_todo_priority(todo_id, body.get("priority"))
    if not todo:
        return jsonify({"code": 404, "data": {"ok": False}}), 404
    return jsonify({"code": 200, "data": {"ok": True, "todo": todo}})


@app.route("/api/first_run/status")
def api_first_run_status():
    """首装判定（安装器方案步 A3）：ENV_FILE 不存在即 first_run。"""
    from first_run import is_first_run  # 延迟导入：非引导场景依赖面零变化
    return jsonify({
        "code": 200,
        "data": {"first_run": is_first_run(), "version": XIAOJU3_VERSION},
    })


@app.route("/api/first_run/probes")
def api_first_run_probes():
    """首装探针聚合（安装器方案步 A3）：四探针并行**只读**探测——
    不写盘、不拉任何服务（NapCat 只检测不拉起），探针实现复用既有函数。"""
    from first_run import is_first_run, run_probes  # 延迟导入同上
    return jsonify({
        "code": 200,
        "data": {"first_run": is_first_run(), "probes": run_probes()},
    })


@app.route("/api/first_run/installer_report")
def api_first_run_installer_report():
    """安装器意向报告（安装器步 B3 消费端，
    docs/INSTALLER_STEP_B3_CONSUMER_DESIGN.md）：只读展示安装期硬件建议
    与三组件意向。独立于 probes（探针是运行态带网络超时；报告读盘即时），
    各自独立降级——文件缺失（便携/直跑/升级后）返回 available:False，
    前端 hints 块保持隐藏。"""
    from first_run import read_installer_report  # 延迟导入：非引导场景依赖面零变化
    return jsonify({
        "code": 200,
        "data": read_installer_report(),
    })


@app.route("/api/first_run/complete", methods=["POST"])
def api_first_run_complete():
    """首装完成落盘（安装器方案步 A4a）：
    - env 子集直调 save_env_file（A2 四防线：39 键白名单硬边界、单槽备份、
      原子落盘、增量合并）；OSError → 500 + 中文 error（原子性保证原文件不损）；
    - autostart=true 时写 HKCU Run 自启键，失败降级 warning 不落 500
      （自启非关键路径）；
    - first_run 翻转零状态代码：.env 落盘即自然变 false（is_first_run 判定
      即文件存在性）。"""
    from autostart import write as autostart_write  # 延迟导入同上
    from first_run import is_first_run
    from xiaoju3 import save_env_file

    payload = request.get_json(silent=True) or {}
    env_updates = payload.get("env") or {}
    want_autostart = bool(payload.get("autostart"))
    warning = None
    try:
        written, skipped, _ = save_env_file(env_updates)
    except OSError as e:
        return jsonify({"code": 500,
                        "error": f"配置保存失败：{e}（原配置未改动，可重试）"}), 500
    if want_autostart:
        try:
            if not autostart_write():
                warning = ("开机自启写入未成功（非 Windows 或权限不足），"
                           "可稍后在设置页重试")
        except Exception as e:  # 自启失败绝不阻塞首装完成
            warning = f"开机自启写入异常：{e}"
    from first_run import clear_skipped, is_first_run  # 延迟导入同上
    clear_skipped()   # 完成落盘顺手清跳过标记（存在才清，幂等）
    return jsonify({
        "code": 200,
        "data": {"written": written, "skipped": skipped,
                 "first_run": is_first_run(), "warning": warning},
    })


@app.route("/api/first_run/skip", methods=["POST"])
def api_first_run_skip():
    """跳过首装引导（安装器方案步 A4b/C：后端文件承载跳过标记，弃用
    localStorage——浏览器/WebView2 容器差异免疫）。写
    xiaoju3_data/.first_run_skipped 后 first_run 自然翻转为 False。"""
    from first_run import is_first_run, mark_skipped  # 延迟导入同上
    mark_skipped()
    return jsonify({
        "code": 200,
        "data": {"first_run": is_first_run(), "version": XIAOJU3_VERSION},
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

        # 📍 位置指令（2026-10-02 隐私口径）：与 QQ 通道同一处理逻辑
        # （main.handle_location_command；命中即系统消息返回，不进大脑）
        location_reply = main.handle_location_command(user_msg)
        if location_reply is not None:
            return jsonify({
                "code": 200,
                "data": {"reply": sanitize_for_web(location_reply),
                         "source": "⚙️ 系统"}
            })

        # 🔒 儿童锁裁决 + ✍️ 创作者署名（2026-10-02 批次②）：与 QQ 通道
        # 同一 main 函数；网页控制台视为成人设备（is_console=True）
        child_reply = main.handle_child_command(user_msg, user_id="console",
                                                is_console=True)
        if child_reply is not None:
            return jsonify({
                "code": 200,
                "data": {"reply": sanitize_for_web(child_reply),
                         "source": "⚙️ 系统"}
            })
        if user_msg.strip() == "/creator":
            return jsonify({
                "code": 200,
                "data": {"reply": sanitize_for_web(main.handle_creator_command()),
                         "source": "⚙️ 系统"}
            })

        # 📋 待办指令族拦截（2026-10-04 Bug 1 修复 + 尾巴 3 过程卡片）：控制台
        # 与 QQ 同一指令链（main.handle_todo_command），命中即返回——不进模型、
        # 不落对话历史，与 /creator 特判同口径；user_id/group_id 传 None：门禁
        # 走全局等级，提取完成通知仅打印控制台日志（无 QQ 上下文）。
        # 尾巴 3：复用 <think> 协议出"指令处理"折叠卡——console.js 渲染入口
        # 对任何含 <think> 的回复出卡（THINK_BLOCK_RE 全局守卫），QQ 链路剥
        # <think> 故过程仅控制台可见，与模型消息同一渲染管线、零前端改动。
        todo_steps = []
        todo_reply = main.handle_todo_command(user_msg, user_msg, None, None,
                                              steps=todo_steps)
        if todo_reply is not None:
            process = "".join("\n· " + s for s in todo_steps)
            reply = "<think>[指令处理]" + process + "</think>" + todo_reply
            return jsonify({
                "code": 200,
                "data": {"reply": sanitize_for_web(reply),
                         "source": "⚙️ 指令"}
            })

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


# ==================== QQ 接入层 webhook（原 :5002 POST /onebot 原样迁入） ====================

@app.route('/onebot', methods=['POST'])
def onebot_webhook():
    """OneBot 11 webhook（LLOneBot 上报；架构合并后 :5003 一个端口承载一切）。

    视图只做两件事：① 解析 JSON；② meta_event 心跳事件打一次性线程标记
    （本次请求的 werkzeug 访问日志由 _HeartbeatAccessFilter 拦截，防刷屏；
    消息类 /onebot 日志不受影响）。业务处理（戳一戳、LLOneBot 容错、
    handle_message 指令族、think 剥离、NapCat 回发）在 main.onebot_event
    纯逻辑函数内，一字未改。
    """
    data = request.get_json(silent=True) or {}

    if data.get('post_type') == 'meta_event':
        _onebot_meta_local.is_meta_event = True

    return main.onebot_event(data)


# ============================ Edge-TTS 语音合成（/api/tts） ============================
# 用户口径：人类少女音、免费无 Key——edge-tts 走微软 Edge 在线朗读接口，
# 免注册、免费、无 API Key。依赖策略沿用红线"延迟导入 + 优雅降级"：服务端
# 未安装时接口返回 501 + 清晰中文提示，绝不让模块 import 崩溃。
DEFAULT_TTS_VOICE = "zh-CN-XiaoxiaoNeural"   # 晓晓：自然温柔的少女音（默认）

# 前端音色参考表（自然女声，GET /api/tts 下发，前端下拉渲染用；
# 互不重复，首个为默认音色）
EDGE_VOICES = [
    {"voice": "zh-CN-XiaoxiaoNeural", "name": "晓晓 · 温柔女声（默认）"},
    {"voice": "zh-CN-XiaoyiNeural",   "name": "晓伊 · 活泼少女音"},
    {"voice": "zh-CN-XiaomoNeural",   "name": "晓墨 · 阳光女声"},
    {"voice": "zh-CN-XiaoqiuNeural",  "name": "晓秋 · 知性女声"},
]


def _edge_tts_synthesize(text, voice):
    """同步封装 edge-tts 合成：asyncio.run 包一层（Flask 同步上下文直接可用），
    收集 Communicate.stream() 的 audio 分片拼接为完整 MP3 bytes 返回。

    stream() 产出 {"type": "audio"|"WordBoundary", ...} 混合分片，只收集
    audio；连接/读取超时由 edge-tts 自身默认值兜底（连接 10s / 读取 60s），
    断网等异常向上抛出、由 /api/tts 统一转 500 JSON。
    """
    import asyncio

    import edge_tts   # 延迟导入：未安装时上层已先行 501，此处正常可用

    async def _collect():
        chunks = []
        async for part in edge_tts.Communicate(text, voice).stream():
            if part.get("type") == "audio":
                chunks.append(part["data"])
        return b"".join(chunks)

    return asyncio.run(_collect())


@app.route("/api/tts", methods=["GET"])
def api_tts_voices():
    """Edge-TTS 音色表：{code, data:{default, voices:[{voice, name}]}}。"""
    return jsonify({
        "code": 200,
        "data": {"default": DEFAULT_TTS_VOICE, "voices": EDGE_VOICES},
    })


@app.route("/api/tts", methods=["POST"])
def api_tts():
    """语音合成 API：JSON {text, voice?} → audio/mpeg 字节流（前端 <audio> 直播）。

    - text 空 → 400 JSON {code, error}；
    - 服务端未安装 edge-tts → 501 JSON {error:"服务端未安装 edge-tts"}；
    - 合成异常（断网/音色非法等）→ 500 JSON {error}（附简短中文原因）。
    """
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "").strip()
    if not text:
        return jsonify({"code": 400, "error": "文本不能为空"}), 400
    voice = str(data.get("voice") or DEFAULT_TTS_VOICE)

    try:
        import edge_tts   # noqa: F401  延迟导入探测：sys.modules 缺失/置 None 即 ImportError
    except Exception:
        return jsonify({"code": 501, "error": "服务端未安装 edge-tts"}), 501

    try:
        audio = _edge_tts_synthesize(text, voice)
    except Exception as e:
        return jsonify({"code": 500, "error": f"语音合成失败: {e}"}), 500

    if not audio:
        # 服务端在线但未产出任何音频分片：按失败口径处理，不给前端空音频
        return jsonify({"code": 500, "error": "语音合成失败: 未返回音频数据"}), 500
    return Response(audio, mimetype="audio/mpeg")


def serve():
    """5003 服务主函数（原 __main__ 逻辑原样抽函数，行为不变）。

    spawn-self 分流（方案 §2）的 dashboard 角色入口：exe 以
    --xj3-role=dashboard 拉起自身时由 desktop_launcher 调用本函数。
    """
    from xiaoju3_launcher import _redirect_stdio  # 延迟导入：保持现依赖面
    _redirect_stdio("dashboard")  # frozen 入口重定向（步 3）；非 frozen 空操作
    print(f"🍊 小橘3号监控仪表盘已启动（端口 {DASHBOARD_PORT}）")
    _creator = main.get_creator_name()
    if _creator:
        print(f"✍️ 创作者署名：{_creator}")
    print("🔌 QQ 接入层已并入本进程（5002 端口废弃）：webhook 地址 "
          "http://127.0.0.1:5003/onebot，请同步修改 LLOneBot 的 HTTP 上报地址")

    # 💓 心跳 + 多设备互相守望（原 main.py __main__ 启动点，随架构合并移交
    # 本进程拉起：start_heartbeat daemon 线程 + PeerWatch（默认关闭））
    main.start_background_services()

    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False)


if __name__ == "__main__":
    import multiprocessing
    # PyInstaller 冻结形态安全阀（方案 §2.2）：onefile 子进程引导必需
    multiprocessing.freeze_support()
    serve()
