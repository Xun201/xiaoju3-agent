# -*- coding: utf-8 -*-
"""agent_state/plugins/video_ingest · 第一号正式插件（#348 信息摄取流一期）。

yt-dlp 元数据提取：视频链接 → 标题/简介/时长/作者（不下载视频，纯元数据）。
B 站/抖音/YouTube 等由 yt-dlp extractor 体系天然支持。

依赖：yt-dlp（pip install yt-dlp）。frozen exe 环境由 xiaoju3.spec
collect_all('yt_dlp') 收录（官方配方——extractor 惰性动态 import 静态
分析盲区）；依赖缺失时工具返回安装指引（诚实降级，绝不崩主程序）。
权限：Lv.3（队长拍板，只读元数据无危险操作）。崩溃隔离：函数内兜底
try/except + dispatch_plugin_tool 既有双层兜底，双保险。
"""
def extract_video_url(message, _match=None):
    """意图参数抽取：从消息抽第一个 http(s) 链接（URL 传递免疫清洗——
    本插件经 intent_router 直达，不经标点清洗链）。"""
    import re
    m = re.search(r"https?://\S+", str(message or ""))
    return {"url": m.group(0).rstrip('，。！？》】")')} if m else {}


PLUGIN = {
    "name": "video_ingest",
    "version": "0.1.0",
    "desc": "视频信息摄取（yt-dlp 元数据提取，信息摄取流一期）",
    "author": "xun",
    "level": 3,
    "tools": [
        {"name": "ext_fetch_video_info",
         "desc": "提取视频链接的信息（标题/简介/时长/作者），支持 B站/抖音/YouTube 等；"
                 "不下载视频，只读元数据",
         "params": "url (完整视频链接，http/https 开头)",
         "note": "当主人发来视频链接并想了解这个视频是什么/讲了什么时使用",
         "handler": "agent_state_plugins_video_ingest:fetch_video_info"},
    ],
    "intents": [
        {"name": "ext_video_ingest", "desc": "解析视频链接信息",
         "patterns": [r"(解析|提取|看看?|读一?下).{0,12}(这个?|这个?)视频",
                      r"视频.{0,8}(讲了?什么|什么内容|什么信息|信息|简介)"],
         "extractor": extract_video_url,
         "handler_name": "agent_state_plugins_video_ingest:reply"},
    ],
}


def reply(url="", **_):
    """意图路由处理器：无链接引导发链接；有链接直接提取。"""
    if not url:
        return "⚠️ 想解析哪个视频？把视频链接（B站/抖音/YouTube）发给我。"
    return fetch_video_info(url)


def fetch_video_info(url=""):
    """模型工具/意图共用执行体：yt-dlp 元数据提取（download=False 纯读）。"""
    url = str(url or "").strip()
    if not url.startswith(("http://", "https://")):
        return "❌ 请提供完整的视频链接（http/https 开头）。"
    try:
        import yt_dlp
    except ImportError:
        return ("❌ 视频摄取插件依赖未安装：请在运行环境执行 "
                "pip install yt-dlp 后重试（frozen 包已内置收录）。")
    try:
        with yt_dlp.YoutubeDL({
                "quiet": True, "no_warnings": True,
                "socket_timeout": 15,          # 网络超时 15s（纪律：禁止卡死）
                "noplaylist": True,            # 只取单视频（列表链接取首条）
        }) as ydl:
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
    return "\n".join(lines)
