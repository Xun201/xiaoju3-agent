# -*- coding: utf-8 -*-
"""search_tools 引擎降级链单元测试（全离线：requests 一律 mock）。

覆盖（2026-10-01 搜索源切换任务）：
- 必应国内站 / 百度结果页 HTML 样例解析（真实结构样例内嵌，bs4 真实解析）；
- Serper / Tavily API mock：请求头/载荷、organic/results 字段映射；
- 降级链顺序：SERPER_API_KEY 配了优先 serper，其次 tavily → bing → baidu；
  bing 失败落 baidu；单引擎零结果自动试下一个；
- SEARCH_ENGINE 手动指定口径：设了只走指定引擎，失败不再链式降级、
  快速短文案报错；非法引擎名报错；大小写不敏感；
- 超时 5 秒断言（10 → 5）；失败统一短文案断言（不外抛异常细节）；
- bs4 缺失优雅降级（HTML 引擎跳过，import 不崩）。
env 经 mock.patch.dict 注入、用后自动还原；本文件不发起任何真实网络请求。
"""
import os
import unittest
from unittest import mock

import search_tools


# ==================== 真实结构 HTML 样例（内嵌，离线解析） ====================

# 必应国内站结果页骨架：li.b_algo → h2>a 标题链接、.b_caption>p 摘要；
# 第三条无 <a>（应跳过），第四条摘要为裸 <p>（b_caption 兜底选择器覆盖）
BING_HTML = """
<html><body><ol id="b_results">
<li class="b_algo" data-id="1">
  <h2><a href="https://xiaoju.example.com/">小橘3号 - 官方网站</a></h2>
  <div class="b_caption">
    <p class="b_lineclamp-4 b_algoSlug">小橘3号是一款<b>私人助理</b>程序，支持联网搜索。</p>
  </div>
</li>
<li class="b_algo">
  <h2><a href="https://docs.example.org/manual">小橘3号 使用手册</a></h2>
  <p>裸段落摘要：安装与部署说明。</p>
</li>
<li class="b_algo"><h2><span>没有链接的条目应当被跳过</span></h2></li>
<li class="b_algo">
  <h2><a href="https://blog.example.net/hi">第三条结果</a></h2>
  <div class="b_caption"><p>第三条摘要</p></div>
</li>
</ol></body></html>
"""

# 百度结果页骨架（新旧两版样式并存）：div.result/c-container → h3>a 标题
# （跳转链接保留原样）、.c-abstract / content-right_* 摘要；末尾嵌套子容器去重
BAIDU_HTML = """
<html><body><div id="content_left">
<div class="result c-container new-pmd" tpl="se_com_default">
  <h3 class="c-title t t tts-title">
    <a href="https://www.baidu.com/link?url=aaa111">小橘3号 - <em>百科</em></a>
  </h3>
  <div class="c-abstract"><span>小橘3号是一款<span class="c-text-red">私人助理</span>程序。</span></div>
</div>
<div class="result c-container" tpl="se_st">
  <h3 class="t"><a href="https://www.baidu.com/link?url=bbb222">小橘3号 使用手册</a></h3>
  <div class="c-span-last">
    <span class="content-right_8Zs40">新版样式的摘要文本。</span>
  </div>
  <div class="result c-container">
    <h3><a href="https://www.baidu.com/link?url=bbb222">小橘3号 使用手册</a></h3>
  </div>
</div>
<div class="c-container"><span>纯推荐块没有标题链接，应被跳过</span></div>
</div></body></html>
"""


def _html_resp(text):
    resp = mock.Mock()
    resp.text = text
    resp.raise_for_status = mock.Mock()
    return resp


def _json_resp(payload):
    resp = mock.Mock()
    resp.json = mock.Mock(return_value=payload)
    resp.raise_for_status = mock.Mock()
    return resp


class SearchEnvTestCase(unittest.TestCase):
    """公共基座：搜索相关 env 全部置空（视为未配置），用后自动还原。"""

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {
            "SEARCH_ENGINE": "", "SERPER_API_KEY": "", "TAVILY_API_KEY": "",
        })
        patcher.start()
        self.addCleanup(patcher.stop)


# ==================== HTML 引擎解析（bs4 真实解析内嵌样例） ====================

class BingParseTests(SearchEnvTestCase):

    def test_bing_parses_title_url_snippet(self):
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = _html_resp(BING_HTML)
            results = search_tools._search_bing("小橘3号", 5)
        self.assertEqual(len(results), 3)  # 无链接条目被跳过
        self.assertEqual(results[0]["title"], "小橘3号 - 官方网站")
        self.assertEqual(results[0]["url"], "https://xiaoju.example.com/")
        self.assertEqual(results[0]["snippet"], "小橘3号是一款私人助理程序，支持联网搜索。")
        # 裸 <p> 摘要兜底
        self.assertEqual(results[1]["snippet"], "裸段落摘要：安装与部署说明。")
        self.assertEqual(results[2]["title"], "第三条结果")

    def test_bing_max_results_truncates(self):
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = _html_resp(BING_HTML)
            results = search_tools._search_bing("小橘3号", 2)
        self.assertEqual(len(results), 2)

    def test_bing_request_shape(self):
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = _html_resp(BING_HTML)
            search_tools._search_bing("小橘3号", 5)
        args, kwargs = mr.get.call_args
        self.assertEqual(args[0], search_tools.BING_URL)
        self.assertEqual(kwargs["params"], {"q": "小橘3号"})
        self.assertIn("Mozilla", kwargs["headers"]["User-Agent"])
        self.assertEqual(kwargs["timeout"], 5)


class BaiduParseTests(SearchEnvTestCase):

    def test_baidu_parses_title_url_snippet(self):
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = _html_resp(BAIDU_HTML)
            results = search_tools._search_baidu("小橘3号", 5)
        # 嵌套子容器按（标题, 链接）去重；无链接推荐块被跳过
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["title"], "小橘3号 - 百科")
        self.assertEqual(results[0]["url"],
                         "https://www.baidu.com/link?url=aaa111")
        self.assertEqual(results[0]["snippet"], "小橘3号是一款私人助理程序。")
        # 新版 content-right_* 样式摘要兜底
        self.assertEqual(results[1]["snippet"], "新版样式的摘要文本。")

    def test_baidu_max_results_truncates(self):
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = _html_resp(BAIDU_HTML)
            results = search_tools._search_baidu("小橘3号", 1)
        self.assertEqual(len(results), 1)

    def test_baidu_request_shape(self):
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = _html_resp(BAIDU_HTML)
            search_tools._search_baidu("小橘3号", 5)
        args, kwargs = mr.get.call_args
        self.assertEqual(args[0], search_tools.BAIDU_URL)
        self.assertEqual(kwargs["params"], {"wd": "小橘3号"})
        self.assertIn("Mozilla", kwargs["headers"]["User-Agent"])
        self.assertEqual(kwargs["timeout"], 5)


# ==================== API 引擎（Serper / Tavily） ====================

class SerperApiTests(SearchEnvTestCase):

    def test_serper_maps_organic_and_sends_key_header(self):
        os.environ["SERPER_API_KEY"] = "sk-test-serper"
        payload = {"organic": [
            {"title": "结果一", "link": "https://a.example.com/", "snippet": "摘要一"},
            {"title": "结果二", "link": "https://b.example.com/", "snippet": "摘要二"},
        ]}
        with mock.patch.object(search_tools, "requests") as mr:
            mr.post.return_value = _json_resp(payload)
            results = search_tools._search_serper("小橘3号", 5)
        self.assertEqual(results[0],
                         {"title": "结果一", "url": "https://a.example.com/",
                          "snippet": "摘要一"})
        args, kwargs = mr.post.call_args
        self.assertEqual(args[0], search_tools.SERPER_URL)
        self.assertEqual(kwargs["json"], {"q": "小橘3号"})
        self.assertEqual(kwargs["headers"]["X-API-KEY"], "sk-test-serper")
        self.assertEqual(kwargs["timeout"], 5)


class TavilyApiTests(SearchEnvTestCase):

    def test_tavily_maps_results_and_sends_key_payload(self):
        os.environ["TAVILY_API_KEY"] = "tvly-test-key"
        payload = {"results": [
            {"title": "Tavily 结果", "url": "https://t.example.com/",
             "content": "Tavily 摘要正文"},
        ]}
        with mock.patch.object(search_tools, "requests") as mr:
            mr.post.return_value = _json_resp(payload)
            results = search_tools._search_tavily("小橘3号", 5)
        self.assertEqual(results[0],
                         {"title": "Tavily 结果", "url": "https://t.example.com/",
                          "snippet": "Tavily 摘要正文"})
        args, kwargs = mr.post.call_args
        self.assertEqual(args[0], search_tools.TAVILY_URL)
        self.assertEqual(kwargs["json"]["api_key"], "tvly-test-key")
        self.assertEqual(kwargs["json"]["query"], "小橘3号")
        self.assertEqual(kwargs["timeout"], 5)


# ==================== 降级链顺序 ====================

class EngineChainTests(SearchEnvTestCase):

    def test_chain_without_keys_is_bing_then_baidu(self):
        self.assertEqual(search_tools._engine_chain(), ["bing", "baidu"])

    def test_chain_prefers_keyed_apis_in_order(self):
        os.environ["SERPER_API_KEY"] = "sk"
        self.assertEqual(search_tools._engine_chain(),
                         ["serper", "bing", "baidu"])
        os.environ["TAVILY_API_KEY"] = "tvly"
        self.assertEqual(search_tools._engine_chain(),
                         ["serper", "tavily", "bing", "baidu"])

    def test_serper_key_takes_priority_over_html_engines(self):
        os.environ["SERPER_API_KEY"] = "sk"
        payload = {"organic": [{"title": "T", "link": "u", "snippet": "s"}]}
        with mock.patch.object(search_tools, "requests") as mr:
            mr.post.return_value = _json_resp(payload)
            out = search_tools.web_search("小橘3号")
        self.assertIn("1. T - s 链接：u", out)
        mr.post.assert_called_once()      # 只走 serper
        mr.get.assert_not_called()        # 不再请求 HTML 引擎

    def test_bing_failure_falls_to_baidu(self):
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.side_effect = [OSError("bing 不可达"), _html_resp(BAIDU_HTML)]
            out = search_tools.web_search("小橘3号")
        self.assertIn("小橘3号 - 百科", out)
        self.assertEqual(mr.get.call_args_list[0][0][0], search_tools.BING_URL)
        self.assertEqual(mr.get.call_args_list[1][0][0], search_tools.BAIDU_URL)

    def test_zero_result_engine_tries_next_then_short_circuits(self):
        # bing 连通但解析零结果 → 自动试 baidu；baidu 有结果即返回
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.side_effect = [_html_resp("<html><body>空页</body></html>"),
                                  _html_resp(BAIDU_HTML)]
            out = search_tools.web_search("小橘3号")
        self.assertIn("小橘3号 - 百科", out)

    def test_all_engines_fail_returns_short_unavailable_message(self):
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.side_effect = OSError("timed out")
            out = search_tools.web_search("小橘3号")
        self.assertEqual(out, "❌ 联网搜索暂不可用，请稍后重试")
        self.assertNotIn("timed out", out)          # 不外抛异常细节
        self.assertNotIn("Traceback", out)

    def test_all_engines_zero_results_keeps_no_result_contract(self):
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = _html_resp("<html><body>没有结果</body></html>")
            out = search_tools.web_search("不存在的东西")
        self.assertIn("未搜到与「不存在的东西」相关的结果", out)

    def test_every_request_uses_five_second_timeout(self):
        os.environ["SERPER_API_KEY"] = "sk"
        with mock.patch.object(search_tools, "requests") as mr:
            mr.post.side_effect = OSError("serper 挂了")
            mr.get.return_value = _html_resp(BING_HTML)
            search_tools.web_search("小橘3号")
        self.assertEqual(search_tools.SEARCH_TIMEOUT, 5)   # 10 → 5 秒
        for call in mr.post.call_args_list + mr.get.call_args_list:
            self.assertEqual(call[1]["timeout"], 5)


# ==================== SEARCH_ENGINE 手动指定口径 ====================

class ManualEngineTests(SearchEnvTestCase):

    def test_manual_bing_failure_does_not_fall_back(self):
        os.environ["SEARCH_ENGINE"] = "bing"
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.side_effect = OSError("bing 不可达")
            out = search_tools.web_search("小橘3号")
        self.assertEqual(out, "❌ 联网搜索暂不可用，请稍后重试")
        mr.get.assert_called_once()       # 失败不再链式降级（没试百度）

    def test_manual_baidu_only_hits_baidu(self):
        os.environ["SEARCH_ENGINE"] = "baidu"
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = _html_resp(BAIDU_HTML)
            out = search_tools.web_search("小橘3号")
        self.assertIn("小橘3号 - 百科", out)
        self.assertEqual(mr.get.call_args_list[0][0][0], search_tools.BAIDU_URL)

    def test_manual_engine_name_is_case_insensitive(self):
        os.environ["SEARCH_ENGINE"] = "Bing"
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = _html_resp(BING_HTML)
            out = search_tools.web_search("小橘3号")
        self.assertIn("小橘3号 - 官方网站", out)

    def test_manual_engine_overrides_keyed_api(self):
        # 手动指定优先于 Key 自动链：配了 SERPER_API_KEY 也只走 baidu
        os.environ["SEARCH_ENGINE"] = "baidu"
        os.environ["SERPER_API_KEY"] = "sk"
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = _html_resp(BAIDU_HTML)
            search_tools.web_search("小橘3号")
        mr.post.assert_not_called()

    def test_manual_serper_without_fallback_on_failure(self):
        # 指定 serper（即使没配 Key 也允许尝试）：失败直接报错，不再试 bing/baidu
        os.environ["SEARCH_ENGINE"] = "serper"
        with mock.patch.object(search_tools, "requests") as mr:
            mr.post.side_effect = OSError("serper 超时")
            out = search_tools.web_search("小橘3号")
        self.assertEqual(out, "❌ 联网搜索暂不可用，请稍后重试")
        mr.post.assert_called_once()
        mr.get.assert_not_called()

    def test_unknown_engine_name_is_rejected(self):
        os.environ["SEARCH_ENGINE"] = "duckduckgo"
        with mock.patch.object(search_tools, "requests") as mr:
            out = search_tools.web_search("小橘3号")
        self.assertIn("❌ 未知的搜索引擎：duckduckgo", out)
        self.assertIn("bing / baidu / serper / tavily", out)
        mr.post.assert_not_called()
        mr.get.assert_not_called()

    def test_manual_engine_zero_results_keeps_no_result_wording(self):
        os.environ["SEARCH_ENGINE"] = "bing"
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = _html_resp("<html><body>空空如也</body></html>")
            out = search_tools.web_search("冷门词")
        self.assertIn("未搜到与「冷门词」相关的结果", out)


# ==================== 契约保持与优雅降级 ====================

class ContractTests(SearchEnvTestCase):

    def test_result_format_contract_unchanged(self):
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = _html_resp(BING_HTML)
            out = search_tools.web_search("小橘3号", max_results=1)
        self.assertIn("🔍 联网搜索「小橘3号」的结果：", out)
        self.assertIn("1. 小橘3号 - 官方网站 - 小橘3号是一款私人助理程序，支持联网搜索。"
                      " 链接：https://xiaoju.example.com/", out)
        self.assertNotIn("使用手册", out)   # 截断生效

    def test_empty_query_returns_missing_keyword_message(self):
        self.assertEqual(search_tools.web_search("   "),
                         "❌ 缺少搜索词：请告诉小橘3号要搜索什么内容。")
        self.assertEqual(search_tools.web_search(None),
                         "❌ 缺少搜索词：请告诉小橘3号要搜索什么内容。")

    def test_invalid_max_results_falls_back_to_five(self):
        with mock.patch.object(search_tools, "requests") as mr:
            mr.get.return_value = _html_resp(BING_HTML)
            out = search_tools.web_search("小橘3号", max_results="abc")
        self.assertIn("3. 第三条结果", out)

    def test_missing_bs4_degrades_gracefully_on_html_engines(self):
        # bs4 缺失：HTML 引擎视为失败跳过（自动链全灭 → 短文案；import 不崩）
        with mock.patch.object(search_tools, "BeautifulSoup", None), \
                mock.patch.object(search_tools, "requests") as mr:
            out = search_tools.web_search("小橘3号")
        self.assertEqual(out, "❌ 联网搜索暂不可用，请稍后重试")
        mr.get.assert_not_called()        # 解析器缺失不发起无效请求

    def test_missing_bs4_with_api_key_still_uses_api_engine(self):
        os.environ["SERPER_API_KEY"] = "sk"
        payload = {"organic": [{"title": "T", "link": "u", "snippet": "s"}]}
        with mock.patch.object(search_tools, "BeautifulSoup", None), \
                mock.patch.object(search_tools, "requests") as mr:
            mr.post.return_value = _json_resp(payload)
            out = search_tools.web_search("小橘3号")
        self.assertIn("1. T - s 链接：u", out)   # API 引擎不受 bs4 缺失影响


if __name__ == "__main__":
    unittest.main()
