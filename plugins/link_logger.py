# -*- coding: utf-8 -*-
"""plugins/link_logger · DeepSeek 分享页抓取（Playwright 无头浏览器真实渲染链路）。

按《架构设计文档》§5 /《功能文档》§6：校验链接前缀须为
chat.deepseek.com/share/ 分享页，用无头 chromium 打开分享页、剥离
script/style 噪声节点、分段滚动触发懒加载直至到底、等待渲染后提取
正文文本并清洗导航噪声行。

playwright 做函数内延迟导入：缺库或浏览器内核缺失时抛出可捕获的
LinkFetchError（中文提示），绝不影响模块 import（import 本文件零副作用）。
"""
import asyncio
import os
import re
import sys
import time

import win_process

# DeepSeek 分享链接前缀（run_link_log 的编排校验与此保持一致）
SHARE_PREFIX = "https://chat.deepseek.com/share/"

# === 抓取护栏参数（超时/重试沿用参考口径，测试可直接 patch） ===
FETCH_DEADLINE_SECONDS = 180.0  # 整体护栏：单次抓取（含重试）不超过 180 秒
GOTO_TIMEOUT_MS = 90_000        # 单次页面加载上限（参考实现口径 90 秒）
RENDER_WAIT_SECONDS = 3.0       # 打开后先等待渲染（参考实现口径）
SCROLL_WAIT_SECONDS = 2.0       # 每次滚动后等待懒加载（参考实现口径）
MAX_SCROLL_STEPS = 60           # 滚动步数硬上限（60×2s=120s，双保险防死循环）
MAX_ATTEMPTS = 2                # 抓取失败重试次数（整体仍受 180 秒护栏约束）
RETRY_WAIT_SECONDS = 1.0        # 两次尝试之间的间隔

# 页面内剥离噪声节点的 JS：script/style 等不参与正文，返回剥离后的页面高度
_STRIP_NOISE_JS = (
    "(() => {"
    "document.querySelectorAll('script, style, noscript, template')"
    ".forEach(el => el.remove());"
    "return document.body ? document.body.scrollHeight : 0;})()"
)

# 网页导航条、按钮等噪声行前缀（沿用参考实现口径）
_NOISE_LINE_PREFIXES = ("登录", "注册", "下载", "分享", "复制", "编辑")


class LinkFetchError(Exception):
    """分享页抓取失败（链接非法 / playwright 缺库 / 浏览器内核缺失 / 异常）。"""


def ensure_frozen_browsers_path():
    """冻结形态浏览器路径修正（2026-10-04 尾巴 1，方案 2）。

    playwright 1.63 在 PyInstaller/Nuitka 冻结态会强制
    PLAYWRIGHT_BROWSERS_PATH=0（_impl/_transport.py:110-112 "For
    pyinstaller and Nuitka"）→ driver 去 包内 .local-browsers 找浏览器，
    而浏览器并不随包分发（spec 只收 lib+driver，705.6MB 的浏览器缓存
    远超拍板体积带）→ 冻结包报 "Executable doesn't exist"。

    修法：冻结时指回用户缓存目录（%LOCALAPPDATA%\\ms-playwright）；
    setdefault 不覆盖用户预设（与方案 1 的 setx 不冲突）；非冻结
    （dev）不进此分支，行为零变化。
    """
    if getattr(sys, "frozen", False):
        os.environ.setdefault(
            "PLAYWRIGHT_BROWSERS_PATH",
            os.path.join(os.environ["LOCALAPPDATA"], "ms-playwright"))


class _QuietChildWindows:
    """抓取期间抑制子进程控制台闪窗（2026-10-04 尾巴 A）。

    playwright driver（node.exe）由库内 `asyncio.create_subprocess_exec`
    以模块命名空间访问启动——无控制台的冻结 exe 里每次抓取都闪黑框
    （库只设了 SW_HIDE，对新 console 进程不够）。本上下文在 win32 下
    给该入口运行期注入 CREATE_NO_WINDOW（不覆盖调用方已有的
    creationflags），退出恢复原函数；非 Windows 空操作。
    """

    def __enter__(self):
        self._orig = None
        if sys.platform == "win32":
            self._orig = asyncio.create_subprocess_exec

            def _quiet_exec(*args, **kwargs):
                kwargs.setdefault("creationflags", win_process.CREATE_NO_WINDOW)
                return self._orig(*args, **kwargs)

            asyncio.create_subprocess_exec = _quiet_exec
        return self

    def __exit__(self, *exc):
        if self._orig is not None:
            asyncio.create_subprocess_exec = self._orig
        return False


def validate_share_url(url):
    """校验链接前缀：合法时返回清理锚点后的链接，非法时抛 LinkFetchError。"""
    if not isinstance(url, str) or not url.strip().startswith(SHARE_PREFIX):
        raise LinkFetchError("❌ 链接格式不对，必须以 https://chat.deepseek.com/share/ 开头")
    return url.strip().split("#")[0]


def clean_text(text_content):
    """剔除 script/style 残块、空行与导航噪声行，返回纯正文文本。"""
    # 双保险：个别站点把脚本/样式内容带进提取结果时，按块剔除
    text_content = re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", text_content)
    text_content = re.sub(r"(?is)<style\b[^>]*>.*?</style>", "", text_content)

    lines = []
    for line in text_content.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith(_NOISE_LINE_PREFIXES):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def _missing_browser_hint(message):
    """识别 playwright「浏览器内核未下载」类报错，转成中文安装指引。"""
    return "playwright install" in message or "Executable doesn't exist" in message


async def _grab_page_text(page, url, deadline):
    """打开页面、剥离噪声节点、分段滚动到底触发懒加载，返回原始正文文本。"""
    # 页面加载超时不越过整体护栏剩余时间
    remaining_ms = int(max(1.0, deadline - time.monotonic()) * 1000)
    await page.goto(url, wait_until="networkidle",
                    timeout=min(GOTO_TIMEOUT_MS, remaining_ms))
    await asyncio.sleep(RENDER_WAIT_SECONDS)

    # 滚动前先剥离 script/style 等噪声节点，避免其撑高页面干扰到底判断
    last_height = await page.evaluate(_STRIP_NOISE_JS)
    steps = 0
    while steps < MAX_SCROLL_STEPS and time.monotonic() < deadline:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(SCROLL_WAIT_SECONDS)  # 等待新内容懒加载
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            break  # 高度不再增长：已滚动到底
        last_height = new_height
        steps += 1

    # 滚动到底后，提取全部文字
    return await page.inner_text("body")


async def _fetch_with_browser(async_playwright, url, deadline):
    """启动无头 chromium 抓取正文；护栏内失败重试，最终失败抛 LinkFetchError。"""
    last_error = None
    async with async_playwright() as p:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if time.monotonic() >= deadline:
                break
            # 回归默认 headless_shell（2026-10-04 尾巴 A2 终版）：channel=chromium
            # 虽消 headless_shell 的 conhost，但 chrome.exe 全家桶引入
            # crashpad-handler（console 子系统）新的 conhost 闪源且无法根除
            # （chromium 内核层）——headless_shell 无 crashpad，其 conhost 由
            # _dev/patch_playwright_windows_hide.py 在 node driver 层
            # windowsHide:true 根治（SW_HIDE：conhost 窗口创建即隐藏），
            # build_exe.bat 构建前自动执行该补丁。
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                return await _grab_page_text(page, url, deadline)
            except Exception as e:  # noqa: BLE001 —— 统一转中文提示
                last_error = e
                print(f"⚠️ 第 {attempt} 次抓取失败：{e}")
            finally:
                await browser.close()
            if attempt < MAX_ATTEMPTS and time.monotonic() < deadline:
                await asyncio.sleep(RETRY_WAIT_SECONDS)

    if last_error is None:
        raise LinkFetchError("❌ 分享页抓取失败：整体护栏时间内未能完成抓取。")
    if _missing_browser_hint(str(last_error)):
        raise LinkFetchError(
            "❌ 浏览器内核缺失，无法抓取页面。"
            "请先执行：python -m playwright install chromium 后重试。"
        ) from last_error
    raise LinkFetchError(f"❌ 分享页抓取失败：{last_error}") from last_error


async def fetch_page_text(url, timeout_seconds=None):
    """通用抓取：无头 chromium 打开页面，滚动到底后返回清洗后的正文文本。

    供 fetch_deepseek_url（带前缀校验）与真实浏览器冒烟测试复用。
    """
    ensure_frozen_browsers_path()   # 冻结形态浏览器路径修正（尾巴 1）

    # 延迟导入：playwright 缺库时优雅降级（清晰中文提示，可捕获）
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        raise LinkFetchError(
            "❌ 缺少 playwright 库，无法打开无头浏览器抓取页面。"
            "请先安装 playwright 与浏览器内核（pip install playwright && "
            "python -m playwright install chromium）后重试。"
        ) from e

    deadline = time.monotonic() + (
        FETCH_DEADLINE_SECONDS if timeout_seconds is None else float(timeout_seconds))
    print("🌐 正在打开链接，请稍候... (这可能需要 30-60 秒)")
    with _QuietChildWindows():
        raw_text = await _fetch_with_browser(async_playwright, url, deadline)

    text = clean_text(raw_text)
    print(f"✅ 抓取完成，共提取 {len(text.splitlines())} 行文本。")
    return text


async def fetch_deepseek_url(url, timeout_seconds=None):
    """用 Playwright 打开 DeepSeek 分享链接，模拟滚动加载，提取全部对话文本。"""
    # 校验前缀并清理锚点，非法链接在触碰浏览器之前就被拒绝
    url = validate_share_url(url)
    return await fetch_page_text(url, timeout_seconds=timeout_seconds)


def fetch_page_text_sync(url, timeout_seconds=None):
    """fetch_page_text 的同步包装（CLI 与真实浏览器冒烟测试使用）。"""
    return asyncio.run(fetch_page_text(url, timeout_seconds))


def fetch_deepseek_url_sync(url):
    """同步包装：CLI / 脚本直连时使用（run_link_log 编排走 async 版）。"""
    return asyncio.run(fetch_deepseek_url(url))
