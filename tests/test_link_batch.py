# -*- coding: utf-8 -*-
"""link_logger / batch_logger / dev_logger / run_link_log 链路测试。

抓取与总结全部 mock，绝不真联网；全部离线可跑（文件副作用用 tmp 目录）。
覆盖：链接前缀校验合法/非法、playwright 缺库优雅降级文案、mock 浏览器
对象链（browser/context/page）下的滚动到底停止、正文提取剔除噪声、
超时/步数护栏、失败重试、浏览器内核缺失中文提示、4000 字分片边界、
倒叙合并顺序、dev_log 自动编号。
真实浏览器冒烟另见 tests/test_genlog_live.py（需 XIAOJU3_LIVE_TEST=1）。
"""
import asyncio
import contextlib
import io
import itertools
import os
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from plugins import batch_logger, dev_logger, link_logger  # noqa: E402
from plugins.link_logger import LinkFetchError  # noqa: E402
import run_link_log  # noqa: E402

VALID_URL = "https://chat.deepseek.com/share/abc123"


def _quiet():
    return contextlib.redirect_stdout(io.StringIO())


class LinkUrlValidationTest(unittest.TestCase):
    """DeepSeek 分享链接前缀校验：合法 / 非法。"""

    def test_valid_prefix_returns_cleaned_url(self):
        self.assertEqual(
            link_logger.validate_share_url("  https://chat.deepseek.com/share/abc#锚点 "),
            "https://chat.deepseek.com/share/abc")

    def test_invalid_prefixes_raise(self):
        for bad in ("", None, "http://evil.com/x", "https://example.com/share/x",
                    "ftp://chat.deepseek.com/share/x", "分享链接"):
            with self.assertRaises(LinkFetchError, msg=repr(bad)) as ctx:
                link_logger.validate_share_url(bad)
            self.assertIn("chat.deepseek.com/share", str(ctx.exception))

    def test_async_fetch_validates_before_browser(self):
        # 非法链接在触碰浏览器之前就被拒绝
        with self.assertRaises(LinkFetchError):
            asyncio.run(link_logger.fetch_deepseek_url("https://evil.com/x"))


class LinkLoggerDegradationTest(unittest.TestCase):
    """playwright 缺库时的优雅降级（绝不影响模块 import）。"""

    def test_module_import_is_side_effect_free(self):
        # 模块已在本文件顶部成功导入且未触发浏览器/网络
        self.assertTrue(callable(link_logger.fetch_deepseek_url))
        self.assertTrue(callable(link_logger.fetch_page_text))
        self.assertTrue(issubclass(link_logger.LinkFetchError, Exception))

    def test_missing_playwright_raises_chinese_hint(self):
        # 向 sys.modules 注入 None 使 import 稳定抛 ImportError（环境无关）
        with mock.patch.dict(sys.modules, {"playwright": None,
                                           "playwright.async_api": None}):
            with self.assertRaises(LinkFetchError) as ctx:
                asyncio.run(link_logger.fetch_deepseek_url(VALID_URL))
        self.assertIn("playwright", str(ctx.exception))
        self.assertIn("缺少", str(ctx.exception))

    def test_sync_wrapper_degrades_gracefully(self):
        with mock.patch.dict(sys.modules, {"playwright": None,
                                           "playwright.sync_api": None}):
            with self.assertRaises(LinkFetchError):
                link_logger.fetch_deepseek_url_sync(VALID_URL)


# === 假 playwright 对象链（async 版）：browser / page 全部替身 ===

class FakeAsyncPage:
    """模拟 Playwright Page：goto/evaluate/inner_text 记录调用，高度按序返回。"""

    def __init__(self, heights, body_text=""):
        self._heights = iter(heights)
        self._last_height = 0
        self._body_text = body_text
        self.goto_calls = []
        self.evaluate_calls = []
        self.scroll_calls = 0
        self.inner_text_selectors = []

    async def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))

    async def evaluate(self, js, *args):
        self.evaluate_calls.append(js)
        if "scrollTo" in js:
            self.scroll_calls += 1
            return None
        try:
            self._last_height = next(self._heights)
        except StopIteration:
            pass  # 高度序列耗尽后维持最后一个读数（模拟已到底）
        return self._last_height

    async def inner_text(self, selector):
        self.inner_text_selectors.append(selector)
        return self._body_text


class FakeAsyncBrowser:
    """模拟 Playwright Browser：new_page 返回注入的 page，close 可断言。"""

    def __init__(self, page):
        self._page = page
        self.closed = False

    async def new_page(self):
        return self._page

    async def close(self):
        self.closed = True


def _failing_async_page(error):
    """goto 即抛异常的假 Page（模拟页面加载失败）。"""

    class _BadPage:
        async def goto(self, url, **kwargs):
            raise error

        async def evaluate(self, js, *args):
            return 0

        async def inner_text(self, selector):
            return ""

    return _BadPage()


def _install_fake_async_playwright(browsers):
    """向 sys.modules 注入假 playwright.async_api，返回 (patcher, pw 命名空间)。"""
    pw = types.SimpleNamespace(
        chromium=types.SimpleNamespace(
            launch=mock.AsyncMock(side_effect=list(browsers))))

    class _Ctx:
        def __call__(self):
            return self

        async def __aenter__(self):
            return pw

        async def __aexit__(self, *exc):
            return False

    api = types.ModuleType("playwright.async_api")
    api.async_playwright = _Ctx()
    package = types.ModuleType("playwright")
    package.async_api = api
    patcher = mock.patch.dict(sys.modules, {"playwright": package,
                                            "playwright.async_api": api})
    return patcher, pw


class LinkFetchBrowserChainTest(unittest.TestCase):
    """真实抓取链路（mock 浏览器对象链）：滚动到底、噪声清洗、护栏、重试。"""

    def _fetch(self, page=None, browsers=None, **kwargs):
        if browsers is None:
            browsers = [FakeAsyncBrowser(page)]
        patcher, pw = _install_fake_async_playwright(browsers)
        with patcher, \
                mock.patch.object(link_logger, "RENDER_WAIT_SECONDS", 0), \
                mock.patch.object(link_logger, "SCROLL_WAIT_SECONDS", 0), \
                mock.patch.object(link_logger, "RETRY_WAIT_SECONDS", 0), _quiet():
            result = asyncio.run(link_logger.fetch_deepseek_url(VALID_URL, **kwargs))
        return result, pw, browsers

    def test_scroll_stops_when_height_stabilizes(self):
        # 高度读数 1000 → 2000 → 2000：第二次滚到底后立即停止，不再空转
        page = FakeAsyncPage([1000, 2000, 2000], "第一行\n第二行")
        result, pw, (browser,) = self._fetch(page)
        self.assertEqual(result, "第一行\n第二行")
        self.assertEqual(page.scroll_calls, 2)
        self.assertEqual(page.inner_text_selectors, ["body"])
        self.assertEqual(pw.chromium.launch.await_count, 1)  # launch 只发生一次
        self.assertTrue(browser.closed)                      # 浏览器用完即关
        url, kwargs = page.goto_calls[0]
        self.assertEqual((url, kwargs["wait_until"]), (VALID_URL, "networkidle"))
        self.assertLessEqual(kwargs["timeout"], link_logger.GOTO_TIMEOUT_MS)

    def test_noise_nodes_stripped_in_page_before_scroll(self):
        # 滚动前先在页面内剥离 script/style 等噪声节点
        page = FakeAsyncPage([500, 500], "正文")
        self._fetch(page)
        first_js = page.evaluate_calls[0]
        self.assertIn("querySelectorAll", first_js)
        self.assertIn("script", first_js)
        self.assertIn("style", first_js)
    def test_clean_text_strips_noise_lines_and_markup(self):
        raw = ("<script>var tracking=1;</script>\n"
               "<style>.x{color:red}</style>\n"
               "登录\n注册\n下载\n分享\n复制\n编辑\n"
               "\n\n 小橘说：今天装好了 chromium \n\n真正对话第二行\n")
        self.assertEqual(
            link_logger.clean_text(raw),
            "小橘说：今天装好了 chromium\n真正对话第二行")
        self.assertEqual(link_logger.clean_text(""), "")
        self.assertEqual(link_logger.clean_text("   \n  "), "")

    def test_deadline_guardrail_stops_infinite_scroll(self):
        # 高度永远增长（无限懒加载）：整体超时护栏触发后停止，仍提取已有正文
        page = FakeAsyncPage(itertools.count(1000, 1000), "还没到底的正文")
        start = time.monotonic()
        result, _, (browser,) = self._fetch(page, timeout_seconds=0.05)
        self.assertEqual(result, "还没到底的正文")
        self.assertTrue(browser.closed)
        self.assertLess(time.monotonic() - start, 30)

    def test_max_scroll_steps_hard_cap(self):
        # 步数硬上限先于超时护栏生效：只滚 5 次就收手
        page = FakeAsyncPage(itertools.count(1000, 1000), "无限长页")
        with mock.patch.object(link_logger, "MAX_SCROLL_STEPS", 5):
            result, _, _ = self._fetch(page, timeout_seconds=60)
        self.assertEqual(result, "无限长页")
        self.assertEqual(page.scroll_calls, 5)

    def test_retry_succeeds_after_transient_failure(self):
        # 第一次页面加载失败 → 护栏内重试一次成功
        bad = FakeAsyncBrowser(_failing_async_page(RuntimeError("首次加载超时")))
        good_page = FakeAsyncPage([100, 100], "重试后的正文")
        good = FakeAsyncBrowser(good_page)
        result, pw, _ = self._fetch(browsers=[bad, good])
        self.assertEqual(result, "重试后的正文")
        self.assertEqual(pw.chromium.launch.await_count, 2)
        self.assertTrue(bad.closed and good.closed)

    def test_all_attempts_fail_raises_chinese_error(self):
        err = RuntimeError("网络超时")
        bad1 = FakeAsyncBrowser(_failing_async_page(err))
        bad2 = FakeAsyncBrowser(_failing_async_page(err))
        with self.assertRaises(LinkFetchError) as ctx:
            self._fetch(browsers=[bad1, bad2])
        self.assertIn("分享页抓取失败", str(ctx.exception))
        self.assertIn("网络超时", str(ctx.exception))
        self.assertTrue(bad1.closed and bad2.closed)  # 失败也关闭浏览器

    def test_missing_browser_binary_gets_chinese_hint(self):
        err = RuntimeError("Executable doesn't exist at ...chrome.exe, "
                           "please run playwright install chromium")
        bad1 = FakeAsyncBrowser(_failing_async_page(err))
        bad2 = FakeAsyncBrowser(_failing_async_page(err))
        with self.assertRaises(LinkFetchError) as ctx:
            self._fetch(browsers=[bad1, bad2])
        self.assertIn("浏览器内核缺失", str(ctx.exception))
        self.assertIn("playwright install chromium", str(ctx.exception))


def make_fake_brain(replies=None, error=None, reply=None):
    """构造替身 brain 模块：记录 ask_cloud 调用，按序返回回复。"""
    calls = []

    def ask_cloud(messages):
        calls.append(messages)
        if error is not None:
            raise error
        if reply is not None:
            return reply
        return replies.pop(0) if replies else "默认总结"

    brain = types.ModuleType("brain")
    brain.ask_cloud = ask_cloud
    brain.calls = calls
    return brain


class BatchLoggerTest(unittest.TestCase):
    """分片总结 + 倒叙说书人汇总（云端经 brain 替身，零联网）。"""

    def _summarize(self, text, brain, **kwargs):
        with mock.patch.dict(sys.modules, {"brain": brain}), \
                mock.patch.object(batch_logger, "time") as fake_time, _quiet():
            result = batch_logger.summarize_long_text(
                text, "test-key", "https://cloud.example/chat", **kwargs)
        return result, fake_time

    def _chunk_of(self, message):
        # 分片 prompt 形如 "请阅读以下对话记录，...：\n\n{chunk}"
        return message["content"].split("\n\n", 1)[-1]

    def test_chunk_boundary_4000(self):
        # 恰好 4000 字 => 1 片 + 1 次汇总 = 2 次云端调用
        brain = make_fake_brain()
        self._summarize("x" * 4000, brain)
        self.assertEqual(len(brain.calls), 2)
        self.assertEqual(self._chunk_of(brain.calls[0][0]), "x" * 4000)

        # 4001 字 => 2 片（第二片仅 1 字）+ 1 次汇总 = 3 次云端调用
        brain = make_fake_brain()
        self._summarize("x" * 4001, brain)
        self.assertEqual(len(brain.calls), 3)
        self.assertEqual(self._chunk_of(brain.calls[0][0]), "x" * 4000)
        self.assertEqual(self._chunk_of(brain.calls[1][0]), "x")

    def test_custom_chunk_size(self):
        brain = make_fake_brain()
        self._summarize("abcdef", brain, chunk_size=2)
        self.assertEqual(len(brain.calls), 4)  # 3 片 + 1 次汇总
        self.assertEqual(self._chunk_of(brain.calls[0][0]), "ab")

    def test_empty_text_returns_error_without_cloud_call(self):
        brain = make_fake_brain()
        result, _ = self._summarize("", brain)
        self.assertEqual(result, "❌ 抓取到的文本为空，请检查链接是否正确。")
        self.assertEqual(len(brain.calls), 0)

    def test_final_prompt_is_narrator_style_and_keeps_order(self):
        brain = make_fake_brain(replies=["总结一", "总结二", "最终成篇"])
        result, _ = self._summarize("A" * 4000 + "B" * 10, brain)
        self.assertEqual(result, "最终成篇")
        self.assertEqual(len(brain.calls), 3)
        final_prompt = brain.calls[2][0]["content"]
        self.assertIn("倒叙", final_prompt)
        self.assertIn("说书人", final_prompt)
        self.assertIn("# 小橘3号开发故事（倒叙）", final_prompt)
        # 碎片按分片顺序拼接
        self.assertLess(final_prompt.index("总结一"), final_prompt.index("总结二"))

    def test_brain_graceful_error_string_skips_chunk(self):
        # brain 返回 ⚠️ 开头的降级提示 => 视为失败，全部失败时返回错误串
        brain = make_fake_brain(reply="⚠️ 云端大脑开小差了，请稍后再试~")
        result, _ = self._summarize("x" * 10, brain)
        self.assertEqual(result, "❌ 所有分片总结均失败。")

    def test_brain_exception_counts_as_failure(self):
        brain = make_fake_brain(error=OSError("网络断了"))
        result, _ = self._summarize("x" * 10, brain)
        self.assertEqual(result, "❌ 所有分片总结均失败。")

    def test_partial_failure_still_summarizes_remaining(self):
        brain = make_fake_brain(replies=[None, "成功总结", "最终成篇"])
        result, _ = self._summarize("x" * 4001, brain)
        self.assertEqual(result, "最终成篇")
        self.assertEqual(len(brain.calls), 3)  # 2 片（第一片失败）+ 1 次汇总

    def test_fallback_direct_requests_without_brain(self):
        # sys.modules 置 None => import brain 抛 ImportError => 回退参考实现
        resp = mock.Mock()
        resp.status_code = 200
        resp.json.return_value = {"choices": [{"message": {"content": "直连总结"}}]}
        with mock.patch.dict(sys.modules, {"brain": None}), \
                mock.patch("requests.post", return_value=resp) as post, \
                mock.patch.object(batch_logger, "time") as _t, _quiet():
            result = batch_logger.summarize_long_text(
                "hello", "test-key", "https://cloud.example/chat")
        self.assertEqual(result, "直连总结")
        self.assertEqual(post.call_count, 2)  # 1 片 + 1 次汇总
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://cloud.example/chat")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(kwargs["json"]["model"], "deepseek-chat")

    def test_fallback_non_200_is_failure(self):
        resp = mock.Mock()
        resp.status_code = 401
        with mock.patch.dict(sys.modules, {"brain": None}), \
                mock.patch("requests.post", return_value=resp), \
                mock.patch.object(batch_logger, "time") as _t, _quiet():
            result = batch_logger.summarize_long_text(
                "hello", "test-key", "https://cloud.example/chat")
        self.assertEqual(result, "❌ 所有分片总结均失败。")


# === dev_logger（同步 playwright 链路替身） ===

class _FakeSyncPage:
    """模拟同步 Playwright Page：goto/evaluate/inner_text/eval_on_selector_all。"""

    def __init__(self, heights, body_text="", img_srcs=None):
        self._heights = iter(heights)
        self._last_height = 0
        self._body_text = body_text
        self._img_srcs = list(img_srcs or [])
        self.scroll_calls = 0
        self.goto_calls = []

    def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))

    def evaluate(self, js, *args):
        if "scrollTo" in js:
            self.scroll_calls += 1
            return None
        try:
            self._last_height = next(self._heights)
        except StopIteration:
            pass
        return self._last_height

    def inner_text(self, selector):
        return self._body_text

    def eval_on_selector_all(self, selector, js):
        return list(self._img_srcs)


class _FakeSyncBrowser:
    def __init__(self, page):
        self._page = page
        self.closed = False

    def new_page(self):
        return self._page

    def close(self):
        self.closed = True


def _install_fake_sync_playwright(browsers):
    """向 sys.modules 注入假 playwright.sync_api，返回 patcher。"""
    pw = types.SimpleNamespace(
        chromium=types.SimpleNamespace(
            launch=mock.Mock(side_effect=list(browsers))))

    class _Ctx:
        def __call__(self):
            return self

        def __enter__(self):
            return pw

        def __exit__(self, *exc):
            return False

    api = types.ModuleType("playwright.sync_api")
    api.sync_playwright = _Ctx()
    package = types.ModuleType("playwright")
    package.sync_api = api
    return mock.patch.dict(sys.modules, {"playwright": package,
                                         "playwright.sync_api": api})


class DevLoggerTest(unittest.TestCase):
    """dev_logger 真实抓取链路（同步 mock 浏览器对象链）与降级。"""

    def _fetch(self, page):
        browser = _FakeSyncBrowser(page)
        with _install_fake_sync_playwright([browser]), \
                mock.patch.object(dev_logger, "RENDER_WAIT_SECONDS", 0), \
                mock.patch.object(dev_logger, "SCROLL_WAIT_SECONDS", 0), _quiet():
            result = dev_logger.fetch_deepseek_share(VALID_URL)
        return result, browser

    def test_fetch_extracts_text_images_and_links(self):
        page = _FakeSyncPage(
            [100, 300, 300],
            "对话正文 https://example.com/a 图片链接",
            img_srcs=["https://img.example/1.png", "data:inline;base64,xx"])
        (text, images, links), browser = self._fetch(page)
        self.assertIn("对话正文", text)
        self.assertEqual(images, ["https://img.example/1.png"])  # data: 链接被过滤
        self.assertEqual(links, ["https://example.com/a"])
        self.assertEqual(page.scroll_calls, 2)  # 高度稳定即到底，立即停止
        self.assertTrue(browser.closed)

    def test_fetch_missing_playwright_degrades(self):
        with mock.patch.dict(sys.modules, {"playwright": None,
                                           "playwright.sync_api": None}), _quiet():
            text, images, links = dev_logger.fetch_deepseek_share(VALID_URL)
        self.assertTrue(text.startswith("❌ 缺少 playwright"))
        self.assertEqual((images, links), ([], []))

    def test_fetch_browser_error_returns_error_string(self):
        class _BoomPage:
            def goto(self, url, **kwargs):
                raise RuntimeError("page crashed")

        (text, images, links), browser = self._fetch(_BoomPage())
        self.assertIn("Fetch error", text)
        self.assertEqual((images, links), ([], []))
        self.assertTrue(browser.closed)  # 出错也关闭浏览器

    def test_generate_dev_log_posts_truncated_prompt(self):
        resp = mock.Mock()
        resp.json.return_value = {"choices": [{"message": {"content": "# 日志"}}]}
        long_text = "x" * 20001  # 超过 20000 字护栏，触发截断
        with mock.patch("requests.post", return_value=resp) as post, _quiet():
            result = dev_logger.generate_dev_log(
                long_text, ["图一"], "test-key", "https://cloud.example/chat")
        self.assertEqual(result, "# 日志")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://cloud.example/chat")
        self.assertEqual(kwargs["timeout"], 180)
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")
        body = kwargs["json"]["messages"][0]["content"]
        self.assertIn("...中间内容过长已截断...", body)
        self.assertIn("图一", body)


def _fake_fetch(text):
    async def _fetch(url):
        return text
    return _fetch


class RunLinkLogTest(unittest.TestCase):
    """/gen_log 编排：编号、落盘、倒序合并（抓取与总结全部 mock）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = self._tmp.name

    def _run(self, url, fetch_text="RAW 对话记录", summary="日志正文"):
        with mock.patch.object(run_link_log, "fetch_deepseek_url",
                               _fake_fetch(fetch_text)), \
                mock.patch.object(run_link_log, "summarize_long_text",
                                  return_value=summary) as fake_sum, _quiet():
            result = run_link_log.run_link_log(url, data_dir=self.data_dir)
        return result, fake_sum

    def _read(self, name):
        with open(os.path.join(self.data_dir, name), "r", encoding="utf-8") as f:
            return f.read()

    def test_invalid_url_aborts_without_files(self):
        for bad in ("", "http://evil.com/x", "https://example.com/share/x"):
            result, fake_sum = self._run(bad)
            self.assertIsNone(result)
            self.assertFalse(fake_sum.called)  # 非法链接不触碰抓取与总结
            self.assertEqual(os.listdir(self.data_dir), [])

    def test_fetch_error_aborts_without_files(self):
        # 抓取抛 LinkFetchError（缺库/浏览器异常）=> 不落盘任何半成品
        def _boom(url):
            raise LinkFetchError("❌ 分享页抓取失败：浏览器炸了")

        with mock.patch.object(run_link_log, "fetch_deepseek_url", _boom), \
                mock.patch.object(run_link_log, "summarize_long_text") as fake_sum, \
                _quiet():
            result = run_link_log.run_link_log(VALID_URL, data_dir=self.data_dir)
        self.assertIsNone(result)
        self.assertFalse(fake_sum.called)
        self.assertEqual(os.listdir(self.data_dir), [])

    def test_generates_numbered_log_raw_and_all_logs(self):
        result, _ = self._run(VALID_URL)
        self.assertEqual(result, "日志正文")
        self.assertEqual(self._read("dev_log_1.md"), "日志正文")
        self.assertEqual(self._read("raw_log_temp.txt"), "RAW 对话记录")  # 原始文本落盘备查
        all_logs = self._read("ALL_LOGS.md")
        self.assertIn("第 1 篇日志（最新）", all_logs)
        self.assertIn("日志正文", all_logs)

    def test_reverse_merge_order_newest_first(self):
        self._run(VALID_URL, summary="第一篇")
        self._run(VALID_URL, summary="第二篇")
        self.assertTrue(os.path.exists(os.path.join(self.data_dir, "dev_log_2.md")))
        all_logs = self._read("ALL_LOGS.md")
        # 倒叙：最新一篇在最前
        self.assertLess(all_logs.index("第 2 篇日志"), all_logs.index("第 1 篇日志"))
        self.assertLess(all_logs.index("第二篇"), all_logs.index("第一篇"))

    def test_auto_numbering_skips_gap_without_overwrite(self):
        # 已有 dev_log_1.md 与 dev_log_3.md（2 被删）=> 下一篇为 4，不覆盖旧文件
        with open(os.path.join(self.data_dir, "dev_log_1.md"), "w", encoding="utf-8") as f:
            f.write("旧一")
        with open(os.path.join(self.data_dir, "dev_log_3.md"), "w", encoding="utf-8") as f:
            f.write("旧三")
        self.assertEqual(run_link_log.next_log_index(self.data_dir), 4)
        self._run(VALID_URL, summary="新一")
        self.assertEqual(self._read("dev_log_3.md"), "旧三")   # 未被覆盖
        self.assertEqual(self._read("dev_log_4.md"), "新一")

    def test_empty_fetch_aborts(self):
        result, _ = self._run(VALID_URL, fetch_text="")
        self.assertIsNone(result)
        self.assertEqual([f for f in os.listdir(self.data_dir) if f.startswith("dev_log")], [])

    def test_failed_summary_aborts_without_saving(self):
        result, _ = self._run(VALID_URL, summary="❌ 汇总失败。")
        self.assertIsNone(result)
        self.assertEqual([f for f in os.listdir(self.data_dir) if f.startswith("dev_log")], [])

    def test_cloud_call_uses_unified_config(self):
        with mock.patch.object(run_link_log, "fetch_deepseek_url", _fake_fetch("RAW")), \
                mock.patch.object(run_link_log, "summarize_long_text",
                                  return_value="OK") as fake_sum, _quiet():
            run_link_log.run_link_log(VALID_URL, data_dir=self.data_dir)
        fake_sum.assert_called_once_with("RAW", run_link_log.CLOUD_KEY, run_link_log.CLOUD_URL)


if __name__ == "__main__":
    unittest.main()
