# -*- coding: utf-8 -*-
"""gen_log 真实浏览器冒烟测试（默认跳过）。

设置环境变量 XIAOJU3_LIVE_TEST=1 且本机已装 playwright + chromium 时才运行：
    XIAOJU3_LIVE_TEST=1 python -m unittest tests.test_genlog_live -v

用真实无头 chromium 打开静态页面（优先 example.com，DNS 不可达时依次
回退 example.org / quotes.toscrape.com），验证「打开 → 渲染 → 滚动 →
提取正文」链路真实可用；不依赖 DeepSeek（分享页内容易变，不适合断言）。
当前网络全部不可达时 skipTest 跳过并说明原因。
"""
import os
import socket
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from plugins import link_logger  # noqa: E402
from plugins.link_logger import LinkFetchError  # noqa: E402

LIVE_ENV = "XIAOJU3_LIVE_TEST"

# 候选静态页（URL, 断言正文必含的标记），按优先级排列
CANDIDATE_PAGES = [
    ("https://example.com/", "Example Domain"),
    # example.org 2025 年起改版，正文不再含 "Example Domain"
    ("https://example.org/", "documentation examples"),
    ("https://quotes.toscrape.com/", "Quotes to Scrape"),
]


def _pick_reachable_page():
    """返回第一个 DNS 可解析的候选静态页；全部不可达时返回 None。"""
    for url, marker in CANDIDATE_PAGES:
        host = url.split("/")[2]
        try:
            socket.gethostbyname(host)
            return url, marker
        except OSError:
            continue
    return None


@unittest.skipUnless(
    os.environ.get(LIVE_ENV) == "1",
    "真实浏览器冒烟默认跳过：需联网且已装 chromium；设置 XIAOJU3_LIVE_TEST=1 启用")
class GenLogLiveSmokeTest(unittest.TestCase):
    """真实 chromium 冒烟：静态页面抓取链路可用。"""

    def setUp(self):
        picked = _pick_reachable_page()
        if picked is None:
            self.skipTest("候选静态页 DNS 均不可达，本机当前无外网，冒烟跳过")
        self.url, self.marker = picked

    def test_fetch_static_page_end_to_end(self):
        text = link_logger.fetch_page_text_sync(self.url)
        self.assertTrue(text.strip())
        self.assertIn(self.marker, text)

    def test_share_prefix_validation_guards_before_browser(self):
        # 真实环境下前缀校验依旧先行：非法链接不触碰浏览器
        with self.assertRaises(LinkFetchError):
            link_logger.fetch_deepseek_url_sync("https://example.com/not-deepseek")


if __name__ == "__main__":
    unittest.main()
