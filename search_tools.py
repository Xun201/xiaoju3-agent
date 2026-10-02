# -*- coding: utf-8 -*-
"""小橘3号 · 联网搜索工具（架构设计文档 §10 #5 / 功能文档 §3）。

web_search(query, max_results=5) 引擎降级链（国内可达性优先）：
1. SERPER_API_KEY 已配置 → Google Serper API（POST https://google.serper.dev/search，
   Header X-API-KEY）；
2. TAVILY_API_KEY 已配置 → Tavily API（POST https://api.tavily.com/search）；
3. Bing 国内站（https://cn.bing.com/search?q=...）requests + BeautifulSoup 解析
   标题 / 链接 / 摘要；
4. 百度（https://www.baidu.com/s?wd=...）同 bs4 解析。

SEARCH_ENGINE 环境变量（.env.example：bing / baidu / serper / tavily）为手动
指定入口：设了就只走指定引擎，失败不再链式降级、快速报错。

- 每次请求超时 5 秒（10 → 5：失败快速暴露，不卡死对话）；全部失败返回固定
  短文案「❌ 联网搜索暂不可用，请稍后重试」，不向外抛异常、不拖长串报错；
- bs4 缺失时优雅降级：HTML 引擎（bing/baidu）视为失败跳过，API 引擎不受影响，
  import 不崩；
- 既有 web_search 返回契约保持兼容：结果清单「1. 标题 - 摘要 链接：url」、
  空结果 🔍 提示、关键词为空 ❌ 提示；
- 权限口径：联网搜索属 LV1（功能文档 §11），不进 DANGER_TOOLS 门禁。

供 tools.py 以 `from search_tools import web_search` 接入白名单；
本模块 import 零副作用，可独立单测（网络一律 mock）。
"""
import os

import requests

try:
    from bs4 import BeautifulSoup
except ImportError:  # 优雅降级：bs4 缺失不崩 import，HTML 引擎运行期再报
    BeautifulSoup = None

# 请求超时（秒）：故意收紧到 5，超时立即降级下一引擎 / 快速失败
SEARCH_TIMEOUT = 5

# API 检索端点（Key 从环境变量读取，不入仓库）
SERPER_URL = "https://google.serper.dev/search"
TAVILY_URL = "https://api.tavily.com/search"

# HTML 检索端点（免 Key 兜底；国内直连可达）
BING_URL = "https://cn.bing.com/search"
BAIDU_URL = "https://www.baidu.com/s"

# 失败统一短文案：不外抛异常细节（长串堆栈喂给模型/打在对话里都是灾难）
UNAVAILABLE_MSG = "❌ 联网搜索暂不可用，请稍后重试"

# 手动指定入口支持的引擎名（SEARCH_ENGINE 环境变量，大小写不敏感）
KNOWN_ENGINES = ("bing", "baidu", "serper", "tavily")

# UA 伪装：必应 / 百度对无 UA / 爬虫 UA 会拒绝或弹验证页
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0.0.0 Safari/537.36")


# ==================== 各引擎实现（结果统一映射为 title/url/snippet） ====================

def _search_serper(query, max_results):
    """Google Serper：POST JSON {"q": query}，Header X-API-KEY 携带密钥。"""
    resp = requests.post(
        SERPER_URL,
        json={"q": query},
        headers={"X-API-KEY": os.environ.get("SERPER_API_KEY", "").strip(),
                 "Content-Type": "application/json"},
        timeout=SEARCH_TIMEOUT)
    resp.raise_for_status()
    organic = resp.json().get("organic") or []
    return [{"title": item.get("title", ""),
             "url": item.get("link", ""),
             "snippet": item.get("snippet", "")}
            for item in organic[:max_results]]


def _search_tavily(query, max_results):
    """Tavily：POST JSON {"api_key": ..., "query": ...}，content 字段作摘要。"""
    resp = requests.post(
        TAVILY_URL,
        json={"api_key": os.environ.get("TAVILY_API_KEY", "").strip(),
              "query": query},
        timeout=SEARCH_TIMEOUT)
    resp.raise_for_status()
    results = resp.json().get("results") or []
    return [{"title": item.get("title", ""),
             "url": item.get("url", ""),
             "snippet": item.get("content", "")}
            for item in results[:max_results]]


def _fetch_html(url, params):
    """GET 检索页 HTML（UA 伪装 + 5 秒超时 + UTF-8 解码）。"""
    resp = requests.get(url, params=params,
                        headers={"User-Agent": USER_AGENT},
                        timeout=SEARCH_TIMEOUT)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def _node_text(node):
    """取节点文本并压缩空白：保留词间空格、去掉换行缩进（兼容内嵌 <b>/<em>）。"""
    return " ".join(node.get_text().split()) if node is not None else ""


def _search_bing(query, max_results):
    """必应国内站：li.b_algo 结果块 → h2 a 标题链接 + .b_caption p 摘要。"""
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 未安装，HTML 搜索引擎不可用")
    soup = BeautifulSoup(_fetch_html(BING_URL, {"q": query}), "html.parser")
    results = []
    for block in soup.select("li.b_algo"):
        a = block.select_one("h2 a") or block.find("a", href=True)
        if a is None:
            continue
        p = block.select_one(".b_caption p") or block.find("p")
        results.append({"title": _node_text(a),
                        "url": a.get("href", "") or "",
                        "snippet": _node_text(p)})
        if len(results) >= max_results:
            break
    return results


def _search_baidu(query, max_results):
    """百度：div.result/c-container 结果块 → h3 a 标题链接 + 摘要。

    百度新旧两版样式摘要类名不同（.c-abstract / content-right_*），
    逐个候选选择器兜底；标题/链接去重防止嵌套容器重复计数。
    """
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 未安装，HTML 搜索引擎不可用")
    soup = BeautifulSoup(_fetch_html(BAIDU_URL, {"wd": query}), "html.parser")
    results, seen = [], set()
    for block in soup.select("div.result, div.c-container"):
        h3 = block.find("h3")
        a = (h3.find("a", href=True) if h3 else None) \
            or block.find("a", href=True)
        if a is None:
            continue
        title = _node_text(a)
        url = a.get("href", "") or ""
        if (not title and not url) or (title, url) in seen:
            continue
        seen.add((title, url))
        snippet = ""
        for sel in (".c-abstract",
                    "span[class*='content-right']",
                    "div[class*='content-right']"):
            node = block.select_one(sel)
            if node is not None:
                snippet = _node_text(node)
                break
        results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


# 引擎注册表（名称 → 实现）；_engine_chain 按优先级取用
_ENGINES = {
    "bing": _search_bing,
    "baidu": _search_baidu,
    "serper": _search_serper,
    "tavily": _search_tavily,
}


def _engine_chain():
    """自动降级链：配了 Key 的 API 引擎优先，其次必应 → 百度兜底。"""
    chain = []
    if os.environ.get("SERPER_API_KEY", "").strip():
        chain.append("serper")
    if os.environ.get("TAVILY_API_KEY", "").strip():
        chain.append("tavily")
    chain.extend(("bing", "baidu"))
    return chain


def _format_results(query, results):
    """既有契约格式：`1. 标题 - 摘要 链接：url` 逐行清单。"""
    lines = [f"🔍 联网搜索「{query}」的结果："]
    for i, item in enumerate(results, 1):
        line = f"{i}. {item['title']}" if item['title'] else f"{i}.（无标题）"
        if item["snippet"]:
            line += f" - {item['snippet']}"
        if item["url"]:
            line += f" 链接：{item['url']}"
        lines.append(line)
    return "\n".join(lines)


# ==================== 天气类搜索结果过滤（2026-10-02 用户口径） ====================
# "长沙市天心区的天气"这类 query 会混入旅游攻略/百科/介绍/历史等无关内容
# ——天气类 query 下按白名单只保留天气数据源特征结果；全部被过滤 → 固定
# 提示。仅天气类 query 生效，普通搜索不受影响。
# （关键词独立定义、不 import brain——brain 延迟导入本模块，避免循环导入）

# 天气类 query 判定（与 brain._WEATHER_KEYWORDS 同口径）
_WEATHER_QUERY_KEYWORDS = ("天气", "气温", "气候", "下雨", "降雨", "下雪",
                           "降雪", "温度", "多少度")

# 天气结果白名单：标题/摘要命中其一才保留（天气数据源特征词）
_WEATHER_RESULT_KEYWORDS = ("天气", "气温", "降水", "预报", "温度", "湿度",
                            "降雨", "降雪", "下雨", "下雪", "降温", "升温",
                            "晴", "多云", "阵雨", "雷雨", "小雨", "大雨",
                            "暴雨", "小雪", "中雪", "大雪", "℃", "°")

# 天气类结果全被过滤时的固定提示
NO_WEATHER_RESULT_MSG = "未找到相关天气信息，请稍后重试"


def _is_weather_query(query):
    """query 是否天气类（天气/气温/下雨/温度等）。"""
    q = str(query or "")
    return any(k in q for k in _WEATHER_QUERY_KEYWORDS)


def _filter_weather_results(results):
    """天气类结果白名单过滤：只保留标题/摘要含天气特征词的条目。"""
    kept = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        text = f"{item.get('title', '')} {item.get('snippet', '')}"
        if any(k in text for k in _WEATHER_RESULT_KEYWORDS):
            kept.append(item)
    return kept


def web_search(query, max_results=5):
    """联网搜索：按引擎降级链检索，返回中文清单文本（不抛异常）。

    - query：搜索关键词；max_results：返回条数上限（默认 5）；
    - 自动链（未设 SEARCH_ENGINE）：serper/tavily（配了 Key 才参与）→
      bing → baidu，单引擎失败静默试下一个，全部失败返回固定短文案；
    - 手动链（设了 SEARCH_ENGINE）：只走指定引擎，失败不再降级、快速报错；
    - 无结果 / 关键词为空 → 返回中文提示串（❌/🔍 开头）。
    """
    query = "" if query is None else str(query).strip()
    if not query:
        return "❌ 缺少搜索词：请告诉小橘3号要搜索什么内容。"

    try:
        max_results = int(max_results)
    except (TypeError, ValueError):
        max_results = 5
    max_results = max(1, max_results)

    manual = os.environ.get("SEARCH_ENGINE", "").strip().lower()
    if manual:
        if manual not in _ENGINES:
            return (f"❌ 未知的搜索引擎：{manual}"
                    f"（可选：{' / '.join(KNOWN_ENGINES)}）")
        chain = [manual]
    else:
        chain = _engine_chain()

    connected = False  # 是否有任何引擎成功响应过（区别于"连不上"）
    for name in chain:
        try:
            results = _ENGINES[name](query, max_results)
        except Exception:
            if manual:  # 手动指定引擎：失败不再链式降级，快速短文案返回
                return UNAVAILABLE_MSG
            continue    # 自动链：静默试下一个引擎
        connected = True
        if results:
            # 🌦️ 天气类结果过滤（2026-10-02 用户口径）：白名单只留天气数据
            # 源特征结果，全被过滤 → 固定提示；普通搜索不过滤
            if _is_weather_query(query):
                results = _filter_weather_results(results)
                if not results:
                    return NO_WEATHER_RESULT_MSG
            return _format_results(query, results)

    if connected:  # 有引擎响应但全部零结果 → 保持既有"未搜到"口径
        return f"🔍 未搜到与「{query}」相关的结果，换个关键词试试吧。"
    return UNAVAILABLE_MSG  # 自动链全军覆没（含 bs4 缺失）→ 固定短文案
