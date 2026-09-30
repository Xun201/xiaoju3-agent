# -*- coding: utf-8 -*-
"""小橘3号 · 联网搜索工具（架构设计文档 §10 #5 / 功能文档 §3）。

web_search(query, max_results=5)：
- requests 抓取 DuckDuckGo HTML 端点（https://html.duckduckgo.com/html/?q=...），
  UA 伪装、超时 10 秒、异常返回中文错误串（不向外抛，供工具层直接喂回模型）；
- html.parser（标准库）解析结果标题 / 链接 / 摘要；
- 权限口径：联网搜索属 LV1（功能文档 §11），不进 DANGER_TOOLS 门禁。

供 tools.py 以 `from search_tools import web_search` 接入 11 项白名单；
本模块 import 零副作用，可独立单测（网络一律 mock）。
"""
import urllib.parse
from html.parser import HTMLParser

import requests

# DuckDuckGo HTML 端点（无需 API Key 的轻量检索入口）
SEARCH_URL = "https://html.duckduckgo.com/html/"
SEARCH_TIMEOUT = 10

# UA 伪装：DuckDuckGo 对无 UA / 爬虫 UA 会拒绝响应
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0.0.0 Safari/537.36")


class _DDGResultParser(HTMLParser):
    """DuckDuckGo HTML 结果页解析器。

    结果块结构：每条结果由两个锚点组成——
    - <a class="result__a" href="跳转链接">标题</a>：开启一条新结果；
    - <a class="result__snippet" ...>摘要（可能内嵌 <b> 等标签）</a>：
      补充当前结果的摘要字段。
    收集期间挂起在 _entry（避免与基类 HTMLParser 内部缓冲重名），遇下一个标题锚点或 close() 时收尾入库。
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self._field = None    # 当前正在收集的字段："title" / "snippet" / None
        self._entry = None  # 收集中的结果 {title, url, snippet}
        self._depth = 0       # 锚点内嵌套子标签层数

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        cls = attr_dict.get("class", "")
        if tag == "a":
            if "result__a" in cls:
                self._flush()   # 新结果开始：先收尾上一条
                self._entry = {"title": "",
                                 "url": _clean_url(attr_dict.get("href", "")),
                                 "snippet": ""}
                self._field = "title"
            elif "result__snippet" in cls:
                if self._entry is None:
                    self._entry = {"title": "", "url": "", "snippet": ""}
                self._field = "snippet"
        elif self._field:
            self._depth += 1

    def handle_endtag(self, tag):
        if not self._field:
            return
        if tag == "a":
            if self._depth:
                self._depth -= 1   # 罕见的锚点错位嵌套，先退层
                return
            self._field = None     # 锚点结束，等待下一个字段/结果
        elif self._depth:
            self._depth -= 1       # 子标签闭合（如 </b>）

    def handle_data(self, data):
        if self._entry is None:
            return
        if self._field == "title":
            self._entry["title"] += data
        elif self._field == "snippet":
            self._entry["snippet"] += data

    def close(self):
        super().close()
        self._flush()

    def _flush(self):
        if self._entry is not None:
            entry = {k: v.strip() for k, v in self._entry.items()}
            if entry["title"] or entry["url"] or entry["snippet"]:
                self.results.append(entry)
            self._entry = None
        self._field = None
        self._depth = 0


def _clean_url(href):
    """还原 DuckDuckGo 跳转链接（//duckduckgo.com/l/?uddg=...）里的真实地址。"""
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    if "uddg=" in href:
        try:
            query = urllib.parse.urlparse(href).query
            real = urllib.parse.parse_qs(query).get("uddg", [""])[0]
            if real:
                return real
        except Exception:
            pass
    return href


def web_search(query, max_results=5):
    """联网搜索：检索 DuckDuckGo，返回中文清单文本（不抛异常）。

    - query：搜索关键词；max_results：返回条数上限（默认 5）；
    - 每条一行：`1. 标题 - 摘要 链接：url`；
    - 无结果 / 关键词为空 / 网络异常 → 返回中文提示串（❌/🔍 开头）。
    """
    query = "" if query is None else str(query).strip()
    if not query:
        return "❌ 缺少搜索词：请告诉小橘3号要搜索什么内容。"

    try:
        max_results = int(max_results)
    except (TypeError, ValueError):
        max_results = 5
    max_results = max(1, max_results)

    try:
        resp = requests.get(SEARCH_URL, params={"q": query},
                            headers={"User-Agent": USER_AGENT},
                            timeout=SEARCH_TIMEOUT)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        parser = _DDGResultParser()
        parser.feed(resp.text)
        parser.close()
        results = parser.results[:max_results]
        if not results:
            return f"🔍 未搜到与「{query}」相关的结果，换个关键词试试吧。"

        lines = [f"🔍 联网搜索「{query}」的结果："]
        for i, item in enumerate(results, 1):
            line = f"{i}. {item['title']}" if item['title'] else f"{i}.（无标题）"
            if item["snippet"]:
                line += f" - {item['snippet']}"
            if item["url"]:
                line += f" 链接：{item['url']}"
            lines.append(line)
        return "\n".join(lines)
    except Exception as e:
        return f"❌ 联网搜索失败：{e}，请稍后再试。"
