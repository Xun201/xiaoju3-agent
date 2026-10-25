# -*- coding: utf-8 -*-
"""agent_state/plugins/video_ingest · 信息摄取插件（#348，v0.2 转写闭环）。

v0.1 元数据提取（yt-dlp，B 站真调 PASS）+ v0.2 转写闭环（2026-10-25）：
链接 → 元数据 →（异步）下载音频 → faster-whisper 转写 → LLM 提炼 3-5 观点
→ 落盘 video_notes/ + 状态可查。

选型依据（法则 1，四维度）：faster-whisper 1.2.1（SYSTRAN，CTranslate2 int8
CPU 约 20x 实时 / 维护稳定 / Python 原生契合插件契约 / pip --target 零包体）；
whisper.cpp CPU 略快+维护更猛但 C++ 编译分发不合本项目打包体系。依赖目录
agent_state/plugins/_deps/（274MB，运维 pip install --target 管理，下划线
开头=总线扫描跳过），setup 钩子 sys.path 注入——frozen exe 零打包增量。

诚实交底（队长三问）：体积=_deps 274MB 磁盘+模型 base 约 145MB（HF 镜像首跑
自动下载，落 _deps_models）；速度=3 分钟音频 base int8 CPU 约 30-60s（实测
见 STATE）；**必须异步**——同步会卡对话通道，本版=受理即回+后台线程+状态
查询（完成后主动推送留三期：控制台历史无轮询推送通道）。

隔离纪律：转写全程后台 daemon 线程+单例锁（并发闸 1）+每步 try/except 落
状态——插件任何故障不触达主程序（dispatch 双层兜底之外再加一层）。
"""
import os
import sys
import threading

def PLUGIN():
        return {
        "name": "video_ingest",
        "version": "0.2.0",
        "desc": "视频信息摄取+语音转写+观点提炼（yt-dlp+faster-whisper+LLM）",
        "author": "xun",
        "level": 3,
        "tools": [
            {"name": "ext_fetch_video_info",
             "desc": "提取视频链接的信息（标题/简介/时长/作者），支持 B站/抖音/YouTube 等；"
                     "不下载视频，只读元数据",
             "params": "url (完整视频链接，http/https 开头)",
             "note": "当主人发来视频链接并想了解这个视频是什么/讲了什么时使用",
             "handler": "agent_state_plugins_video_ingest:fetch_video_info"},
            {"name": "ext_transcribe_video",
             "desc": "深度解析视频：下载音频并转写成文字，提炼 3-5 个核心观点"
                     "（后台任务，受理即回，用 ext_transcribe_status 查询结果）",
             "params": "url (完整视频链接)",
             "note": "当主人想让小橘看完/听完一个视频并总结观点时使用（比 ext_fetch_video_info 更深，耗时 1-2 分钟）",
             "handler": "agent_state_plugins_video_ingest:start_transcribe"},
            {"name": "ext_transcribe_status",
             "desc": "查询视频深度解析任务的状态与结果（running/done/error 与提炼观点）",
             "params": "无（查最近一个任务）",
             "handler": "agent_state_plugins_video_ingest:status_reply"},
        ],
        "intents": [
            {"name": "ext_video_ingest", "desc": "解析视频链接信息",
             "patterns": [r"(解析|提取|看看?|读一?下).{0,12}(这个?|这个?)视频",
                          r"视频.{0,8}(讲了?什么|什么内容|什么信息|信息|简介)"],
             "extractor": extract_video_url,
             "handler_name": "agent_state_plugins_video_ingest:reply"},
            {"name": "ext_video_transcribe", "desc": "深度解析视频（转写+观点）",
             "patterns": [r"(看完|听完|总结|提炼|深度解析).{0,10}(这个?|这个?)视频",
                          r"(总结|提炼).{0,8}观点"],
             "extractor": extract_video_url,
             "handler_name": "agent_state_plugins_video_ingest:transcribe_reply"},
            {"name": "ext_video_status", "desc": "查询转写状态与结果",
             "patterns": [r"(查|看).{0,4}转写状态", r"转写(得|的)?(怎么样|如何|结果)",
                          r"转写状态"],
             "extractor": _extract_noargs,
             "handler_name": "agent_state_plugins_video_ingest:status_reply"},
        ],
        "setup": setup,
        "teardown": teardown,
    }

# ── 运行时状态（插件内单例；主程序不碰） ──
_LOCK = threading.Lock()
_JOB = {"state": "idle", "url": "", "title": "", "error": "",
        "result_path": "", "started": 0.0, "elapsed": 0.0}
_DEPS = None      # setup 注入：插件 deps 目录（sys.path 注入点）
_DATA = None      # 插件数据目录（video_notes 落盘位）


def setup(ctx):
    """生命周期钩子：sys.path 注入依赖目录+数据目录就位（依赖自足关键）。"""
    global _DEPS, _DATA
    _DEPS = os.path.abspath(os.path.join(ctx.get("data_dir") or "",
                                         os.pardir, "_deps"))
    _DATA = os.path.abspath(ctx.get("data_dir")
                            or os.path.join(_DEPS, os.pardir, "video_ingest_data"))
    os.makedirs(_DATA, exist_ok=True)
    os.makedirs(os.path.join(_DATA, "video_notes"), exist_ok=True)
    if os.path.isdir(_DEPS) and _DEPS not in sys.path:
        sys.path.insert(0, _DEPS)   # faster-whisper/ctranslate2 自带依赖加载
    # 预检 import（装载期暴露依赖问题+预热 sys.modules——转写线程 import
    # 必命中缓存，结构上消灭"线程内 No module"错位）：
    try:
        import faster_whisper  # noqa: F401
        ctx.get("log")("faster_whisper 预检通过")
    except Exception as e:
        raise RuntimeError(f"依赖预检失败（faster-whisper 不可用）: {e}")
    ctx.get("log")(f"video_ingest setup：deps={_DEPS} data={_DATA}")


def teardown():
    """卸载钩子：转写线程为 daemon 自动终止；本钩子留资源清理位。"""
    _audit("teardown 调用（转写线程 daemon 随主程序退出，状态表随实例废弃）")


def extract_video_url(message, _match=None):
    """意图参数抽取：从消息抽第一个 http(s) 链接（URL 传递免疫清洗）。"""
    import re
    m = re.search(r"https?://\S+", str(message or ""))
    return {"url": m.group(0).rstrip('，。！？》】")')} if m else {}


def reply(url="", **_):
    """意图路由处理器（元数据）：无链接引导发链接。"""
    if not url:
        return "⚠️ 想解析哪个视频？把视频链接（B站/抖音/YouTube）发给我。"
    return fetch_video_info(url)


def transcribe_reply(url="", **_):
    """意图路由处理器（深度解析）：受理即回+后台转写。"""
    return start_transcribe(url)


def fetch_video_info(url=""):
    """模型工具：yt-dlp 元数据提取（v0.1 既有，download=False 纯读）。"""
    url = str(url or "").strip()
    if not url.startswith(("http://", "https://")):
        return "❌ 请提供完整的视频链接（http/https 开头）。"
    try:
        import yt_dlp
    except ImportError:
        return "❌ 视频摄取插件依赖未安装（yt-dlp）。"
    try:
        with yt_dlp.YoutubeDL({
                "quiet": True, "no_warnings": True,
                "socket_timeout": 15, "noplaylist": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return f"❌ 视频信息提取失败：{e}"
    if not info:
        return "❌ 未取到视频信息（链接可能无效或平台不支持）。"
    dur = info.get("duration")
    dur_txt = (f"{int(dur) // 60}分{int(dur) % 60}秒"
               if isinstance(dur, (int, float)) and dur else "未知")
    desc = str(info.get("description") or "").strip()
    if len(desc) > 300:
        desc = desc[:300] + "……"
    lines = [f"🎬 {info.get('title') or '无标题'}",
             f"👤 作者：{info.get('uploader') or info.get('channel') or '未知'}"
             f"　⏱️ 时长：{dur_txt}"
             f"　来源：{info.get('extractor_key') or '未知'}"]
    if info.get("view_count"):
        lines.append(f"👁️ 播放：{info['view_count']:,}")
    if desc:
        lines.append(f"📄 简介：{desc}")
    lines.append("💡 想让我「看完总结观点」请说：总结这个视频的内容")
    return "\n".join(lines)


def start_transcribe(url=""):
    """模型工具/意图共用：受理即回（并发闸 1）+后台线程全链转写。"""
    url = str(url or "").strip()
    if not url.startswith(("http://", "https://")):
        return "❌ 请提供完整的视频链接（http/https 开头）。"
    with _LOCK:
        if _JOB["state"] == "running":
            return ("⏳ 已有一个转写任务在进行（请用「查转写状态」查询），"
                    "完成后再来。")
        _JOB.update(state="running", url=url, error="", result_path="",
                    title="", started=__import__("time").time(), elapsed=0.0)
    th = threading.Thread(target=_pipeline, args=(url,), daemon=True)
    th.start()
    return ("🎬 已受理！正在下载音频并转写（约 1-2 分钟，视视频长度），"
            "完成后用「查转写状态」取结果。转写期间你可以继续聊别的。")


def status_reply(**_):
    """模型工具：查询最近任务状态/结果。"""
    with _LOCK:
        job = dict(_JOB)
    st = job["state"]
    if st == "idle":
        return "📭 还没有转写任务。发一个视频链接并说「总结这个视频」即可开始。"
    if st == "running":
        el = __import__("time").time() - job["started"]
        return f"⏳ 转写进行中（已 {el:.0f}s）：{job['title'] or job['url']}"
    if st == "error":
        return f"❌ 转写失败：{job['error']}"
    if st == "done":
        try:
            with open(job["result_path"], encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"❌ 结果文件读取失败：{e}"
    return f"未知状态 {st}"


def _set(state, **kw):
    with _LOCK:
        _JOB["state"] = state
        _JOB.update(kw)
        if state in ("done", "error"):
            import time
            _JOB["elapsed"] = time.time() - _JOB["started"]


def _audit(msg):
    print(f"[插件][video_ingest] {msg}")


def _pipeline(url):
    """后台全链：下载音频 → 转写 → LLM 提炼 → 落盘。任何异常→error 状态。"""
    import time
    t0 = time.time()
    tmp_dir = os.path.join(_DATA, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    audio = None
    try:
        # ① 元数据（标题）
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True,
                               "socket_timeout": 15, "noplaylist": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title") or url
            _set("running", title=title)
            # ② 下载音频（bestaudio 低码率，纯音频远小于视频）
            audio = os.path.join(tmp_dir, "audio.%(ext)s")
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True,
                                   "socket_timeout": 30, "noplaylist": True,
                                   "format": "bestaudio[abr<=64]/bestaudio",
                                   "outtmpl": audio}) as y2:
                y2.download([url])
        audio_file = next((os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)
                           if f.startswith("audio.")), None)
        if not audio_file:
            raise RuntimeError("音频下载产物缺失")
        # ③ 转写（faster-whisper base int8 CPU；HF 镜像走环境变量）
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        # hf-xet 新下载协议与 HF 镜像不兼容（CAS 401 实锤）——禁 Xet 走普通 HTTP
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        from faster_whisper import WhisperModel
        # av>=18 移除了 open(metadata_errors=...) 参数，faster-whisper 1.2.1
        # audio.py 尚未适配（上游兼容债）——兼容 shim：剥掉该 kwarg 透传。
        # Python 3.14 只有 av 19 wheel（av<15 无 cp314），shim 是当前唯一通路；
        # 上游适配后删除本段。Python 3.14 环境硬约束记录于插件 docstring。
        import av as _av
        if not getattr(_av, "_xj3_compat_patched", False):
            _av_open_orig = _av.open
            def _av_open_compat(*a, **k):
                k.pop("metadata_errors", None)
                return _av_open_orig(*a, **k)
            _av.open = _av_open_compat
            _av._xj3_compat_patched = True
        model = WhisperModel("base", device="cpu", compute_type="int8",
                             download_root=os.path.join(_DEPS, "_models"))
        segments, info = model.transcribe(audio_file, beam_size=1,
                                          vad_filter=True)
        text = "\n".join(f"[{s.start:.0f}s] {s.text.strip()}"
                         for s in segments if s.text.strip())
        if not text.strip():
            # 降级重试：VAD 会滤掉音乐背景下的歌声（MV 场景实测）——关 VAD 再试一次
            segments, info = model.transcribe(audio_file, beam_size=1,
                                              vad_filter=False)
            text = "\n".join(f"[{s.start:.0f}s] {s.text.strip()}"
                             for s in segments if s.text.strip())
        if not text.strip():
            raise RuntimeError("转写结果为空（可能是纯音乐/无声视频）")
        # ④ LLM 提炼 3-5 观点（云端，todo_text 同款 CLOUD_KEY 先例）
        digest = _digest(title, text)
        # ⑤ 落盘
        note = os.path.join(_DATA, "video_notes",
                            time.strftime("%Y%m%d_%H%M%S") + ".md")
        with open(note, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n- 链接：{url}\n- 转写+提炼耗时："
                    f"{time.time()-t0:.0f}s（base int8 CPU）\n\n## 核心观点\n\n"
                    f"{digest}\n\n## 转写全文\n\n{text}\n")
        _set("done", result_path=note)
        _audit(f"转写完成 {title}（{time.time()-t0:.0f}s）→ {note}")
    except Exception as e:
        _set("error", error=str(e))
        _audit(f"转写失败: {e}")
    finally:
        if audio and os.path.isdir(tmp_dir):   # 音频临时件清理（磁盘卫生）
            for f in os.listdir(tmp_dir):
                try:
                    os.remove(os.path.join(tmp_dir, f))
                except OSError:
                    pass


def _digest(title, text):
    """LLM 观点提炼（云端 deepseek，todo_text 同款密钥先例）；失败回退
    「转写原文摘录」——提炼挂了转写成果不丢。"""
    try:
        import requests
        from xiaoju3 import CLOUD_KEY, CLOUD_URL
        prompt = (f"以下是视频《{title}》的语音转写文本。请提炼 3-5 个核心观点，"
                  f"每条一行、以「· 」开头、不超过 40 字，直接给观点不要客套：\n\n"
                  f"{text[:6000]}")
        resp = requests.post(CLOUD_URL, headers={
            "Authorization": f"Bearer {CLOUD_KEY}",
            "Content-Type": "application/json"}, timeout=60, json={
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500, "temperature": 0.3})
        content = resp.json()["choices"][0]["message"]["content"].strip()
        return content if content else "（提炼为空，见转写全文）"
    except Exception as e:
        _audit(f"LLM 提炼失败，回退原文摘录: {e}")
        return f"（LLM 提炼失败: {e}；转写开头摘录）\n{text[:600]}"
